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

### 运行

需要一个 OpenAI 兼容服务的 API key：

```bash
export OPENAI_API_KEY=sk-xxx

# 可选：换成 DeepSeek 或任何兼容服务
export OPENAI_BASE_URL=https://api.deepseek.com/v1
export MINIAGENT_MODEL=deepseek-v4-pro   # 以你的服务商支持的模型名为准

uv run miniagent "2*(3+4) 等于多少？"
```

输出示例（工具调用过程对用户可见）：

```
我算一下
[tool] calculator({"expr": "2*(3+4)"})
[tool result] 14
等于 14
```

> 当前阶段只支持单轮问答；多轮会话在阶段 3 的 session 持久化中实现。

### 切换 provider

```bash
# Anthropic（Claude）
export ANTHROPIC_API_KEY=sk-ant-xxx
uv run miniagent --provider anthropic "2*(3+4) 等于多少？"

# 或用环境变量设置默认 provider
export MINIAGENT_PROVIDER=anthropic
```

两个 provider 共用同一套核心（`agent.py` / `tools.py` / `messages.py`），
协议差异全部收敛在 `core/providers/` 里。

一致性验收（不联网，用 MockTransport 模拟两家 SSE）：

```bash
uv run python tests/provider_consistency.py
```
