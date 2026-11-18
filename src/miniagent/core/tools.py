"""工具系统（最小版）—— 对应 pi 的 `RunTool`。

一个工具由两部分组成：
    1. **给模型看的说明书**：name / description / parameters（JSON Schema）
    2. **给程序执行的回调**：handler

模型只读说明书决定"调谁、传什么"，执行器只关心 handler 怎么跑。
两者解耦，所以以后用 Pydantic 自动生成 schema 时，执行逻辑一行不用改。

本阶段（0.4）刻意保持最小：
- 手写 JSON Schema（阶段 2 换成 Pydantic 自动生成）
- 没有审批门（阶段 2 加 approve）
- 没有输出截断（阶段 3 加）

但有一条从第一天就必须遵守：**工具失败不抛异常，而是返回 is_error=True 的结果块**。
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable

from .messages import ToolResultBlock


@dataclass(frozen=True)
class Tool:
    """一个可被模型调用的工具。"""

    name: str
    description: str
    # JSON Schema（顶层必须是 type: object），模型据此生成参数
    parameters: dict[str, Any]
    # 同步或异步函数均可；参数名必须与 schema 里的 properties 对应
    handler: Callable[..., Any]


class ToolRegistry:
    """工具注册表：按名字查找、执行。

    注册时拒绝重名 —— 与其等到运行时被模型随机选中一个，不如启动时报错。
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"工具名重复: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def __len__(self) -> int:
        return len(self._tools)

    def __iter__(self):
        return iter(self._tools.values())

    async def execute(
        self,
        *,
        tool_use_id: str,
        name: str,
        arguments: dict[str, Any],
    ) -> ToolResultBlock:
        """执行一次工具调用，**永远返回结果块，不抛异常**。

        - 工具名不存在 → is_error=True
        - 参数不匹配 / handler 内部报错 → is_error=True
        模型会看到错误内容，自己决定重试、换工具还是向用户解释。
        """
        tool = self.get(name)
        if tool is None:
            return ToolResultBlock(
                tool_use_id=tool_use_id,
                content=f"未知工具: {name!r}，可用工具: {sorted(self._tools)}",
                is_error=True,
            )

        try:
            result = tool.handler(**arguments)
            if inspect.isawaitable(result):
                result = await result
            return ToolResultBlock(
                tool_use_id=tool_use_id,
                content=result if isinstance(result, str) else str(result),
            )
        except Exception as exc:  # noqa: BLE001 - 故意兜住一切，交给模型处理
            return ToolResultBlock(
                tool_use_id=tool_use_id,
                content=f"{type(exc).__name__}: {exc}",
                is_error=True,
            )
