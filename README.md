# miniAgent

一个最小的**通用 agent 框架**，用 Python 实现，学习 [pi](https://github.com/earendil-works/pi) 的核心架构。

核心思想：
- 分层：providers / agent-core / tools / ui
- 类型化事件流
- Agent 是配置，run 是状态

WIP —— 按阶段增量构建。

完整的架构、路线图、阶段拆解见 [PLAN.md](PLAN.md)。

## 快速开始

依赖：git、[uv](https://docs.astral.sh/uv/)（uv 会自动下载 Python，无需单独安装）。

```bash
git clone https://github.com/ArthurWHR/miniAgent.git
cd miniAgent
uv sync

# 按源码路径运行
PYTHONPATH=src uv run python -c "import miniagent; print('ok')"
```

- 环境由 `uv.lock` 锁定，不要提交或复制 `.venv`。
- 密钥（如 `OPENAI_API_KEY`）通过环境变量提供，不要写进仓库。
- 多机开发：开工前和提交前先 `git pull --rebase`。
