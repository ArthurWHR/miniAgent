"""OpenAI 兼容 provider —— 一套代码覆盖 OpenAI / DeepSeek / vLLM 等。

为什么先做这个：它们都提供 ``POST /chat/completions`` + SSE 流式响应，
接口形状一致，换 ``base_url`` 就能换服务商。第一版用它把循环跑通，
后面再加 Anthropic 实现来验证 Provider 抽象是否真的中立。

注意：本文件是**唯一**允许出现 OpenAI 字段名（tool_calls、arguments 字符串、
role="tool"）的地方。核心层只认识规范 Message / Tool。
"""
from __future__ import annotations

import json
import os
from typing import Any, AsyncIterator, Sequence

import httpx

from ..events import Event, EventKind
from ..messages import Message
from ..tools import Tool
from .base import ModelConfig, ProviderError

DEFAULT_BASE_URL = "https://api.openai.com/v1"


# ---------------------------------------------------------------- 请求翻译


def to_openai_messages(messages: list[Message]) -> list[dict[str, Any]]:
    """规范 Message → OpenAI messages 数组。

    这是本层存在意义的直接体现：翻译集中在一个纯函数里，
    想验证对不对，直接拿它做单元测试，不用发网络请求。
    """
    out: list[dict[str, Any]] = []

    for msg in messages:
        if msg.role in ("system", "user"):
            out.append({"role": msg.role, "content": msg.text})

        elif msg.role == "assistant":
            item: dict[str, Any] = {
                "role": "assistant",
                # OpenAI 允许 content 为 null（纯工具调用时）
                "content": msg.text or None,
            }
            if msg.tool_uses:
                item["tool_calls"] = [
                    {
                        "id": tu.id,
                        "type": "function",
                        "function": {
                            "name": tu.name,
                            # 注意：OpenAI 要求 arguments 是**字符串**，不是对象
                            "arguments": json.dumps(tu.input, ensure_ascii=False),
                        },
                    }
                    for tu in msg.tool_uses
                ]
            out.append(item)

        elif msg.role == "tool":
            # 一个 tool_call_id 对应一条 tool 消息 —— 多个结果要拆成多条
            for block in msg.content:
                out.append(
                    {
                        "role": "tool",
                        "tool_call_id": block.tool_use_id,  # type: ignore[union-attr]
                        "content": block.content,  # type: ignore[union-attr]
                    }
                )

    return out


def to_openai_tool(tool: Tool) -> dict[str, Any]:
    """规范 Tool → OpenAI tools 声明。厂商格式只在本文件出现。"""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


# ---------------------------------------------------------------- provider


class OpenAICompatibleProvider:
    """基于 httpx 的 OpenAI 兼容流式实现。"""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or ""
        self.base_url = (
            base_url or os.environ.get("OPENAI_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")
        # 允许注入 client：测试时用 MockTransport，生产时用默认实现
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
        payload: dict[str, Any] = {
            "model": config.model,
            "messages": to_openai_messages(messages),
            "stream": True,
        }
        if config.temperature is not None:
            payload["temperature"] = config.temperature
        if config.max_tokens is not None:
            payload["max_tokens"] = config.max_tokens
        if tools:
            payload["tools"] = [to_openai_tool(t) for t in tools]

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        url = f"{self.base_url}/chat/completions"

        # 工具参数是**分片**到达的，按 index 累积；流结束后再统一产出
        pending: dict[int, dict[str, str]] = {}

        async with self._client.stream(
            "POST", url, json=payload, headers=headers
        ) as resp:
            if resp.status_code >= 400:
                body = (await resp.aread()).decode("utf-8", "replace")
                raise ProviderError(
                    f"HTTP {resp.status_code} from {url}: {body[:500]}"
                )

            async for line in resp.aiter_lines():
                chunk = _parse_sse_line(line)
                if chunk is None:
                    continue

                # 有些兼容实现会在流里塞 error 对象
                if "error" in chunk:
                    raise ProviderError(f"provider 返回错误: {chunk['error']}")

                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}

                    text = delta.get("content")
                    if text:
                        yield Event(EventKind.ASSISTANT, {"text": text})

                    for call in delta.get("tool_calls") or []:
                        _accumulate_tool_call(pending, call)

        # 流结束，产出完整的工具调用（可能一次多个）
        for index in sorted(pending):
            slot = pending[index]
            arguments, parse_error = _parse_arguments(slot["arguments"])
            yield Event(
                EventKind.TOOL_CALL,
                {
                    "id": slot["id"],
                    "name": slot["name"],
                    "input": arguments,
                    "parse_error": parse_error,
                },
            )


# ---------------------------------------------------------------- SSE 解析


def _parse_sse_line(line: str) -> dict[str, Any] | None:
    """解析一行 SSE，返回 chunk dict；空行 / 注释 / [DONE] 返回 None。"""
    line = line.strip()
    if not line or not line.startswith("data:"):
        return None

    data = line[len("data:") :].strip()
    if data == "[DONE]":
        return None

    try:
        chunk = json.loads(data)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"无法解析流式响应: {data[:200]}") from exc

    return chunk


def _accumulate_tool_call(pending: dict[int, dict[str, str]], call: dict[str, Any]) -> None:
    """把一片 tool_call delta 合并进累积器。

    OpenAI 的分片规则：
    - 第一片带 id / name 和空的 arguments
    - 后续片只带 arguments 的一个**字符串片段**，需要按 index 拼接
    - 多工具并行时，不同 index 的片会交错到达
    """
    index = call.get("index", 0)
    slot = pending.setdefault(index, {"id": "", "name": "", "arguments": ""})

    if call.get("id"):
        slot["id"] = call["id"]

    function = call.get("function") or {}
    if function.get("name"):
        slot["name"] = function["name"]
    if function.get("arguments"):
        slot["arguments"] += function["arguments"]


def _parse_arguments(raw: str) -> tuple[dict[str, Any], str | None]:
    """把累积后的参数字符串解析成 dict。

    解析失败**不抛异常**：把错误信息装进事件，让模型知道"你给的 JSON 不合法"，
    它可以自行重试。这比直接中断整个对话更符合 agent 的恢复哲学。
    """
    if not raw.strip():
        return {}, None

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {}, f"工具参数不是合法 JSON: {exc}"

    if not isinstance(parsed, dict):
        return {}, f"工具参数必须是 JSON 对象，收到 {type(parsed).__name__}"

    return parsed, None
