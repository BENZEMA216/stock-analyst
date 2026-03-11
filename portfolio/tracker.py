#!/usr/bin/env python3
"""
📊 马的持仓追踪器
用法: python3 tracker.py
"""

import json
import sys
import os
from datetime import datetime

try:
    import yfinance as yf
except ImportError:
    print("请先安装 yfinance: pip3 install yfinance")
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PORTFOLIO_FILE = os.path.join(SCRIPT_DIR, "portfolio.json")


def get_prices(symbols):
    """批量获取实时股价"""
    prices = {}
    for sym in symbols:
        try:
            t = yf.Ticker(sym)
            hist = t.history(period="1d")
            if not hist.empty:
                prices[sym] = float(hist["Close"].iloc[-1])
        except Exception:
            pass
    return prices


def fmt_pnl(val, currency="USD"):
    if val is None:
        return "价格待更新"
    sign = "+" if val >= 0 else ""
    sym = "$" if currency == "USD" else "HK$"
    return f"{sign}{sym}{val:,.0f}"


def fmt_cnh(val):
    if val is None:
        return ""
    sign = "+" if val >= 0 else ""
    return f"({sign}{val:,.0f} CNH)"


def main():
    with open(PORTFOLIO_FILE) as f:
        data = json.load(f)

    meta = data["meta"]
    USD = meta["usd_to_cnh"]
    HKD = meta["hkd_to_cnh"]

    # 获取所有股票实时价格
    symbols = [p["symbol"] for p in data["positions"] if p["type"] == "stock"]
    print("正在获取实时价格...", end="", flush=True)
    prices = get_prices(symbols)
    print(" ✓\n")

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"{'='*62}")
    print(f"  📊 持仓快照  {now}")
    print(f"  汇率: USD/CNH={USD}  HKD/CNH={HKD}")
    print(f"{'='*62}")

    total_pnl_cnh = 0
    total_mv_cnh = 0

    # ── 美股正股 ──────────────────────────────────────────────
    print(f"\n🇺🇸 美股正股")
    print(f"  {'标的':<22} {'现价':>8} {'数量':>6} {'成本':>8} {'浮盈亏':>12} {'CNH换算':>12}")
    print(f"  {'─'*70}")

    for pos in data["positions"]:
        if pos["type"] != "stock" or pos["currency"] != "USD":
            continue
        sym = pos["symbol"]
        qty = pos["quantity"]
        cost = pos["avg_cost"]
        cp = prices.get(sym)

        if cp:
            mv = qty * cp
            cb = qty * cost
            pnl = mv - cb
            pnl_pct = pnl / cb * 100
            pnl_cnh = pnl * USD
            total_pnl_cnh += pnl_cnh
            total_mv_cnh += mv * USD
            stop = pos.get("stop_loss")
            stop_str = f" [止损:{stop}]" if stop else ""
            sign = "▲" if pnl >= 0 else "▼"
            print(f"  {pos['name']:<22} ${cp:>7.2f} {qty:>6} ${cost:>7.3f} "
                  f"  {sign}${abs(pnl):>7,.0f}({pnl_pct:+.1f}%)  {fmt_cnh(pnl_cnh)}{stop_str}")
        else:
            print(f"  {pos['name']:<22} 价格获取失败")

    # ── 美股期权 ──────────────────────────────────────────────
    print(f"\n📋 期权持仓（last_price 需手动更新）")
    print(f"  {'标的':<34} {'成本/权利金':>10} {'最新价':>8} {'浮盈亏':>10} {'CNH换算':>12}")
    print(f"  {'─'*76}")

    for pos in data["positions"]:
        if pos["type"] not in ("short_put", "call_spread"):
            continue

        last = pos.get("last_price")
        note = ""

        if pos["type"] == "short_put":
            n = abs(pos["contracts"])
            received = pos["premium_received"]
            if last is not None:
                pnl = (received - last) * 100 * n
                pnl_cnh = pnl * USD
                total_pnl_cnh += pnl_cnh
                sign = "▲" if pnl >= 0 else "▼"
                note = f"  {sign}${abs(pnl):>6,.0f}  {fmt_cnh(pnl_cnh)}"
            else:
                note = "  价格待更新"
            print(f"  {pos['name']:<34} 收${received:>6.2f}  ${last if last else '?':>6}  {note}")

        elif pos["type"] == "call_spread":
            n = pos["contracts"]
            cost = pos["avg_cost"]
            if last is not None:
                pnl = (last - cost) * 100 * n
                pnl_cnh = pnl * USD
                total_pnl_cnh += pnl_cnh
                max_gain = (pos["short_strike"] - pos["long_strike"] - cost) * 100 * n
                sign = "▲" if pnl >= 0 else "▼"
                note = f"  {sign}${abs(pnl):>6,.0f}  {fmt_cnh(pnl_cnh)}  [max+${max_gain:.0f}]"
            else:
                note = "  价格待更新"
            print(f"  {pos['name']:<34} 成${cost:>5.2f}   ${last if last else '?':>6}  {note}")

    # ── 港股 ──────────────────────────────────────────────────
    print(f"\n🇭🇰 港股持仓")
    print(f"  {'标的':<22} {'现价':>9} {'数量':>6} {'成本':>8} {'浮盈亏':>12} {'CNH换算':>12}")
    print(f"  {'─'*72}")

    for pos in data["positions"]:
        if pos["type"] != "stock" or pos["currency"] != "HKD":
            continue
        sym = pos["symbol"]
        qty = pos["quantity"]
        cost = pos["avg_cost"]
        cp = prices.get(sym)

        if cp:
            mv = qty * cp
            cb = qty * cost
            pnl = mv - cb
            pnl_pct = pnl / cb * 100
            pnl_cnh = pnl * HKD
            total_pnl_cnh += pnl_cnh
            total_mv_cnh += mv * HKD
            sign = "▲" if pnl >= 0 else "▼"
            print(f"  {pos['name']:<22} HK${cp:>7.2f} {qty:>6} ${cost:>7.3f} "
                  f"  {sign}HK${abs(pnl):>7,.0f}({pnl_pct:+.1f}%)  {fmt_cnh(pnl_cnh)}")
        else:
            print(f"  {pos['name']:<22} 价格获取失败")

    # ── 加密 ──────────────────────────────────────────────────
    crypto_usd = sum(c["value_usd"] for c in data.get("crypto", []))
    crypto_cnh = crypto_usd * USD

    # ── 总结 ──────────────────────────────────────────────────
    print(f"\n{'='*62}")
    sign = "+" if total_pnl_cnh >= 0 else ""
    print(f"  📈 持仓总浮盈亏:  {sign}{total_pnl_cnh:,.0f} CNH")
    print(f"  🪙 加密资产:      ~${crypto_usd:,.0f} USD  (~{crypto_cnh:,.0f} CNH)")
    print(f"  ⚠️  期权价格为手动录入，盈亏仅供参考")
    if data["meta"].get("note"):
        print(f"  📌 {data['meta']['note']}")
    print(f"{'='*62}\n")


if __name__ == "__main__":
    main()
