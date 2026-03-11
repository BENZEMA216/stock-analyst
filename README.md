# stock-analyst

> 美股/港股盘前分析 Skill for OpenClaw / Claude Code / Codex

一套适合个人投资者的量化辅助工具，核心是**五大观测指标框架**，配合持仓追踪和量化模块。

## 功能

- **五大指标实时抓取**：VIX · IGV · MAGS · MEME · 布伦特油
- **个股价格 + 支撑阻力验证**：美股 / 港股 / A 股
- **持仓追踪**：JSON 格式管理，支持正股 / 期权 / 港股 / 加密货币
- **量化模块**：
  - 蒙特卡洛期权定价
  - 粒子滤波概率追踪（事件驱动贝叶斯更新）
  - Copula VaR
  - Brier Score 预测准确率

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 抓取五大指标 + 常用个股
python scripts/indicators.py

# 追踪持仓
cp portfolio/portfolio.json.example portfolio/portfolio.json
# 编辑 portfolio.json 填入你的持仓
python portfolio/tracker.py
```

## 五大观测指标框架

每次盘前分析必须包含：

| 指标 | 代码 | 危险区 | 确认区 |
|------|------|--------|--------|
| VIX 恐慌指数 | `^VIX` | >27-28 看空；>30 崩盘 | <20 健康 |
| IGV 软件科技 ETF | `IGV` | <82 弱势 | >85 右侧确认 ✅ |
| MAGS 七巨头 ETF | `MAGS` | <60 关键支撑破位 | >62 修复中 |
| MEME 散户情绪 ETF | `MEME` | 跌速>MAGS=散户恐慌 | 上涨=risk-on |
| 布伦特原油 | `BZ=F` | >90 通胀冲击 | <80 压力缓解 |

## 量化模块

### 粒子滤波（概率追踪）

对"NVDA 在 7 月前涨到 $195"这类事件进行实时概率追踪：

```bash
# 更新观测（bullish/bearish/neutral）
python quant/run.py pf --event nvda_195_by_july --obs bullish

# 查看当前所有事件概率
python quant/run.py pf --list
```

### 期权蒙卡定价

```bash
python quant/run.py mc \
  --symbol NVDA \
  --strike 195 \
  --expiry 2026-07-17 \
  --type call
```

## 持仓 JSON 格式

```json
{
  "meta": {
    "last_updated": "2026-03-11",
    "usd_to_cnh": 7.28,
    "hkd_to_cnh": 0.93
  },
  "positions": [
    {
      "id": "nvda_stock",
      "name": "NVDA 正股",
      "type": "stock",
      "symbol": "NVDA",
      "currency": "USD",
      "quantity": 20,
      "avg_cost": 174.85,
      "stop_loss": 168
    },
    {
      "id": "baba_hk",
      "name": "阿里巴巴 09988",
      "type": "stock",
      "symbol": "9988.HK",
      "currency": "HKD",
      "quantity": 400,
      "avg_cost": 144.42
    },
    {
      "id": "nvda_call_spread",
      "name": "NVDA C195/200 0717",
      "type": "call_spread",
      "symbol": "NVDA",
      "currency": "USD",
      "contracts": 12,
      "long_strike": 195,
      "short_strike": 200,
      "expiry": "2026-07-17",
      "avg_cost": 2.10
    }
  ]
}
```

支持的持仓类型：`stock` · `short_put` · `call_spread` · `short_stock`

## 地缘政治新闻验证协议

> 防止"假战争新闻"引发情绪化操作

收到重大地缘政治消息时，**先验证再交易**：

1. 查布伦特油涨幅（真实冲突油价必涨 >3%）
2. 查 VIX 变化（真实恐慌 VIX 必同步上升）
3. 查股指期货反应（真实冲击期货必跌）

三者一致 → 真实，可操作；任一不符 → 可能是假新闻。

## 依赖

- Python 3.10+
- yfinance
- akshare（港股 / A 股数据）
- numpy / pandas / scipy

## License

MIT
