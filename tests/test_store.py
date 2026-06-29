import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from mymoney.store import MoneyStore, export_package, import_package
from mymoney.models import CURRENCY_TYPE
from mymoney.valuation import MarketRates, normalize_currency


class MoneyStoreTest(unittest.TestCase):
    def test_create_asset_adds_tags_and_initial_change(self) -> None:
        store = MoneyStore.default()

        asset = store.create_asset(
            name="Emergency Fund",
            value="1000.50",
            currency="usd",
            asset_type="Cash",
            storage_type="New Bank",
            note="Opening balance",
        )

        self.assertEqual(asset.currency, "USD")
        self.assertEqual(asset.value, Decimal("1000.50"))
        self.assertEqual(len(store.asset_history(asset.id)), 1)
        self.assertIsNotNone(store.find_tag("New Bank", "storage_type"))
        self.assertIsNotNone(store.find_tag("USD", CURRENCY_TYPE))
        self.assertIn(store.find_tag("USD", CURRENCY_TYPE).id, asset.tag_ids)

    def test_currency_tag_is_normalized_when_added(self) -> None:
        store = MoneyStore.default()

        tag = store.add_tag("人民币", CURRENCY_TYPE)

        self.assertEqual(tag.name, "CNY")
        self.assertIs(store.find_tag("CNY", CURRENCY_TYPE), tag)

    def test_create_asset_supports_second_level_asset_type(self) -> None:
        store = MoneyStore.default()

        asset = store.create_asset(
            name="Index Fund",
            value="5000",
            currency="USD",
            asset_type="Fund",
            asset_subtype="ETF",
            storage_type="Broker",
            note="Initial buy",
        )

        parent = store.find_tag("Fund", "asset_type")
        child = store.find_tag("ETF", "asset_type", parent_id=parent.id if parent else None)
        self.assertIsNotNone(parent)
        self.assertIsNotNone(child)
        self.assertEqual(child.parent_id, parent.id)
        self.assertEqual(store.asset_type_display(asset), "Fund / ETF")

    def test_change_asset_requires_note_and_updates_history(self) -> None:
        store = MoneyStore.default()
        asset = store.create_asset("Brokerage", "100", "USD", "Stock", "Broker", "Initial")

        change = store.change_asset(asset.id, "25.25", "Dividend reinvested")

        self.assertEqual(change.value_after, Decimal("125.25"))
        self.assertEqual(store.assets[asset.id].value, Decimal("125.25"))
        self.assertEqual(len(store.asset_history(asset.id)), 2)

    def test_update_asset_changes_fields_and_records_history(self) -> None:
        store = MoneyStore.default()
        asset = store.create_asset("Brokerage", "100", "USD", "Stock", "Broker", "Initial")

        change = store.update_asset(
            asset_id=asset.id,
            name="Long Term Brokerage",
            value="150",
            currency="usd",
            asset_type="Fund",
            asset_subtype="ETF",
            storage_type="New Broker",
            note="Corrected account setup",
        )

        updated = store.assets[asset.id]
        self.assertEqual(updated.name, "Long Term Brokerage")
        self.assertEqual(updated.value, Decimal("150"))
        self.assertEqual(updated.currency, "USD")
        self.assertEqual(change.delta, Decimal("50"))
        self.assertEqual(change.value_after, Decimal("150"))
        self.assertIn("Corrected account setup", change.note)
        self.assertEqual(store.asset_type_display(updated), "Fund / ETF")
        self.assertEqual(store.storage_type_name(updated), "New Broker")
        self.assertEqual(len(store.asset_history(asset.id)), 2)

    def test_prune_unused_tags_removes_only_unused_tags(self) -> None:
        store = MoneyStore.default()
        asset = store.create_asset(
            name="Index Fund",
            value="5000",
            currency="USD",
            asset_type="Fund",
            asset_subtype="ETF",
            storage_type="Broker",
            note="Initial buy",
        )
        unused_parent = store.add_tag("Unused Parent", "asset_type")
        unused_child = store.add_tag("Unused Child", "asset_type", parent_id=unused_parent.id)
        unused_storage = store.add_tag("Unused Storage", "storage_type")

        removed = store.prune_unused_tags()

        removed_ids = {tag.id for tag in removed}
        self.assertIn(unused_parent.id, removed_ids)
        self.assertIn(unused_child.id, removed_ids)
        self.assertIn(unused_storage.id, removed_ids)
        self.assertEqual(store.asset_type_display(asset), "Fund / ETF")
        self.assertEqual(store.storage_type_name(asset), "Broker")

    def test_transfer_asset_between_same_currency_assets(self) -> None:
        store = MoneyStore.default()
        source = store.create_asset("Bank A", "1000", "CNY", "Cash", "Bank", "Initial")
        target = store.create_asset("Bank B", "100", "CNY", "Cash", "Bank", "Initial")

        out_change, in_change = store.transfer_asset(source.id, target.id, "250", "Move cash")

        self.assertEqual(store.assets[source.id].value, Decimal("750"))
        self.assertEqual(store.assets[target.id].value, Decimal("350"))
        self.assertEqual(out_change.delta, Decimal("-250"))
        self.assertEqual(in_change.delta, Decimal("250"))
        self.assertIn("Move cash", out_change.note)
        self.assertIn("Move cash", in_change.note)
        self.assertEqual(len(store.asset_history(source.id)), 2)
        self.assertEqual(len(store.asset_history(target.id)), 2)

    def test_transfer_asset_rejects_different_currency_assets(self) -> None:
        store = MoneyStore.default()
        source = store.create_asset("Bank A", "1000", "CNY", "Cash", "Bank", "Initial")
        target = store.create_asset("GBP Wallet", "100", "GBP", "Cash", "Wallet", "Initial")

        with self.assertRaises(ValueError):
            store.transfer_asset(source.id, target.id, "100", "Move cash")

    def test_transfer_asset_rejects_insufficient_balance(self) -> None:
        store = MoneyStore.default()
        source = store.create_asset("Bank A", "100", "CNY", "Cash", "Bank", "Initial")
        target = store.create_asset("Bank B", "100", "CNY", "Cash", "Bank", "Initial")

        with self.assertRaises(ValueError):
            store.transfer_asset(source.id, target.id, "101", "Move cash")

    def test_deprecate_asset_requires_zero_balance_and_excludes_allocations(self) -> None:
        store = MoneyStore.default()
        active = store.create_asset("Active Cash", "100", "CNY", "Cash", "Bank", "Initial")
        deprecated = store.create_asset("Closed Cash", "0", "CNY", "Cash", "Wallet", "Initial")
        rates = MarketRates(
            gbp_to_cny=Decimal("9"),
            cny_to_gbp=Decimal("0.1111111111"),
            gold_cny_per_gram=Decimal("500"),
            source="test",
        )

        with self.assertRaises(ValueError):
            store.deprecate_asset(active.id, "Close")

        change = store.deprecate_asset(deprecated.id, "Account closed")
        store.update_equivalent_values(rates)

        self.assertIsNotNone(store.assets[deprecated.id].deprecated_at)
        self.assertEqual(change.delta, Decimal("0"))
        self.assertEqual([asset.id for asset in store.active_assets()], [active.id])
        self.assertEqual([asset.id for asset in store.deprecated_assets()], [deprecated.id])
        self.assertEqual(set(store.allocation_by_storage_type()), {"Bank"})

    def test_restore_asset_returns_asset_to_allocations(self) -> None:
        store = MoneyStore.default()
        asset = store.create_asset("Closed Cash", "0", "CNY", "Cash", "Wallet", "Initial")
        store.deprecate_asset(asset.id, "Account closed")

        change = store.restore_asset(asset.id, "Reopened")

        self.assertIsNone(store.assets[asset.id].deprecated_at)
        self.assertEqual(change.delta, Decimal("0"))
        self.assertEqual(store.active_assets()[0].id, asset.id)

    def test_update_equivalent_values_and_allocations(self) -> None:
        store = MoneyStore.default()
        store.create_asset("RMB Cash", "1000", "CNY", "Cash", "Bank", "Initial")
        store.create_asset("GBP Cash", "100", "GBP", "Cash", "Wallet", "Initial")
        store.create_asset("Gold Bar", "10", "实体黄金(G)", "Real Estate", "Physical", "Initial")
        rates = MarketRates(
            gbp_to_cny=Decimal("9"),
            cny_to_gbp=Decimal("0.1111111111"),
            gold_cny_per_gram=Decimal("500"),
            source="test",
        )

        store.update_equivalent_values(rates)

        values = {asset.name: asset.equivalent_values for asset in store.assets.values()}
        self.assertEqual(values["RMB Cash"]["CNY"], "1000.00")
        self.assertEqual(values["GBP Cash"]["CNY"], "900.00")
        self.assertEqual(values["Gold Bar"]["CNY"], "5000.00")
        self.assertEqual(store.allocation_by_storage_type()["Physical"], Decimal("5000.00"))
        self.assertEqual(store.allocation_by_asset_type()["Real Estate"], Decimal("5000.00"))
        self.assertEqual(store.allocation_by_storage_type("GBP")["Physical"], Decimal("555.56"))
        self.assertEqual(store.allocation_by_asset_type("GOLD_GRAM")["Real Estate"], Decimal("10.0000"))
        self.assertEqual(store.allocation_items_by_storage_type("CNY")["Physical"][0][0], "Gold Bar")
        self.assertEqual(store.allocation_items_by_asset_type("CNY")["Real Estate"][0][0], "Gold Bar")
        gold_asset = next(asset for asset in store.assets.values() if asset.name == "Gold Bar")
        self.assertEqual(store.asset_share_display(gold_asset), "72.46%")

    def test_normalize_currency_accepts_physical_gold_grams(self) -> None:
        self.assertEqual(normalize_currency("实体黄金(G)"), "GOLD")
        self.assertEqual(normalize_currency("黄金(g)"), "GOLD")
        self.assertEqual(normalize_currency("G"), "GOLD")
        self.assertEqual(normalize_currency("人民币"), "CNY")
        self.assertEqual(normalize_currency("英镑"), "GBP")

    def test_export_import_package_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            data_path = tmp_path / "mymoney_data.json"
            package_path = tmp_path / "backup.zip"
            imported_path = tmp_path / "imported.json"

            store = MoneyStore.default()
            store.create_asset("Wallet Cash", "80", "USD", "Cash", "Wallet", "Initial")
            store.save(data_path)

            export_package(data_path, package_path)
            import_package(package_path, imported_path)

            imported = MoneyStore.load(imported_path)
            self.assertEqual(len(imported.assets), 1)
            self.assertEqual(len(imported.changes), 1)


if __name__ == "__main__":
    unittest.main()
