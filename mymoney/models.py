from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4


ASSET_TYPE = "asset_type"
STORAGE_TYPE = "storage_type"
CURRENCY_TYPE = "currency"
TAG_CATEGORIES = {ASSET_TYPE, STORAGE_TYPE, CURRENCY_TYPE}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def money(value: str | int | float | Decimal) -> Decimal:
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid numeric value: {value}") from exc


def decimal_to_str(value: Decimal) -> str:
    return format(value, "f")


@dataclass
class Tag:
    id: str
    name: str
    category: str
    parent_id: str | None = None
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if self.category not in TAG_CATEGORIES:
            raise ValueError(f"Unsupported tag category: {self.category}")
        if not self.name.strip():
            raise ValueError("Tag name cannot be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "parent_id": self.parent_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Tag":
        return cls(
            id=data["id"],
            name=data["name"],
            category=data["category"],
            parent_id=data.get("parent_id"),
            created_at=data["created_at"],
        )


@dataclass
class AssetChange:
    id: str
    asset_id: str
    delta: Decimal
    note: str
    created_at: str = field(default_factory=utc_now)
    value_after: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if not self.note.strip():
            raise ValueError("Asset change note is required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "asset_id": self.asset_id,
            "delta": decimal_to_str(self.delta),
            "note": self.note,
            "created_at": self.created_at,
            "value_after": decimal_to_str(self.value_after),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AssetChange":
        return cls(
            id=data["id"],
            asset_id=data["asset_id"],
            delta=money(data["delta"]),
            note=data["note"],
            created_at=data["created_at"],
            value_after=money(data["value_after"]),
        )


@dataclass
class Asset:
    id: str
    name: str
    value: Decimal
    currency: str
    tag_ids: list[str]
    equivalent_values: dict[str, str] = field(default_factory=dict)
    valuation_updated_at: str | None = None
    deprecated_at: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Asset name cannot be empty")
        if not self.currency.strip():
            raise ValueError("Currency cannot be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "value": decimal_to_str(self.value),
            "currency": self.currency,
            "tag_ids": self.tag_ids,
            "equivalent_values": self.equivalent_values,
            "valuation_updated_at": self.valuation_updated_at,
            "deprecated_at": self.deprecated_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Asset":
        return cls(
            id=data["id"],
            name=data["name"],
            value=money(data["value"]),
            currency=data["currency"],
            tag_ids=list(data["tag_ids"]),
            equivalent_values=dict(data.get("equivalent_values", {})),
            valuation_updated_at=data.get("valuation_updated_at"),
            deprecated_at=data.get("deprecated_at"),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )
