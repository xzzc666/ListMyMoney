# myMoney

A small Python asset management app focused on portable data, tag-based grouping, and auditable asset changes.

## Features

- Manage assets with two tag categories:
  - `asset_type`: what the asset is, with optional first-level and second-level hierarchy, such as fund / ETF
  - `storage_type`: where or how it is stored, such as bank, broker, wallet, physical
- Create custom tags while creating assets, or reuse existing tags.
- Record every asset value change with a required note.
- Store data in a single JSON file that is easy to inspect.
- Export and import a portable `.zip` package for migration.

## Quick Start

Start the Chinese visual desktop app:

```powershell
python -m mymoney.gui
```

You can also double-click `start_mymoney.bat` on Windows.

The GUI lets you add and edit assets, choose or type first-level and second-level asset tags, manage tags from the tag panel, clean unused tags with one click, update equivalent values, view allocation pie charts, record asset changes with notes, view history, and import/export migration packages. Editing an existing asset requires using the edit button, a note, and a confirmation prompt before saving; double-clicking the asset list no longer opens editing.

Asset transfers are supported between two existing assets. Direct transfers require the source and target assets to use the same currency, require a note, and create one outgoing history record plus one incoming history record.

Zero-balance assets can be moved to the `已废除` list with a required note and confirmation. Deprecated assets are hidden from the active asset list, allocation charts, equivalent-value updates, and transfers, but they can be restored from the `已废除` tab at any time.

For live equivalent values, use these currency labels:

- `CNY`, `RMB`, or `人民币` for Chinese yuan
- `GBP` or `英镑` for British pounds
- `GOLD`, `XAU`, `G`, `黄金`, `黄金(g)`, `实体黄金`, or `实体黄金(G)` for physical gold, with the asset balance recorded in grams

Click `更新等价值` to fetch live GBP/CNY and Shanghai Gold Exchange Au(T+D) pricing from Sina Finance. The asset list shows each asset's share of total assets, and `存放配比` / `类型配比` pie charts can switch between CNY, GBP, and physical gold grams.

Currency is also managed as a tag category. Asset create/edit forms let you choose an existing currency tag or type a new one, and currency tags such as `人民币` are normalized to `CNY`. The asset list includes the last update time; click a column header to sort by name, balance, currency, equivalent value, storage type, asset type, share of total assets, or last update time. Use the tag filter above the asset list to limit the visible assets by asset type, storage type, or currency; allocation chart windows calculate only from the currently visible filtered assets and include expandable rows so each storage/type group can show the assets inside it.

Command-line usage is also available:

```powershell
python -m mymoney.cli init
python -m mymoney.cli tags
python -m mymoney.cli add-asset --name "Index Fund" --value 10000 --currency USD --asset-type Fund --asset-subtype ETF --storage-type Broker --note "Initial balance"
python -m mymoney.cli list-assets
python -m mymoney.cli change --asset-id <asset-id> --delta 500 --note "Monthly saving"
python -m mymoney.cli history --asset-id <asset-id>
python -m mymoney.cli export --output mymoney-backup.zip
```

By default the app stores data in `mydatas/mymoney_data.json`, and GUI exports default to the `mydatas` folder. Use `--data PATH` before the command to choose another location:

```powershell
python -m mymoney.cli --data D:\finance\assets.json list-assets
```

## Data Portability

The exported zip contains:

- `mymoney_data.json`: all app data
- `manifest.json`: schema version, creation time, and checksums

Importing validates the package before replacing or creating the target data file.
