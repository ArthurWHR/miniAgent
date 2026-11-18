"""命令行入口 —— 阶段 0 的最终验收。

它只做两件事：
1. 组装 Agent（provider + tools + system prompt）
2. 订阅事件流并渲染到终端

注意第 2 点：CLI 不认识 Agent 的内部逻辑，只认识 Event。
以后换成 Web UI，改的是渲染器，不是这里，更不是 core。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import TextIO

from .builtin_tools import CALCULATOR
from .core.agent import Agent
from .core.events import Event, EventKind
from .core.providers import ModelConfig, OpenAICompatibleProvider, ProviderError
from .core.tools import ToolRegistry

DEFAULT_SYSTEM_PROMPT = (
    "你是一个通用助手。需要算术时调用 calculator 工具，不要心算。"
    "工具返回错误时，根据错误信息调整后重试，或向用户说明原因。"
)


class ConsoleRenderer:
    """把事件流渲染成终端文本。

    维护 ``_at_line_start`` 是为了流式文本和提示行不粘在一起：
    模型输出到一半时插入 ``[tool] ...``，必须先补一个换行。
    """

    def __init__(self, out: TextIO = sys.stdout, err: TextIO = sys.stderr) -> None:
        self.out = out
        self.err = err
        self._at_line_start = True

    def _write(self, text: str) -> None:
        self.out.write(text)
        self.out.flush()
        self._at_line_start = text.endswith("\n")

    def _ensure_newline(self) -> None:
        if not self._at_line_start:
            self._write("\n")

    def render(self, event: Event) -> None:
        match event.kind:
            case EventKind.ASSISTANT:
                self._write(event.data["text"])

            case EventKind.TOOL_CALL:
                self._ensure_newline()
                if event.data.get("parse_error"):
                    self._write(f"[tool] {event.data['name']} 参数解析失败\n")
                else:
                    args = json.dumps(event.data["input"], ensure_ascii=False)
                    self._write(f"[tool] {event.data['name']}({args})\n")

            case EventKind.TOOL_RESULT:
                self._ensure_newline()
                tag = "tool error" if event.data.get("is_error") else "tool result"
                self._write(f"[{tag}] {event.data['content']}\n")

            case EventKind.ERROR:
                self._ensure_newline()
                self.err.write(f"[error] {event.data['message']}\n")
                self.err.flush()

            case EventKind.DONE:
                self._ensure_newline()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="miniagent",
        description="miniAgent —— 一个最小的通用 agent",
    )
    parser.add_argument("prompt", help="要发给 agent 的问题")
    parser.add_argument(
        "--model",
        default=os.environ.get("MINIAGENT_MODEL", "gpt-4o-mini"),
        help="模型名（默认取 MINIAGENT_MODEL，否则 gpt-4o-mini）",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="OpenAI 兼容服务的 base URL（默认取 OPENAI_BASE_URL）",
    )
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--max-turns", type=int, default=10)
    parser.add_argument(
        "--system",
        default=None,
        help="覆盖默认 system prompt",
    )
    return parser


async def _run(agent: Agent, prompt: str, renderer: ConsoleRenderer) -> int:
    had_error = False
    async for event in agent.run(prompt):
        if event.kind == EventKind.ERROR:
            had_error = True
        renderer.render(event)
    return 1 if had_error else 0


async def _async_main(args: argparse.Namespace) -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print(
            "缺少环境变量 OPENAI_API_KEY。\n"
            "例如：\n"
            "  export OPENAI_API_KEY=sk-xxx\n"
            "  export OPENAI_BASE_URL=https://api.deepseek.com/v1   # 可选\n"
            "  uv run miniagent --model deepseek-v4-pro '2*(3+4) 等于多少？'",
            file=sys.stderr,
        )
        return 2

    provider = OpenAICompatibleProvider(base_url=args.base_url)
    registry = ToolRegistry()
    registry.register(CALCULATOR)

    agent = Agent(
        provider=provider,
        config=ModelConfig(
            model=args.model,
            temperature=args.temperature,
        ),
        tools=registry,
        system_prompt=args.system or DEFAULT_SYSTEM_PROMPT,
        max_turns=args.max_turns,
    )

    try:
        return await _run(agent, args.prompt, ConsoleRenderer())
    except ProviderError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    finally:
        await provider.aclose()


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        return asyncio.run(_async_main(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
