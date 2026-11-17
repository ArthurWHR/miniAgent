"""类型化事件流 —— 整个框架的"神经信号"。

对应 pi 里 pi-agent-core 产出的事件（KindDone / KindToolResult 等）。
Agent 循环只负责产出 Event，UI / server 只负责订阅 Event，二者互不认识对方。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventKind(str, Enum):
    """有哪些事件类型。

    这一步只把"种类"定下来；每种事件的 data 形状，等接 provider / 工具时自然浮现，
    不提前过度设计。
    """

    ASSISTANT = "assistant"      # 模型输出的一段文本增量
    TOOL_CALL = "tool_call"      # 模型请求调用一个工具
    TOOL_RESULT = "tool_result"  # 工具执行结果（成功/失败都走这里）
    DONE = "done"                # 本轮对话结束
    ERROR = "error"              # 循环层面的错误（区别于工具错误）


@dataclass
class Event:
    """最小事件单元。上层只依赖 kind 分发，不关心内部实现。"""

    kind: EventKind
    data: dict[str, Any] = field(default_factory=dict)
