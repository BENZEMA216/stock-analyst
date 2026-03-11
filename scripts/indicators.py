#!/usr/bin/env python3
"""
indicators.py — 五大观测指标 + 个股实时行情
用法: python scripts/indicators.py [--symbols NVDA TSLA ...]
      python scripts/indicators.py --proxy http://127.0.0.1:7890
"""

import argparse
import json
import urllib.request
import urllib.error
from datetime import datetime


# ── 配置 ───────────────────────────────────────────────────────────
FIVE_INDICATORS = {
    "^VIX":  "VIX恐慌",
    "IGV":   "IGV软件",
    "MAGS":  "MAGS七巨",
    "MEME":  "MEME散户",
    "BZ=F":  "布伦特油",
}

DEFAULT_STOCKS = {
    "NQ=F":   "纳指期指",
    "ES=F":   "标普期指",
    "NVDA":   "NVDA",
    "TSLA":   "TSLA",
    "GOOGL":  "GOOGL",
    "AMZN":   "AMZN",
    "MSFT":   "MSFT",
    "AAPL":   "AAPL",
    "BRK-B":  "BRK-B",
}

# 信号阈值
THRESHOLDS = {
    "^VIX": {"danger": 27, "healthy": 20},
    "IGV":  {"danger": 82, "healthy": 85},
    "MAGS": {"danger": 60, "healthy": 62},
    "BZ=F": {"danger": 90, "healthy": 80},
}


# ── 数据获取 ────────────────────────────────────────────────────────
def fetch_yahoo(symbol: str, proxy: str = None, days: int = 5) -> dict:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range={days}d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        if proxy:
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({"http": proxy, "https": proxy})
            )
        else:
            opener = urllib.request.build_opener()
        resp = opener.open(req, timeout=10)
        return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def parse_quote(symbol: str, data: dict) -> dict | None:
    if "error" in data:
        return {"symbol": symbol, "error": data["error"]}
    try:
        result = data["chart"]["result"][0]
        meta = result["meta"]
        closes = [c for c in result["indicators"]["quote"][0]["close"] if c is not None]
        if not closes:
            return None
        cur = meta.get("regularMarketPrice", closes[-1])
        prev = closes[-2] if len(closes) >= 2 else closes[-1]
        chg_pct = (cur - prev) / prev * 100
        return {
            "symbol": symbol,
            "price": round(cur, 2),
            "prev_close": round(prev, 2),
            "change_pct": round(chg_pct, 2),
        }
    except Exception as e:
        return {"symbol": symbol, "error": str(e)}


# ── 信号判断 ────────────────────────────────────────────────────────
def signal(symbol: str, price: float, chg: float) -> str:
    t = THRESHOLDS.get(symbol)
    if symbol == "^VIX":
        if price > 30:   return "🔴 崩盘预警"
        if price > 27:   return "🟠 看空"
        if price > 22:   return "🟡 警惕"
        return "🟢 健康"
    if symbol == "IGV":
        if price > 85:   return "🟢 右侧确认"
        if price > 82:   return "🟡 临界"
        return "🔴 弱势"
    if symbol == "MAGS":
        if price > 62:   return "🟢 修复中"
        if price > 60:   return "🟡 支撑"
        return "🔴 关键支撑破位"
    if symbol == "MEME":
        if chg > 2:      return "🟢 risk-on"
        if chg > 0:      return "🟡 中性"
        return "🔴 散户撤退"
    if symbol == "BZ=F":
        if price > 90:   return "🔴 通胀冲击"
        if price > 80:   return "🟡 留意"
        return "🟢 压力缓解"
    return ""


# ── 输出 ────────────────────────────────────────────────────────────
def print_indicators(quotes: list[dict]):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n{'='*60}")
    print(f"  📊 五大观测指标  {now}")
    print(f"{'='*60}")
    print(f"  {'指标':<10} {'代码':<8} {'价格':>8} {'涨跌':>8}  信号")
    print(f"  {'─'*54}")
    for q in quotes:
        sym = q["symbol"]
        name = FIVE_INDICATORS.get(sym, sym)
        if "error" in q:
            print(f"  {name:<10} {sym:<8} {'ERROR':>8}")
            continue
        price = q["price"]
        chg = q["change_pct"]
        sig = signal(sym, price, chg)
        print(f"  {name:<10} {sym:<8} {price:>8.2f} {chg:>+7.2f}%  {sig}")
    print()


def print_stocks(quotes: list[dict], names: dict):
    print(f"{'─'*60}")
    print(f"  📈 个股行情")
    print(f"  {'名称':<10} {'代码':<8} {'价格':>9} {'涨跌':>8}")
    print(f"  {'─'*40}")
    for q in quotes:
        sym = q["symbol"]
        name = names.get(sym, sym)
        if "error" in q:
            print(f"  {name:<10} {sym:<8} {'ERROR':>9}")
            continue
        price = q["price"]
        chg = q["change_pct"]
        arrow = "▲" if chg >= 0 else "▼"
        print(f"  {name:<10} {sym:<8} {price:>9.2f} {arrow}{abs(chg):>6.2f}%")
    print()


# ── 主流程 ──────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="五大指标 + 个股行情抓取器")
    parser.add_argument("--proxy", default=None, help="HTTP代理，如 http://127.0.0.1:7890")
    parser.add_argument("--symbols", nargs="*", help="额外个股代码，如 NVDA TSLA")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    args = parser.parse_args()

    # 合并额外股票
    stocks = dict(DEFAULT_STOCKS)
    if args.symbols:
        for s in args.symbols:
            stocks[s] = s

    # 抓取五大指标
    ind_quotes = []
    for sym in FIVE_INDICATORS:
        data = fetch_yahoo(sym, proxy=args.proxy)
        q = parse_quote(sym, data)
        if q:
            ind_quotes.append(q)

    # 抓取个股
    stock_quotes = []
    for sym in stocks:
        data = fetch_yahoo(sym, proxy=args.proxy)
        q = parse_quote(sym, data)
        if q:
            stock_quotes.append(q)

    if args.json:
        print(json.dumps({"indicators": ind_quotes, "stocks": stock_quotes}, ensure_ascii=False, indent=2))
        return

    print_indicators(ind_quotes)
    print_stocks(stock_quotes, stocks)


if __name__ == "__main__":
    main()
