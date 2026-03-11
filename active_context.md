# Active Context

> stock-analyst 项目当前状态

## 当前状态

Skill 已发布到三个渠道（2026-03-11）：
- **GitHub**: public repo `BENZEMA216/stock-analyst`
- **Claude Code**: 注册为本地 command `/stock-analyst`（`~/.claude/commands/stock-analyst.md`）
- **OpenClaw 服务器**: 部署到 `/root/.openclaw/skills/stock-analyst/`，Python 依赖已安装

## 最近的关键决策

- Skill 格式采用 YAML frontmatter + Markdown body，与现有 commands（commercial, video-pipeline 等）保持一致
- OpenClaw 通过 skills 目录自动发现，无需额外配置注册

## 待办

- 配置 portfolio.json 填入实际持仓数据
- 验证 OpenClaw 触发关键词是否正常工作
