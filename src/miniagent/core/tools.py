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
import typing
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, create_model

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
    # 由 from_function 生成，供执行前的参数校验使用（阶段 2.2）
    arg_model: type[BaseModel] | None = None

    @classmethod
    def from_function(
        cls,
        fn: Callable[..., Any],
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> "Tool":
        """从一个普通函数推导出工具。

        - **参数 schema** 来自类型注解（`Annotated[str, Field(description=...)]`
          可以带参数说明）
        - **工具描述** 默认取 docstring 的第一段
        - 函数名即工具名，可用 ``name=`` 覆盖

        这样工具作者只需要写函数，schema 和实现不可能再漂移。
        """
        arg_model = _args_model(fn)
        schema = _clean_schema(arg_model.model_json_schema())
        return cls(
            name=name or fn.__name__,
            description=description if description is not None else _first_paragraph(fn),
            parameters=schema,
            handler=fn,
            arg_model=arg_model,
        )


def _args_model(fn: Callable[..., Any]) -> type[BaseModel]:
    """把函数签名转成一个 Pydantic 模型（只用于描述和校验，不执行 handler）。"""
    signature = inspect.signature(fn)
    # 模块里有 `from __future__ import annotations` 时注解是字符串，
    # get_type_hints 负责解析；include_extras=True 保留 Annotated 里的 Field 信息
    hints = typing.get_type_hints(fn, include_extras=True)

    fields: dict[str, Any] = {}
    for name, param in signature.parameters.items():
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            raise TypeError(f"工具函数不支持 *args / **kwargs: {fn.__name__}")

        annotation = hints.get(name, param.annotation)
        if annotation is inspect.Parameter.empty:
            raise TypeError(
                f"工具参数 {name!r} 缺少类型注解: {fn.__name__}；"
                "类型注解就是给模型看的 schema"
            )

        default = ... if param.default is inspect.Parameter.empty else param.default
        fields[name] = (annotation, default)

    return create_model(f"{fn.__name__}_Args", **fields)


def _first_paragraph(fn: Callable[..., Any]) -> str:
    """docstring 的第一段作为工具描述，后面的段落留给人类读者。"""
    doc = inspect.getdoc(fn) or ""
    paragraph = doc.split("\n\n", 1)[0]
    # 去掉源码里的换行折行，得到一行干净的描述
    return " ".join(line.strip() for line in paragraph.splitlines()).strip()


def _clean_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Pydantic 生成的 schema 里有给人类看的 title，模型不需要，去掉省 token。"""
    _strip_titles(schema)
    schema.setdefault("type", "object")
    schema.setdefault("properties", {})
    # 明确禁止模型塞 schema 之外的字段
    schema["additionalProperties"] = False
    return schema


def _strip_titles(node: Any) -> None:
    if isinstance(node, dict):
        node.pop("title", None)
        for value in node.values():
            _strip_titles(value)
    elif isinstance(node, list):
        for value in node:
            _strip_titles(value)


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
