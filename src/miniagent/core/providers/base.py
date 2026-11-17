"""Provider 抽象 —— 对应 pi 的 `pi-ai` 层。

职责边界：
    规范 Message  ──翻译──>  厂商格式  ──HTTP──>  模型
    规范 Event    <──翻译──  流式响应  <──HTTP──

上层（Agent 循环）只面对 Provider 接口，永远不知道背后是 OpenAI、DeepSeek
还是 Anthropic。接入新模型 = 新增一个实现，核心代码一行不改。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator, Protocol

from ..events import Event
from ..messages import Message


class ProviderError(Exception):
    """provider 层错误：鉴权失败、HTTP 错误、响应无法解析等。

    注意：**模型自己说"我做不到"不是错误**，那是一条正常的 assistant 消息。
    这里只处理"请求根本没成功"的情况。
    """


@dataclass
class ModelConfig:
    """一次请求的模型参数（与消息内容无关的旋钮）。"""

    model: str
    temperature: float | None = None
    max_tokens: int | None = None


class Provider(Protocol):
    """模型适配器接口。

    约定：
    - 输入：规范 Message 列表（历史由调用方管理，provider 不持有状态）
    - 输出：类型化 Event 流（当前只有 ASSISTANT 文本增量；
      工具调用事件在 0.5 加入）
    - 生命周期：``stream()`` 返回异步生成器，调用方 ``async for`` 消费；
      它是一次**请求**，不是一个会话。
    """

    def stream(
        self,
        messages: list[Message],
        *,
        config: ModelConfig,
    ) -> AsyncIterator[Event]: ...
