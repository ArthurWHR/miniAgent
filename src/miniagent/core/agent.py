"""Agent 循环 —— 对应 pi 的 `pi-agent-core`。

核心只有一件事：

    问模型 → 它要工具就执行、把结果塞回历史 → 再问 → 直到它不再要工具

两条从 pi 学来的原则：

1. **Agent 是配置，run 是状态**
   provider / tools / model / system prompt 都在构造时给定，Agent 自己不持有
   任何对话状态。每次 ``run()`` 拥有独立的 transcript，因此同一个 Agent
   可以被多个并发请求复用。

2. **事件流是唯一的输出**
   循环只 yield ``Event``，不 print、不碰 UI。CLI / Web 各自订阅各自渲染。
"""
from __future__ import annotations

from typing import AsyncIterator

from .events import Event, EventKind
from .messages import Message, TextBlock, ToolResultBlock, ToolUseBlock
from .providers.base import ModelConfig, Provider
from .tools import ToolRegistry


class Agent:
    """一个可复用的 agent 配置。每次 run() 是一次独立的对话运行。"""

    def __init__(
        self,
        *,
        provider: Provider,
        config: ModelConfig,
        tools: ToolRegistry | None = None,
        system_prompt: str | None = None,
        max_turns: int = 10,
    ) -> None:
        self.provider = provider
        self.config = config
        self.tools = tools or ToolRegistry()
        self.system_prompt = system_prompt
        # 防止模型陷入"无限调工具"的死循环 —— 必须有兜底
        self.max_turns = max_turns

    async def run(self, prompt: str) -> AsyncIterator[Event]:
        """跑一轮完整对话，产出事件流，直到 DONE。"""
        transcript: list[Message] = []
        if self.system_prompt:
            transcript.append(Message.system(self.system_prompt))
        transcript.append(Message.user(prompt))

        # 没有工具时传 None，provider 就不会带 tools 字段
        tools = list(self.tools) if len(self.tools) else None

        for turn in range(1, self.max_turns + 1):
            text_parts: list[str] = []
            tool_calls: list[dict] = []

            # 1. 请求模型，边收边转发事件
            async for event in self.provider.stream(
                transcript, config=self.config, tools=tools
            ):
                if event.kind == EventKind.ASSISTANT:
                    text_parts.append(event.data["text"])
                elif event.kind == EventKind.TOOL_CALL:
                    tool_calls.append(event.data)
                yield event

            # 2. 把这一轮模型输出拼成一条 assistant 消息，存进历史
            #
            #    必须原文保留文本 + **全部** tool_use：下一轮模型要看到自己
            #    请求过什么，API 也要求 tool_use 后面必须紧跟对应的结果。
            blocks: list = []
            text = "".join(text_parts)
            if text:
                blocks.append(TextBlock(text))
            blocks.extend(
                ToolUseBlock(id=call["id"], name=call["name"], input=call["input"])
                for call in tool_calls
            )
            if blocks:
                transcript.append(Message.assistant(blocks))

            # 3. 模型没要工具 → 对话自然结束
            if not tool_calls:
                yield Event(EventKind.DONE, {"turns": turn})
                return

            # 4. 执行工具，结果作为一条 tool 消息回填
            results: list[ToolResultBlock] = []
            for call in tool_calls:
                if call.get("parse_error"):
                    # 参数 JSON 坏了：不执行，把错误告诉模型让它重发
                    block = ToolResultBlock(
                        tool_use_id=call["id"],
                        content=call["parse_error"],
                        is_error=True,
                    )
                else:
                    block = await self.tools.execute(
                        tool_use_id=call["id"],
                        name=call["name"],
                        arguments=call["input"],
                    )

                results.append(block)
                yield Event(
                    EventKind.TOOL_RESULT,
                    {
                        "id": call["id"],
                        "name": call["name"],
                        "content": block.content,
                        "is_error": block.is_error,
                    },
                )

            transcript.append(Message.tool_results(results))
            # 5. 带着工具结果回到第 1 步，继续问模型

        # 轮数用尽：仍然产出 DONE，保证消费者能正常收尾
        yield Event(
            EventKind.ERROR,
            {"message": f"达到最大轮数 {self.max_turns}，已停止"},
        )
        yield Event(EventKind.DONE, {"turns": self.max_turns, "stopped": True})
