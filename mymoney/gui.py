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
FILTER_LOGIC_OPTIONS = ("与", "或", "与非", "或非")


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

    DIMENSION_OPTIONS = {
        "存放方式": "storage",
        "一级资产类型": "asset_type_level_1",
        "二级资产类型": "asset_type_level_2",
        "资产名称": "asset_name",
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
        self.dimension_var = tk.StringVar(value="存放方式")
        self.totals: dict[str, Decimal] = {}
        self.items: dict[str, list[tuple[str, Decimal]]] = {}

        frame = ttk.Frame(self, padding=16, style="App.TFrame")
        frame.pack(fill="both", expand=True)
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)

        header = ttk.Frame(frame, style="App.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=title, style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="币种").grid(row=0, column=1, sticky="e", padx=(0, 6))
        currency = ttk.Combobox(
            header,
            textvariable=self.currency_var,
            values=list(self.CURRENCY_OPTIONS),
            state="readonly",
            width=16,
        )
        currency.grid(row=0, column=2, sticky="e", padx=(0, 12))
        currency.bind("<<ComboboxSelected>>", lambda _event: self._draw())
        ttk.Label(header, text="统计维度").grid(row=0, column=3, sticky="e", padx=(0, 6))
        dimension = ttk.Combobox(
            header,
            textvariable=self.dimension_var,
            values=list(self.DIMENSION_OPTIONS),
            state="readonly",
            width=14,
        )
        dimension.grid(row=0, column=4, sticky="e")
        dimension.bind("<<ComboboxSelected>>", lambda _event: self._draw())

        paned = ttk.PanedWindow(frame, orient=tk.VERTICAL)
        paned.grid(row=1, column=0, sticky="nsew")
        chart_pane = ttk.Frame(paned, padding=6, style="Border.TFrame")
        detail_pane = ttk.Frame(paned, padding=6, style="Border.TFrame")
        chart_pane.rowconfigure(0, weight=1)
        chart_pane.columnconfigure(0, weight=1)
        detail_pane.rowconfigure(0, weight=1)
        detail_pane.columnconfigure(0, weight=1)
        paned.add(chart_pane, weight=2)
        paned.add(detail_pane, weight=1)

        self.canvas = tk.Canvas(chart_pane, bg="#ffffff", highlightthickness=0, height=280)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", lambda _event: self._draw())
        self.detail_tree = ttk.Treeview(detail_pane, columns=("value", "percent"), show="tree headings")
        self.detail_tree.heading("#0", text="分组 / 资产")
        self.detail_tree.heading("value", text="金额")
        self.detail_tree.heading("percent", text="占比")
        self.detail_tree.column("#0", width=260, anchor="w")
        self.detail_tree.column("value", width=130, anchor="e")
        self.detail_tree.column("percent", width=90, anchor="e")
        self.detail_tree.grid(row=0, column=0, sticky="nsew")
        self._bind_detail_mousewheel(detail_pane)
        self._bind_detail_mousewheel(self.detail_tree)
        self.transient(parent)

    def _bind_detail_mousewheel(self, widget: tk.Widget) -> None:
        widget.bind("<MouseWheel>", self._on_detail_mousewheel, add="+")
        widget.bind("<Button-4>", lambda _event: self.detail_tree.yview_scroll(-1, "units"), add="+")
        widget.bind("<Button-5>", lambda _event: self.detail_tree.yview_scroll(1, "units"), add="+")

    def _on_detail_mousewheel(self, event: tk.Event[tk.Widget]) -> str:
        direction = -1 if event.delta > 0 else 1
        self.detail_tree.yview_scroll(direction * max(1, abs(event.delta) // 120), "units")
        return "break"

    def _draw(self) -> None:
        self.canvas.delete("all")
        currency_key = self.CURRENCY_OPTIONS[self.currency_var.get()]
        dimension_key = self.DIMENSION_OPTIONS[self.dimension_var.get()]
        self.totals = {key: value for key, value in self.totals_provider(currency_key, dimension_key).items() if value > 0}
        self.items = self.items_provider(currency_key, dimension_key)
        self._refresh_detail_tree(currency_key)
        if not self.totals:
            self.canvas.create_text(320, 220, text="没有可展示的数据", fill="#64748b", font=("Microsoft YaHei UI", 12))
            return

        total = sum(self.totals.values(), Decimal("0"))
        width = max(self.canvas.winfo_width(), 520)
        row_height = 34
        top = 24
        left = 28
        right = width - 28
        bar_left = min(220, max(150, int(width * 0.30)))
        bar_right = max(bar_left + 120, right - 170)
        value_x = bar_right + 18

        for index, (label, value) in enumerate(sorted(self.totals.items(), key=lambda item: item[1], reverse=True)):
            percent = (value / total * Decimal("100")) if total else Decimal("0")
            color = self.COLORS[index % len(self.COLORS)]
            unit = self.UNIT_LABELS[currency_key]
            value_text = f"{unit}{value.quantize(Decimal('0.01'))}" if currency_key != "GOLD_GRAM" else f"{value.quantize(Decimal('0.0001'))}{unit}"
            y = top + index * row_height
            bar_width = float(percent / Decimal("100")) * (bar_right - bar_left)
            self.canvas.create_text(left, y + 12, text=label, anchor="w", fill="#1f2937", font=("Microsoft YaHei UI", 10))
            self.canvas.create_rectangle(bar_left, y + 4, bar_right, y + 22, fill="#eef2f7", outline="#cbd5e1")
            self.canvas.create_rectangle(bar_left, y + 4, bar_left + bar_width, y + 22, fill=color, outline=color)
            self.canvas.create_text(
                value_x,
                y + 12,
                text=f"{percent.quantize(Decimal('0.01'))}%  {value_text}",
                anchor="w",
                fill="#1f2937",
                font=("Microsoft YaHei UI", 10),
            )

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
        self.filter_name_var = tk.StringVar()
        self.filter_tag_options: dict[str, str | None] = {}
        self.selected_filter_tag_ids: list[str] = []
        self.pie_injection_var = tk.StringVar()
        self.pie_no_sell_var = tk.BooleanVar(value=False)
        self.pie_status_var = tk.StringVar(value="按当前筛选结果设置目标配比，金额以人民币等价值计算。")
        self.pie_asset_ids: list[str] = []
        self.pie_target_vars: dict[str, tk.StringVar] = {}
        self.group_pie_injection_var = tk.StringVar()
        self.group_pie_status_var = tk.StringVar(value="添加组别并分配资产后，按组目标配比计算。")
        self.group_pie_mode_var = tk.StringVar(value="默认模式")
        self.group_pie_modes: dict[str, dict[str, object]] = {}
        self.group_pie_asset_ids: list[str] = []
        self.group_pie_targets: dict[str, tk.StringVar] = {}
        self.group_pie_asset_groups: dict[str, tk.StringVar] = {}
        self.group_pie_asset_locked: dict[str, tk.BooleanVar] = {}
        self.sort_column = "updated_at"
        self.sort_reverse = True
        self._load_tool_configs()
        self._last_group_pie_mode_name = self.group_pie_mode_var.get()

        self._configure_style()
        self._build_menu()
        self._build_layout()
        self._refresh_all()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

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
        style.configure("Border.TFrame", background="#ffffff", borderwidth=1, relief="solid")
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
        tool_menu = tk.Menu(menu, tearoff=False)
        tool_menu.add_command(label="配比查看", command=self.show_allocation_view)
        tool_menu.add_command(label="补pie", command=self.show_pie_window)
        tool_menu.add_command(label="分组补pie", command=self.show_group_pie_window)
        menu.add_cascade(label="工具", menu=tool_menu)
        self.config(menu=menu)

    def _load_tool_configs(self) -> None:
        tools = self.store.ui_state.get("tools", {})
        pie = tools.get("pie", {})
        self.pie_asset_ids = list(pie.get("asset_ids", []))
        self.pie_no_sell_var.set(bool(pie.get("no_sell", False)))
        self.pie_injection_var.set(str(pie.get("injection", "")))
        self.pie_target_vars = {
            asset_id: tk.StringVar(value=str(value))
            for asset_id, value in dict(pie.get("targets", {})).items()
        }

        group_pie = tools.get("group_pie", {})
        self.group_pie_modes = dict(group_pie.get("modes", {}))
        if not self.group_pie_modes:
            self.group_pie_modes = {
                "默认模式": {
                    "asset_ids": list(group_pie.get("asset_ids", [])),
                    "injection": group_pie.get("injection", ""),
                    "targets": dict(group_pie.get("targets", {})),
                    "asset_groups": dict(group_pie.get("asset_groups", {})),
                    "asset_locked": dict(group_pie.get("asset_locked", {})),
                }
            }
        active_mode = str(group_pie.get("active_mode") or next(iter(self.group_pie_modes), "默认模式"))
        if active_mode not in self.group_pie_modes:
            active_mode = next(iter(self.group_pie_modes), "默认模式")
        self.group_pie_mode_var.set(active_mode)
        self._load_group_pie_mode(active_mode)

    def _sync_tool_configs(self) -> None:
        self.store.ui_state["tools"] = {
            "pie": {
                "asset_ids": list(self.pie_asset_ids),
                "injection": self.pie_injection_var.get(),
                "no_sell": self.pie_no_sell_var.get(),
                "targets": {
                    asset_id: variable.get()
                    for asset_id, variable in self.pie_target_vars.items()
                },
            },
            "group_pie": {
                "active_mode": self.group_pie_mode_var.get(),
                "modes": self._group_pie_modes_for_save(),
            },
        }

    def _current_group_pie_mode_data(self) -> dict[str, object]:
        return {
            "asset_ids": list(self.group_pie_asset_ids),
            "injection": self.group_pie_injection_var.get(),
            "targets": {
                name: variable.get()
                for name, variable in self.group_pie_targets.items()
            },
            "asset_groups": {
                asset_id: variable.get()
                for asset_id, variable in self.group_pie_asset_groups.items()
            },
            "asset_locked": {
                asset_id: variable.get()
                for asset_id, variable in self.group_pie_asset_locked.items()
            },
        }

    def _group_pie_modes_for_save(self) -> dict[str, dict[str, object]]:
        current = self.group_pie_mode_var.get() or "默认模式"
        self.group_pie_modes[current] = self._current_group_pie_mode_data()
        return dict(self.group_pie_modes)

    def _load_group_pie_mode(self, mode_name: str) -> None:
        data = dict(self.group_pie_modes.get(mode_name, {}))
        self.group_pie_asset_ids = list(data.get("asset_ids", []))
        self.group_pie_injection_var.set(str(data.get("injection", "")))
        self.group_pie_targets = {
            name: tk.StringVar(value=str(value))
            for name, value in dict(data.get("targets", {})).items()
        }
        self.group_pie_asset_groups = {
            asset_id: tk.StringVar(value=str(group))
            for asset_id, group in dict(data.get("asset_groups", {})).items()
        }
        self.group_pie_asset_locked = {
            asset_id: tk.BooleanVar(value=bool(locked))
            for asset_id, locked in dict(data.get("asset_locked", {})).items()
        }

    def _on_close(self) -> None:
        self._save()
        self.destroy()

    def _create_tool_window(self, title: str, geometry: str) -> tk.Toplevel:
        window = tk.Toplevel(self)
        window.title(title)
        window.geometry(geometry)
        window.minsize(840, 560)
        window.configure(bg="#eef2f7")
        window.withdraw()
        window.protocol("WM_DELETE_WINDOW", window.withdraw)
        return window

    def _bind_mousewheel(self, widget: tk.Widget) -> None:
        widget.bind("<MouseWheel>", lambda event, target=widget: self._on_mousewheel(event, target), add="+")
        widget.bind("<Button-4>", lambda event, target=widget: target.yview_scroll(-1, "units"), add="+")
        widget.bind("<Button-5>", lambda event, target=widget: target.yview_scroll(1, "units"), add="+")

    def _bind_mousewheel_area(self, area: tk.Widget, target: tk.Widget) -> None:
        self._bind_mousewheel_to(area, target)
        for child in area.winfo_children():
            self._bind_mousewheel_area(child, target)

    def _bind_mousewheel_to(self, widget: tk.Widget, target: tk.Widget) -> None:
        widget.bind("<MouseWheel>", lambda event, scroll_target=target: self._on_mousewheel(event, scroll_target), add="+")
        widget.bind("<Button-4>", lambda event, scroll_target=target: scroll_target.yview_scroll(-1, "units"), add="+")
        widget.bind("<Button-5>", lambda event, scroll_target=target: scroll_target.yview_scroll(1, "units"), add="+")

    def _on_mousewheel(self, event: tk.Event[tk.Widget], widget: tk.Widget) -> str:
        direction = -1 if event.delta > 0 else 1
        widget.yview_scroll(direction * max(1, abs(event.delta) // 120), "units")
        return "break"

    def show_pie_window(self) -> None:
        self._refresh_pie_targets()
        self.pie_window.deiconify()
        self.pie_window.lift()
        self.pie_window.focus_force()

    def show_group_pie_window(self) -> None:
        self._refresh_group_pie()
        self.group_pie_window.deiconify()
        self.group_pie_window.lift()
        self.group_pie_window.focus_force()

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

        toolbar = ttk.Frame(root, padding=8, style="Border.TFrame")
        toolbar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        toolbar.columnconfigure(0, weight=1)
        ttk.Label(toolbar, text="资产列表", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(toolbar, text="新增资产", style="Accent.TButton", command=self.add_asset).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(toolbar, text="编辑资产", command=self.edit_asset).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(toolbar, text="记录变动", command=self.record_change).grid(row=0, column=3, padx=(0, 8))
        ttk.Button(toolbar, text="资产转换", command=self.transfer_asset).grid(row=0, column=4, padx=(0, 8))
        ttk.Button(toolbar, text="废除资产", command=self.deprecate_asset).grid(row=0, column=5, padx=(0, 8))
        ttk.Button(toolbar, text="更新等价值", command=self.update_equivalent_values).grid(row=0, column=6)

        filter_bar = ttk.Frame(root, padding=8, style="Border.TFrame")
        filter_bar.grid(row=2, column=0, columnspan=2, sticky="ew")
        filter_bar.columnconfigure(9, weight=1)
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
        ttk.Label(filter_bar, text="资产名称").grid(row=0, column=7, sticky="w", padx=(0, 6))
        name_filter = ttk.Entry(filter_bar, textvariable=self.filter_name_var, width=18)
        name_filter.grid(row=0, column=8, sticky="w", padx=(0, 8))
        name_filter.bind("<KeyRelease>", self._apply_asset_filter)
        ttk.Button(filter_bar, text="清空限定", command=self.clear_asset_filter).grid(row=0, column=9, sticky="w")
        content_paned = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        content_paned.grid(row=3, column=0, columnspan=2, sticky="nsew")
        asset_pane = ttk.Frame(content_paned, padding=6, style="Border.TFrame")
        detail_pane = ttk.Frame(content_paned, padding=6, style="Border.TFrame")
        asset_pane.rowconfigure(0, weight=1)
        asset_pane.columnconfigure(0, weight=1)
        detail_pane.rowconfigure(0, weight=1)
        detail_pane.columnconfigure(0, weight=1)
        content_paned.add(asset_pane, weight=3)
        content_paned.add(detail_pane, weight=2)

        asset_workspace = ttk.PanedWindow(asset_pane, orient=tk.HORIZONTAL)
        asset_workspace.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        filter_display_pane = ttk.Frame(asset_workspace, padding=6, style="Border.TFrame")
        asset_list_pane = ttk.Frame(asset_workspace, padding=6, style="Border.TFrame")
        filter_display_pane.rowconfigure(1, weight=1)
        filter_display_pane.columnconfigure(0, weight=1)
        asset_list_pane.rowconfigure(0, weight=1)
        asset_list_pane.columnconfigure(0, weight=1)
        asset_workspace.add(filter_display_pane, weight=1)
        asset_workspace.add(asset_list_pane, weight=4)
        ttk.Label(filter_display_pane, text="已选标签条件").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.filter_tag_list = tk.Listbox(
            filter_display_pane,
            activestyle="none",
            exportselection=False,
            selectmode=tk.EXTENDED,
            font=("Microsoft YaHei UI", 9),
        )
        self.filter_tag_list.grid(row=1, column=0, sticky="nsew")
        self._bind_mousewheel(self.filter_tag_list)
        self._bind_mousewheel_to(filter_display_pane, self.filter_tag_list)

        self.asset_tree = ttk.Treeview(
            asset_list_pane,
            columns=("name", "value", "currency", "equivalent", "share", "asset_type", "storage_type", "updated_at"),
            show="headings",
            selectmode="extended",
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
        self.asset_tree.grid(row=0, column=0, sticky="nsew")
        self.asset_tree.bind("<<TreeviewSelect>>", self._on_asset_selected)
        self._bind_mousewheel(self.asset_tree)
        self._bind_mousewheel_to(asset_list_pane, self.asset_tree)

        right = ttk.Notebook(detail_pane)
        right.grid(row=0, column=0, sticky="nsew")

        history_frame = ttk.Frame(right, padding=8, style="Border.TFrame")
        tag_frame = ttk.Frame(right, padding=8, style="Border.TFrame")
        deprecated_frame = ttk.Frame(right, padding=8, style="Border.TFrame")
        right.add(history_frame, text="变动流水")
        right.add(tag_frame, text="标签")
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
        self._bind_mousewheel(self.history_tree)
        self._bind_mousewheel_to(history_frame, self.history_tree)

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
        self._bind_mousewheel(self.tag_tree)
        self._bind_mousewheel_to(tag_frame, self.tag_tree)

        self.pie_window = self._create_tool_window("补pie", "980x720")
        pie_frame = ttk.Frame(self.pie_window, padding=12, style="App.TFrame")
        pie_frame.pack(fill="both", expand=True)
        pie_frame.rowconfigure(2, weight=1)
        pie_frame.columnconfigure(0, weight=1)
        pie_controls = ttk.Frame(pie_frame, padding=8, style="Border.TFrame")
        pie_controls.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        pie_controls.columnconfigure(5, weight=1)
        ttk.Label(pie_controls, text="新注资金额(CNY)").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Entry(pie_controls, textvariable=self.pie_injection_var, width=16).grid(row=0, column=1, sticky="w", padx=(0, 8))
        ttk.Button(pie_controls, text="当前配比", command=self.fill_pie_targets_current).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(pie_controls, text="平均目标", command=self.fill_pie_targets_equal).grid(row=0, column=3, padx=(0, 8))
        ttk.Button(pie_controls, text="计算分配", style="Accent.TButton", command=self.calculate_pie_top_up).grid(row=0, column=4)
        ttk.Button(pie_controls, text="加入左侧选中资产", command=self.add_selected_assets_to_pie).grid(row=1, column=0, padx=(0, 8), pady=(8, 0))
        ttk.Button(pie_controls, text="清空分配区", command=self.clear_pie_assets).grid(row=1, column=1, padx=(0, 8), pady=(8, 0))
        ttk.Checkbutton(pie_controls, text="非卖出再分配", variable=self.pie_no_sell_var).grid(
            row=1, column=2, columnspan=3, sticky="w", pady=(8, 0)
        )
        ttk.Label(pie_frame, textvariable=self.pie_status_var, foreground="#64748b").grid(row=1, column=0, sticky="ew", pady=(0, 6))
        pie_paned = ttk.PanedWindow(pie_frame, orient=tk.VERTICAL)
        pie_paned.grid(row=2, column=0, sticky="nsew")
        pie_target_pane = ttk.Frame(pie_paned, padding=6, style="Border.TFrame")
        pie_result_pane = ttk.Frame(pie_paned, padding=6, style="Border.TFrame")
        pie_target_pane.rowconfigure(0, weight=1)
        pie_target_pane.columnconfigure(0, weight=1)
        pie_result_pane.rowconfigure(0, weight=1)
        pie_result_pane.columnconfigure(0, weight=1)
        pie_paned.add(pie_target_pane, weight=1)
        pie_paned.add(pie_result_pane, weight=2)
        self.pie_target_canvas = tk.Canvas(pie_target_pane, height=150, bg="#ffffff", highlightthickness=0)
        self.pie_target_canvas.grid(row=0, column=0, sticky="nsew")
        pie_target_scroll = ttk.Scrollbar(pie_target_pane, orient="vertical", command=self.pie_target_canvas.yview)
        pie_target_scroll.grid(row=0, column=1, sticky="ns")
        self.pie_target_canvas.configure(yscrollcommand=pie_target_scroll.set)
        self._bind_mousewheel(self.pie_target_canvas)
        self._bind_mousewheel_to(pie_target_pane, self.pie_target_canvas)
        self.pie_target_inner = ttk.Frame(self.pie_target_canvas, padding=6)
        self.pie_target_window = self.pie_target_canvas.create_window((0, 0), window=self.pie_target_inner, anchor="nw")
        self.pie_target_canvas.bind("<Configure>", self._resize_pie_target_canvas)
        self.pie_target_inner.bind(
            "<Configure>",
            lambda _event: self.pie_target_canvas.configure(scrollregion=self.pie_target_canvas.bbox("all")),
        )
        self.pie_result_tree = ttk.Treeview(
            pie_result_pane,
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
        self.pie_result_tree.grid(row=0, column=0, sticky="nsew")
        self._bind_mousewheel(self.pie_result_tree)
        self._bind_mousewheel_to(pie_result_pane, self.pie_result_tree)

        self.group_pie_window = self._create_tool_window("分组补pie", "1120x780")
        group_pie_frame = ttk.Frame(self.group_pie_window, padding=12, style="App.TFrame")
        group_pie_frame.pack(fill="both", expand=True)
        group_pie_frame.rowconfigure(2, weight=1)
        group_pie_frame.columnconfigure(0, weight=1)
        group_controls = ttk.Frame(group_pie_frame, padding=8, style="Border.TFrame")
        group_controls.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        group_controls.columnconfigure(5, weight=1)
        ttk.Label(group_controls, text="新注资金额(CNY)").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Entry(group_controls, textvariable=self.group_pie_injection_var, width=14).grid(row=0, column=1, sticky="w", padx=(0, 8))
        ttk.Button(group_controls, text="计算分配", style="Accent.TButton", command=self.calculate_group_pie).grid(row=0, column=2)
        ttk.Button(group_controls, text="加入左侧选中资产", command=self.add_selected_assets_to_group_pie).grid(row=1, column=0, padx=(0, 8), pady=(8, 0))
        ttk.Button(group_controls, text="清空资产区", command=self.clear_group_pie_assets).grid(row=1, column=1, padx=(0, 8), pady=(8, 0))
        ttk.Label(group_controls, text="分组模式").grid(row=2, column=0, sticky="w", pady=(8, 0), padx=(0, 6))
        self.group_pie_mode_combo = ttk.Combobox(
            group_controls,
            textvariable=self.group_pie_mode_var,
            values=self._group_mode_names(),
            state="readonly",
            width=18,
        )
        self.group_pie_mode_combo.grid(row=2, column=1, sticky="w", pady=(8, 0), padx=(0, 8))
        self.group_pie_mode_combo.bind("<<ComboboxSelected>>", self._on_group_pie_mode_changed)
        ttk.Button(group_controls, text="添加模式", command=self.add_group_pie_mode).grid(row=2, column=2, padx=(0, 8), pady=(8, 0))
        ttk.Button(group_controls, text="移除模式", command=self.remove_group_pie_mode).grid(row=2, column=3, padx=(0, 8), pady=(8, 0))
        ttk.Label(group_pie_frame, textvariable=self.group_pie_status_var, foreground="#64748b").grid(row=1, column=0, sticky="ew", pady=(0, 6))

        group_paned = ttk.PanedWindow(group_pie_frame, orient=tk.VERTICAL)
        group_paned.grid(row=2, column=0, sticky="nsew")
        setup_section = ttk.Frame(group_paned, style="App.TFrame")
        result_section = ttk.Frame(group_paned, padding=6, style="Border.TFrame")
        setup_section.rowconfigure(0, weight=1)
        setup_section.columnconfigure(0, weight=1)
        setup_paned = ttk.PanedWindow(setup_section, orient=tk.HORIZONTAL)
        setup_paned.grid(row=0, column=0, sticky="nsew")
        group_section = ttk.Frame(setup_paned, padding=6, style="Border.TFrame")
        asset_section = ttk.Frame(setup_paned, padding=6, style="Border.TFrame")
        group_section.rowconfigure(1, weight=1)
        group_section.columnconfigure(0, weight=1)
        asset_section.rowconfigure(1, weight=1)
        asset_section.columnconfigure(0, weight=1)
        result_section.rowconfigure(0, weight=1)
        result_section.columnconfigure(0, weight=1)
        setup_paned.add(group_section, weight=1)
        setup_paned.add(asset_section, weight=2)
        group_paned.add(setup_section, weight=2)
        group_paned.add(result_section, weight=2)

        group_header = ttk.Frame(group_section)
        group_header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        group_header.columnconfigure(0, weight=1)
        ttk.Label(group_header, text="组别").grid(row=0, column=0, sticky="w")
        ttk.Button(group_header, text="添加组别", command=self.add_group_pie_group).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(group_header, text="移除组别", command=self.remove_group_pie_group).grid(row=0, column=2)

        self.group_pie_group_canvas = tk.Canvas(group_section, height=90, bg="#ffffff", highlightthickness=0)
        self.group_pie_group_canvas.grid(row=1, column=0, sticky="nsew")
        group_scroll = ttk.Scrollbar(group_section, orient="vertical", command=self.group_pie_group_canvas.yview)
        group_scroll.grid(row=1, column=1, sticky="ns")
        self.group_pie_group_canvas.configure(yscrollcommand=group_scroll.set)
        self._bind_mousewheel(self.group_pie_group_canvas)
        self._bind_mousewheel_to(group_section, self.group_pie_group_canvas)
        self.group_pie_group_inner = ttk.Frame(self.group_pie_group_canvas, padding=6)
        self.group_pie_group_window = self.group_pie_group_canvas.create_window((0, 0), window=self.group_pie_group_inner, anchor="nw")
        self.group_pie_group_canvas.bind("<Configure>", self._resize_group_pie_group_canvas)
        self.group_pie_group_inner.bind(
            "<Configure>",
            lambda _event: self.group_pie_group_canvas.configure(scrollregion=self.group_pie_group_canvas.bbox("all")),
        )

        ttk.Label(asset_section, text="资产分组").grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.group_pie_asset_canvas = tk.Canvas(asset_section, height=150, bg="#ffffff", highlightthickness=0)
        self.group_pie_asset_canvas.grid(row=1, column=0, sticky="nsew")
        asset_group_scroll = ttk.Scrollbar(asset_section, orient="vertical", command=self.group_pie_asset_canvas.yview)
        asset_group_scroll.grid(row=1, column=1, sticky="ns")
        self.group_pie_asset_canvas.configure(yscrollcommand=asset_group_scroll.set)
        self._bind_mousewheel(self.group_pie_asset_canvas)
        self._bind_mousewheel_to(asset_section, self.group_pie_asset_canvas)
        self.group_pie_asset_inner = ttk.Frame(self.group_pie_asset_canvas, padding=6)
        self.group_pie_asset_window = self.group_pie_asset_canvas.create_window((0, 0), window=self.group_pie_asset_inner, anchor="nw")
        self.group_pie_asset_canvas.bind("<Configure>", self._resize_group_pie_asset_canvas)
        self.group_pie_asset_inner.bind(
            "<Configure>",
            lambda _event: self.group_pie_asset_canvas.configure(scrollregion=self.group_pie_asset_canvas.bbox("all")),
        )

        self.group_pie_result_tree = ttk.Treeview(
            result_section,
            columns=("current", "target", "suggested", "final", "final_percent", "note"),
            show="tree headings",
        )
        self.group_pie_result_tree.heading("#0", text="组别 / 资产")
        for key, label, width in (
            ("current", "当前CNY", 86),
            ("target", "目标%", 68),
            ("suggested", "建议调整", 86),
            ("final", "调整后CNY", 96),
            ("final_percent", "调整后%", 78),
            ("note", "说明", 110),
        ):
            self.group_pie_result_tree.heading(key, text=label)
            self.group_pie_result_tree.column(key, width=width, anchor="w")
        self.group_pie_result_tree.grid(row=0, column=0, sticky="nsew")
        self._bind_mousewheel(self.group_pie_result_tree)
        self._bind_mousewheel_to(result_section, self.group_pie_result_tree)

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
        self._bind_mousewheel(self.deprecated_tree)
        self._bind_mousewheel_to(deprecated_frame, self.deprecated_tree)

        ttk.Label(root, textvariable=self.status_var, style="Status.TLabel").grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(10, 0)
        )

    def _refresh_all(self) -> None:
        self._refresh_summary()
        self._refresh_filter_tags()
        self._refresh_assets()
        self._refresh_pie_targets()
        self._refresh_group_pie()
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
        if logic == "与非":
            return not all(matches)
        if logic == "或非":
            return not any(matches)
        return all(matches)

    def _filtered_assets(self) -> list[Asset]:
        name_query = self.filter_name_var.get().strip().casefold()
        assets = [asset for asset in self.store.active_assets() if self._asset_matches_filter_tags(asset)]
        if name_query:
            assets = [asset for asset in assets if name_query in asset.name.casefold()]
        return assets

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
        self._refresh_group_pie()
        self._refresh_history()

    def clear_asset_filter(self) -> None:
        self.filter_category_var.set(ALL_FILTER_CATEGORIES)
        self.filter_tag_var.set(ALL_FILTER_TAGS)
        self.filter_logic_var.set("与")
        self.filter_name_var.set("")
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

    def _selected_asset_ids_from_list(self) -> list[str]:
        return [asset_id for asset_id in self.asset_tree.selection() if asset_id in self.store.assets]

    def _active_assets_from_ids(self, asset_ids: list[str]) -> list[Asset]:
        assets: list[Asset] = []
        kept_ids: list[str] = []
        for asset_id in asset_ids:
            asset = self.store.assets.get(asset_id)
            if asset and asset.deprecated_at is None:
                assets.append(asset)
                kept_ids.append(asset_id)
        asset_ids[:] = kept_ids
        return assets

    def _pie_assets(self) -> list[Asset]:
        return self._active_assets_from_ids(self.pie_asset_ids)

    def _group_pie_assets(self) -> list[Asset]:
        return self._active_assets_from_ids(self.group_pie_asset_ids)

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

        assets = self._pie_assets()
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
        ttk.Label(self.pie_target_inner, text="操作").grid(row=0, column=4, sticky="w", padx=(8, 0))

        if not assets:
            ttk.Label(self.pie_target_inner, text="分配区还没有资产。请在左侧资产列表多选后点击“加入左侧选中资产”。", foreground="#64748b").grid(
                row=1, column=0, columnspan=5, sticky="w", pady=(8, 0)
            )
            self.pie_status_var.set("分配区还没有资产。搜索只是用来找到资产，加入后不会受搜索条件变化影响。")
            self._bind_mousewheel_area(self.pie_target_inner, self.pie_target_canvas)
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
            row_widgets = [
                ttk.Label(self.pie_target_inner, text=asset.name),
                ttk.Label(self.pie_target_inner, text=current_text),
                ttk.Label(self.pie_target_inner, text=percent_text),
                ttk.Entry(self.pie_target_inner, textvariable=self.pie_target_vars[asset.id], width=10),
                ttk.Button(self.pie_target_inner, text="移除", command=lambda asset_id=asset.id: self.remove_pie_asset(asset_id)),
            ]
            row_widgets[0].grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
            row_widgets[1].grid(row=row, column=1, sticky="w", padx=(0, 8), pady=2)
            row_widgets[2].grid(row=row, column=2, sticky="w", padx=(0, 8), pady=2)
            row_widgets[3].grid(row=row, column=3, sticky="w", pady=2)
            row_widgets[4].grid(row=row, column=4, sticky="w", padx=(8, 0), pady=2)
        self._bind_mousewheel_area(self.pie_target_inner, self.pie_target_canvas)
        self.pie_status_var.set("按分配区资产设置目标配比，金额以人民币等价值计算。")

    def add_selected_assets_to_pie(self) -> None:
        selected_ids = self._selected_asset_ids_from_list()
        if not selected_ids:
            messagebox.showinfo("请选择资产", "请先在左侧资产列表中选择一个或多个资产。", parent=self)
            return
        for asset_id in selected_ids:
            if asset_id not in self.pie_asset_ids:
                self.pie_asset_ids.append(asset_id)
        self._refresh_pie_targets()
        self.show_pie_window()

    def remove_pie_asset(self, asset_id: str) -> None:
        if asset_id in self.pie_asset_ids:
            self.pie_asset_ids.remove(asset_id)
        self.pie_target_vars.pop(asset_id, None)
        self._refresh_pie_targets()

    def clear_pie_assets(self) -> None:
        if self.pie_asset_ids and not messagebox.askyesno("确认清空", "确认清空补pie分配区吗？", parent=self):
            return
        self.pie_asset_ids.clear()
        self.pie_target_vars.clear()
        self._refresh_pie_targets()

    def fill_pie_targets_current(self) -> None:
        assets = self._pie_assets()
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
        assets = self._pie_assets()
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
        assets = self._pie_assets()
        if not assets:
            messagebox.showinfo("无法计算", "请先把资产加入补pie分配区。", parent=self)
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

    def _resize_group_pie_group_canvas(self, event: tk.Event[tk.Widget]) -> None:
        self.group_pie_group_canvas.itemconfigure(self.group_pie_group_window, width=event.width)

    def _resize_group_pie_asset_canvas(self, event: tk.Event[tk.Widget]) -> None:
        self.group_pie_asset_canvas.itemconfigure(self.group_pie_asset_window, width=event.width)

    def _group_mode_names(self) -> list[str]:
        if not self.group_pie_modes:
            self.group_pie_modes["默认模式"] = self._current_group_pie_mode_data()
        return list(self.group_pie_modes)

    def _refresh_group_pie_mode_combo(self) -> None:
        if hasattr(self, "group_pie_mode_combo"):
            self.group_pie_mode_combo.configure(values=self._group_mode_names())

    def _on_group_pie_mode_changed(self, _event: tk.Event[tk.Widget] | None = None) -> None:
        previous = getattr(self, "_last_group_pie_mode_name", "")
        if previous:
            self.group_pie_modes[previous] = self._current_group_pie_mode_data()
        selected = self.group_pie_mode_var.get()
        self._load_group_pie_mode(selected)
        self._last_group_pie_mode_name = selected
        self._refresh_group_pie()

    def add_group_pie_mode(self) -> None:
        name = self._ask_short_text("添加分组模式", "请输入分组模式名称：")
        if not name:
            return
        if name in self.group_pie_modes:
            messagebox.showinfo("模式已存在", "这个分组模式已经存在。", parent=self)
            return
        current = self.group_pie_mode_var.get() or "默认模式"
        self.group_pie_modes[current] = self._current_group_pie_mode_data()
        self.group_pie_modes[name] = {
            "asset_ids": [],
            "injection": "",
            "targets": {},
            "asset_groups": {},
            "asset_locked": {},
        }
        self.group_pie_mode_var.set(name)
        self._last_group_pie_mode_name = name
        self._load_group_pie_mode(name)
        self._refresh_group_pie_mode_combo()
        self._refresh_group_pie()

    def remove_group_pie_mode(self) -> None:
        name = self.group_pie_mode_var.get()
        if len(self.group_pie_modes) <= 1:
            messagebox.showinfo("无法移除", "至少需要保留一个分组模式。", parent=self)
            return
        if not messagebox.askyesno("确认移除分组模式", f"确认移除分组模式「{name}」吗？", parent=self):
            return
        self.group_pie_modes.pop(name, None)
        next_name = next(iter(self.group_pie_modes))
        self.group_pie_mode_var.set(next_name)
        self._last_group_pie_mode_name = next_name
        self._load_group_pie_mode(next_name)
        self._refresh_group_pie_mode_combo()
        self._refresh_group_pie()

    def _group_names(self) -> list[str]:
        return list(self.group_pie_targets)

    def add_group_pie_group(self) -> None:
        name = self._ask_short_text("添加组别", "请输入组别名称：")
        if not name:
            return
        if name in self.group_pie_targets:
            messagebox.showinfo("组别已存在", "这个组别已经存在。", parent=self)
            return
        self.group_pie_targets[name] = tk.StringVar(value="")
        self._refresh_group_pie()

    def remove_group_pie_group(self) -> None:
        name = self._ask_short_text("移除组别", "请输入要移除的组别名称：")
        if not name:
            return
        self.remove_group_pie_group_by_name(name)

    def remove_group_pie_group_by_name(self, name: str) -> None:
        if name not in self.group_pie_targets:
            messagebox.showinfo("组别不存在", "没有找到这个组别。", parent=self)
            return
        if not messagebox.askyesno("确认移除组别", f"确认移除组别「{name}」吗？资产会变为未分组。", parent=self):
            return
        self.group_pie_targets.pop(name, None)
        for group_var in self.group_pie_asset_groups.values():
            if group_var.get() == name:
                group_var.set("")
        self._refresh_group_pie()

    def _refresh_group_pie(self) -> None:
        self._refresh_group_pie_mode_combo()
        for child in self.group_pie_group_inner.winfo_children():
            child.destroy()
        for child in self.group_pie_asset_inner.winfo_children():
            child.destroy()
        self.group_pie_result_tree.delete(*self.group_pie_result_tree.get_children())

        assets = self._group_pie_assets()
        available_ids = {asset.id for asset in assets}
        self.group_pie_asset_groups = {
            asset_id: variable
            for asset_id, variable in self.group_pie_asset_groups.items()
            if asset_id in available_ids
        }
        self.group_pie_asset_locked = {
            asset_id: variable
            for asset_id, variable in self.group_pie_asset_locked.items()
            if asset_id in available_ids
        }

        self.group_pie_group_inner.columnconfigure(0, weight=1)
        ttk.Label(self.group_pie_group_inner, text="组别").grid(row=0, column=0, sticky="w", padx=(0, 12))
        ttk.Label(self.group_pie_group_inner, text="目标%").grid(row=0, column=1, sticky="w", padx=(0, 12))
        ttk.Label(self.group_pie_group_inner, text="操作").grid(row=0, column=2, sticky="w")
        for row, (name, target_var) in enumerate(self.group_pie_targets.items(), start=1):
            name_label = ttk.Label(self.group_pie_group_inner, text=name)
            target_entry = ttk.Entry(self.group_pie_group_inner, textvariable=target_var, width=12)
            remove_button = ttk.Button(
                self.group_pie_group_inner,
                text="移除",
                command=lambda group_name=name: self.remove_group_pie_group_by_name(group_name),
            )
            name_label.grid(row=row, column=0, sticky="ew", padx=(0, 12), pady=2)
            target_entry.grid(row=row, column=1, sticky="w", padx=(0, 12), pady=2)
            remove_button.grid(row=row, column=2, sticky="w", pady=2)
        if not self.group_pie_targets:
            ttk.Label(self.group_pie_group_inner, text="请先添加组别。", foreground="#64748b").grid(
                row=1, column=0, columnspan=3, sticky="w", pady=(6, 0)
            )
        self._bind_mousewheel_area(self.group_pie_group_inner, self.group_pie_group_canvas)

        ttk.Label(self.group_pie_asset_inner, text="资产").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Label(self.group_pie_asset_inner, text="当前CNY").grid(row=0, column=1, sticky="w", padx=(0, 8))
        ttk.Label(self.group_pie_asset_inner, text="组别").grid(row=0, column=2, sticky="w", padx=(0, 8))
        ttk.Label(self.group_pie_asset_inner, text="不可动").grid(row=0, column=3, sticky="w")
        ttk.Label(self.group_pie_asset_inner, text="操作").grid(row=0, column=4, sticky="w", padx=(8, 0))
        group_values = [""] + self._group_names()
        for row, asset in enumerate(assets, start=1):
            value = self._asset_cny_value_or_none(asset)
            current_text = "未更新" if value is None else self._format_cny(value)
            self.group_pie_asset_groups.setdefault(asset.id, tk.StringVar(value=""))
            self.group_pie_asset_locked.setdefault(asset.id, tk.BooleanVar(value=False))
            row_widgets = [
                ttk.Label(self.group_pie_asset_inner, text=asset.name),
                ttk.Label(self.group_pie_asset_inner, text=current_text),
            ]
            row_widgets[0].grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
            row_widgets[1].grid(row=row, column=1, sticky="w", padx=(0, 8), pady=2)
            combo = ttk.Combobox(
                self.group_pie_asset_inner,
                textvariable=self.group_pie_asset_groups[asset.id],
                values=group_values,
                state="readonly",
                width=14,
            )
            combo.grid(row=row, column=2, sticky="w", padx=(0, 8), pady=2)
            locked = ttk.Checkbutton(self.group_pie_asset_inner, variable=self.group_pie_asset_locked[asset.id])
            locked.grid(row=row, column=3, sticky="w", pady=2)
            remove = ttk.Button(self.group_pie_asset_inner, text="移除", command=lambda asset_id=asset.id: self.remove_group_pie_asset(asset_id))
            remove.grid(row=row, column=4, sticky="w", padx=(8, 0), pady=2)
            row_widgets.extend([combo, locked, remove])
        if not assets:
            ttk.Label(self.group_pie_asset_inner, text="资产区还没有资产。请在左侧资产列表多选后点击“加入左侧选中资产”。", foreground="#64748b").grid(
                row=1, column=0, columnspan=5, sticky="w", pady=(8, 0)
            )
        self._bind_mousewheel_area(self.group_pie_asset_inner, self.group_pie_asset_canvas)

    def add_selected_assets_to_group_pie(self) -> None:
        selected_ids = self._selected_asset_ids_from_list()
        if not selected_ids:
            messagebox.showinfo("请选择资产", "请先在左侧资产列表中选择一个或多个资产。", parent=self)
            return
        for asset_id in selected_ids:
            if asset_id not in self.group_pie_asset_ids:
                self.group_pie_asset_ids.append(asset_id)
        self._refresh_group_pie()
        self.show_group_pie_window()

    def remove_group_pie_asset(self, asset_id: str) -> None:
        if asset_id in self.group_pie_asset_ids:
            self.group_pie_asset_ids.remove(asset_id)
        self.group_pie_asset_groups.pop(asset_id, None)
        self.group_pie_asset_locked.pop(asset_id, None)
        self._refresh_group_pie()

    def clear_group_pie_assets(self) -> None:
        if self.group_pie_asset_ids and not messagebox.askyesno("确认清空", "确认清空分组补pie资产区吗？组别本身会保留。", parent=self):
            return
        self.group_pie_asset_ids.clear()
        self.group_pie_asset_groups.clear()
        self.group_pie_asset_locked.clear()
        self._refresh_group_pie()

    def _parse_group_pie_inputs(self):
        try:
            injection = Decimal(self.group_pie_injection_var.get().strip())
        except Exception:
            messagebox.showerror("金额无效", "请输入有效的新注资金额。", parent=self)
            return None
        if not self.group_pie_targets:
            messagebox.showinfo("无法计算", "请先添加至少一个组别。", parent=self)
            return None

        group_targets: dict[str, Decimal] = {}
        for name, variable in self.group_pie_targets.items():
            try:
                group_targets[name] = Decimal(variable.get().strip())
            except Exception:
                messagebox.showerror("组配比无效", f"请检查组别「{name}」的目标配比。", parent=self)
                return None
        target_sum = sum(group_targets.values(), Decimal("0"))
        if target_sum <= 0:
            messagebox.showerror("组配比无效", "组配比合计必须大于 0。", parent=self)
            return None

        grouped_assets: dict[str, list[Asset]] = {name: [] for name in group_targets}
        current_values: dict[str, Decimal] = {}
        for asset in self._group_pie_assets():
            group_var = self.group_pie_asset_groups.get(asset.id)
            group = group_var.get() if group_var else ""
            if not group:
                continue
            if group not in grouped_assets:
                continue
            value = self._asset_cny_value_or_none(asset)
            if value is None:
                messagebox.showerror("无法计算", "请先点击“更新等价值”，确保已分组资产都有人民币等价值。", parent=self)
                return None
            grouped_assets[group].append(asset)
            current_values[asset.id] = value
        if not any(grouped_assets.values()):
            messagebox.showinfo("无法计算", "请先把至少一个资产分配到组别。", parent=self)
            return None

        warnings = []
        if injection <= 0:
            warnings.append("新注资金额为 0 或负数，本次将按重配置/卖出计算。")
        if any(target < 0 for target in group_targets.values()):
            warnings.append("组配比包含负数，本次将按做空组目标计算。")
        if abs(target_sum - Decimal("100")) > Decimal("0.01"):
            warnings.append(f"组配比合计为 {target_sum.quantize(Decimal('0.01'))}%，将自动归一化后计算。")
        if warnings and not messagebox.askyesno("确认分组补pie计算", "\n\n".join(warnings) + "\n\n确认继续计算吗？", parent=self):
            return None
        return injection, group_targets, grouped_assets, current_values

    def calculate_group_pie(self) -> None:
        parsed = self._parse_group_pie_inputs()
        if parsed is None:
            return
        injection, group_targets, grouped_assets, current_values = parsed
        self.group_pie_result_tree.delete(*self.group_pie_result_tree.get_children())

        target_sum = sum(group_targets.values(), Decimal("0"))
        current_total = sum(current_values.values(), Decimal("0"))
        final_total = current_total + injection
        if final_total < 0:
            messagebox.showerror("无法计算", f"卖出金额不能超过已分组资产总额。当前总额为 {self._format_cny(current_total)}。", parent=self)
            return

        suggestions: dict[str, Decimal] = {asset_id: Decimal("0") for asset_id in current_values}
        group_rows: dict[str, tuple[Decimal, Decimal, Decimal, Decimal]] = {}
        exact = True
        for group_name, assets in grouped_assets.items():
            group_current = sum((current_values[asset.id] for asset in assets), Decimal("0"))
            target_ratio = group_targets[group_name] / target_sum
            desired = final_total * target_ratio
            adjustment = desired - group_current
            movable = [
                asset
                for asset in assets
                if not (self.group_pie_asset_locked.get(asset.id).get() if self.group_pie_asset_locked.get(asset.id) else False)
            ]
            applied = Decimal("0")
            if movable and adjustment != 0:
                movable_total = sum((current_values[asset.id] for asset in movable), Decimal("0"))
                if adjustment > 0:
                    base_total = movable_total if movable_total > 0 else Decimal(len(movable))
                    for asset in movable:
                        weight = current_values[asset.id] if movable_total > 0 else Decimal("1")
                        value = adjustment * weight / base_total
                        suggestions[asset.id] += value
                        applied += value
                else:
                    sell_capacity = movable_total
                    sell_amount = min(-adjustment, sell_capacity)
                    if sell_amount < -adjustment:
                        exact = False
                    if sell_amount > 0 and movable_total > 0:
                        for asset in movable:
                            value = -sell_amount * current_values[asset.id] / movable_total
                            suggestions[asset.id] += value
                            applied += value
            elif adjustment != 0:
                exact = False
            if applied != adjustment:
                exact = False
            group_rows[group_name] = (group_current, target_ratio * Decimal("100"), applied, group_current + applied)

        for group_name, assets in grouped_assets.items():
            group_current, target_percent, applied, group_final = group_rows[group_name]
            final_percent = (group_final / final_total * Decimal("100")) if final_total > 0 else Decimal("0")
            group_note = "按目标达成" if applied == (final_total * group_targets[group_name] / target_sum - group_current) else "受不可动限制"
            parent_id = self.group_pie_result_tree.insert(
                "",
                "end",
                text=group_name,
                values=(
                    self._format_cny(group_current),
                    f"{target_percent.quantize(Decimal('0.01'))}%",
                    self._format_cny(applied),
                    self._format_cny(group_final),
                    f"{final_percent.quantize(Decimal('0.01'))}%",
                    group_note,
                ),
                open=True,
            )
            for asset in assets:
                suggested = suggestions[asset.id]
                final_value = current_values[asset.id] + suggested
                locked_var = self.group_pie_asset_locked.get(asset.id)
                locked = locked_var.get() if locked_var else False
                if locked:
                    note = "不可动"
                elif suggested > 0:
                    note = "买入/注入"
                elif suggested < 0:
                    note = "卖出/转出"
                else:
                    note = "不调整"
                self.group_pie_result_tree.insert(
                    parent_id,
                    "end",
                    text=asset.name,
                    values=(
                        self._format_cny(current_values[asset.id]),
                        "",
                        self._format_cny(suggested),
                        self._format_cny(final_value),
                        "",
                        note,
                    ),
                )

        if exact:
            self.group_pie_status_var.set("计算完成：在不改动不可动资产的前提下，组配比可以达成。")
        else:
            self.group_pie_status_var.set("计算完成：受不可动资产或可卖出额度限制，结果为尽可能靠近组配比的方案。")

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

    def _allocation_label_for_asset(self, asset: Asset, dimension: str) -> str:
        if dimension == "storage":
            return self.store.storage_type_name(asset) or "未分类"
        if dimension == "asset_type_level_1":
            level_1, _level_2 = self.store.asset_type_parts(asset)
            return level_1 or "未分类"
        if dimension == "asset_type_level_2":
            level_1, level_2 = self.store.asset_type_parts(asset)
            if level_2:
                return f"{level_1} / {level_2}" if level_1 else level_2
            return "未分二级"
        if dimension == "asset_name":
            return asset.name or "未命名资产"
        return self.store.asset_type_display(asset) or "未分类"

    def _allocation_totals_for_assets(self, currency_key: str, dimension: str) -> dict[str, Decimal]:
        totals: dict[str, Decimal] = {}
        for asset in self._filtered_assets():
            label = self._allocation_label_for_asset(asset, dimension)
            totals[label] = totals.get(label, Decimal("0")) + self.store.asset_equivalent_value(asset, currency_key)
        return totals

    def _allocation_items_for_assets(self, currency_key: str, dimension: str) -> dict[str, list[tuple[str, Decimal]]]:
        items: dict[str, list[tuple[str, Decimal]]] = {}
        for asset in self._filtered_assets():
            label = self._allocation_label_for_asset(asset, dimension)
            items.setdefault(label, []).append((asset.name, self.store.asset_equivalent_value(asset, currency_key)))
        return items

    def _filtered_allocation(self, currency_key: str = "CNY", dimension: str = "storage") -> dict[str, Decimal]:
        return self._allocation_totals_for_assets(currency_key, dimension)

    def _filtered_allocation_items(self, currency_key: str = "CNY", dimension: str = "storage") -> dict[str, list[tuple[str, Decimal]]]:
        return self._allocation_items_for_assets(currency_key, dimension)

    def show_allocation_view(self) -> None:
        try:
            self._filtered_allocation("CNY", "storage")
        except Exception as exc:
            messagebox.showerror("无法展示配比", f"请先点击“更新等价值”。\n\n{exc}", parent=self)
            return
        PieChartWindow(
            self,
            "配比查看",
            self._filtered_allocation,
            self._filtered_allocation_items,
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
            self._load_tool_configs()
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
            self._load_tool_configs()
        except Exception as exc:
            messagebox.showerror("无法导入", str(exc), parent=self)
            return
        self.selected_asset_id = None
        self.status_var.set(f"数据文件：{self.data_path}")
        self._refresh_all()

    def _save(self) -> None:
        self._sync_tool_configs()
        self.store.save(self.data_path)
        self.status_var.set(f"已保存：{self.data_path}")


def main() -> None:
    app = MoneyApp()
    app.mainloop()


if __name__ == "__main__":
    main()
