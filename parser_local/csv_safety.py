"""Safe CSV serialization for text received from Telegram or an LLM."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeVar

_DANGEROUS_FORMULA_PREFIXES = frozenset({"=", "+", "-", "@", "\t", "\r"})

CellValue = TypeVar("CellValue")


def neutralize_csv_cell(value: CellValue) -> CellValue | str:
    """Prevent spreadsheet formula execution while preserving non-text values.

    CSV readers still receive the original text with a leading apostrophe. Numeric,
    boolean, and null cells are returned unchanged so metrics retain their types.
    """

    if isinstance(value, str) and value[:1] in _DANGEROUS_FORMULA_PREFIXES:
        return f"'{value}"
    return value


def neutralize_csv_row(row: Mapping[str, CellValue]) -> dict[str, CellValue | str]:
    """Return a CSV-safe copy of a row without mutating the caller's mapping."""

    return {key: neutralize_csv_cell(value) for key, value in row.items()}
