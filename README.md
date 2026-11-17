# miniAgent

一个最小的**通用 agent 框架**，用 Python 实现，学习 [pi](https://github.com/earendil-works/pi) 的核心架构。

核心思想：
- 分层：providers / agent-core / tools / ui
- 类型化事件流
- Agent 是配置，run 是状态

WIP —— 按阶段增量构建。

完整的架构、路线图、阶段拆解见 [PLAN.md](PLAN.md)。

## 运行环境

本机没有可用的 `python`（Windows 商店占位符），统一用 `uv`：

```bash
uv run python -c "print('ok')"        # 自动准备环境并安装依赖
PYTHONPATH=src uv run python ...      # 按源码路径导入 src/miniagent
```
