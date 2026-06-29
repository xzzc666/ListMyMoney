from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from decimal import Decimal
from urllib.request import Request, urlopen

from .models import money


SINA_HEADERS = {
    "Referer": "https://finance.sina.com.cn/",
    "User-Agent": "Mozilla/5.0",
}


@dataclass(frozen=True)
class MarketRates:
    gbp_to_cny: Decimal
    cny_to_gbp: Decimal
    gold_cny_per_gram: Decimal
    source: str


def normalize_currency(currency: str) -> str:
    raw = currency.strip()
    upper = raw.upper()
    compact = re.sub(r"[\s_\-（）()]+", "", upper)

    cny_aliases = {"CNY", "RMB", "人民币", "人民币元", "元"}
    gbp_aliases = {"GBP", "英镑"}
    gold_aliases = {
        "G",
        "GRAM",
        "GRAMS",
        "GOLD",
        "XAU",
        "黄金",
        "黄金G",
        "黄金克",
        "实体黄金",
        "实体黄金G",
        "实体黄金克",
    }

    if upper in cny_aliases or compact in cny_aliases:
        return "CNY"
    if upper in gbp_aliases or compact in gbp_aliases:
        return "GBP"
    if upper in gold_aliases or compact in gold_aliases:
        return "GOLD"
    if "实体黄金" in raw or "黄金" in raw:
        return "GOLD"
    return upper


def fetch_sina_quote(symbol: str) -> list[str]:
    request = Request(f"https://hq.sinajs.cn/list={symbol}", headers=SINA_HEADERS)
    with urlopen(request, timeout=10) as response:
        text = response.read().decode("gb18030", errors="replace")
    try:
        payload = text.split('"', 2)[1]
    except IndexError as exc:
        raise ValueError(f"Cannot parse Sina quote for {symbol}") from exc
    if not payload:
        raise ValueError(f"Empty Sina quote for {symbol}")
    return next(csv.reader([payload]))


def fetch_sina_gbp_cny() -> Decimal:
    fields = fetch_sina_quote("fx_sgbpcny")
    if len(fields) < 2:
        raise ValueError("Cannot parse GBP/CNY quote")
    return money(fields[1])


def fetch_sina_gold_cny_per_gram() -> Decimal:
    fields = fetch_sina_quote("SGE_AUTD")
    if len(fields) < 4:
        raise ValueError("Cannot parse SGE Au(T+D) quote")
    return money(fields[3])


def fetch_market_rates() -> MarketRates:
    gbp_to_cny = fetch_sina_gbp_cny()
    gold_cny_per_gram = fetch_sina_gold_cny_per_gram()
    return MarketRates(
        gbp_to_cny=gbp_to_cny,
        cny_to_gbp=Decimal("1") / gbp_to_cny,
        gold_cny_per_gram=gold_cny_per_gram,
        source="新浪财经 fx_sgbpcny + SGE_AUTD",
    )


def cny_value(amount: Decimal, currency: str, rates: MarketRates) -> Decimal:
    normalized = normalize_currency(currency)
    if normalized == "CNY":
        return amount
    if normalized == "GBP":
        return amount * rates.gbp_to_cny
    if normalized == "GOLD":
        return amount * rates.gold_cny_per_gram
    raise ValueError(f"Unsupported currency for valuation: {currency}")


def equivalent_values(amount: Decimal, currency: str, rates: MarketRates) -> dict[str, Decimal]:
    value_cny = cny_value(amount, currency, rates)
    return {
        "CNY": value_cny,
        "GBP": value_cny * rates.cny_to_gbp,
        "GOLD_GRAM": value_cny / rates.gold_cny_per_gram,
    }
