"""
Prompt templates for agents
"""

from .barter_prompts import get_barter_system_prompt
from .general_prompts import get_general_system_prompt
from .sales_prompts import get_sales_system_prompt

__all__ = [
    "get_general_system_prompt",
    "get_sales_system_prompt",
    "get_barter_system_prompt",
]
