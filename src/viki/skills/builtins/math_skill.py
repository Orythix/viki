import math
import ast
import operator
from typing import Dict, Any
from viki.skills.base import BaseSkill

class SafeMathEvaluator(ast.NodeVisitor):
    """Safe evaluator for mathematical expressions using AST parsing."""
    
    # Allowed operators
    operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }
    
    # Allowed functions from math module
    functions = {
        'sin': math.sin, 'cos': math.cos, 'tan': math.tan,
        'asin': math.asin, 'acos': math.acos, 'atan': math.atan,
        'sqrt': math.sqrt, 'log': math.log, 'log10': math.log10,
        'exp': math.exp, 'floor': math.floor, 'ceil': math.ceil,
        'abs': abs, 'round': round, 'min': min, 'max': max,
        'pi': math.pi, 'e': math.e,
    }
    
    def evaluate(self, expression: str):
        """Safely evaluate a mathematical expression."""
        try:
            node = ast.parse(expression, mode='eval')
            return self.visit(node.body)
        except SyntaxError as e:
            raise ValueError(f"Invalid syntax: {e}")
    
    def visit_Constant(self, node):
        """Handle numeric constants."""
        return node.value
    
    def visit_Num(self, node):
        """Handle numeric literals (Python < 3.8)."""
        return node.n
    
    def visit_BinOp(self, node):
        """Handle binary operations (e.g., 2 + 3)."""
        left = self.visit(node.left)
        right = self.visit(node.right)
        op = self.operators.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported operator: {node.op.__class__.__name__}")
        return op(left, right)
    
    def visit_UnaryOp(self, node):
        """Handle unary operations (e.g., -5)."""
        operand = self.visit(node.operand)
        op = self.operators.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported operator: {node.op.__class__.__name__}")
        return op(operand)
    
    def visit_Call(self, node):
        """Handle function calls (e.g., sqrt(16))."""
        if not isinstance(node.func, ast.Name):
            raise ValueError("Only simple function calls are allowed")
        
        func_name = node.func.id
        if func_name not in self.functions:
            raise ValueError(f"Function '{func_name}' is not allowed")
        
        func = self.functions[func_name]
        args = [self.visit(arg) for arg in node.args]
        
        try:
            return func(*args)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Error calling {func_name}: {e}")
    
    def visit_Name(self, node):
        """Handle variable names (constants like pi, e)."""
        if node.id in self.functions:
            return self.functions[node.id]
        raise ValueError(f"Undefined variable: {node.id}")
    
    def generic_visit(self, node):
        """Reject any node types we haven't explicitly allowed."""
        raise ValueError(f"Unsupported operation: {node.__class__.__name__}")


class MathSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "math_skill"

    @property
    def description(self) -> str:
        return "Evaluates mathematical expressions safely. Params: 'expression' (str)."

    async def execute(self, params: Dict[str, Any]) -> str:
        expression = params.get("expression")
        if not expression:
            return "Error: No expression provided."
        
        evaluator = SafeMathEvaluator()
        try:
            result = evaluator.evaluate(expression)
            return str(result)
        except ValueError as e:
            return f"Math Error: {str(e)}"
        except Exception as e:
            return f"Unexpected Error: {str(e)}"
