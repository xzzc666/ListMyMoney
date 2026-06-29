from __future__ import annotations

import tkinter as tk
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .models import ASSET_TYPE, CURRENCY_TYPE, STORAGE_TYPE, Asset, Tag
from .store import MoneyStore, export_package, import_package
from .valuation import fetch_market_rates


DATA_DIR = Path("mydatas")
DEFAULT_DATA_PATH = DATA_DIR / "mymoney_data.json"
CATEGORY_OPTIONS = {
    "资产类型": ASSET_TYPE,
    "存放方式": STORAGE_TYPE,
    "币种": CURRENCY_TYPE,
}
ALL_FILTER_CATEGORIES = "全部分类"
ALL_FILTER_TAGS = "全部标签"
FILTER_LOGIC_OPTIONS = ("与", "或", "非与", "非或")


def category_label(category: str) -> str:
    labels = {
        ASSET_TYPE: "资产类型",
        STORAGE_TYPE: "存放方式",
        CURRENCY_TYPE: "币种",
    }
    return labels.get(category, category)


class AssetDialog(tk.Toplevel):
    def __init__(self, parent: tk.Widget, store: MoneyStore, asset: Asset | None = None) -> None:
        super().__init__(parent)
        self.title("编辑资产" if asset else "新增资产")
        self.resizable(False, False)
        self.result: dict[str, str] | None = None
        self.store = store
        self.asset = asset

        asset_type, asset_subtype = store.asset_type_parts(asset) if asset else ("", "")
        self.name_var = tk.StringVar(value=asset.name if asset else "")
        self.value_var = tk.StringVar(value=str(asset.value) if asset else "")
        self.currency_var = tk.StringVar(value=asset.currency if asset else "USD")
        self.asset_type_var = tk.StringVar(value=asset_type)
        self.asset_subtype_var = tk.StringVar(value=asset_subtype)
        self.storage_type_var = tk.StringVar(value=store.storage_type_name(asset) if asset else "")
        self.note_var = tk.StringVar()

        self._build()
        self.transient(parent)
        self.grab_set()
        self.wait_visibility()
        self.name_entry.focus_set()

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=18, style="Panel.TFrame")
        frame.grid(row=0, column=0, sticky="nsew")

        title = "编辑资产" if self.asset else "新增资产"
        ttk.Label(frame, text=title, style="DialogTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12)
        )
        self.name_entry = self._entry(frame, "资产名称", self.name_var, 1)
        self._entry(frame, "当前余额", self.value_var, 2)
        self._combo(frame, "币种", self.currency_var, self._currency_types(), 3)
        self.asset_type_combo = self._combo(frame, "一级资产类型", self.asset_type_var, self._root_asset_types(), 4)
        self.asset_subtype_combo = self._combo(frame, "二级资产类型", self.asset_subtype_var, [], 5)
        self._combo(frame, "存放方式", self.storage_type_var, self._storage_types(), 6)
        self._entry(frame, "备注", self.note_var, 7)

        self.asset_type_combo.bind("<<ComboboxSelected>>", self._refresh_subtype_values)
        self.asset_type_combo.bind("<FocusOut>", self._refresh_subtype_values)
        self._refresh_subtype_values()

        hint = "一级和二级资产类型都可以直接输入新名称；二级可留空。编辑资产时备注必填。"
        ttk.Label(frame, text=hint, foreground="#64748b").grid(row=8, column=0, columnspan=2, sticky="w", pady=(8, 0))

        actions = ttk.Frame(frame)
        actions.grid(row=9, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(actions, text="取消", command=self.destroy).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="保存", style="Accent.TButton", command=self._save).grid(row=0, column=1)

    def _entry(self, parent: ttk.Frame, label: str, variable: tk.StringVar, row: int) -> ttk.Entry:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        entry = ttk.Entry(parent, textvariable=variable, width=34)
        entry.grid(row=row, column=1, sticky="ew", pady=4)
        return entry

    def _combo(
        self,
        parent: ttk.Frame,
        label: str,
        variable: tk.StringVar,
        values: list[str],
        row: int,
    ) -> ttk.Combobox:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        combo = ttk.Combobox(parent, textvariable=variable, values=values, width=31)
        combo.grid(row=row, column=1, sticky="ew", pady=4)
        return combo

    def _root_asset_types(self) -> list[str]:
        return [tag.name for tag in self.store.root_tags_by_category(ASSET_TYPE)]

    def _storage_types(self) -> list[str]:
        return [tag.name for tag in self.store.tags_by_category(STORAGE_TYPE)]

    def _currency_types(self) -> list[str]:
        return [tag.name for tag in self.store.tags_by_category(CURRENCY_TYPE)]

    def _refresh_subtype_values(self, _event: tk.Event[tk.Widget] | None = None) -> None:
        parent = self.store.find_tag(self.asset_type_var.get(), ASSET_TYPE)
        values = [tag.name for tag in self.store.child_tags(parent.id)] if parent else []
        self.asset_subtype_combo.configure(values=values)

    def _save(self) -> None:
        self.result = {
            "name": self.name_var.get(),
            "value": self.value_var.get(),
            "currency": self.currency_var.get(),
            "asset_type": self.asset_type_var.get(),
            "asset_subtype": self.asset_subtype_var.get(),
            "storage_type": self.storage_type_var.get(),
            "note": self.note_var.get(),
        }
        self.destroy()


class ChangeDialog(tk.Toplevel):
    def __init__(self, parent: tk.Widget, asset_name: str) -> None:
        super().__init__(parent)
        self.title(f"记录变动 - {asset_name}")
        self.resizable(False, False)
        self.result: dict[str, str] | None = None

        self.delta_var = tk.StringVar()
        self.note_var = tk.StringVar()

        frame = ttk.Frame(self, padding=18, style="Panel.TFrame")
        frame.grid(row=0, column=0, sticky="nsew")
        ttk.Label(frame, text="记录变动", style="DialogTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12)
        )
        ttk.Label(frame, text="变动金额").grid(row=1, column=0, sticky="w", pady=4)
        self.delta_entry = ttk.Entry(frame, textvariable=self.delta_var, width=34)
        self.delta_entry.grid(row=1, column=1, pady=4)
        ttk.Label(frame, text="备注").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.note_var, width=34).grid(row=2, column=1, pady=4)

        actions = ttk.Frame(frame)
        actions.grid(row=3, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(actions, text="取消", command=self.destroy).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="保存", style="Accent.TButton", command=self._save).grid(row=0, column=1)

        self.transient(parent)
        self.grab_set()
        self.wait_visibility()
        self.delta_entry.focus_set()

    def _save(self) -> None:
        self.result = {"delta": self.delta_var.get(), "note": self.note_var.get()}
        self.destroy()


class TransferDialog(tk.Toplevel):
    def __init__(self, parent: tk.Widget, store: MoneyStore, selected_asset_id: str | None = None) -> None:
        super().__init__(parent)
        self.title("资产转换")
        self.resizable(False, False)
        self.result: dict[str, str] | None = None
        self.asset_options = {
            f"{asset.name} ({asset.value} {asset.currency})": asset.id
            for asset in store.active_assets()
        }

        self.from_var = tk.StringVar()
        self.to_var = tk.StringVar()
        self.amount_var = tk.StringVar()
        self.note_var = tk.StringVar()

        frame = ttk.Frame(self, padding=18, style="Panel.TFrame")
        frame.grid(row=0, column=0, sticky="nsew")
        ttk.Label(frame, text="资产转换", style="DialogTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12)
        )

        values = list(self.asset_options)
        ttk.Label(frame, text="转出资产").grid(row=1, column=0, sticky="w", pady=4)
        from_combo = ttk.Combobox(frame, textvariable=self.from_var, values=values, state="readonly", width=40)
        from_combo.grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="转入资产").grid(row=2, column=0, sticky="w", pady=4)
        to_combo = ttk.Combobox(frame, textvariable=self.to_var, values=values, state="readonly", width=40)
        to_combo.grid(row=2, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="转换金额").grid(row=3, column=0, sticky="w", pady=4)
        amount_entry = ttk.Entry(frame, textvariable=self.amount_var, width=43)
        amount_entry.grid(row=3, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="备注").grid(row=4, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.note_var, width=43).grid(row=4, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text="仅支持相同币种资产之间直接转换。", foreground="#64748b").grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )

        if selected_asset_id:
            for label, asset_id in self.asset_options.items():
                if asset_id == selected_asset_id:
                    self.from_var.set(label)
                    break
        if not self.from_var.get() and values:
            self.from_var.set(values[0])
        if len(values) > 1:
            self.to_var.set(next((label for label in values if label != self.from_var.get()), values[0]))
        elif values:
            self.to_var.set(values[0])

        actions = ttk.Frame(frame)
        actions.grid(row=6, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(actions, text="取消", command=self.destroy).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="保存", style="Accent.TButton", command=self._save).grid(row=0, column=1)

        self.transient(parent)
        self.grab_set()
        self.wait_visibility()
        amount_entry.focus_set()

    def _save(self) -> None:
        self.result = {
            "from_asset_id": self.asset_options.get(self.from_var.get(), ""),
            "to_asset_id": self.asset_options.get(self.to_var.get(), ""),
            "amount": self.amount_var.get(),
            "note": self.note_var.get(),
        }
        self.destroy()


class TagDialog(tk.Toplevel):
    def __init__(self, parent: tk.Widget, store: MoneyStore) -> None:
        super().__init__(parent)
        self.title("新增标签")
        self.resizable(False, False)
        self.result: dict[str, str] | None = None
        self.store = store

        self.category_label_var = tk.StringVar(value="资产类型")
        self.parent_asset_type_var = tk.StringVar()
        self.name_var = tk.StringVar()

        self._build(parent)

    def _build(self, parent: tk.Widget) -> None:
        frame = ttk.Frame(self, padding=18, style="Panel.TFrame")
        frame.grid(row=0, column=0, sticky="nsew")
        ttk.Label(frame, text="新增自定义标签", style="DialogTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12)
        )
        ttk.Label(frame, text="标签类别").grid(row=1, column=0, sticky="w", pady=4)
        category = ttk.Combobox(
            frame,
            textvariable=self.category_label_var,
            values=list(CATEGORY_OPTIONS),
            state="readonly",
            width=31,
        )
        category.grid(row=1, column=1, sticky="ew", pady=4)
        category.bind("<<ComboboxSelected>>", self._refresh_parent_state)

        ttk.Label(frame, text="上级资产类型").grid(row=2, column=0, sticky="w", pady=4)
        self.parent_combo = ttk.Combobox(
            frame,
            textvariable=self.parent_asset_type_var,
            values=[""] + [tag.name for tag in self.store.root_tags_by_category(ASSET_TYPE)],
            width=31,
        )
        self.parent_combo.grid(row=2, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text="标签名称").grid(row=3, column=0, sticky="w", pady=4)
        self.name_entry = ttk.Entry(frame, textvariable=self.name_var, width=34)
        self.name_entry.grid(row=3, column=1, sticky="ew", pady=4)

        hint = "上级资产类型留空时新增一级类型；选择上级时新增二级类型；币种标签会自动规范化。"
        ttk.Label(frame, text=hint, foreground="#64748b").grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))

        actions = ttk.Frame(frame)
        actions.grid(row=5, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(actions, text="取消", command=self.destroy).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="保存", style="Accent.TButton", command=self._save).grid(row=0, column=1)

        self._refresh_parent_state()
        self.transient(parent)
        self.grab_set()
        self.wait_visibility()
        self.name_entry.focus_set()

    def _refresh_parent_state(self, _event: tk.Event[tk.Widget] | None = None) -> None:
        if CATEGORY_OPTIONS[self.category_label_var.get()] == ASSET_TYPE:
            self.parent_combo.configure(state="normal")
        else:
            self.parent_asset_type_var.set("")
            self.parent_combo.configure(state="disabled")

    def _save(self) -> None:
        self.result = {
            "category": CATEGORY_OPTIONS[self.category_label_var.get()],
            "parent_asset_type": self.parent_asset_type_var.get(),
            "name": self.name_var.get(),
        }
        self.destroy()


class PieChartWindow(tk.Toplevel):
    COLORS = [
        "#256d63",
        "#d97706",
        "#3b82f6",
        "#be123c",
        "#7c3aed",
        "#059669",
        "#475569",
        "#ea580c",
    ]

    CURRENCY_OPTIONS = {
        "人民币 CNY": "CNY",
        "英镑 GBP": "GBP",
        "实体黄金 克": "GOLD_GRAM",
    }

    UNIT_LABELS = {
        "CNY": "¥",
        "GBP": "£",
        "GOLD_GRAM": "g",
    }

    def __init__(self, parent: tk.Widget, title: str, totals_provider, items_provider) -> None:
        super().__init__(parent)
        self.title(title)
        self.geometry("720x520")
        self.minsize(640, 460)
        self.configure(bg="#eef2f7")
        self.totals_provider = totals_provider
        self.items_provider = items_provider
        self.currency_var = tk.StringVar(value="人民币 CNY")
        self.totals: dict[str, Decimal] = {}
        self.items: dict[str, list[tuple[str, Decimal]]] = {}

        frame = ttk.Frame(self, padding=16, style="App.TFrame")
        frame.pack(fill="both", expand=True)

        header = ttk.Frame(frame, style="App.TFrame")
        header.pack(fill="x", pady=(0, 12))
        ttk.Label(header, text=title, style="Section.TLabel").pack(side="left")
        currency = ttk.Combobox(
            header,
            textvariable=self.currency_var,
            values=list(self.CURRENCY_OPTIONS),
            state="readonly",
            width=16,
        )
        currency.pack(side="right")
        currency.bind("<<ComboboxSelected>>", lambda _event: self._draw())

        self.canvas = tk.Canvas(frame, bg="#ffffff", highlightthickness=0, height=280)
        self.canvas.pack(fill="x")
        self.canvas.bind("<Configure>", lambda _event: self._draw())
        self.detail_tree = ttk.Treeview(frame, columns=("value", "percent"), show="tree headings")
        self.detail_tree.heading("#0", text="分组 / 资产")
        self.detail_tree.heading("value", text="金额")
        self.detail_tree.heading("percent", text="占比")
        self.detail_tree.column("#0", width=260, anchor="w")
        self.detail_tree.column("value", width=130, anchor="e")
        self.detail_tree.column("percent", width=90, anchor="e")
        self.detail_tree.pack(fill="both", expand=True, pady=(10, 0))
        self.transient(parent)

    def _draw(self) -> None:
        self.canvas.delete("all")
        currency_key = self.CURRENCY_OPTIONS[self.currency_var.get()]
        self.totals = {key: value for key, value in self.totals_provider(currency_key).items() if value > 0}
        self.items = self.items_provider(currency_key)
        self._refresh_detail_tree(currency_key)
        if not self.totals:
            self.canvas.create_text(320, 220, text="没有可展示的数据", fill="#64748b", font=("Microsoft YaHei UI", 12))
            return

        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        diameter = min(width * 0.42, height * 0.72)
        x0 = 36
        y0 = (height - diameter) / 2
        x1 = x0 + diameter
        y1 = y0 + diameter

        total = sum(self.totals.values(), Decimal("0"))
        start = 90.0
        legend_x = x1 + 36
        legend_y = max(24, y0)
        row_height = 28

        for index, (label, value) in enumerate(sorted(self.totals.items(), key=lambda item: item[1], reverse=True)):
            percent = (value / total * Decimal("100")) if total else Decimal("0")
            extent = float(percent / Decimal("100") * Decimal("360"))
            color = self.COLORS[index % len(self.COLORS)]
            self.canvas.create_arc(x0, y0, x1, y1, start=start, extent=extent, fill=color, outline="#ffffff", width=2)
            start += extent

            y = legend_y + index * row_height
            self.canvas.create_rectangle(legend_x, y + 5, legend_x + 14, y + 19, fill=color, outline=color)
            unit = self.UNIT_LABELS[currency_key]
            value_text = f"{unit}{value.quantize(Decimal('0.01'))}" if currency_key != "GOLD_GRAM" else f"{value.quantize(Decimal('0.0001'))}{unit}"
            text = f"{label}  {percent.quantize(Decimal('0.01'))}%  {value_text}"
            self.canvas.create_text(legend_x + 24, y + 12, text=text, anchor="w", fill="#1f2937", font=("Microsoft YaHei UI", 10))

    def _format_value(self, value: Decimal, currency_key: str) -> str:
        unit = self.UNIT_LABELS[currency_key]
        if currency_key == "GOLD_GRAM":
            return f"{value.quantize(Decimal('0.0001'))}{unit}"
        return f"{unit}{value.quantize(Decimal('0.01'))}"

    def _refresh_detail_tree(self, currency_key: str) -> None:
        self.detail_tree.delete(*self.detail_tree.get_children())
        total = sum(self.totals.values(), Decimal("0"))
        for group, value in sorted(self.totals.items(), key=lambda item: item[1], reverse=True):
            percent = (value / total * Decimal("100")) if total else Decimal("0")
            parent_id = self.detail_tree.insert(
                "",
                "end",
                text=group,
                values=(self._format_value(value, currency_key), f"{percent.quantize(Decimal('0.01'))}%"),
                open=False,
            )
            for asset_name, asset_value in sorted(self.items.get(group, []), key=lambda item: item[1], reverse=True):
                asset_percent = (asset_value / total * Decimal("100")) if total else Decimal("0")
                self.detail_tree.insert(
                    parent_id,
                    "end",
                    text=asset_name,
                    values=(self._format_value(asset_value, currency_key), f"{asset_percent.quantize(Decimal('0.01'))}%"),
                )


class MoneyApp(tk.Tk):
    def __init__(self, data_path: Path = DEFAULT_DATA_PATH) -> None:
        super().__init__()
        self.title("myMoney 资产管理")
        self.geometry("1120x700")
        self.minsize(940, 580)
        self.data_path = data_path
        self.store = MoneyStore.load(self.data_path)

        self.selected_asset_id: str | None = None
        self.summary_var = tk.StringVar()
        self.selected_var = tk.StringVar(value="请选择一项资产查看流水")
        self.status_var = tk.StringVar(value=f"数据文件：{self.data_path}")
        self.filter_category_var = tk.StringVar(value=ALL_FILTER_CATEGORIES)
        self.filter_tag_var = tk.StringVar(value=ALL_FILTER_TAGS)
        self.filter_logic_var = tk.StringVar(value="与")
        self.filter_tag_options: dict[str, str | None] = {}
        self.selected_filter_tag_ids: list[str] = []
        self.pie_injection_var = tk.StringVar()
        self.pie_no_sell_var = tk.BooleanVar(value=False)
        self.pie_status_var = tk.StringVar(value="按当前筛选结果设置目标配比，金额以人民币等价值计算。")
        self.pie_target_vars: dict[str, tk.StringVar] = {}
        self.sort_column = "updated_at"
        self.sort_reverse = True

        self._configure_style()
        self._build_menu()
        self._build_layout()
        self._refresh_all()

    def _configure_style(self) -> None:
        self.configure(bg="#eef2f7")
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        base_font = ("Microsoft YaHei UI", 10)
        title_font = ("Microsoft YaHei UI", 18, "bold")
        section_font = ("Microsoft YaHei UI", 12, "bold")
        style.configure(".", font=base_font)
        style.configure("App.TFrame", background="#eef2f7")
        style.configure("Panel.TFrame", background="#ffffff")
        style.configure("Hero.TFrame", background="#1f4f46")
        style.configure("Title.TLabel", font=title_font, foreground="#ffffff", background="#1f4f46")
        style.configure("Subtitle.TLabel", foreground="#dcebe7", background="#1f4f46")
        style.configure("Section.TLabel", font=section_font, foreground="#1f2937", background="#eef2f7")
        style.configure("DialogTitle.TLabel", font=section_font)
        style.configure("Status.TLabel", foreground="#64748b", background="#eef2f7")
        style.configure("Summary.TLabel", font=("Microsoft YaHei UI", 11, "bold"), foreground="#ffffff", background="#1f4f46")
        style.configure("Accent.TButton", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Treeview", rowheight=30, font=base_font, fieldbackground="#ffffff", background="#ffffff")
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 10, "bold"))
        style.map("Treeview", background=[("selected", "#256d63")], foreground=[("selected", "#ffffff")])

    def _build_menu(self) -> None:
        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="打开数据文件...", command=self.open_data_file)
        file_menu.add_command(label="导出迁移包...", command=self.export_data)
        file_menu.add_command(label="导入迁移包...", command=self.import_data)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.destroy)
        menu.add_cascade(label="文件", menu=file_menu)
        self.config(menu=menu)

    def _build_layout(self) -> None:
        root = ttk.Frame(self, padding=14, style="App.TFrame")
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=3)
        root.columnconfigure(1, weight=2)
        root.rowconfigure(3, weight=1)

        header = ttk.Frame(root, padding=18, style="Hero.TFrame")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="myMoney 资产管理", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self.summary_var, style="Summary.TLabel").grid(row=0, column=1, sticky="e")
        ttk.Label(header, text="按一级/二级资产类型和存放方式管理资产，每次变动都会留下备注流水。", style="Subtitle.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )

        toolbar = ttk.Frame(root, style="App.TFrame")
        toolbar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        toolbar.columnconfigure(0, weight=1)
        ttk.Label(toolbar, text="资产列表", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(toolbar, text="新增资产", style="Accent.TButton", command=self.add_asset).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(toolbar, text="编辑资产", command=self.edit_asset).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(toolbar, text="记录变动", command=self.record_change).grid(row=0, column=3, padx=(0, 8))
        ttk.Button(toolbar, text="资产转换", command=self.transfer_asset).grid(row=0, column=4, padx=(0, 8))
        ttk.Button(toolbar, text="废除资产", command=self.deprecate_asset).grid(row=0, column=5, padx=(0, 8))
        ttk.Button(toolbar, text="更新等价值", command=self.update_equivalent_values).grid(row=0, column=6, padx=(0, 8))
        ttk.Button(toolbar, text="存放配比", command=self.show_storage_allocation).grid(row=0, column=7, padx=(0, 8))
        ttk.Button(toolbar, text="类型配比", command=self.show_asset_type_allocation).grid(row=0, column=8)

        filter_bar = ttk.Frame(root, padding=(0, 0, 0, 10), style="App.TFrame")
        filter_bar.grid(row=2, column=0, columnspan=2, sticky="ew")
        filter_bar.columnconfigure(6, weight=1)
        ttk.Label(filter_bar, text="按标签显示").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Label(filter_bar, text="逻辑").grid(row=0, column=1, sticky="w", padx=(0, 6))
        logic_filter = ttk.Combobox(
            filter_bar,
            textvariable=self.filter_logic_var,
            values=list(FILTER_LOGIC_OPTIONS),
            state="readonly",
            width=8,
        )
        logic_filter.grid(row=0, column=2, sticky="w", padx=(0, 8))
        logic_filter.bind("<<ComboboxSelected>>", self._apply_asset_filter)
        category_filter = ttk.Combobox(
            filter_bar,
            textvariable=self.filter_category_var,
            values=[ALL_FILTER_CATEGORIES, *CATEGORY_OPTIONS.keys()],
            state="readonly",
            width=14,
        )
        category_filter.grid(row=0, column=3, sticky="w", padx=(0, 8))
        category_filter.bind("<<ComboboxSelected>>", self._on_filter_category_changed)
        self.filter_tag_combo = ttk.Combobox(
            filter_bar,
            textvariable=self.filter_tag_var,
            values=[ALL_FILTER_TAGS],
            state="readonly",
            width=28,
        )
        self.filter_tag_combo.grid(row=0, column=4, sticky="w", padx=(0, 8))
        ttk.Button(filter_bar, text="加入条件", command=self.add_filter_tag).grid(row=0, column=5, sticky="w", padx=(0, 8))
        ttk.Button(filter_bar, text="移除条件", command=self.remove_selected_filter_tag).grid(row=0, column=6, sticky="w", padx=(0, 8))
        ttk.Button(filter_bar, text="清空限定", command=self.clear_asset_filter).grid(row=0, column=7, sticky="w")
        self.filter_tag_list = tk.Listbox(
            filter_bar,
            height=2,
            activestyle="none",
            exportselection=False,
            selectmode=tk.EXTENDED,
            font=("Microsoft YaHei UI", 9),
        )
        self.filter_tag_list.grid(row=1, column=0, columnspan=8, sticky="ew", pady=(8, 0))

        self.asset_tree = ttk.Treeview(
            root,
            columns=("name", "value", "currency", "equivalent", "share", "asset_type", "storage_type", "updated_at"),
            show="headings",
            selectmode="browse",
        )
        for key, label, width in (
            ("name", "资产名称", 190),
            ("value", "余额", 120),
            ("currency", "币种", 80),
            ("equivalent", "等价值其他币种", 230),
            ("share", "占总资产", 90),
            ("asset_type", "资产类型", 170),
            ("storage_type", "存放方式", 130),
            ("updated_at", "最后更改时间", 180),
        ):
            self.asset_tree.heading(key, text=label, command=lambda column=key: self._sort_by_column(column))
            self.asset_tree.column(key, width=width, anchor="w")
        self.asset_tree.grid(row=3, column=0, sticky="nsew", padx=(0, 12))
        self.asset_tree.bind("<<TreeviewSelect>>", self._on_asset_selected)

        right = ttk.Notebook(root)
        right.grid(row=3, column=1, sticky="nsew")

        history_frame = ttk.Frame(right, padding=8)
        tag_frame = ttk.Frame(right, padding=8)
        pie_frame = ttk.Frame(right, padding=8)
        deprecated_frame = ttk.Frame(right, padding=8)
        right.add(history_frame, text="变动流水")
        right.add(tag_frame, text="标签")
        right.add(pie_frame, text="补pie")
        right.add(deprecated_frame, text="已废除")

        history_frame.rowconfigure(1, weight=1)
        history_frame.columnconfigure(0, weight=1)
        ttk.Label(history_frame, textvariable=self.selected_var).grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.history_tree = ttk.Treeview(
            history_frame,
            columns=("created_at", "delta", "value_after", "note"),
            show="headings",
        )
        for key, label, width in (
            ("created_at", "时间", 150),
            ("delta", "变动", 80),
            ("value_after", "变动后", 90),
            ("note", "备注", 190),
        ):
            self.history_tree.heading(key, text=label)
            self.history_tree.column(key, width=width, anchor="w")
        self.history_tree.grid(row=1, column=0, sticky="nsew")

        tag_header = ttk.Frame(tag_frame)
        tag_header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        tag_header.columnconfigure(0, weight=1)
        ttk.Label(tag_header, text="自定义标签").grid(row=0, column=0, sticky="w")
        ttk.Button(tag_header, text="新增标签", command=self.add_tag).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(tag_header, text="清理未用标签", command=self.prune_unused_tags).grid(row=0, column=2)

        tag_frame.rowconfigure(1, weight=1)
        tag_frame.columnconfigure(0, weight=1)
        self.tag_tree = ttk.Treeview(tag_frame, columns=("category", "name"), show="headings")
        self.tag_tree.heading("category", text="分类")
        self.tag_tree.heading("name", text="标签名称")
        self.tag_tree.column("category", width=120)
        self.tag_tree.column("name", width=220)
        self.tag_tree.grid(row=1, column=0, sticky="nsew")

        pie_frame.rowconfigure(2, weight=1)
        pie_frame.rowconfigure(4, weight=1)
        pie_frame.columnconfigure(0, weight=1)
        pie_controls = ttk.Frame(pie_frame)
        pie_controls.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        pie_controls.columnconfigure(5, weight=1)
        ttk.Label(pie_controls, text="新注资金额(CNY)").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Entry(pie_controls, textvariable=self.pie_injection_var, width=16).grid(row=0, column=1, sticky="w", padx=(0, 8))
        ttk.Button(pie_controls, text="当前配比", command=self.fill_pie_targets_current).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(pie_controls, text="平均目标", command=self.fill_pie_targets_equal).grid(row=0, column=3, padx=(0, 8))
        ttk.Button(pie_controls, text="计算分配", style="Accent.TButton", command=self.calculate_pie_top_up).grid(row=0, column=4)
        ttk.Checkbutton(pie_controls, text="非卖出再分配", variable=self.pie_no_sell_var).grid(
            row=1, column=0, columnspan=5, sticky="w", pady=(8, 0)
        )
        ttk.Label(pie_frame, textvariable=self.pie_status_var, foreground="#64748b").grid(row=1, column=0, sticky="ew", pady=(0, 6))
        self.pie_target_canvas = tk.Canvas(pie_frame, height=150, bg="#ffffff", highlightthickness=0)
        self.pie_target_canvas.grid(row=2, column=0, sticky="nsew")
        pie_target_scroll = ttk.Scrollbar(pie_frame, orient="vertical", command=self.pie_target_canvas.yview)
        pie_target_scroll.grid(row=2, column=1, sticky="ns")
        self.pie_target_canvas.configure(yscrollcommand=pie_target_scroll.set)
        self.pie_target_inner = ttk.Frame(self.pie_target_canvas, padding=6)
        self.pie_target_window = self.pie_target_canvas.create_window((0, 0), window=self.pie_target_inner, anchor="nw")
        self.pie_target_canvas.bind("<Configure>", self._resize_pie_target_canvas)
        self.pie_target_inner.bind(
            "<Configure>",
            lambda _event: self.pie_target_canvas.configure(scrollregion=self.pie_target_canvas.bbox("all")),
        )
        self.pie_result_tree = ttk.Treeview(
            pie_frame,
            columns=("current", "target", "suggested", "final", "final_percent", "note"),
            show="tree headings",
        )
        self.pie_result_tree.heading("#0", text="资产")
        for key, label, width in (
            ("current", "当前CNY", 86),
            ("target", "目标%", 68),
            ("suggested", "建议注资", 86),
            ("final", "注资后CNY", 96),
            ("final_percent", "注资后%", 78),
            ("note", "说明", 110),
        ):
            self.pie_result_tree.heading(key, text=label)
            self.pie_result_tree.column(key, width=width, anchor="w")
        self.pie_result_tree.grid(row=4, column=0, sticky="nsew", pady=(8, 0))

        deprecated_header = ttk.Frame(deprecated_frame)
        deprecated_header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        deprecated_header.columnconfigure(0, weight=1)
        ttk.Label(deprecated_header, text="已废除资产").grid(row=0, column=0, sticky="w")
        ttk.Button(deprecated_header, text="恢复资产", command=self.restore_asset).grid(row=0, column=1)

        deprecated_frame.rowconfigure(1, weight=1)
        deprecated_frame.columnconfigure(0, weight=1)
        self.deprecated_tree = ttk.Treeview(
            deprecated_frame,
            columns=("value", "currency", "asset_type", "storage_type", "deprecated_at"),
            show="tree headings",
            selectmode="browse",
        )
        self.deprecated_tree.heading("#0", text="资产名称")
        for key, label, width in (
            ("value", "余额", 80),
            ("currency", "币种", 70),
            ("asset_type", "资产类型", 120),
            ("storage_type", "存放方式", 100),
            ("deprecated_at", "废除时间", 160),
        ):
            self.deprecated_tree.heading(key, text=label)
            self.deprecated_tree.column(key, width=width, anchor="w")
        self.deprecated_tree.grid(row=1, column=0, sticky="nsew")

        ttk.Label(root, textvariable=self.status_var, style="Status.TLabel").grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(10, 0)
        )

    def _refresh_all(self) -> None:
        self._refresh_summary()
        self._refresh_filter_tags()
        self._refresh_assets()
        self._refresh_pie_targets()
        self._refresh_deprecated_assets()
        self._refresh_tags()
        self._refresh_history()

    def _refresh_summary(self) -> None:
        totals: dict[str, object] = {}
        for asset in self.store.active_assets():
            totals[asset.currency] = totals.get(asset.currency, 0) + asset.value
        if totals:
            total_text = " / ".join(f"{value} {currency}" for currency, value in sorted(totals.items()))
        else:
            total_text = "暂无资产"
        self.summary_var.set(f"{len(self.store.assets)} 项资产    {total_text}")

    def _refresh_filter_tags(self, reset: bool = False) -> None:
        current_tag_id = None if reset else self.filter_tag_options.get(self.filter_tag_var.get())
        self.selected_filter_tag_ids = [tag_id for tag_id in self.selected_filter_tag_ids if tag_id in self.store.tags]
        category = CATEGORY_OPTIONS.get(self.filter_category_var.get())
        if category:
            tags = self.store.tags_by_category(category)
            labels = [self.store.tag_display_name(tag) for tag in tags]
        else:
            tags = sorted(
                self.store.tags.values(),
                key=lambda tag: (category_label(tag.category), self.store.tag_display_name(tag)),
            )
            labels = [f"{category_label(tag.category)}：{self.store.tag_display_name(tag)}" for tag in tags]

        self.filter_tag_options = {ALL_FILTER_TAGS: None}
        self.filter_tag_options.update({label: tag.id for label, tag in zip(labels, tags)})
        values = list(self.filter_tag_options)
        self.filter_tag_combo.configure(values=values)

        if current_tag_id:
            for label, tag_id in self.filter_tag_options.items():
                if tag_id == current_tag_id:
                    self.filter_tag_var.set(label)
                    break
            else:
                self.filter_tag_var.set(ALL_FILTER_TAGS)
        elif self.filter_tag_var.get() not in self.filter_tag_options:
            self.filter_tag_var.set(ALL_FILTER_TAGS)
        self._refresh_filter_tag_list()

    def _filter_tag_label(self, tag: Tag) -> str:
        return f"{category_label(tag.category)}：{self.store.tag_display_name(tag)}"

    def _refresh_filter_tag_list(self) -> None:
        self.filter_tag_list.delete(0, tk.END)
        for tag_id in self.selected_filter_tag_ids:
            tag = self.store.tags.get(tag_id)
            if tag:
                self.filter_tag_list.insert(tk.END, self._filter_tag_label(tag))

    def _selected_filter_tag(self) -> Tag | None:
        tag_id = self.filter_tag_options.get(self.filter_tag_var.get())
        return self.store.tags.get(tag_id) if tag_id else None

    def _asset_matches_tag(self, asset: Asset, tag: Tag) -> bool:
        if tag.id in asset.tag_ids:
            return True
        return any(
            asset_tag.parent_id == tag.id
            for asset_tag in self.store.asset_tags(asset)
        )

    def _asset_matches_filter_tags(self, asset: Asset) -> bool:
        tags = [self.store.tags[tag_id] for tag_id in self.selected_filter_tag_ids if tag_id in self.store.tags]
        if not tags:
            return True
        matches = [self._asset_matches_tag(asset, tag) for tag in tags]
        logic = self.filter_logic_var.get()
        if logic == "或":
            return any(matches)
        if logic == "非与":
            return not all(matches)
        if logic == "非或":
            return not any(matches)
        return all(matches)

    def _filtered_assets(self) -> list[Asset]:
        return [asset for asset in self.store.active_assets() if self._asset_matches_filter_tags(asset)]

    def _on_filter_category_changed(self, _event: tk.Event[tk.Widget] | None = None) -> None:
        self._refresh_filter_tags(reset=True)

    def add_filter_tag(self) -> None:
        tag = self._selected_filter_tag()
        if tag is None:
            return
        if tag.id not in self.selected_filter_tag_ids:
            self.selected_filter_tag_ids.append(tag.id)
        self._refresh_filter_tag_list()
        self._apply_asset_filter()

    def remove_selected_filter_tag(self) -> None:
        selected_indexes = list(self.filter_tag_list.curselection())
        if not selected_indexes:
            return
        for index in sorted(selected_indexes, reverse=True):
            if 0 <= index < len(self.selected_filter_tag_ids):
                del self.selected_filter_tag_ids[index]
        self._refresh_filter_tag_list()
        self._apply_asset_filter()

    def _apply_asset_filter(self, _event: tk.Event[tk.Widget] | None = None) -> None:
        visible_ids = {asset.id for asset in self._filtered_assets()}
        if self.selected_asset_id not in visible_ids:
            self.selected_asset_id = None
        self._refresh_assets()
        self._refresh_pie_targets()
        self._refresh_history()

    def clear_asset_filter(self) -> None:
        self.filter_category_var.set(ALL_FILTER_CATEGORIES)
        self.filter_tag_var.set(ALL_FILTER_TAGS)
        self.filter_logic_var.set("与")
        self.selected_filter_tag_ids.clear()
        self._refresh_filter_tags(reset=True)
        self._apply_asset_filter()

    def _refresh_assets(self) -> None:
        self.asset_tree.delete(*self.asset_tree.get_children())
        for asset in self._sorted_assets():
            self.asset_tree.insert(
                "",
                "end",
                iid=asset.id,
                values=(
                    asset.name,
                    str(asset.value),
                    asset.currency,
                    self.store.equivalent_display(asset),
                    self.store.asset_share_display(asset),
                    self.store.asset_type_display(asset),
                    self.store.storage_type_name(asset),
                    asset.updated_at,
                ),
            )

    def _sorted_assets(self) -> list[Asset]:
        assets = self._filtered_assets()
        sorters = {
            "name": lambda asset: asset.name.casefold(),
            "value": lambda asset: asset.value,
            "currency": lambda asset: (asset.currency, asset.name.casefold()),
            "equivalent": lambda asset: self._sort_equivalent_value(asset),
            "share": lambda asset: self.store.asset_share_percent(asset) or Decimal("-1"),
            "asset_type": lambda asset: (self.store.asset_type_display(asset), asset.name.casefold()),
            "storage_type": lambda asset: (self.store.storage_type_name(asset), asset.name.casefold()),
            "updated_at": lambda asset: asset.updated_at,
        }
        sorter = sorters.get(self.sort_column, sorters["updated_at"])
        return sorted(assets, key=sorter, reverse=self.sort_reverse)

    def _sort_equivalent_value(self, asset: Asset) -> Decimal:
        try:
            return self.store.asset_equivalent_value(asset, "CNY")
        except ValueError:
            return Decimal("-1")

    def _sort_by_column(self, column: str) -> None:
        if self.sort_column == column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column
            self.sort_reverse = column in {"value", "equivalent", "share", "updated_at"}
        self._refresh_assets()

    def _resize_pie_target_canvas(self, event: tk.Event[tk.Widget]) -> None:
        self.pie_target_canvas.itemconfigure(self.pie_target_window, width=event.width)

    def _asset_cny_value_or_none(self, asset: Asset) -> Decimal | None:
        try:
            return self.store.asset_equivalent_value(asset, "CNY")
        except ValueError:
            return None

    def _format_cny(self, value: Decimal) -> str:
        return f"¥{value.quantize(Decimal('0.01'))}"

    def _refresh_pie_targets(self) -> None:
        for child in self.pie_target_inner.winfo_children():
            child.destroy()
        self.pie_result_tree.delete(*self.pie_result_tree.get_children())

        assets = self._filtered_assets()
        current_values = {asset.id: self._asset_cny_value_or_none(asset) for asset in assets}
        available_ids = {asset.id for asset in assets}
        self.pie_target_vars = {
            asset_id: variable
            for asset_id, variable in self.pie_target_vars.items()
            if asset_id in available_ids
        }

        ttk.Label(self.pie_target_inner, text="资产").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Label(self.pie_target_inner, text="当前CNY").grid(row=0, column=1, sticky="w", padx=(0, 8))
        ttk.Label(self.pie_target_inner, text="当前%").grid(row=0, column=2, sticky="w", padx=(0, 8))
        ttk.Label(self.pie_target_inner, text="目标%").grid(row=0, column=3, sticky="w")

        if not assets:
            ttk.Label(self.pie_target_inner, text="当前筛选结果没有资产。", foreground="#64748b").grid(
                row=1, column=0, columnspan=4, sticky="w", pady=(8, 0)
            )
            self.pie_status_var.set("当前筛选结果没有资产。")
            return

        known_values = [value for value in current_values.values() if value is not None]
        total = sum(known_values, Decimal("0")) if len(known_values) == len(assets) else None
        for row, asset in enumerate(assets, start=1):
            value = current_values[asset.id]
            current_text = "未更新" if value is None else self._format_cny(value)
            if value is None or total is None or total == 0:
                percent_text = "-"
            else:
                percent_text = f"{(value / total * Decimal('100')).quantize(Decimal('0.01'))}%"
            if asset.id not in self.pie_target_vars:
                default_percent = "" if value is None or total is None or total == 0 else str((value / total * Decimal("100")).quantize(Decimal("0.01")))
                self.pie_target_vars[asset.id] = tk.StringVar(value=default_percent)
            ttk.Label(self.pie_target_inner, text=asset.name).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
            ttk.Label(self.pie_target_inner, text=current_text).grid(row=row, column=1, sticky="w", padx=(0, 8), pady=2)
            ttk.Label(self.pie_target_inner, text=percent_text).grid(row=row, column=2, sticky="w", padx=(0, 8), pady=2)
            ttk.Entry(self.pie_target_inner, textvariable=self.pie_target_vars[asset.id], width=10).grid(
                row=row, column=3, sticky="w", pady=2
            )
        self.pie_status_var.set("按当前筛选结果设置目标配比，金额以人民币等价值计算。")

    def fill_pie_targets_current(self) -> None:
        assets = self._filtered_assets()
        values = {asset.id: self._asset_cny_value_or_none(asset) for asset in assets}
        if any(value is None for value in values.values()):
            messagebox.showerror("无法载入当前配比", "请先点击“更新等价值”。", parent=self)
            return
        total = sum((value for value in values.values() if value is not None), Decimal("0"))
        if total <= 0:
            return
        for asset in assets:
            value = values[asset.id] or Decimal("0")
            self.pie_target_vars.setdefault(asset.id, tk.StringVar()).set(str((value / total * Decimal("100")).quantize(Decimal("0.01"))))

    def fill_pie_targets_equal(self) -> None:
        assets = self._filtered_assets()
        if not assets:
            return
        equal = Decimal("100") / Decimal(len(assets))
        for index, asset in enumerate(assets):
            percent = equal
            if index == len(assets) - 1:
                assigned = equal.quantize(Decimal("0.01")) * Decimal(len(assets) - 1)
                percent = Decimal("100") - assigned
            self.pie_target_vars.setdefault(asset.id, tk.StringVar()).set(str(percent.quantize(Decimal("0.01"))))

    def _parse_pie_inputs(self) -> tuple[list[Asset], dict[str, Decimal], dict[str, Decimal], Decimal] | None:
        assets = self._filtered_assets()
        if not assets:
            messagebox.showinfo("无法计算", "当前筛选结果没有资产。", parent=self)
            return None
        try:
            injection = Decimal(self.pie_injection_var.get().strip())
        except Exception:
            messagebox.showerror("金额无效", "请输入有效的新注资金额。", parent=self)
            return None

        current_values: dict[str, Decimal] = {}
        targets: dict[str, Decimal] = {}
        for asset in assets:
            value = self._asset_cny_value_or_none(asset)
            if value is None:
                messagebox.showerror("无法计算", "请先点击“更新等价值”，确保筛选出的资产都有人民币等价值。", parent=self)
                return None
            current_values[asset.id] = value
            try:
                target = Decimal(self.pie_target_vars[asset.id].get().strip())
            except Exception:
                messagebox.showerror("目标比例无效", f"请检查「{asset.name}」的目标比例。", parent=self)
                return None
            targets[asset.id] = target

        target_sum = sum(targets.values(), Decimal("0"))
        if target_sum <= 0:
            messagebox.showerror("目标比例无效", "目标比例合计必须大于 0。", parent=self)
            return None
        warnings = []
        if injection <= 0:
            warnings.append(
                "新注资金额为 0 或负数，本次将按重配置/卖出计算；结果中的负数表示需要卖出或转出。"
            )
        if any(target < 0 for target in targets.values()):
            warnings.append(
                "目标百分比包含负数，本次将按做空目标计算；结果可能出现负目标占比或卖出/转出建议。"
            )
        if abs(target_sum - Decimal("100")) > Decimal("0.01"):
            warnings.append(
                f"目标比例合计为 {target_sum.quantize(Decimal('0.01'))}%，将自动归一化后计算。"
            )
        if warnings and not messagebox.askyesno("确认补pie计算", "\n\n".join(warnings) + "\n\n确认继续计算吗？", parent=self):
            return None
        return assets, current_values, targets, injection

    def calculate_pie_top_up(self) -> None:
        parsed = self._parse_pie_inputs()
        if parsed is None:
            return
        assets, current_values, targets, injection = parsed
        self.pie_result_tree.delete(*self.pie_result_tree.get_children())

        current_total = sum(current_values.values(), Decimal("0"))
        final_total = current_total + injection
        target_sum = sum(targets.values(), Decimal("0"))
        no_sell_mode = self.pie_no_sell_var.get()
        if no_sell_mode and injection < 0:
            messagebox.showerror("无法计算", "“非卖出再分配”模式下，新注资金额不能为负数。", parent=self)
            return
        if final_total < 0:
            messagebox.showerror(
                "无法计算",
                f"卖出金额不能超过当前筛选资产总额。当前总额为 {self._format_cny(current_total)}。",
                parent=self,
            )
            return

        suggestions: dict[str, Decimal] = {}
        target_ratios = {asset.id: targets[asset.id] / target_sum for asset in assets}
        if no_sell_mode:
            desired_values = {asset.id: final_total * target_ratios[asset.id] for asset in assets}
            positive_gaps = {
                asset.id: desired_values[asset.id] - current_values[asset.id]
                for asset in assets
                if desired_values[asset.id] > current_values[asset.id]
            }
            positive_gap_total = sum(positive_gaps.values(), Decimal("0"))
            if injection == 0:
                suggestions = {asset.id: Decimal("0") for asset in assets}
            elif positive_gap_total > 0:
                suggestions = {
                    asset.id: injection * positive_gaps.get(asset.id, Decimal("0")) / positive_gap_total
                    for asset in assets
                }
            else:
                best_asset = max(assets, key=lambda asset: target_ratios[asset.id])
                suggestions = {asset.id: Decimal("0") for asset in assets}
                suggestions[best_asset.id] = injection
        else:
            for asset in assets:
                desired_value = final_total * target_ratios[asset.id]
                suggestions[asset.id] = desired_value - current_values[asset.id]

        for asset in assets:
            suggested = suggestions[asset.id]
            final_value = current_values[asset.id] + suggested
            final_percent = (final_value / final_total * Decimal("100")) if final_total > 0 else Decimal("0")
            normalized_target = target_ratios[asset.id] * Decimal("100")
            if suggested > 0:
                note = "买入/注入"
            elif suggested < 0:
                note = "卖出/转出"
            elif no_sell_mode and injection > 0:
                note = "不买入"
            else:
                note = "不调整"
            self.pie_result_tree.insert(
                "",
                "end",
                text=asset.name,
                values=(
                    self._format_cny(current_values[asset.id]),
                    f"{normalized_target.quantize(Decimal('0.01'))}%",
                    self._format_cny(suggested),
                    self._format_cny(final_value),
                    f"{final_percent.quantize(Decimal('0.01'))}%",
                    note,
                ),
            )

        if no_sell_mode:
            self.pie_status_var.set("计算完成：非卖出再分配模式下，所有建议注资均不为负，结果为尽量靠近目标的近似方案。")
        elif injection > 0:
            self.pie_status_var.set("计算完成：正数表示买入/注入，负数表示为达成目标需要卖出/转出。")
        elif injection == 0:
            self.pie_status_var.set("计算完成：这是 0 新资金重配置方案，正数买入，负数卖出/转出。")
        else:
            self.pie_status_var.set("计算完成：这是卖出后重配置方案，负数表示卖出/转出，正数表示回补到目标资产。")

    def _refresh_tags(self) -> None:
        self.tag_tree.delete(*self.tag_tree.get_children())
        for category in (ASSET_TYPE, STORAGE_TYPE, CURRENCY_TYPE):
            for tag in self.store.tags_by_category(category):
                self.tag_tree.insert(
                    "",
                    "end",
                    iid=tag.id,
                    values=(category_label(category), self.store.tag_display_name(tag)),
                )

    def _refresh_history(self) -> None:
        self.history_tree.delete(*self.history_tree.get_children())
        if not self.selected_asset_id or self.selected_asset_id not in self.store.assets:
            self.selected_var.set("请选择一项资产查看流水")
            return
        asset = self.store.assets[self.selected_asset_id]
        self.selected_var.set(f"当前资产：{asset.name}")
        for change in self.store.asset_history(self.selected_asset_id):
            self.history_tree.insert(
                "",
                "end",
                iid=change.id,
                values=(change.created_at, str(change.delta), str(change.value_after), change.note),
            )

    def _on_asset_selected(self, _event: tk.Event[tk.Widget]) -> None:
        selection = self.asset_tree.selection()
        self.selected_asset_id = selection[0] if selection else None
        self._refresh_history()

    def _refresh_deprecated_assets(self) -> None:
        self.deprecated_tree.delete(*self.deprecated_tree.get_children())
        for asset in sorted(self.store.deprecated_assets(), key=lambda item: item.deprecated_at or "", reverse=True):
            self.deprecated_tree.insert(
                "",
                "end",
                iid=asset.id,
                text=asset.name,
                values=(
                    str(asset.value),
                    asset.currency,
                    self.store.asset_type_display(asset),
                    self.store.storage_type_name(asset),
                    asset.deprecated_at or "",
                ),
            )

    def _selected_asset_id_or_warn(self) -> str | None:
        asset_id = self.selected_asset_id
        if not asset_id:
            messagebox.showinfo("请选择资产", "请先在左侧选择一项资产。", parent=self)
            return None
        return asset_id

    def _select_visible_asset(self, asset_id: str) -> None:
        if self.asset_tree.exists(asset_id):
            self.selected_asset_id = asset_id
            self.asset_tree.selection_set(asset_id)
        else:
            self.selected_asset_id = None
        self._refresh_history()

    def add_asset(self) -> None:
        dialog = AssetDialog(self, self.store)
        self.wait_window(dialog)
        if not dialog.result:
            return
        try:
            asset = self.store.create_asset(**dialog.result)
            self._save()
        except Exception as exc:
            messagebox.showerror("无法新增资产", str(exc), parent=self)
            return
        self.selected_asset_id = asset.id
        self._refresh_all()
        self._select_visible_asset(asset.id)

    def edit_asset(self) -> None:
        asset_id = self._selected_asset_id_or_warn()
        if not asset_id:
            return
        asset = self.store.assets[asset_id]
        dialog = AssetDialog(self, self.store, asset)
        self.wait_window(dialog)
        if not dialog.result:
            return
        if not dialog.result["note"].strip():
            messagebox.showerror("需要备注", "编辑资产前请填写备注，方便之后追踪原因。", parent=self)
            return

        confirm_text = (
            "即将修改资产信息，并写入一条变动流水。\n\n"
            f"资产：{asset.name}\n"
            f"新名称：{dialog.result['name']}\n"
            f"新余额：{dialog.result['value']} {dialog.result['currency']}\n\n"
            "确认保存这次修改吗？"
        )
        if not messagebox.askyesno("确认编辑资产", confirm_text, parent=self):
            return

        try:
            self.store.update_asset(asset_id=asset_id, **dialog.result)
            self._save()
        except Exception as exc:
            messagebox.showerror("无法编辑资产", str(exc), parent=self)
            return
        self.selected_asset_id = asset_id
        self._refresh_all()
        self._select_visible_asset(asset_id)

    def add_tag(self) -> None:
        dialog = TagDialog(self, self.store)
        self.wait_window(dialog)
        if not dialog.result:
            return
        try:
            parent_id = None
            if dialog.result["category"] == ASSET_TYPE and dialog.result["parent_asset_type"].strip():
                parent = self.store.add_tag(dialog.result["parent_asset_type"], ASSET_TYPE)
                parent_id = parent.id
            tag = self.store.add_tag(dialog.result["name"], dialog.result["category"], parent_id=parent_id)
            self._save()
        except Exception as exc:
            messagebox.showerror("无法新增标签", str(exc), parent=self)
            return
        self._refresh_all()
        self.tag_tree.selection_set(tag.id)

    def transfer_asset(self) -> None:
        if len(self.store.active_assets()) < 2:
            messagebox.showinfo("资产不足", "至少需要两项资产才能进行转换。", parent=self)
            return
        dialog = TransferDialog(self, self.store, self.selected_asset_id)
        self.wait_window(dialog)
        if not dialog.result:
            return

        from_asset = self.store.assets.get(dialog.result["from_asset_id"])
        to_asset = self.store.assets.get(dialog.result["to_asset_id"])
        if not from_asset or not to_asset:
            messagebox.showerror("无法转换", "请选择有效的转出资产和转入资产。", parent=self)
            return

        confirm_text = (
            "即将执行资产转换，并分别写入两条流水。\n\n"
            f"转出：{from_asset.name}\n"
            f"转入：{to_asset.name}\n"
            f"金额：{dialog.result['amount']} {from_asset.currency}\n\n"
            "确认继续吗？"
        )
        if not messagebox.askyesno("确认资产转换", confirm_text, parent=self):
            return

        try:
            self.store.transfer_asset(**dialog.result)
            self._save()
        except Exception as exc:
            messagebox.showerror("无法转换资产", str(exc), parent=self)
            return
        self.selected_asset_id = to_asset.id
        self._refresh_all()
        self._select_visible_asset(to_asset.id)

    def deprecate_asset(self) -> None:
        asset_id = self._selected_asset_id_or_warn()
        if not asset_id:
            return
        asset = self.store.assets[asset_id]
        if asset.value != 0:
            messagebox.showerror("无法废除资产", "只有余额等于 0 的资产才能设为已废除。", parent=self)
            return
        note = self._ask_short_text("废除资产", "请输入废除备注：")
        if not note:
            return
        if not messagebox.askyesno("确认废除资产", f"确认将「{asset.name}」设为已废除吗？", parent=self):
            return
        try:
            self.store.deprecate_asset(asset_id, note)
            self._save()
        except Exception as exc:
            messagebox.showerror("无法废除资产", str(exc), parent=self)
            return
        self.selected_asset_id = None
        self._refresh_all()

    def restore_asset(self) -> None:
        selection = self.deprecated_tree.selection()
        if not selection:
            messagebox.showinfo("请选择资产", "请先在已废除列表中选择一项资产。", parent=self)
            return
        asset_id = selection[0]
        asset = self.store.assets[asset_id]
        note = self._ask_short_text("恢复资产", "请输入恢复备注：")
        if not note:
            return
        if not messagebox.askyesno("确认恢复资产", f"确认恢复「{asset.name}」吗？", parent=self):
            return
        try:
            self.store.restore_asset(asset_id, note)
            self._save()
        except Exception as exc:
            messagebox.showerror("无法恢复资产", str(exc), parent=self)
            return
        self.selected_asset_id = asset_id
        self._refresh_all()
        self._select_visible_asset(asset_id)

    def _ask_short_text(self, title: str, prompt: str) -> str | None:
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.resizable(False, False)
        result: dict[str, str | None] = {"value": None}
        value_var = tk.StringVar()

        frame = ttk.Frame(dialog, padding=16, style="Panel.TFrame")
        frame.grid(row=0, column=0, sticky="nsew")
        ttk.Label(frame, text=prompt).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        entry = ttk.Entry(frame, textvariable=value_var, width=38)
        entry.grid(row=1, column=0, columnspan=2, sticky="ew")

        def save() -> None:
            result["value"] = value_var.get().strip()
            dialog.destroy()

        actions = ttk.Frame(frame)
        actions.grid(row=2, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(actions, text="取消", command=dialog.destroy).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="确定", style="Accent.TButton", command=save).grid(row=0, column=1)

        dialog.transient(self)
        dialog.grab_set()
        dialog.wait_visibility()
        entry.focus_set()
        self.wait_window(dialog)
        return result["value"]

    def prune_unused_tags(self) -> None:
        unused = self.store.unused_tags()
        if not unused:
            messagebox.showinfo("无需清理", "当前没有未使用的标签。", parent=self)
            return

        names = "\n".join(f"- {category_label(tag.category)}：{self.store.tag_display_name(tag)}" for tag in unused[:12])
        extra = "" if len(unused) <= 12 else f"\n... 还有 {len(unused) - 12} 个"
        confirm_text = (
            f"将移除 {len(unused)} 个没有被任何资产使用的标签：\n\n"
            f"{names}{extra}\n\n"
            "确认清理吗？"
        )
        if not messagebox.askyesno("确认清理未使用标签", confirm_text, parent=self):
            return

        removed = self.store.prune_unused_tags()
        self._save()
        self._refresh_all()
        messagebox.showinfo("清理完成", f"已移除 {len(removed)} 个未使用标签。", parent=self)

    def update_equivalent_values(self) -> None:
        if not self.store.assets:
            messagebox.showinfo("暂无资产", "当前没有资产需要更新。", parent=self)
            return
        try:
            rates = fetch_market_rates()
            self.store.update_equivalent_values(rates)
            self._save()
        except Exception as exc:
            messagebox.showerror(
                "无法更新等价值",
                f"实时汇率或金价获取失败：\n{exc}\n\n请检查网络连接后重试。",
                parent=self,
            )
            return
        self._refresh_all()
        messagebox.showinfo(
            "更新完成",
            (
                f"已更新 {len(self.store.assets)} 项资产的等价值。\n"
                f"GBP/CNY: {rates.gbp_to_cny.quantize(Decimal('0.0001'))}\n"
                f"实体黄金: ¥{rates.gold_cny_per_gram.quantize(Decimal('0.01'))}/克\n"
                f"来源: {rates.source}"
            ),
            parent=self,
        )

    def _allocation_totals_for_assets(self, currency_key: str, group: str) -> dict[str, Decimal]:
        totals: dict[str, Decimal] = {}
        for asset in self._filtered_assets():
            if group == "storage":
                label = self.store.storage_type_name(asset) or "未分类"
            else:
                label = self.store.asset_type_display(asset) or "未分类"
            totals[label] = totals.get(label, Decimal("0")) + self.store.asset_equivalent_value(asset, currency_key)
        return totals

    def _allocation_items_for_assets(self, currency_key: str, group: str) -> dict[str, list[tuple[str, Decimal]]]:
        items: dict[str, list[tuple[str, Decimal]]] = {}
        for asset in self._filtered_assets():
            if group == "storage":
                label = self.store.storage_type_name(asset) or "未分类"
            else:
                label = self.store.asset_type_display(asset) or "未分类"
            items.setdefault(label, []).append((asset.name, self.store.asset_equivalent_value(asset, currency_key)))
        return items

    def _filtered_storage_allocation(self, currency_key: str = "CNY") -> dict[str, Decimal]:
        return self._allocation_totals_for_assets(currency_key, "storage")

    def _filtered_storage_items(self, currency_key: str = "CNY") -> dict[str, list[tuple[str, Decimal]]]:
        return self._allocation_items_for_assets(currency_key, "storage")

    def _filtered_asset_type_allocation(self, currency_key: str = "CNY") -> dict[str, Decimal]:
        return self._allocation_totals_for_assets(currency_key, "asset_type")

    def _filtered_asset_type_items(self, currency_key: str = "CNY") -> dict[str, list[tuple[str, Decimal]]]:
        return self._allocation_items_for_assets(currency_key, "asset_type")

    def show_storage_allocation(self) -> None:
        try:
            self._filtered_storage_allocation("CNY")
        except Exception as exc:
            messagebox.showerror("无法展示配比", f"请先点击“更新等价值”。\n\n{exc}", parent=self)
            return
        PieChartWindow(
            self,
            "按存放方式的资产配比",
            self._filtered_storage_allocation,
            self._filtered_storage_items,
        )

    def show_asset_type_allocation(self) -> None:
        try:
            self._filtered_asset_type_allocation("CNY")
        except Exception as exc:
            messagebox.showerror("无法展示配比", f"请先点击“更新等价值”。\n\n{exc}", parent=self)
            return
        PieChartWindow(
            self,
            "按资产类型的资产配比",
            self._filtered_asset_type_allocation,
            self._filtered_asset_type_items,
        )

    def record_change(self) -> None:
        asset_id = self._selected_asset_id_or_warn()
        if not asset_id:
            return

        asset = self.store.assets[asset_id]
        dialog = ChangeDialog(self, asset.name)
        self.wait_window(dialog)
        if not dialog.result:
            return
        try:
            self.store.change_asset(asset_id, dialog.result["delta"], dialog.result["note"])
            self._save()
        except Exception as exc:
            messagebox.showerror("无法记录变动", str(exc), parent=self)
            return
        self._refresh_all()
        self._select_visible_asset(asset_id)

    def open_data_file(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="打开数据文件",
            filetypes=[("myMoney 数据文件", "*.json"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            self.data_path = Path(path)
            self.store = MoneyStore.load(self.data_path)
        except Exception as exc:
            messagebox.showerror("无法打开数据文件", str(exc), parent=self)
            return
        self.selected_asset_id = None
        self.status_var.set(f"数据文件：{self.data_path}")
        self._refresh_all()

    def export_data(self) -> None:
        default_name = f"mymoney_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path = filedialog.asksaveasfilename(
            parent=self,
            title="导出迁移包",
            initialdir=DATA_DIR,
            initialfile=default_name,
            defaultextension=".zip",
            filetypes=[("Zip 迁移包", "*.zip")],
        )
        if not path:
            return
        try:
            self._save()
            export_package(self.data_path, Path(path))
        except Exception as exc:
            messagebox.showerror("无法导出", str(exc), parent=self)
            return
        messagebox.showinfo("导出完成", f"迁移包已保存到：\n{path}", parent=self)

    def import_data(self) -> None:
        package = filedialog.askopenfilename(
            parent=self,
            title="导入迁移包",
            filetypes=[("Zip 迁移包", "*.zip"), ("所有文件", "*.*")],
        )
        if not package:
            return
        target = filedialog.asksaveasfilename(
            parent=self,
            title="导入后保存为",
            initialfile=self.data_path.name,
            defaultextension=".json",
            filetypes=[("myMoney 数据文件", "*.json")],
        )
        if not target:
            return
        try:
            import_package(Path(package), Path(target))
            self.data_path = Path(target)
            self.store = MoneyStore.load(self.data_path)
        except Exception as exc:
            messagebox.showerror("无法导入", str(exc), parent=self)
            return
        self.selected_asset_id = None
        self.status_var.set(f"数据文件：{self.data_path}")
        self._refresh_all()

    def _save(self) -> None:
        self.store.save(self.data_path)
        self.status_var.set(f"已保存：{self.data_path}")


def main() -> None:
    app = MoneyApp()
    app.mainloop()


if __name__ == "__main__":
    main()
