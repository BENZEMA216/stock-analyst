"""
particle_filter.py — 实时事件概率追踪器
用途：Jensen演讲、MiniMax财报、NVDA止损概率等实时更新
"""

import numpy as np
import json
import os
from datetime import datetime
from scipy.special import expit, logit  # sigmoid / logit

STATE_FILE = os.path.join(os.path.dirname(__file__), "pf_state.json")


class EventTracker:
    """
    单个事件的粒子滤波器
    例："NVDA在4月前涨回$195" 或 "MiniMax财报后大跌"
    """

    def __init__(self, name: str, prior_prob: float = 0.5,
                 N: int = 3000, process_vol: float = 0.04,
                 obs_noise: float = 0.03):
        self.name = name
        self.N = N
        self.process_vol = process_vol
        self.obs_noise = obs_noise
        self.history = []

        # 初始化粒子（logit空间）
        logit_prior = logit(np.clip(prior_prob, 0.01, 0.99))
        self.logit_particles = logit_prior + np.random.normal(0, 0.5, N)
        self.weights = np.ones(N) / N
        self.created_at = datetime.now().isoformat()

    def update(self, obs: float, obs_label: str = ""):
        """
        传入一个观测值（0-1之间的概率信号）
        obs: 价格信号 / 新闻情绪分 / 直接概率估计
        """
        # 1. 传播：logit空间随机游走
        noise = np.random.normal(0, self.process_vol, self.N)
        self.logit_particles += noise

        # 2. 观测似然
        prob_particles = expit(self.logit_particles)
        log_lik = -0.5 * ((obs - prob_particles) / self.obs_noise) ** 2
        log_w = np.log(self.weights + 1e-300) + log_lik
        log_w -= log_w.max()
        self.weights = np.exp(log_w)
        self.weights /= self.weights.sum()

        # 3. ESS重采样
        ess = 1.0 / np.sum(self.weights ** 2)
        if ess < self.N / 2:
            self._resample()

        est = self.estimate()
        ci = self.credible_interval()
        entry = {
            "ts": datetime.now().isoformat(),
            "obs": obs,
            "label": obs_label,
            "prob": est,
            "ci_lo": ci[0],
            "ci_hi": ci[1],
        }
        self.history.append(entry)
        return entry

    def _resample(self):
        cumsum = np.cumsum(self.weights)
        u = (np.arange(self.N) + np.random.uniform()) / self.N
        idx = np.searchsorted(cumsum, u)
        idx = np.clip(idx, 0, self.N - 1)
        self.logit_particles = self.logit_particles[idx]
        self.weights = np.ones(self.N) / self.N

    def estimate(self) -> float:
        return float(np.average(expit(self.logit_particles), weights=self.weights))

    def credible_interval(self, alpha: float = 0.05):
        probs = expit(self.logit_particles)
        idx = np.argsort(probs)
        cumw = np.cumsum(self.weights[idx])
        lo = probs[idx[np.searchsorted(cumw, alpha / 2)]]
        hi = probs[idx[np.searchsorted(cumw, 1 - alpha / 2)]]
        return float(lo), float(hi)

    def summary(self) -> str:
        est = self.estimate()
        ci = self.credible_interval()
        last_obs = self.history[-1]["label"] if self.history else "无观测"
        n = len(self.history)
        return (f"[{self.name}]  P={est:.1%}  95%CI=({ci[0]:.1%},{ci[1]:.1%})"
                f"  观测次数={n}  最后={last_obs}")

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "N": self.N,
            "process_vol": self.process_vol,
            "obs_noise": self.obs_noise,
            "logit_particles": self.logit_particles.tolist(),
            "weights": self.weights.tolist(),
            "history": self.history,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EventTracker":
        obj = cls(d["name"], N=d["N"],
                  process_vol=d["process_vol"], obs_noise=d["obs_noise"])
        obj.logit_particles = np.array(d["logit_particles"])
        obj.weights = np.array(d["weights"])
        obj.history = d["history"]
        obj.created_at = d["created_at"]
        return obj


# ─────────────────────────────────────────────
# 多事件管理器（持久化到json）
# ─────────────────────────────────────────────

class EventPortfolio:
    def __init__(self):
        self.trackers: dict[str, EventTracker] = {}
        self._load()

    def _load(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE) as f:
                    data = json.load(f)
                for k, v in data.items():
                    self.trackers[k] = EventTracker.from_dict(v)
            except Exception:
                pass

    def save(self):
        data = {k: v.to_dict() for k, v in self.trackers.items()}
        with open(STATE_FILE, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add_event(self, key: str, name: str, prior: float = 0.5) -> EventTracker:
        if key not in self.trackers:
            self.trackers[key] = EventTracker(name, prior_prob=prior)
            self.save()
        return self.trackers[key]

    def update(self, key: str, obs: float, label: str = "") -> dict:
        t = self.trackers[key]
        result = t.update(obs, label)
        self.save()
        return result

    def status(self):
        print("=" * 60)
        print("🎯 事件概率追踪器")
        print("=" * 60)
        if not self.trackers:
            print("  暂无追踪事件")
        for t in self.trackers.values():
            print(" ", t.summary())
        print("=" * 60)

    def resolve(self, key: str, outcome: bool):
        """事件结束，记录结果（用于Brier Score计算）"""
        if key in self.trackers:
            final_prob = self.trackers[key].estimate()
            self.trackers[key].history.append({
                "ts": datetime.now().isoformat(),
                "label": f"RESOLVED={'YES' if outcome else 'NO'}",
                "final_prob": final_prob,
                "outcome": int(outcome),
                "brier": (final_prob - int(outcome)) ** 2,
            })
            self.save()
            print(f"✅ {key} resolved: outcome={'YES' if outcome else 'NO'}, "
                  f"final_prob={final_prob:.1%}, "
                  f"Brier={self.trackers[key].history[-1]['brier']:.4f}")


# ─────────────────────────────────────────────
# 当前活跃事件（初始化）
# ─────────────────────────────────────────────

ACTIVE_EVENTS = {
    "nvda_195_by_july": {
        "name": "NVDA 7月前涨回$195",
        "prior": 0.40,
    },
    "jensen_ms_bullish": {
        "name": "Jensen 3/4 MS演讲 超预期看多",
        "prior": 0.55,
    },
    "minimax_drop_after_earnings": {
        "name": "MiniMax 财报后跌破$700",
        "prior": 0.60,
    },
    "baba_150_by_april": {
        "name": "阿里 4月前反弹到$150",
        "prior": 0.40,
    },
    "xiaomi_su7_launch_strong": {
        "name": "小米新SU7发布后1周涨5%+",
        "prior": 0.50,
    },
}


def init_events():
    ep = EventPortfolio()
    for key, cfg in ACTIVE_EVENTS.items():
        if key not in ep.trackers:
            ep.add_event(key, cfg["name"], cfg["prior"])
            print(f"  新建事件: {cfg['name']} (prior={cfg['prior']:.0%})")
    return ep


if __name__ == "__main__":
    import sys
    np.random.seed(42)
    ep = init_events()

    if len(sys.argv) >= 4:
        # 用法: python particle_filter.py <event_key> <obs_0_to_1> <label>
        key = sys.argv[1]
        obs = float(sys.argv[2])
        label = sys.argv[3] if len(sys.argv) > 3 else ""
        result = ep.update(key, obs, label)
        print(f"更新: {ep.trackers[key].summary()}")
    else:
        ep.status()
