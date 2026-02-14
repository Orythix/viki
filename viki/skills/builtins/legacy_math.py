"""
Refactored math utilities module.
Provides simple arithmetic operations with proper error handling.
"""
import logging
from typing import Union

logger = logging.getLogger('viki.skills.legacy_math')


def do_math(op: str, a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """
    Perform basic arithmetic operations.
    
    Args:
        op: Operation to perform ('add', 'sub', 'mul', 'div')
        a: First operand
        b: Second operand
        
    Returns:
        Result of the operation
        
    Raises:
        ValueError: If operation is not supported
        ZeroDivisionError: If dividing by zero
    """
    operations = {
        'add': lambda x, y: x + y,
        'sub': lambda x, y: x - y,
        'mul': lambda x, y: x * y,
        'div': lambda x, y: x / y if y != 0 else (_ for _ in ()).throw(ZeroDivisionError("Division by zero")),
    }
    
    if op not in operations:
        logger.warning(f"Unsupported operation requested: {op}")
        raise ValueError(f"Unsupported operation: {op}. Supported: {list(operations.keys())}")
    
    logger.debug(f"Performing {op} operation: {a} {op} {b}")
    return operations[op](a, b)
