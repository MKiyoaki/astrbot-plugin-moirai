from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any


class SerializableMixin:
    """Provides consistent JSON serialization for domain models."""

    def to_dict(self) -> dict[str, Any]:
        """Convert the instance to a dictionary using dataclasses.asdict."""
        if is_dataclass(self):
            return asdict(self)
        return {}


class ValidationMixin:
    """Provides shared validation logic for bounded numeric values."""

    __slots__ = ()

    @staticmethod
    def _check_unit(name: str, value: float) -> None:
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be in [0, 1], got {value}")

    @staticmethod
    def _check_range(name: str, value: float, lo: float, hi: float) -> None:
        if not lo <= value <= hi:
            raise ValueError(f"{name} must be in [{lo}, {hi}], got {value}")
