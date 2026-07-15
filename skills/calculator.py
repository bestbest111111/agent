from __future__ import annotations

import ast
import math
import operator
from numbers import Real

from skills.core.context import current_context
from skills.core.errors import ErrorCode, SkillFault


_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS = {ast.UAdd: operator.pos, ast.USub: operator.neg}

#每一步计算完都校验结果是否合法，四层拦截风险数值
def _validate_number(value: object, *, max_integer_bits: int, max_abs_result: float) -> int | float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise SkillFault(ErrorCode.EXECUTION_ERROR, "calculation did not produce a real number")
    if isinstance(value, int) and value.bit_length() > max_integer_bits:
        raise SkillFault(
            ErrorCode.RESOURCE_EXHAUSTED,
            f"integer result exceeds {max_integer_bits} bits",
        )
    try:
        finite = math.isfinite(float(value))
    except OverflowError as exc:
        raise SkillFault(ErrorCode.RESOURCE_EXHAUSTED, "calculation result is too large") from exc
    if not finite or abs(value) > max_abs_result:
        raise SkillFault(ErrorCode.PARAM_OUT_OF_RANGE, "calculation result is out of range")
    return value

#递归遍历 ast 语法树节点，只处理白名单允许的节点，不认识的节点直接报错。
def _evaluate(node: ast.AST, limits) -> int | float:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body, limits)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return _validate_number(
            node.value,
            max_integer_bits=limits.max_integer_bits,
            max_abs_result=limits.max_abs_result,
        )
        #一元运算符 
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        value = _UNARY_OPERATORS[type(node.op)](_evaluate(node.operand, limits))
        return _validate_number(
            value,
            max_integer_bits=limits.max_integer_bits,
            max_abs_result=limits.max_abs_result,
        )
        #分支 4：二元运算符 + - * / // % **
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        left = _evaluate(node.left, limits)
        right = _evaluate(node.right, limits)
        if isinstance(node.op, ast.Pow) and abs(right) > limits.max_exponent:
            raise SkillFault(
                ErrorCode.PARAM_OUT_OF_RANGE,
                f"exponent magnitude must not exceed {limits.max_exponent}",
            )
        try:
            result = _BINARY_OPERATORS[type(node.op)](left, right)
        except ZeroDivisionError as exc:#除数为 0 专属错误
            raise SkillFault(ErrorCode.EXECUTION_ERROR, "division by zero") from exc
        except (ArithmeticError, OverflowError) as exc:#数值溢出，数字大到无法存储
            raise SkillFault(ErrorCode.EXECUTION_ERROR, str(exc) or type(exc).__name__) from exc
        return _validate_number(
            result,#统一校验函数 _validate_number，做四层安全检查
            max_integer_bits=limits.max_integer_bits,
            max_abs_result=limits.max_abs_result,
        )
    raise SkillFault(
        ErrorCode.UNSUPPORTED_OPERATION,
        f"unsupported expression element: {type(node).__name__}",
    )


def calculator(expression: str) -> dict:
    """Safely evaluate a numeric arithmetic expression."""
   # 读取全局限制配置
    limits = current_context().limits.calculator
    # 校验输入：必须非空字符串
    if not isinstance(expression, str) or not expression.strip():
        raise SkillFault(ErrorCode.PARAM_INVALID, "expression must be a non-empty string")
    #检查长度
    if len(expression) > limits.max_expression_chars:
        raise SkillFault(
            ErrorCode.RESOURCE_EXHAUSTED,
            f"expression is too long (maximum {limits.max_expression_chars} characters)",
        )
    #异常处理
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise SkillFault(ErrorCode.PARAM_INVALID, "invalid arithmetic expression") from exc
    return {"result": _evaluate(tree, limits)}
