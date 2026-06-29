from __future__ import annotations

import argparse
from pathlib import Path

from .models import ASSET_TYPE, STORAGE_TYPE
from .store import MoneyStore, export_package, import_package


DEFAULT_DATA_PATH = Path("mydatas") / "mymoney_data.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mymoney", description="Tag-based asset management")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_PATH, help="Path to the JSON data file")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Create the data file with default tags")
    subparsers.add_parser("tags", help="List all tags")
    subparsers.add_parser("list-assets", help="List all assets")

    add_asset = subparsers.add_parser("add-asset", help="Create a new asset")
    add_asset.add_argument("--name", required=True)
    add_asset.add_argument("--value", required=True)
    add_asset.add_argument("--currency", default="USD")
    add_asset.add_argument("--asset-type", required=True, help="Existing or new first-level asset type tag")
    add_asset.add_argument("--asset-subtype", default="", help="Optional second-level asset type tag")
    add_asset.add_argument("--storage-type", required=True, help="Existing or new storage type tag")
    add_asset.add_argument("--note", required=True, help="Required note for the initial record")

    change = subparsers.add_parser("change", help="Record an asset value change")
    change.add_argument("--asset-id", required=True)
    change.add_argument("--delta", required=True)
    change.add_argument("--note", required=True)

    history = subparsers.add_parser("history", help="Show change history for one asset")
    history.add_argument("--asset-id", required=True)

    export_cmd = subparsers.add_parser("export", help="Export a portable zip package")
    export_cmd.add_argument("--output", required=True, type=Path)

    import_cmd = subparsers.add_parser("import", help="Import a portable zip package")
    import_cmd.add_argument("--input", required=True, type=Path)

    return parser


def print_tags(store: MoneyStore) -> None:
    for category in (ASSET_TYPE, STORAGE_TYPE):
        print(f"[{category}]")
        for tag in store.tags_by_category(category):
            print(f"  {tag.id}  {tag.name}")


def print_assets(store: MoneyStore) -> None:
    if not store.assets:
        print("No assets.")
        return

    for asset in store.assets.values():
        tags = ", ".join(tag.name for tag in store.asset_tags(asset))
        print(f"{asset.id}  {asset.name}  {asset.value} {asset.currency}  [{tags}]")


def print_history(store: MoneyStore, asset_id: str) -> None:
    asset = store.assets[asset_id]
    print(f"{asset.name} ({asset.id})")
    for change in store.asset_history(asset_id):
        print(f"{change.created_at}  delta={change.delta}  value_after={change.value_after}  note={change.note}")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    data_path: Path = args.data

    if args.command == "import":
        import_package(args.input, data_path)
        print(f"Imported package into {data_path}")
        return

    store = MoneyStore.load(data_path)

    if args.command == "init":
        store.save(data_path)
        print(f"Initialized {data_path}")
    elif args.command == "tags":
        print_tags(store)
    elif args.command == "list-assets":
        print_assets(store)
    elif args.command == "add-asset":
        asset = store.create_asset(
            name=args.name,
            value=args.value,
            currency=args.currency,
            asset_type=args.asset_type,
            asset_subtype=args.asset_subtype,
            storage_type=args.storage_type,
            note=args.note,
        )
        store.save(data_path)
        print(f"Created asset {asset.id}")
    elif args.command == "change":
        change = store.change_asset(args.asset_id, args.delta, args.note)
        store.save(data_path)
        print(f"Recorded change {change.id}; value_after={change.value_after}")
    elif args.command == "history":
        print_history(store, args.asset_id)
    elif args.command == "export":
        store.save(data_path)
        export_package(data_path, args.output)
        print(f"Exported package to {args.output}")


if __name__ == "__main__":
    main()
