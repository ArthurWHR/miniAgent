"""Anthropic provider —— 阶段 1.1 请求翻译 + 1.2 流式解析。

和 OpenAI 兼容接口的**结构差异**（不是字段换个名字那么简单）：

1. **system 不是消息**
   Anthropic 把 system prompt 放在请求体的顶层 ``system`` 字段里，
   messages 数组里只能出现 user / assistant。

2. **工具结果是 user 消息**
   没有 ``role="tool"``。工具结果以 ``tool_result`` content block 的形式
   放进一条 **user** 消息里。

3. **工具声明用 input_schema**
   没有 ``{"type": "function", "function": {...}}`` 包装，
   直接是 ``{"name", "description", "input_schema"}``。

4. **流式事件是一套状态机**
   ``message_start → content_block_start → content_block_delta(×N)
   → content_block_stop → message_stop``
   工具参数不是一整串 JSON，而是按 block index 分组的 ``input_json_delta``。

本文件是**唯一**允许出现 Anthropic 字段名的地方。
"""
from __future__ import annotations

import json
import os
from typing import Any, AsyncIterator, Sequence

import httpx

from ..events import Event, EventKind
from ..messages import Message, TextBlock, ToolResultBlock, ToolUseBlock
from ..tools import Tool
from .base import ModelConfig, ProviderError, parse_tool_arguments

DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MAX_TOKENS = 4096


# ---------------------------------------------------------------- 请求翻译


def to_anthropic_messages(
    messages: list[Message],
) -> tuple[str | None, list[dict[str, Any]]]:
    """规范 Message → (system, Anthropic messages)。

    system 被单独抽出来返回，因为它不属于 messages 数组。
    多个 system 消息用空行拼接。
    """
    system_parts: list[str] = []
    out: list[dict[str, Any]] = []

    for msg in messages:
        if msg.role == "system":
            if msg.text:
                system_parts.append(msg.text)

        elif msg.role == "user":
            if msg.text:
                _append_user(out, [{"type": "text", "text": msg.text}])

        elif msg.role == "assistant":
            content: list[dict[str, Any]] = []
            for block in msg.content:
                if isinstance(block, TextBlock):
                    if block.text:
                        content.append({"type": "text", "text": block.text})
                elif isinstance(block, ToolUseBlock):
                    content.append(
                        {
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            # Anthropic 的 input 本来就是**结构化对象**，
                            # 不需要像 OpenAI 那样序列化成字符串
                            "input": block.input,
                        }
                    )
            # 空 assistant 消息会被拒绝，直接跳过
            if content:
                out.append({"role": "assistant", "content": content})

        elif msg.role == "tool":
            blocks = [
                {
                    "type": "tool_result",
                    "tool_use_id": block.tool_use_id,
                    "content": block.content,
                    "is_error": block.is_error,
                }
                for block in msg.content
                if isinstance(block, ToolResultBlock)
            ]
            if blocks:
                _append_user(out, blocks)

    system = "\n\n".join(system_parts) if system_parts else None
    return system, out


def _append_user(out: list[dict[str, Any]], blocks: list[dict[str, Any]]) -> None:
    """追加 user 消息；如果上一条也是 user，就合并。

    Anthropic 要求 user / assistant 交替出现。工具结果（user）后面如果紧跟
    用户输入（也是 user），不合并会被 API 拒绝。
    """
    if out and out[-1]["role"] == "user":
        out[-1]["content"].extend(blocks)
    else:
        out.append({"role": "user", "content": blocks})


def to_anthropic_tool(tool: Tool) -> dict[str, Any]:
    """规范 Tool → Anthropic tools 声明。"""
    return {
        "name": tool.name,
        "description": tool.description,
        # 我们的 Tool.parameters 就是 JSON Schema，正好直接放进来
        "input_schema": tool.parameters,
    }


# ---------------------------------------------------------------- provider


class AnthropicProvider:
    """Anthropic Messages API 的流式实现。"""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY") or ""
        self.base_url = (
            base_url or os.environ.get("ANTHROPIC_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def stream(
        self,
        messages: list[Message],
        *,
        config: ModelConfig,
        tools: Sequence[Tool] | None = None,
    ) -> AsyncIterator[Event]:
        system, anthropic_messages = to_anthropic_messages(messages)

        payload: dict[str, Any] = {
            "model": config.model,
            "messages": anthropic_messages,
            # Anthropic 的 max_tokens 是**必填**，不像 OpenAI 可省略
            "max_tokens": config.max_tokens or DEFAULT_MAX_TOKENS,
            "stream": True,
        }
        if system:
            payload["system"] = system
        if config.temperature is not None:
            payload["temperature"] = config.temperature
        if tools:
            payload["tools"] = [to_anthropic_tool(t) for t in tools]

        headers = {
            "content-type": "application/json",
            "anthropic-version": ANTHROPIC_VERSION,
        }
        if self.api_key:
            headers["x-api-key"] = self.api_key

        url = f"{self.base_url}/messages"

        # 正在累积的 tool_use block，key 是 content block 的 index
        tool_blocks: dict[int, dict[str, Any]] = {}

        async with self._client.stream(
            "POST", url, json=payload, headers=headers
        ) as resp:
            if resp.status_code >= 400:
                body = (await resp.aread()).decode("utf-8", "replace")
                raise ProviderError(
                    f"HTTP {resp.status_code} from {url}: {body[:500]}"
                )

            async for line in resp.aiter_lines():
                chunk = _parse_sse_data(line)
                if chunk is None:
                    continue

                event_type = chunk.get("type")

                if event_type == "error":
                    error = chunk.get("error") or {}
                    message = (
                        error.get("message", error)
                        if isinstance(error, dict)
                        else error
                    )
                    raise ProviderError(f"provider 返回错误: {message}")

                elif event_type == "content_block_start":
                    index = chunk.get("index", 0)
                    block = chunk.get("content_block") or {}
                    block_type = block.get("type")
                    if block_type == "tool_use":
                        tool_blocks[index] = {
                            "id": block.get("id", ""),
                            "name": block.get("name", ""),
                            "json": "",
                        }
                    elif block_type == "text" and block.get("text"):
                        yield Event(EventKind.ASSISTANT, {"text": block["text"]})

                elif event_type == "content_block_delta":
                    index = chunk.get("index", 0)
                    delta = chunk.get("delta") or {}
                    delta_type = delta.get("type")
                    if delta_type == "text_delta":
                        text = delta.get("text")
                        if text:
                            yield Event(EventKind.ASSISTANT, {"text": text})
                    elif delta_type == "input_json_delta":
                        slot = tool_blocks.get(index)
                        if slot is not None:
                            slot["json"] += delta.get("partial_json", "")

                elif event_type == "content_block_stop":
                    index = chunk.get("index", 0)
                    slot = tool_blocks.pop(index, None)
                    if slot is not None:
                        yield _tool_call_event(slot)

                # message_start / message_delta / message_stop / ping 无需处理：
                # 终止由 agent 根据"本轮有没有 TOOL_CALL"决定
        # 兜底：若没收到 content_block_stop，也要把已累积的工具调用交出去
        for index in sorted(tool_blocks):
            yield _tool_call_event(tool_blocks[index])


def _tool_call_event(slot: dict[str, Any]) -> Event:
    arguments, parse_error = parse_tool_arguments(slot["json"])
    return Event(
        EventKind.TOOL_CALL,
        {
            "id": slot["id"],
            "name": slot["name"],
            "input": arguments,
            "parse_error": parse_error,
        },
    )


def _parse_sse_data(line: str) -> dict[str, Any] | None:
    """Anthropic 的 SSE 每行要么是 ``event: xxx``，要么是 ``data: {...}``。

    事件类型在 JSON 的 ``type`` 字段里也有，所以 ``event:`` 行直接跳过。
    """
    line = line.strip()
    if not line.startswith("data:"):
        return None

    data = line[len("data:") :].strip()
    if not data:
        return None

    try:
        return json.loads(data)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"无法解析流式响应: {data[:200]}") from exc
