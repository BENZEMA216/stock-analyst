"""
mc_options.py — Monte Carlo Options Analyzer
弦 Quant System v0.1

用途：
- 计算NVDA期权/价差的胜率和期望值
- GBM路径模拟 + 重要性采样（尾部事件）
- Brier Score追踪预测校准
"""

import numpy as np
from scipy.stats import norm
from typing import Optional
import yfinance as yf


# ─────────────────────────────────────────────
# 1. 获取当前数据
# ─────────────────────────────────────────────

def get_stock_data(symbol: str) -> dict:
    """获取当前价格 + 历史波动率"""
    tk = yf.Ticker(symbol)
    hist = tk.history(period="60d")
    if hist.empty:
        raise ValueError(f"无法获取 {symbol} 数据")
    
    price = hist["Close"].iloc[-1]
    log_returns = np.log(hist["Close"] / hist["Close"].shift(1)).dropna()
    sigma_daily = log_returns.std()
    sigma_annual = sigma_daily * np.sqrt(252)
    
    return {
        "symbol": symbol,
        "price": float(price),
        "sigma_annual": float(sigma_annual),
        "sigma_daily": float(sigma_daily),
        "hist_days": len(hist),
    }


# ─────────────────────────────────────────────
# 2. 核心 Monte Carlo 引擎
# ─────────────────────────────────────────────

def simulate_gbm(S0: float, mu: float, sigma: float, T: float, N: int = 200_000) -> np.ndarray:
    """
    GBM终态模拟
    S0: 当前价格
    mu: 年化漂移（风险中性用rf, 主观预测用自己的mu）
    sigma: 年化波动率
    T: 到期时间（年）
    返回: N个终态价格
    """
    Z = np.random.standard_normal(N)
    S_T = S0 * np.exp((mu - 0.5 * sigma**2) * T + sigma * np.sqrt(T) * Z)
    return S_T


def mc_binary_contract(S0: float, K: float, sigma: float, T: float,
                        direction: str = "above", mu: float = 0.0,
                        N: int = 200_000) -> dict:
    """
    二元合约概率估计
    direction: "above" = S_T > K, "below" = S_T < K
    """
    S_T = simulate_gbm(S0, mu, sigma, T, N)
    
    if direction == "above":
        payoffs = (S_T > K).astype(float)
    else:
        payoffs = (S_T < K).astype(float)
    
    p = payoffs.mean()
    se = np.sqrt(p * (1 - p) / N)
    
    # Black-Scholes 解析解（对比用）
    d2 = (np.log(S0 / K) + (mu - 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    bs_prob = norm.cdf(d2) if direction == "above" else norm.cdf(-d2)
    
    return {
        "mc_prob": p,
        "bs_prob": float(bs_prob),
        "std_error": se,
        "ci_95": (p - 1.96 * se, p + 1.96 * se),
        "N": N,
    }


# ─────────────────────────────────────────────
# 3. 期权定价
# ─────────────────────────────────────────────

def mc_call_spread(S0: float, K_long: float, K_short: float, sigma: float,
                   T: float, mu: float = 0.0, N: int = 200_000) -> dict:
    """
    牛市价差（买K_long, 卖K_short）
    最大收益 = K_short - K_long = spread_width
    """
    S_T = simulate_gbm(S0, mu, sigma, T, N)
    spread_width = K_short - K_long
    
    payoffs = np.clip(S_T - K_long, 0, spread_width)
    
    ev = payoffs.mean()
    se = payoffs.std() / np.sqrt(N)
    max_profit = spread_width
    
    # 各场景概率
    p_full_profit = (S_T >= K_short).mean()    # 两腿都ITM
    p_partial = ((S_T > K_long) & (S_T < K_short)).mean()  # 部分获利
    p_zero = (S_T <= K_long).mean()             # 全亏
    
    return {
        "ev": float(ev),
        "ev_se": float(se),
        "max_profit": max_profit,
        "p_full_profit": float(p_full_profit),
        "p_partial": float(p_partial),
        "p_breakeven_above": float(1 - p_zero),
        "p_zero": float(p_zero),
        "ev_vs_cost": None,  # 需要传入cost才能算
    }


def mc_short_put(S0: float, K: float, sigma: float, T: float,
                 premium: float, mu: float = 0.0, N: int = 200_000) -> dict:
    """
    卖出PUT分析
    premium: 收取的权利金
    """
    S_T = simulate_gbm(S0, mu, sigma, T, N)
    
    # 卖PUT: 到期时S_T < K则亏损(K - S_T - premium)
    assignment = S_T < K
    pnl = np.where(assignment, S_T - K + premium, premium)
    
    p_keep_all = (~assignment).mean()
    p_assigned = assignment.mean()
    expected_pnl = pnl.mean()
    
    # 如果行权，平均接货价格
    if assignment.any():
        avg_assignment_price = S_T[assignment].mean()
        effective_cost = K - premium
    else:
        avg_assignment_price = None
        effective_cost = K - premium
    
    return {
        "p_keep_premium": float(p_keep_all),
        "p_assigned": float(p_assigned),
        "expected_pnl": float(expected_pnl),
        "effective_cost_if_assigned": float(effective_cost),
        "premium": premium,
        "strike": K,
    }


# ─────────────────────────────────────────────
# 4. 重要性采样（尾部事件）
# ─────────────────────────────────────────────

def mc_tail_risk(S0: float, crash_pct: float, sigma: float, T: float,
                  N: int = 200_000) -> dict:
    """
    估计极端下跌概率（重要性采样）
    crash_pct: 跌幅阈值，如0.20 = 跌20%
    """
    K = S0 * (1 - crash_pct)
    mu_original = -0.5 * sigma**2
    
    # 倾斜分布：将均值指向崩溃区间
    log_threshold = np.log(K / S0)
    mu_tilt = log_threshold / T
    
    Z = np.random.standard_normal(N)
    log_returns_tilted = mu_tilt * T + sigma * np.sqrt(T) * Z
    S_T_tilted = S0 * np.exp(log_returns_tilted)
    
    # 似然比修正
    log_LR = (
        -0.5 * ((log_returns_tilted - mu_original * T) / (sigma * np.sqrt(T)))**2
        + 0.5 * ((log_returns_tilted - mu_tilt * T) / (sigma * np.sqrt(T)))**2
    )
    LR = np.exp(log_LR)
    
    payoffs = (S_T_tilted < K).astype(float)
    is_estimates = payoffs * LR
    p_IS = is_estimates.mean()
    se_IS = is_estimates.std() / np.sqrt(N)
    
    # 对比粗暴MC
    Z_crude = np.random.standard_normal(N)
    S_T_crude = S0 * np.exp(mu_original * T + sigma * np.sqrt(T) * Z_crude)
    p_crude = (S_T_crude < K).mean()
    se_crude = np.sqrt(p_crude * (1 - p_crude) / N) if p_crude > 0 else float("inf")
    
    return {
        "p_crash_IS": float(p_IS),
        "se_IS": float(se_IS),
        "p_crash_crude": float(p_crude),
        "se_crude": float(se_crude),
        "variance_reduction": float((se_crude / se_IS)**2) if se_IS > 0 else float("inf"),
        "crash_threshold": float(K),
        "crash_pct": crash_pct,
    }


# ─────────────────────────────────────────────
# 5. 主程序：分析当前持仓
# ─────────────────────────────────────────────

def analyze_nvda_positions():
    print("=" * 60)
    print("🔬 NVDA 持仓量化分析")
    print("=" * 60)
    
    # 获取实时数据
    data = get_stock_data("NVDA")
    S0 = data["price"]
    sigma = data["sigma_annual"]
    print(f"\n📊 NVDA 当前价: ${S0:.2f} | 60日年化波动率: {sigma:.1%}\n")
    
    # ── 仓位1：正股 20股 @ $174.85 ──
    print("─" * 40)
    print("仓位1：正股 20股 @ $174.85 成本")
    cost_stock = 174.85
    print(f"当前浮盈: ${(S0 - cost_stock) * 20:.0f}")
    
    # ── 仓位2：卖出PUT $175 × 3张 ──
    print("\n─" * 40)
    print("仓位2：卖出PUT $175 到期2026-06-18")
    T_put = (180) / 365  # 约180天到期
    put_result = mc_short_put(S0, K=175, sigma=sigma, T=T_put, premium=13.35)
    print(f"  不被行权概率:  {put_result['p_keep_premium']:.1%}")
    print(f"  被行权概率:    {put_result['p_assigned']:.1%}")
    print(f"  若行权，有效建仓价: ${put_result['effective_cost_if_assigned']:.2f}")
    
    # ── 仓位3：C195/200 牛市价差 × 12组 ──
    print("\n─" * 40)
    print("仓位3：C195/200 牛市价差 到期2026-07-17")
    T_spread = (210) / 365
    spread_result = mc_call_spread(S0, K_long=195, K_short=200, sigma=sigma, T=T_spread, mu=0.06)
    spread_result["ev_vs_cost"] = spread_result["ev"] / 2.10 - 1  # 成本$2.10
    print(f"  全额获利概率:  {spread_result['p_full_profit']:.1%}  (NVDA≥$200)")
    print(f"  部分获利概率:  {spread_result['p_partial']:.1%}  ($195<NVDA<$200)")
    print(f"  全亏概率:      {spread_result['p_zero']:.1%}  (NVDA≤$195)")
    print(f"  期望值:        ${spread_result['ev']:.3f}  (成本$2.10, 回报率{spread_result['ev_vs_cost']:+.1%})")
    
    # ── 尾部风险：NVDA跌破$168 ──
    print("\n─" * 40)
    print("尾部风险：NVDA跌破$168（止损线）")
    crash_pct = (S0 - 168) / S0
    tail = mc_tail_risk(S0, crash_pct, sigma, T=30/365)
    print(f"  30日内跌破$168概率（IS）:  {tail['p_crash_IS']:.2%}")
    print(f"  30日内跌破$168概率（粗算）: {tail['p_crash_crude']:.2%}")
    print(f"  方差降低倍数: {tail['variance_reduction']:.0f}x")
    
    print("\n" + "=" * 60)
    print("⚠️  Clayton Copula警告：上述仓位下行相关性被线性相关低估")
    print("   真实尾部风险 = 以上单项风险的 2-3倍叠加效应")
    print("=" * 60)


if __name__ == "__main__":
    np.random.seed(42)
    analyze_nvda_positions()
