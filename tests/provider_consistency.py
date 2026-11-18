"""阶段 1.3 验收：同一 Agent + 同一工具，两个 provider 产出等价的规范事件。

不联网：用 httpx.MockTransport 模拟两家的 SSE 流。
运行：uv run python tests/provider_consistency.py
"""
from __future__ import annotations

import asyncio
import json

import httpx

from miniagent.builtin_tools import CALCULATOR
from miniagent.core.agent import Agent
from miniagent.core.events import EventKind
from miniagent.core.providers import (
    AnthropicProvider,
    ModelConfig,
    OpenAICompatibleProvider,
)
from miniagent.core.tools import ToolRegistry

SYSTEM = "你是助手"


def openai_sse(chunks: list[dict]) -> bytes:
    body = "".join(
        "data: " + json.dumps(c, ensure_ascii=False) + "\n\n" for c in chunks
    )
    return (body + "data: [DONE]\n\n").encode()


def anthropic_sse(events: list[dict]) -> bytes:
    return "".join(
        f"event: {e['type']}\ndata: " + json.dumps(e, ensure_ascii=False) + "\n\n"
        for e in events
    ).encode()


OPENAI_TOOL_TURN = [
    {"choices": [{"delta": {"content": "我算一下"}}]},
    {
        "choices": [
            {
                "delta": {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "calculator", "arguments": ""},
                        }
                    ]
                }
            }
        ]
    },
    {
        "choices": [
            {
                "delta": {
                    "tool_calls": [
                        {"index": 0, "function": {"arguments": '{"expr": "2*(3+4)"}'}}
                    ]
                }
            }
        ]
    },
]
OPENAI_FINAL_TURN = [{"choices": [{"delta": {"content": "等于 14"}}]}]

ANTHROPIC_TOOL_TURN = [
    {"type": "message_start", "message": {}},
    {
        "type": "content_block_start",
        "index": 0,
        "content_block": {"type": "text", "text": ""},
    },
    {
        "type": "content_block_delta",
        "index": 0,
        "delta": {"type": "text_delta", "text": "我算一下"},
    },
    {"type": "content_block_stop", "index": 0},
    {
        "type": "content_block_start",
        "index": 1,
        "content_block": {
            "type": "tool_use",
            "id": "toolu_1",
            "name": "calculator",
            "input": {},
        },
    },
    {
        "type": "content_block_delta",
        "index": 1,
        "delta": {"type": "input_json_delta", "partial_json": '{"expr": '},
    },
    {
        "type": "content_block_delta",
        "index": 1,
        "delta": {"type": "input_json_delta", "partial_json": '"2*(3+4)"}'},
    },
    {"type": "content_block_stop", "index": 1},
    {"type": "message_delta", "delta": {"stop_reason": "tool_use"}},
    {"type": "message_stop"},
]
ANTHROPIC_FINAL_TURN = [
    {"type": "message_start", "message": {}},
    {
        "type": "content_block_start",
        "index": 0,
        "content_block": {"type": "text", "text": ""},
    },
    {
        "type": "content_block_delta",
        "index": 0,
        "delta": {"type": "text_delta", "text": "等于 14"},
    },
    {"type": "content_block_stop", "index": 0},
    {"type": "message_stop"},
]


def make_openai_client() -> httpx.AsyncClient:
    state = {"turn": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        state["turn"] += 1

        if state["turn"] == 1:
            # 工具声明和 system 都在 messages 里
            assert body["tools"][0]["function"]["name"] == "calculator"
            assert body["messages"][0] == {"role": "system", "content": SYSTEM}
            content = openai_sse(OPENAI_TOOL_TURN)
        else:
            # 第二轮历史里必须有工具结果
            assert any(
                m["role"] == "tool" and m["content"] == "14"
                for m in body["messages"]
            )
            content = openai_sse(OPENAI_FINAL_TURN)

        return httpx.Response(
            200, content=content, headers={"content-type": "text/event-stream"}
        )

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def make_anthropic_client() -> httpx.AsyncClient:
    state = {"turn": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        state["turn"] += 1

        # 两家协议的关键差异，这里是验收点
        assert request.headers["x-api-key"] == "test"
        assert request.headers["anthropic-version"]
        assert body["max_tokens"] > 0

        if state["turn"] == 1:
            assert body["system"] == SYSTEM
            assert (
                body["tools"][0]["input_schema"]["properties"]["expr"]["type"]
                == "string"
            )
            content = anthropic_sse(ANTHROPIC_TOOL_TURN)
        else:
            assert body["messages"][-1]["role"] == "user"
            assert any(
                block.get("type") == "tool_result" and block.get("content") == "14"
                for block in body["messages"][-1]["content"]
            )
            content = anthropic_sse(ANTHROPIC_FINAL_TURN)

        return httpx.Response(
            200, content=content, headers={"content-type": "text/event-stream"}
        )

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def run_agent(provider) -> list:
    registry = ToolRegistry()
    registry.register(CALCULATOR)
    agent = Agent(
        provider=provider,
        config=ModelConfig(model="test-model"),
        tools=registry,
        system_prompt=SYSTEM,
    )
    return [event async for event in agent.run("2*(3+4) 等于多少？")]


def normalize(events: list) -> dict:
    """只保留规范事件里的语义内容，忽略 provider 分配的 id。"""
    return {
        "text": "".join(
            e.data["text"] for e in events if e.kind == EventKind.ASSISTANT
        ),
        "calls": [
            (e.data["name"], e.data["input"], e.data["parse_error"])
            for e in events
            if e.kind == EventKind.TOOL_CALL
        ],
        "results": [
            (e.data["name"], e.data["content"], e.data["is_error"])
            for e in events
            if e.kind == EventKind.TOOL_RESULT
        ],
        "done": [e.data for e in events if e.kind == EventKind.DONE],
    }


async def main() -> None:
    openai = OpenAICompatibleProvider(
        api_key="test",
        base_url="https://fake.local/v1",
        client=make_openai_client(),
    )
    anthropic = AnthropicProvider(
        api_key="test",
        base_url="https://fake.local",
        client=make_anthropic_client(),
    )

    try:
        openai_events = await run_agent(openai)
        anthropic_events = await run_agent(anthropic)
    finally:
        await openai.aclose()
        await anthropic.aclose()

    a = normalize(openai_events)
    b = normalize(anthropic_events)

    print("OpenAI   :", a)
    print("Anthropic:", b)
    print()

    assert a == b, "两个 provider 的规范事件不一致"
    assert a["calls"] == [("calculator", {"expr": "2*(3+4)"}, None)]
    assert a["results"] == [("calculator", "14", False)]
    assert a["text"] == "我算一下等于 14"
    assert a["done"] == [{"turns": 2}]

    print("PASS: 两个 provider 产出等价的规范事件")


if __name__ == "__main__":
    asyncio.run(main())
