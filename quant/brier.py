"""
brier.py — 预测校准追踪器（Brier Score）
弦 Quant System v0.1

用途：
- 记录我每次做的概率预测
- 事后验证：预测的70%事件实际发生了多少次？
- 长期追踪校准度，发现系统性偏差
"""

import json
import os
import numpy as np
from datetime import datetime

BRIER_FILE = os.path.join(os.path.dirname(__file__), "brier_log.json")


def load_log() -> list:
    if os.path.exists(BRIER_FILE):
        with open(BRIER_FILE) as f:
            return json.load(f)
    return []


def save_log(log: list):
    with open(BRIER_FILE, "w") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def add_prediction(description: str, prob: float, category: str = "stock",
                   target_date: str = "") -> dict:
    """
    记录一条预测
    description: 预测内容，如"NVDA在4月大厂财报前反弹至$195+"
    prob: 概率，0-1
    category: stock / macro / event / earnings
    target_date: 预测目标日期
    """
    log = load_log()
    record = {
        "id": len(log) + 1,
        "created_at": datetime.now().isoformat(),
        "description": description,
        "prob": prob,
        "category": category,
        "target_date": target_date,
        "outcome": None,  # 1=发生, 0=未发生, None=待定
        "resolved_at": None,
        "brier": None,
    }
    log.append(record)
    save_log(log)
    print(f"✅ 预测已记录 [#{record['id']}]: {description} → {prob:.0%}")
    return record


def resolve_prediction(pred_id: int, outcome: int) -> dict:
    """
    解析一条预测结果
    outcome: 1=发生了, 0=没发生
    """
    log = load_log()
    for record in log:
        if record["id"] == pred_id:
            record["outcome"] = outcome
            record["resolved_at"] = datetime.now().isoformat()
            record["brier"] = (record["prob"] - outcome) ** 2
            save_log(log)
            result = "✅ 对了" if (record["prob"] > 0.5) == (outcome == 1) else "❌ 错了"
            print(f"{result} #{pred_id}: {record['description']}")
            print(f"   预测={record['prob']:.0%}, 结果={'发生' if outcome else '未发生'}")
            print(f"   Brier={record['brier']:.4f}")
            return record
    print(f"未找到预测 #{pred_id}")
    return {}


def show_stats():
    """展示校准统计"""
    log = load_log()
    resolved = [r for r in log if r["outcome"] is not None]
    pending = [r for r in log if r["outcome"] is None]
    
    print("\n" + "=" * 55)
    print("📊 预测校准统计")
    print("=" * 55)
    print(f"总预测: {len(log)} | 已解析: {len(resolved)} | 待定: {len(pending)}")
    
    if not resolved:
        print("暂无已解析预测")
        return
    
    # Brier Score
    brier_scores = [r["brier"] for r in resolved]
    overall_brier = np.mean(brier_scores)
    print(f"\nBrier Score: {overall_brier:.4f}", end="")
    if overall_brier < 0.10:
        print(" 🌟 优秀（<0.10）")
    elif overall_brier < 0.20:
        print(" ✅ 良好（<0.20）")
    else:
        print(" ⚠️  需改善（>0.20）")
    
    # 按置信度分组校准曲线
    print("\n校准曲线（预测 vs 实际发生率）:")
    bins = [(0, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.01)]
    for lo, hi in bins:
        subset = [r for r in resolved if lo <= r["prob"] < hi]
        if subset:
            avg_pred = np.mean([r["prob"] for r in subset])
            actual_rate = np.mean([r["outcome"] for r in subset])
            bar_pred = "█" * int(avg_pred * 20)
            bar_act = "░" * int(actual_rate * 20)
            print(f"  [{lo:.0%}-{hi:.0%}]: 预测均值={avg_pred:.0%} 实际={actual_rate:.0%} "
                  f"({'偏高' if avg_pred > actual_rate + 0.1 else '偏低' if avg_pred < actual_rate - 0.1 else '校准OK'})")
    
    # 分类统计
    categories = set(r["category"] for r in resolved)
    if len(categories) > 1:
        print("\n按类别:")
        for cat in categories:
            cat_records = [r for r in resolved if r["category"] == cat]
            cat_brier = np.mean([r["brier"] for r in cat_records])
            print(f"  {cat:12s}: Brier={cat_brier:.4f} ({len(cat_records)}条)")
    
    # 最近10条
    print("\n最近记录:")
    for r in log[-10:]:
        status = "待定" if r["outcome"] is None else ("✅" if r["brier"] < 0.1 else "❌")
        print(f"  [{status}] #{r['id']} {r['prob']:.0%} {r['description'][:40]}")


def list_pending():
    log = load_log()
    pending = [r for r in log if r["outcome"] is None]
    if not pending:
        print("没有待定预测")
        return
    print(f"\n⏳ 待解析预测 ({len(pending)}条):")
    for r in pending:
        print(f"  #{r['id']} [{r['category']}] {r['prob']:.0%} → {r['description']}")
        if r["target_date"]:
            print(f"       目标日期: {r['target_date']}")


# ─────────────────────────────────────────────
# 初始化：写入我已有的预测
# ─────────────────────────────────────────────

def seed_initial_predictions():
    """写入当前已有的主要预测"""
    log = load_log()
    if log:
        print(f"已有 {len(log)} 条记录，跳过初始化")
        return
    
    predictions = [
        ("NVDA在2026年7月到期前至少到$195（C195腿ITM）", 0.38, "stock", "2026-07-17"),
        ("NVDA在2026年4月大厂Q1资本开支指引后反弹至$195+", 0.45, "earnings", "2026-04-30"),
        ("NVDA不被行权PUT$175（到2026-06-18收盘>$175）", 0.72, "stock", "2026-06-18"),
        ("MiniMax(0100.HK)在3个月内跌至HK$600以下", 0.55, "stock", "2026-06-01"),
        ("小米(1810.HK)在新SU7发布后1个月内反弹至HK$40+", 0.42, "stock", "2026-05-30"),
        ("阿里巴巴(9988.HK)在腾讯财报后1周内反弹至HK$150+", 0.38, "earnings", "2026-03-31"),
        ("Jensen在Morgan Stanley演讲中给出明确看多信号", 0.55, "event", "2026-03-04"),
        ("MiniMax今日财报超预期（营收或商业化亮眼）", 0.38, "earnings", "2026-03-02"),
    ]
    
    for desc, prob, cat, date in predictions:
        add_prediction(desc, prob, cat, date)
    
    print(f"\n✅ 已初始化 {len(predictions)} 条基准预测")


if __name__ == "__main__":
    seed_initial_predictions()
    print()
    list_pending()
    print()
    show_stats()
