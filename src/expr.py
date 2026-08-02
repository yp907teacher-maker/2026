"""安全運算式求值器。

策略 JSON（filters／derived_factors／entry_signals／exit_signals）裡的運算式
一律經過這裡求值，不使用 Python 內建 eval()，只允許數字、已知變數、四則運算、
乘冪與比較/布林運算子，避免執行任意程式碼。
"""

from __future__ import annotations

import ast
import operator

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}
_UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
_COMPARE = {
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}


class ExpressionError(ValueError):
    pass


def safe_eval(expr: str, variables: dict[str, float | bool | None]):
    """求值運算式；若任一輸入變數為 None，結果一律回傳 None（資料不足，不當作 0）。"""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"運算式語法錯誤: {expr!r}") from exc
    return _eval_node(tree.body, variables)


def _eval_node(node: ast.AST, variables: dict[str, float | bool | None]):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, bool)):
            return node.value
        raise ExpressionError(f"不支援的常數: {node.value!r}")

    if isinstance(node, ast.Name):
        if node.id not in variables:
            raise ExpressionError(f"未知變數: {node.id}")
        return variables[node.id]

    if isinstance(node, ast.BinOp):
        op_func = _BINOPS.get(type(node.op))
        if op_func is None:
            raise ExpressionError(f"不支援的運算子: {type(node.op).__name__}")
        left = _eval_node(node.left, variables)
        right = _eval_node(node.right, variables)
        if left is None or right is None:
            return None
        try:
            return op_func(left, right)
        except ZeroDivisionError:
            return None

    if isinstance(node, ast.UnaryOp):
        op_func = _UNARYOPS.get(type(node.op))
        if op_func is None:
            raise ExpressionError(f"不支援的運算子: {type(node.op).__name__}")
        operand = _eval_node(node.operand, variables)
        return None if operand is None else op_func(operand)

    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, variables)
        for op, comparator in zip(node.ops, node.comparators):
            op_func = _COMPARE.get(type(op))
            if op_func is None:
                raise ExpressionError(f"不支援的比較運算子: {type(op).__name__}")
            right = _eval_node(comparator, variables)
            if left is None or right is None:
                return None
            if not op_func(left, right):
                return False
            left = right
        return True

    if isinstance(node, ast.BoolOp):
        values = [_eval_node(v, variables) for v in node.values]
        if any(v is None for v in values):
            return None
        return all(values) if isinstance(node.op, ast.And) else any(values)

    raise ExpressionError(f"不支援的語法節點: {type(node).__name__}")
