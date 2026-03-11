"""
data.py — 统一数据层
US股 → yfinance
HK股 → AKShare stock_hk_hist（主）/ mootdx（备）
"""

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional


# ─────────────────────────────────────────────
# US 股：yfinance
# ─────────────────────────────────────────────

def get_us_history(symbol: str, days: int = 90) -> pd.DataFrame:
    import yfinance as yf
    tk = yf.Ticker(symbol)
    df = tk.history(period=f"{days}d")[["Open","High","Low","Close","Volume"]]
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df.columns = ["开盘","最高","最低","收盘","成交量"]
    return df


def get_us_price(symbol: str) -> dict:
    df = get_us_history(symbol, days=5)
    price = df["收盘"].iloc[-1]
    log_ret = np.log(df["收盘"] / df["收盘"].shift(1)).dropna()
    sigma = float(log_ret.std() * np.sqrt(252))
    prev = df["收盘"].iloc[-2]
    return {
        "symbol": symbol,
        "price": float(price),
        "change_pct": float((price - prev) / prev * 100),
        "sigma_annual": sigma,
        "source": "yfinance",
    }


# ─────────────────────────────────────────────
# HK 股：AKShare
# ─────────────────────────────────────────────

def get_hk_history(code: str, days: int = 90) -> pd.DataFrame:
    """
    code: 5位数字，如 '09988', '01810', '00100'
    """
    import akshare as ak
    end = datetime.today().strftime("%Y%m%d")
    start = (datetime.today() - timedelta(days=days+10)).strftime("%Y%m%d")
    df = ak.stock_hk_hist(symbol=code, period="daily",
                          start_date=start, end_date=end, adjust="")
    df = df.rename(columns={"日期":"date","开盘":"开盘","收盘":"收盘",
                             "最高":"最高","最低":"最低","成交量":"成交量",
                             "成交额":"成交额","涨跌幅":"涨跌幅"})
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df.tail(days)


def get_hk_price(code: str) -> dict:
    try:
        df = get_hk_history(code, days=10)
        price = float(df["收盘"].iloc[-1])
        prev  = float(df["收盘"].iloc[-2]) if len(df) > 1 else price
        log_ret = np.log(df["收盘"] / df["收盘"].shift(1)).dropna()
        sigma = float(log_ret.std() * np.sqrt(252)) if len(log_ret) >= 5 else 0.40
        chg = (price - prev) / prev * 100
        vol = float(df["成交额"].iloc[-1]) if "成交额" in df.columns else None
        return {
            "code": code,
            "price": price,
            "change_pct": chg,
            "sigma_annual": sigma,
            "volume_hkd": vol,
            "source": "akshare",
        }
    except Exception as e:
        return {"code": code, "error": str(e)[:100], "source": "akshare_failed"}


# ─────────────────────────────────────────────
# mootdx：A股 tick 级数据（备用）
# ─────────────────────────────────────────────

def get_ashare_quote(code: str) -> dict:
    """
    code: 6位A股代码，如 '600519'（茅台）
    返回实时报价（通达信协议）
    """
    try:
        from mootdx.quotes import Quotes
        client = Quotes.factory(market="std", multithread=True, heartbeat=True)
        market = 1 if code.startswith("6") else 0  # 0=深 1=沪
        result = client.quote(market=market, code=code)
        client.close()
        if result:
            q = result[0]
            return {
                "code": code,
                "price": q.get("price", 0),
                "open": q.get("open", 0),
                "high": q.get("high", 0),
                "low": q.get("low", 0),
                "volume": q.get("vol", 0),
                "change_pct": q.get("price_diff", 0),
                "source": "mootdx",
            }
    except Exception as e:
        return {"code": code, "error": str(e)[:100], "source": "mootdx_failed"}
    return {"code": code, "error": "no data", "source": "mootdx_failed"}


# ─────────────────────────────────────────────
# 便捷：快照我们的完整持仓
# ─────────────────────────────────────────────

PORTFOLIO_SYMBOLS = {
    "US":  ["NVDA", "MSFT"],
    "HK":  {"09988": "阿里", "01810": "小米", "00100": "MiniMax", "00883": "中海油"},
}

def snapshot_portfolio() -> dict:
    result = {"us": {}, "hk": {}, "ts": datetime.now().isoformat()}

    print("📡 拉取实时行情...")
    for sym in PORTFOLIO_SYMBOLS["US"]:
        try:
            result["us"][sym] = get_us_price(sym)
            p = result["us"][sym]
            print(f"  {sym}: ${p['price']:.2f} ({p['change_pct']:+.2f}%) σ={p['sigma_annual']:.1%}")
        except Exception as e:
            result["us"][sym] = {"error": str(e)[:80]}

    for code, name in PORTFOLIO_SYMBOLS["HK"].items():
        try:
            result["hk"][code] = get_hk_price(code)
            p = result["hk"][code]
            if "error" not in p:
                vol_str = f"成交{p['volume_hkd']/1e8:.1f}亿" if p.get("volume_hkd") else ""
                print(f"  {name} {code}: HK${p['price']:.2f} ({p['change_pct']:+.2f}%) {vol_str}")
            else:
                print(f"  {name} {code}: ❌ {p['error'][:60]}")
        except Exception as e:
            result["hk"][code] = {"error": str(e)[:80]}

    return result


if __name__ == "__main__":
    snap = snapshot_portfolio()
