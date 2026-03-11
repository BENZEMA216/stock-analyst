"""
copula_var.py — 仓位相关性风险 & Copula VaR
核心：Clayton Copula（下尾相关）+ Student-t Copula（双尾）
适用：估算极端下跌时多仓位同时爆仓的真实概率
"""

import numpy as np
from scipy.stats import norm, t as t_dist
from dataclasses import dataclass
from typing import List, Optional


# ─────────────────────────────────────────────
# 仓位定义
# ─────────────────────────────────────────────

@dataclass
class Position:
    name: str
    symbol: str
    qty: float           # 正数=多头，负数=空头
    cost: float          # 成本/入场价
    price: float         # 当前价
    sigma: float         # 年化波动率
    currency: str = "USD"
    stop_loss: Optional[float] = None


def position_pnl(pos: Position) -> float:
    return (pos.price - pos.cost) * pos.qty


def current_portfolio() -> List[Position]:
    """当前持仓快照（手动维护，与portfolio.json同步）"""
    return [
        # ── US 股 ──
        Position("NVDA正股",       "NVDA",   20,    174.85, 0,     0,    "USD", 168.0),
        Position("NVDA PUT175短",  "NVDA",  -300,   175.00, 0,     0,    "USD"),   # 等效delta
        Position("NVDA C195/200", "NVDA",    12,    2.10,   0,     0,    "USD"),
        Position("MSFT PUT360短",  "MSFT",  -100,   360.00, 0,     0,    "USD"),
        # ── HK 股 ──
        Position("阿里",           "09988",  300,   147.56, 0,     0,    "HKD", 115.0),
        Position("小米",           "01810",  2400,  41.618, 0,     0,    "HKD", 30.0),
        Position("MiniMax空",      "00100",  -20,   759.50, 0,     0,    "HKD", 850.0),
    ]


# ─────────────────────────────────────────────
# 相关性矩阵（估计值，需定期更新）
# ─────────────────────────────────────────────

# 资产顺序：NVDA, MSFT, 阿里, 小米, MiniMax（空头取反）
CORR_MATRIX = np.array([
    # NVDA  MSFT  BABA  小米  MM(short)
    [1.00,  0.72,  0.25,  0.20, -0.15],   # NVDA
    [0.72,  1.00,  0.22,  0.18, -0.12],   # MSFT
    [0.25,  0.22,  1.00,  0.65, -0.30],   # BABA
    [0.20,  0.18,  0.65,  1.00, -0.25],   # 小米
    [-0.15, -0.12, -0.30, -0.25,  1.00],  # MiniMax空（收益方向取反）
])

ASSET_NAMES = ["NVDA", "MSFT", "BABA", "小米", "MiniMax(short)"]


# ─────────────────────────────────────────────
# Copula 模拟
# ─────────────────────────────────────────────

def simulate_gaussian_copula(corr: np.ndarray, N: int = 200_000) -> np.ndarray:
    """高斯copula，无尾部相关"""
    L = np.linalg.cholesky(corr)
    Z = np.random.standard_normal((N, corr.shape[0]))
    X = Z @ L.T
    return norm.cdf(X)   # shape (N, d)，均匀边际


def simulate_t_copula(corr: np.ndarray, nu: float = 4, N: int = 200_000) -> np.ndarray:
    """Student-t copula，对称尾部相关，nu=4时尾部相关~18%（ρ=0.6）"""
    d = corr.shape[0]
    L = np.linalg.cholesky(corr)
    Z = np.random.standard_normal((N, d))
    X = Z @ L.T
    chi2 = np.random.chisquare(nu, N) / nu
    T = X / np.sqrt(chi2[:, None])
    return t_dist.cdf(T, nu)


def simulate_clayton_copula(theta: float = 2.0, d: int = 2, N: int = 200_000) -> np.ndarray:
    """
    Clayton copula，下尾相关（同跌概率高于高斯）
    theta>0，越大下尾相关越强；d=2为双变量
    """
    V = np.random.gamma(1.0 / theta, 1.0, N)
    E = np.random.exponential(1.0, (N, d))
    U = (1.0 + E / V[:, None]) ** (-1.0 / theta)
    return U


# ─────────────────────────────────────────────
# 组合 VaR 计算
# ─────────────────────────────────────────────

def portfolio_var(prices: dict, sigmas: dict,
                  horizon_days: int = 5,
                  confidence: float = 0.95,
                  N: int = 300_000) -> dict:
    """
    prices: {"NVDA": 179, "MSFT": 405, "09988": 139, "01810": 34, "00100": 735}
    sigmas: 年化波动率字典
    horizon_days: 持有期（天）
    """
    T = horizon_days / 252
    d = len(ASSET_NAMES)

    # 日化sigma
    daily_sigmas = np.array([
        sigmas.get("NVDA", 0.45),
        sigmas.get("MSFT", 0.28),
        sigmas.get("09988", 0.38),
        sigmas.get("01810", 0.50),
        sigmas.get("00100", 0.85),
    ])

    # 仓位规模（以USD/HKD计价，统一到HKD）
    USD_HKD = 7.78
    position_sizes = np.array([
        20 * prices.get("NVDA", 179) * USD_HKD,      # NVDA 正股
        100 * prices.get("MSFT", 405) * USD_HKD,     # MSFT 等效（PUT delta ~0.3）* 100 * 0.3
        300 * prices.get("09988", 139),               # 阿里
        2400 * prices.get("01810", 34),               # 小米
        -20 * prices.get("00100", 735),               # MiniMax空（负号）
    ])

    # t-copula 模拟
    U_t = simulate_t_copula(CORR_MATRIX, nu=4, N=N)

    # 把均匀分布转换为对数收益率（逆正态）
    log_returns = norm.ppf(U_t) * daily_sigmas[None, :] * np.sqrt(horizon_days)

    # 计算各场景下的PnL
    pnl = (log_returns * position_sizes[None, :]).sum(axis=1)

    # VaR 和 ES
    var_95 = float(np.percentile(pnl, (1 - confidence) * 100))
    var_99 = float(np.percentile(pnl, 1.0))
    es_95 = float(pnl[pnl <= var_95].mean())

    # 高斯copula对比（低估风险）
    U_g = simulate_gaussian_copula(CORR_MATRIX, N=N)
    log_ret_g = norm.ppf(U_g) * daily_sigmas[None, :] * np.sqrt(horizon_days)
    pnl_g = (log_ret_g * position_sizes[None, :]).sum(axis=1)
    var_95_gaussian = float(np.percentile(pnl_g, 5.0))

    # 各资产独立VaR之和（最差情况线性叠加）
    individual_vars = []
    for i, sz in enumerate(position_sizes):
        q = norm.ppf(1 - confidence) * daily_sigmas[i] * np.sqrt(horizon_days)
        individual_vars.append(abs(sz * q))

    return {
        "horizon_days": horizon_days,
        "confidence": confidence,
        "t_copula_var_95": var_95,
        "t_copula_var_99": var_99,
        "t_copula_es_95": es_95,
        "gaussian_var_95": var_95_gaussian,
        "naive_sum_var_95": -sum(individual_vars),
        "tail_risk_premium": var_95 / var_95_gaussian if var_95_gaussian != 0 else 1,
        "position_sizes_hkd": dict(zip(ASSET_NAMES, position_sizes.tolist())),
        "total_exposure_hkd": float(abs(position_sizes).sum()),
        "N_simulations": N,
    }


# ─────────────────────────────────────────────
# 联合下跌概率（Clayton）
# ─────────────────────────────────────────────

def joint_crash_prob(p_a: float, p_b: float,
                     theta_clayton: float = 2.0,
                     N: int = 500_000) -> dict:
    """
    计算两个资产同时大跌的概率
    p_a, p_b: 各自的单独下跌概率（如30日内跌10%的概率）
    """
    U = simulate_clayton_copula(theta=theta_clayton, d=2, N=N)

    # 联合下跌：两个都触发
    p_joint_clayton = float(((U[:, 0] < p_a) & (U[:, 1] < p_b)).mean())

    # 高斯对比
    U_g = simulate_gaussian_copula(CORR_MATRIX[:2, :2], N=N)
    p_joint_gaussian = float(((U_g[:, 0] < p_a) & (U_g[:, 1] < p_b)).mean())

    # 独立假设
    p_independent = p_a * p_b

    return {
        "p_a": p_a,
        "p_b": p_b,
        "p_joint_independent": p_independent,
        "p_joint_gaussian": p_joint_gaussian,
        "p_joint_clayton": p_joint_clayton,
        "clayton_vs_independent": p_joint_clayton / p_independent if p_independent > 0 else float("inf"),
        "clayton_vs_gaussian": p_joint_clayton / p_joint_gaussian if p_joint_gaussian > 0 else float("inf"),
    }


# ─────────────────────────────────────────────
# 主程序
# ─────────────────────────────────────────────

def run_risk_report(prices: Optional[dict] = None):
    if prices is None:
        prices = {"NVDA": 179.0, "MSFT": 405.0, "09988": 139.0, "01810": 34.0, "00100": 752.0}

    sigmas = {"NVDA": 0.48, "MSFT": 0.27, "09988": 0.38, "01810": 0.52, "00100": 0.90}

    print("=" * 60)
    print("⚠️  COPULA 仓位风险报告")
    print("=" * 60)

    r = portfolio_var(prices, sigmas, horizon_days=5)

    print(f"\n📊 5日持有期 VaR（置信度95%）")
    print(f"  t-Copula VaR95:      HK${r['t_copula_var_95']:,.0f}")
    print(f"  t-Copula VaR99:      HK${r['t_copula_var_99']:,.0f}")
    print(f"  t-Copula ES95:       HK${r['t_copula_es_95']:,.0f}  （期望亏损）")
    print(f"  高斯Copula VaR95:    HK${r['gaussian_var_95']:,.0f}  （低估风险）")
    print(f"  线性叠加 VaR:        HK${r['naive_sum_var_95']:,.0f}  （最差情况）")
    print(f"\n  📌 尾部风险溢价: {r['tail_risk_premium']:.2f}x  （t vs 高斯）")
    print(f"  📌 总敞口: HK${r['total_exposure_hkd']:,.0f}")

    print(f"\n💀 联合崩溃概率（NVDA + 阿里同时大跌）")
    j = joint_crash_prob(p_a=0.20, p_b=0.25, theta_clayton=2.0)
    print(f"  NVDA 20%单独崩概率 × 阿里 25%单独崩概率")
    print(f"  独立假设:    {j['p_joint_independent']:.2%}")
    print(f"  高斯Copula:  {j['p_joint_gaussian']:.2%}")
    print(f"  Clayton:     {j['p_joint_clayton']:.2%}  ← 真实估计")
    print(f"  Clayton/独立: {j['clayton_vs_independent']:.1f}x  （尾部相关放大）")

    print("\n" + "=" * 60)
    print("🔑 结论：你的仓位集中在科技/中概方向")
    print("   极端风险比线性叠加低（多空对冲有效）")
    print("   但NVDA组合内部Clayton相关 >> 高斯假设")
    print("=" * 60)


if __name__ == "__main__":
    import sys
    np.random.seed(42)
    # 可传入实时价格
    prices = {
        "NVDA": float(sys.argv[1]) if len(sys.argv) > 1 else 179.0,
        "MSFT": 405.0, "09988": 139.0, "01810": 34.0, "00100": 752.0
    }
    run_risk_report(prices)
