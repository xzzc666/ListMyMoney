from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from . import __version__
from .models import ASSET_TYPE, CURRENCY_TYPE, STORAGE_TYPE, Asset, AssetChange, Tag, decimal_to_str, money, new_id, utc_now
from .valuation import MarketRates, cny_value, equivalent_values, normalize_currency


SCHEMA_VERSION = 1
DATA_FILENAME = "mymoney_data.json"
MANIFEST_FILENAME = "manifest.json"


DEFAULT_TAGS = [
    ("Cash", ASSET_TYPE),
    ("Stock", ASSET_TYPE),
    ("Fund", ASSET_TYPE),
    ("Real Estate", ASSET_TYPE),
    ("Bank", STORAGE_TYPE),
    ("Broker", STORAGE_TYPE),
    ("Wallet", STORAGE_TYPE),
    ("Physical", STORAGE_TYPE),
    ("CNY", CURRENCY_TYPE),
    ("GBP", CURRENCY_TYPE),
    ("GOLD", CURRENCY_TYPE),
]


@dataclass
class MoneyStore:
    assets: dict[str, Asset] = field(default_factory=dict)
    tags: dict[str, Tag] = field(default_factory=dict)
    changes: list[AssetChange] = field(default_factory=list)
    ui_state: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def default(cls) -> "MoneyStore":
        store = cls()
        for name, category in DEFAULT_TAGS:
            store.add_tag(name, category)
        return store

    @classmethod
    def load(cls, path: Path) -> "MoneyStore":
        if not path.exists():
            return cls.default()

        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"Unsupported schema version: {data.get('schema_version')}")

        store = cls(
            assets={item["id"]: Asset.from_dict(item) for item in data.get("assets", [])},
            tags={item["id"]: Tag.from_dict(item) for item in data.get("tags", [])},
            changes=[AssetChange.from_dict(item) for item in data.get("changes", [])],
            ui_state=dict(data.get("ui_state", {})),
        )
        store.ensure_currency_tags()
        return store

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "app_version": __version__,
            "saved_at": utc_now(),
            "assets": [asset.to_dict() for asset in self.assets.values()],
            "tags": [tag.to_dict() for tag in self.tags.values()],
            "changes": [change.to_dict() for change in self.changes],
            "ui_state": self.ui_state,
        }

    def add_tag(self, name: str, category: str, parent_id: str | None = None) -> Tag:
        if category == CURRENCY_TYPE:
            name = normalize_currency(name)

        if parent_id is not None:
            parent = self.tags.get(parent_id)
            if parent is None:
                raise ValueError(f"Unknown parent tag id: {parent_id}")
            if parent.category != category:
                raise ValueError("Parent tag category must match child tag category")
            if category != ASSET_TYPE:
                raise ValueError("Only asset type tags support hierarchy")

        existing = self.find_tag(name, category, parent_id)
        if existing:
            return existing

        tag = Tag(id=new_id("tag"), name=name.strip(), category=category, parent_id=parent_id)
        self.tags[tag.id] = tag
        return tag

    def find_tag(self, name: str, category: str, parent_id: str | None = None) -> Tag | None:
        normalized = name.strip().casefold()
        for tag in self.tags.values():
            if tag.category == category and tag.parent_id == parent_id and tag.name.casefold() == normalized:
                return tag
        return None

    def tags_by_category(self, category: str) -> list[Tag]:
        return sorted((tag for tag in self.tags.values() if tag.category == category), key=lambda tag: tag.name)

    def root_tags_by_category(self, category: str) -> list[Tag]:
        return sorted(
            (tag for tag in self.tags.values() if tag.category == category and tag.parent_id is None),
            key=lambda tag: tag.name,
        )

    def child_tags(self, parent_id: str) -> list[Tag]:
        return sorted((tag for tag in self.tags.values() if tag.parent_id == parent_id), key=lambda tag: tag.name)

    def tag_display_name(self, tag: Tag) -> str:
        if tag.parent_id and tag.parent_id in self.tags:
            return f"{self.tags[tag.parent_id].name} / {tag.name}"
        return tag.name

    def asset_type_display(self, asset: Asset) -> str:
        asset_type_tags = [tag for tag in self.asset_tags(asset) if tag.category == ASSET_TYPE]
        child = next((tag for tag in asset_type_tags if tag.parent_id is not None), None)
        if child:
            return self.tag_display_name(child)
        root = next((tag for tag in asset_type_tags if tag.parent_id is None), None)
        return root.name if root else ""

    def asset_type_parts(self, asset: Asset) -> tuple[str, str]:
        asset_type_tags = [tag for tag in self.asset_tags(asset) if tag.category == ASSET_TYPE]
        child = next((tag for tag in asset_type_tags if tag.parent_id is not None), None)
        if child:
            parent = self.tags.get(child.parent_id)
            return (parent.name if parent else "", child.name)
        root = next((tag for tag in asset_type_tags if tag.parent_id is None), None)
        return (root.name if root else "", "")

    def storage_type_name(self, asset: Asset) -> str:
        storage = next((tag for tag in self.asset_tags(asset) if tag.category == STORAGE_TYPE), None)
        return storage.name if storage else ""

    def currency_tag_name(self, asset: Asset) -> str:
        currency = next((tag for tag in self.asset_tags(asset) if tag.category == CURRENCY_TYPE), None)
        return currency.name if currency else asset.currency

    def ensure_currency_tags(self) -> None:
        for asset in self.assets.values():
            normalized = normalize_currency(asset.currency)
            asset.currency = normalized
            currency_tag = self.add_tag(normalized, CURRENCY_TYPE)
            if currency_tag.id not in asset.tag_ids:
                asset.tag_ids.append(currency_tag.id)

    def active_assets(self) -> list[Asset]:
        return [asset for asset in self.assets.values() if asset.deprecated_at is None]

    def deprecated_assets(self) -> list[Asset]:
        return [asset for asset in self.assets.values() if asset.deprecated_at is not None]

    def equivalent_display(self, asset: Asset) -> str:
        values = asset.equivalent_values
        if not values:
            return "未更新"
        return (
            f"¥{values.get('CNY', '-')}"
            f" / £{values.get('GBP', '-')}"
            f" / 黄金{values.get('GOLD_GRAM', '-')}g"
        )

    def create_asset(
        self,
        name: str,
        value: str | int | float,
        currency: str,
        asset_type: str,
        storage_type: str,
        note: str,
        asset_subtype: str = "",
    ) -> Asset:
        if not note.strip():
            raise ValueError("Initial asset note is required")

        asset_type_tag = self.add_tag(asset_type, ASSET_TYPE)
        tag_ids = [asset_type_tag.id]
        if asset_subtype.strip():
            asset_subtype_tag = self.add_tag(asset_subtype, ASSET_TYPE, parent_id=asset_type_tag.id)
            tag_ids.append(asset_subtype_tag.id)
        storage_type_tag = self.add_tag(storage_type, STORAGE_TYPE)
        tag_ids.append(storage_type_tag.id)
        normalized_currency = normalize_currency(currency)
        currency_tag = self.add_tag(normalized_currency, CURRENCY_TYPE)
        tag_ids.append(currency_tag.id)
        initial_value = money(value)
        asset = Asset(
            id=new_id("asset"),
            name=name.strip(),
            value=initial_value,
            currency=normalized_currency,
            tag_ids=tag_ids,
        )
        self.assets[asset.id] = asset
        self.changes.append(
            AssetChange(
                id=new_id("change"),
                asset_id=asset.id,
                delta=initial_value,
                note=note.strip(),
                value_after=asset.value,
            )
        )
        return asset

    def update_asset(
        self,
        asset_id: str,
        name: str,
        value: str | int | float,
        currency: str,
        asset_type: str,
        storage_type: str,
        note: str,
        asset_subtype: str = "",
    ) -> AssetChange:
        if asset_id not in self.assets:
            raise KeyError(f"Unknown asset id: {asset_id}")
        if not note.strip():
            raise ValueError("Asset update note is required")
        if not name.strip():
            raise ValueError("Asset name cannot be empty")
        if not currency.strip():
            raise ValueError("Currency cannot be empty")

        asset = self.assets[asset_id]
        new_value = money(value)
        delta_value = new_value - asset.value

        asset_type_tag = self.add_tag(asset_type, ASSET_TYPE)
        tag_ids = [asset_type_tag.id]
        if asset_subtype.strip():
            asset_subtype_tag = self.add_tag(asset_subtype, ASSET_TYPE, parent_id=asset_type_tag.id)
            tag_ids.append(asset_subtype_tag.id)
        storage_type_tag = self.add_tag(storage_type, STORAGE_TYPE)
        tag_ids.append(storage_type_tag.id)
        normalized_currency = normalize_currency(currency)
        currency_tag = self.add_tag(normalized_currency, CURRENCY_TYPE)
        tag_ids.append(currency_tag.id)

        asset.name = name.strip()
        asset.value = new_value
        asset.currency = normalized_currency
        asset.tag_ids = tag_ids
        asset.equivalent_values = {}
        asset.valuation_updated_at = None
        asset.updated_at = utc_now()

        change = AssetChange(
            id=new_id("change"),
            asset_id=asset.id,
            delta=delta_value,
            note=f"编辑资产：{note.strip()}",
            value_after=asset.value,
        )
        self.changes.append(change)
        return change

    def update_equivalent_values(self, rates: MarketRates) -> None:
        updated_at = utc_now()
        for asset in self.active_assets():
            values = equivalent_values(asset.value, asset.currency, rates)
            asset.equivalent_values = {
                "CNY": decimal_to_str(values["CNY"].quantize(money("0.01"))),
                "GBP": decimal_to_str(values["GBP"].quantize(money("0.01"))),
                "GOLD_GRAM": decimal_to_str(values["GOLD_GRAM"].quantize(money("0.0001"))),
            }
            asset.valuation_updated_at = updated_at
            asset.updated_at = updated_at

    def asset_value_cny(self, asset: Asset, rates: MarketRates | None = None) -> Decimal:
        if asset.equivalent_values.get("CNY"):
            return money(asset.equivalent_values["CNY"])
        if rates is None:
            raise ValueError("Asset equivalent value is not updated")
        return cny_value(asset.value, asset.currency, rates)

    def asset_equivalent_value(self, asset: Asset, currency_key: str = "CNY") -> Decimal:
        key = currency_key.strip().upper()
        if key == "GOLD":
            key = "GOLD_GRAM"
        if not asset.equivalent_values.get(key):
            raise ValueError("Asset equivalent value is not updated")
        return money(asset.equivalent_values[key])

    def total_equivalent_value(self, currency_key: str = "CNY") -> Decimal:
        total = Decimal("0")
        for asset in self.active_assets():
            total += self.asset_equivalent_value(asset, currency_key)
        return total

    def asset_share_percent(self, asset: Asset) -> Decimal | None:
        try:
            total = self.total_equivalent_value("CNY")
            if total == 0:
                return Decimal("0")
            return self.asset_equivalent_value(asset, "CNY") / total * Decimal("100")
        except ValueError:
            return None

    def asset_share_display(self, asset: Asset) -> str:
        percent = self.asset_share_percent(asset)
        if percent is None:
            return "未更新"
        return f"{percent.quantize(Decimal('0.01'))}%"

    def allocation_by_storage_type(self, currency_key: str = "CNY") -> dict[str, Decimal]:
        totals: dict[str, Decimal] = {}
        for asset in self.active_assets():
            label = self.storage_type_name(asset) or "未分类"
            totals[label] = totals.get(label, Decimal("0")) + self.asset_equivalent_value(asset, currency_key)
        return totals

    def allocation_by_asset_type(self, currency_key: str = "CNY") -> dict[str, Decimal]:
        totals: dict[str, Decimal] = {}
        for asset in self.active_assets():
            label = self.asset_type_display(asset) or "未分类"
            totals[label] = totals.get(label, Decimal("0")) + self.asset_equivalent_value(asset, currency_key)
        return totals

    def allocation_items_by_storage_type(self, currency_key: str = "CNY") -> dict[str, list[tuple[str, Decimal]]]:
        items: dict[str, list[tuple[str, Decimal]]] = {}
        for asset in self.active_assets():
            label = self.storage_type_name(asset) or "未分类"
            items.setdefault(label, []).append((asset.name, self.asset_equivalent_value(asset, currency_key)))
        return items

    def allocation_items_by_asset_type(self, currency_key: str = "CNY") -> dict[str, list[tuple[str, Decimal]]]:
        items: dict[str, list[tuple[str, Decimal]]] = {}
        for asset in self.active_assets():
            label = self.asset_type_display(asset) or "未分类"
            items.setdefault(label, []).append((asset.name, self.asset_equivalent_value(asset, currency_key)))
        return items

    def change_asset(self, asset_id: str, delta: str | int | float, note: str) -> AssetChange:
        if asset_id not in self.assets:
            raise KeyError(f"Unknown asset id: {asset_id}")
        if not note.strip():
            raise ValueError("Asset change note is required")

        asset = self.assets[asset_id]
        delta_value = money(delta)
        asset.value += delta_value
        asset.updated_at = utc_now()
        change = AssetChange(
            id=new_id("change"),
            asset_id=asset.id,
            delta=delta_value,
            note=note.strip(),
            value_after=asset.value,
        )
        self.changes.append(change)
        return change

    def transfer_asset(
        self,
        from_asset_id: str,
        to_asset_id: str,
        amount: str | int | float,
        note: str,
    ) -> tuple[AssetChange, AssetChange]:
        if from_asset_id not in self.assets:
            raise KeyError(f"Unknown source asset id: {from_asset_id}")
        if to_asset_id not in self.assets:
            raise KeyError(f"Unknown target asset id: {to_asset_id}")
        if from_asset_id == to_asset_id:
            raise ValueError("Source and target assets must be different")
        if not note.strip():
            raise ValueError("Asset transfer note is required")

        from_asset = self.assets[from_asset_id]
        to_asset = self.assets[to_asset_id]
        if from_asset.deprecated_at is not None or to_asset.deprecated_at is not None:
            raise ValueError("Deprecated assets cannot be transferred")
        from_currency = normalize_currency(from_asset.currency)
        to_currency = normalize_currency(to_asset.currency)
        if from_currency != to_currency:
            raise ValueError("Only assets with the same currency can be transferred directly")

        transfer_amount = money(amount)
        if transfer_amount <= 0:
            raise ValueError("Transfer amount must be greater than zero")
        if from_asset.value < transfer_amount:
            raise ValueError("Source asset balance is not enough")

        now = utc_now()
        from_asset.value -= transfer_amount
        to_asset.value += transfer_amount
        for asset in (from_asset, to_asset):
            asset.equivalent_values = {}
            asset.valuation_updated_at = None
            asset.updated_at = now

        transfer_note = note.strip()
        out_change = AssetChange(
            id=new_id("change"),
            asset_id=from_asset.id,
            delta=-transfer_amount,
            note=f"资产转换转出到 {to_asset.name}：{transfer_note}",
            created_at=now,
            value_after=from_asset.value,
        )
        in_change = AssetChange(
            id=new_id("change"),
            asset_id=to_asset.id,
            delta=transfer_amount,
            note=f"资产转换转入自 {from_asset.name}：{transfer_note}",
            created_at=now,
            value_after=to_asset.value,
        )
        self.changes.extend([out_change, in_change])
        return out_change, in_change

    def deprecate_asset(self, asset_id: str, note: str) -> AssetChange:
        if asset_id not in self.assets:
            raise KeyError(f"Unknown asset id: {asset_id}")
        if not note.strip():
            raise ValueError("Asset deprecation note is required")

        asset = self.assets[asset_id]
        if asset.deprecated_at is not None:
            raise ValueError("Asset is already deprecated")
        if asset.value != 0:
            raise ValueError("Only zero-balance assets can be deprecated")

        now = utc_now()
        asset.deprecated_at = now
        asset.updated_at = now
        asset.equivalent_values = {}
        asset.valuation_updated_at = None
        change = AssetChange(
            id=new_id("change"),
            asset_id=asset.id,
            delta=Decimal("0"),
            note=f"废除资产：{note.strip()}",
            created_at=now,
            value_after=asset.value,
        )
        self.changes.append(change)
        return change

    def restore_asset(self, asset_id: str, note: str) -> AssetChange:
        if asset_id not in self.assets:
            raise KeyError(f"Unknown asset id: {asset_id}")
        if not note.strip():
            raise ValueError("Asset restore note is required")

        asset = self.assets[asset_id]
        if asset.deprecated_at is None:
            raise ValueError("Asset is not deprecated")

        now = utc_now()
        asset.deprecated_at = None
        asset.updated_at = now
        change = AssetChange(
            id=new_id("change"),
            asset_id=asset.id,
            delta=Decimal("0"),
            note=f"恢复资产：{note.strip()}",
            created_at=now,
            value_after=asset.value,
        )
        self.changes.append(change)
        return change

    def asset_history(self, asset_id: str) -> list[AssetChange]:
        if asset_id not in self.assets:
            raise KeyError(f"Unknown asset id: {asset_id}")
        return [change for change in self.changes if change.asset_id == asset_id]

    def asset_tags(self, asset: Asset) -> list[Tag]:
        return [self.tags[tag_id] for tag_id in asset.tag_ids if tag_id in self.tags]

    def used_tag_ids(self) -> set[str]:
        used: set[str] = set()
        for asset in self.assets.values():
            used.update(tag_id for tag_id in asset.tag_ids if tag_id in self.tags)

        # Keep the parent of a used child tag, even if an older data file did not
        # store both the parent and child on the asset.
        changed = True
        while changed:
            changed = False
            for tag_id in list(used):
                parent_id = self.tags[tag_id].parent_id
                if parent_id and parent_id in self.tags and parent_id not in used:
                    used.add(parent_id)
                    changed = True
        return used

    def unused_tags(self) -> list[Tag]:
        used = self.used_tag_ids()
        return sorted(
            (tag for tag in self.tags.values() if tag.id not in used),
            key=lambda tag: (tag.category, self.tag_display_name(tag)),
        )

    def prune_unused_tags(self) -> list[Tag]:
        unused = self.unused_tags()
        for tag in unused:
            del self.tags[tag.id]
        return unused


def export_package(data_path: Path, output_path: Path) -> None:
    data_bytes = data_path.read_bytes()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "app_version": __version__,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data_file": DATA_FILENAME,
        "sha256": hashlib.sha256(data_bytes).hexdigest(),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(DATA_FILENAME, data_bytes)
        archive.writestr(MANIFEST_FILENAME, json.dumps(manifest, indent=2))


def import_package(package_path: Path, data_path: Path) -> None:
    with zipfile.ZipFile(package_path, "r") as archive:
        names = set(archive.namelist())
        if DATA_FILENAME not in names or MANIFEST_FILENAME not in names:
            raise ValueError("Invalid package: missing data or manifest")

        data_bytes = archive.read(DATA_FILENAME)
        manifest = json.loads(archive.read(MANIFEST_FILENAME).decode("utf-8"))
        expected_hash = manifest.get("sha256")
        actual_hash = hashlib.sha256(data_bytes).hexdigest()
        if expected_hash != actual_hash:
            raise ValueError("Invalid package: data checksum mismatch")

        parsed = json.loads(data_bytes.decode("utf-8"))
        if parsed.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"Unsupported schema version: {parsed.get('schema_version')}")

    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_bytes(data_bytes)
