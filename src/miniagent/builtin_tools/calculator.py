"""计算器工具。

为什么不用 `eval()`：
    `eval("__import__('os').system('rm -rf /')")` 能直接执行任意代码，
    而工具参数是**模型生成的**（还可能被提示注入污染）。
    这里改用 AST 白名单：只允许数字、四则运算、取模、整除、幂和括号，
    其余节点一律拒绝。这是 agent 安全的第一课：工具边界必须自己守。
"""
from __future__ import annotations

import ast
import operator
from typing import Annotated, Any, Callable

from pydantic import Field

from ..core.tools import Tool

_BIN_OPS: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPS: dict[type[ast.unaryop], Callable[[Any], Any]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

_MAX_EXPONENT = 1000


def _evaluate(node: ast.AST) -> float | int:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)

    # 只接受字面量数字，拒绝变量名、字符串、True/False 等
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise ValueError(f"不支持的常量: {node.value!r}")

    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"不支持的运算符: {type(node.op).__name__}")
        left, right = _evaluate(node.left), _evaluate(node.right)
        # 防止 9**9**9 这类表达式把进程卡死
        if isinstance(node.op, ast.Pow) and abs(right) > _MAX_EXPONENT:
            raise ValueError(f"指数过大: {right}")
        return op(left, right)

    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"不支持的一元运算符: {type(node.op).__name__}")
        return op(_evaluate(node.operand))

    raise ValueError(f"不支持的表达式: {type(node).__name__}")


def calculator(
    expr: Annotated[
        str,
        Field(description="要计算的数学表达式，例如 '2*(3+4)'"),
    ],
) -> str:
    """计算一个数学表达式，支持 + - * / // % ** 和括号。
    例如 '2*(3+4)'、'(1+2)/3'。不要用它做非数学任务。

    安全说明：参数由模型生成，因此这里用 AST 白名单求值，不调用 eval。
    这段是给人类读者看的，工具描述只取第一段。
    """
    try:
        tree = ast.parse(expr, mode="eval")
        value = _evaluate(tree)
    except SyntaxError as exc:
        raise ValueError(f"表达式语法错误: {expr!r}") from exc

    # 7.0 → "7"，0.5 保持 "0.5"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value)


# 函数名 → 工具名；docstring 第一段 → 工具描述；类型注解 → 参数 schema
CALCULATOR = Tool.from_function(calculator)
