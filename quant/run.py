"""
run.py — 量化系统主入口
每日晨跑：拉行情 → MC期权分析 → Copula VaR → 事件概率状态
"""

import numpy as np
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from data import snapshot_portfolio
from mc_options import analyze_nvda_positions
from copula_var import run_risk_report
from particle_filter import init_events


def main():
    np.random.seed(None)

    print("\n" + "🔬 " * 20)
    print("  弦 Quant System — 每日风控报告")
    print("🔬 " * 20 + "\n")

    # 1. 实时行情快照
    snap = snapshot_portfolio()

    # 提取价格
    us = snap.get("us", {})
    hk = snap.get("hk", {})
    prices = {
        "NVDA":  us.get("NVDA", {}).get("price", 179.0),
        "MSFT":  us.get("MSFT", {}).get("price", 405.0),
        "09988": hk.get("09988", {}).get("price", 139.0),
        "01810": hk.get("01810", {}).get("price", 34.0),
        "00100": hk.get("00100", {}).get("price", 752.0),
    }
    sigmas = {
        "NVDA":  us.get("NVDA", {}).get("sigma_annual", 0.48),
        "MSFT":  us.get("MSFT", {}).get("sigma_annual", 0.27),
        "09988": hk.get("09988", {}).get("sigma_annual", 0.38),
        "01810": hk.get("01810", {}).get("sigma_annual", 0.52),
        "00100": hk.get("00100", {}).get("sigma_annual", 0.90),
    }

    print()

    # 2. NVDA 期权 MC 分析（需要 NVDA 价格）
    try:
        analyze_nvda_positions()
    except Exception as e:
        print(f"⚠️  MC分析失败: {e}")

    print()

    # 3. Copula VaR
    try:
        run_risk_report(prices)
    except Exception as e:
        print(f"⚠️  Copula VaR失败: {e}")

    print()

    # 4. 事件概率追踪
    ep = init_events()
    ep.status()

    print("\n✅ 报告完成\n")


if __name__ == "__main__":
    main()
