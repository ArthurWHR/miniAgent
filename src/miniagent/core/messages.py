"""消息模型 —— agent 与模型之间传递的"语言"。

对应 pi 里的 transcript / conversation 内容模型。
设计原则：**provider 中立**。这里定义 miniAgent 自己的规范格式，
OpenAI / Anthropic 等厂商的字段差异由 core/providers/ 负责翻译，
本文件里不出现任何厂商特有的字段名。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Union


@dataclass
class TextBlock:
    """一段纯文本。user 的输入、assistant 的普通回答都是它。"""

    text: str
    type: Literal["text"] = "text"


@dataclass
class ToolUseBlock:
    """模型请求调用一个工具。

    input 是**已经解析好**的 dict：流式传输时它由分片 JSON 拼接而成，
    拼接逻辑在 agent 循环里（0.5），本模型只承载最终结果。
    """

    id: str                    # provider 分配的工具调用 id，回填结果时必须带上
    name: str                  # 要调用的工具名
    input: dict[str, Any] = field(default_factory=dict)
    type: Literal["tool_use"] = "tool_use"


@dataclass
class ToolResultBlock:
    """工具执行结果，作为一条消息回填给模型。

    失败用 is_error 标记，而不是抛异常 —— 对应 pi 的"工具失败是事件"哲学：
    让模型看到失败原因，自己决定重试、换工具、还是向用户解释。
    """

    tool_use_id: str
    content: str
    is_error: bool = False
    type: Literal["tool_result"] = "tool_result"


ContentBlock = Union[TextBlock, ToolUseBlock, ToolResultBlock]

Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class Message:
    """一条对话消息。

    content 统一用 ``list[ContentBlock]``，而不是有时 str、有时 list：
      - 一条 assistant 消息可以同时包含文本和**多个** tool_use（单轮多工具调用的基础）
      - 一条 tool 消息可以包含多个 tool_result

    如果允许 str，就会不知不觉写出"一条消息只能有一种内容"的错误假设，
    这个 bug 在接入第二个 provider 或做多工具时才会爆出来。
    """

    role: Role
    content: list[ContentBlock] = field(default_factory=list)

    def __post_init__(self) -> None:
        if isinstance(self.content, str):
            raise TypeError(
                "content 必须是 list[ContentBlock]，请用 Message.user(...) 等构造器"
            )
        if self.role == "tool":
            for block in self.content:
                if not isinstance(block, ToolResultBlock):
                    raise ValueError(
                        "role='tool' 的消息只能包含 ToolResultBlock，"
                        f"收到 {type(block).__name__}"
                    )

    # ---------- 便捷构造 ----------

    @classmethod
    def system(cls, text: str) -> "Message":
        return cls("system", [TextBlock(text)])

    @classmethod
    def user(cls, text: str) -> "Message":
        return cls("user", [TextBlock(text)])

    @classmethod
    def assistant(cls, blocks: list[ContentBlock]) -> "Message":
        return cls("assistant", blocks)

    @classmethod
    def tool_results(cls, blocks: list[ToolResultBlock]) -> "Message":
        return cls("tool", list(blocks))

    # ---------- 读取 ----------

    @property
    def text(self) -> str:
        """把所有文本块拼起来，方便展示 / 日志。"""
        return "".join(b.text for b in self.content if isinstance(b, TextBlock))

    @property
    def tool_uses(self) -> list[ToolUseBlock]:
        return [b for b in self.content if isinstance(b, ToolUseBlock)]

    def append(self, block: ContentBlock) -> None:
        self.content.append(block)
