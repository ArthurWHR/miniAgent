# miniAgent 项目规划

> 一个用 Python 手写的**通用 agent 框架**，参考 [earendil-works/pi](https://github.com/earendil-works/pi) 的核心架构思想。
> 目的：**边做边学**，产出一个结构正确、可扩展、拿得出手的项目，而不是一次性拼出来的 toy demo。

---

## 1. 项目定位

| 项 | 说明 |
|---|---|
| 是什么 | 通用的 agent 框架 / runtime（不绑定任何垂直领域） |
| 不是什么 | 不是简历问答机器人、不是某个产品的后端，**通用性本身就是目标** |
| 参考对象 | pi（TypeScript 的终端编码 agent / agent runtime），只学**核心思想**，不照抄代码 |
| 技术栈 | Python 3.11+ / FastAPI / 手写 agent loop |
| 第一个 provider | OpenAI 兼容接口（如 DeepSeek），Provider 抽象做好，后续再加 Anthropic Claude |
| 开发方式 | **小步增量**：每步只写一小块，写完解释 + 停下来消化，再进下一步 |

---

## 2. 从 pi 提炼的核心思想

这是整个项目的"设计宪法"，每一步实现都要能对回这里：

| # | 思想 | 含义 |
|---|---|---|
| 1 | **分层** | providers（模型适配）/ agent-core（循环+工具+状态）/ tools / ui 各自独立 |
| 2 | **Agent 是配置，状态在 run 上** | `Agent` 不持有对话状态，可复用；每次 `run()` 拥有自己的 transcript |
| 3 | **类型化事件流** | 循环产出 `Event`，UI 只订阅事件，两者互不认识 → 换 UI 不改核心 |
| 4 | **工具失败是事件，不是异常** | 工具报错喂回模型，让模型自己决定怎么恢复 |
| 5 | **per-call 审批门** | 每次工具调用前可被 `approve` 拦截（默认允许 / 默认拒绝策略可配） |
| 6 | **上下文管理** | `count_tokens` + `compact` 压缩对话，控制 context window |
| 7 | **生命周期钩子** | `prepare_request` / `before_tool_call` / `after_tool_call` / `finish_turn` |
| 8 | **分层扩展** | skills（md + yaml）→ extensions（注册工具/命令）→ packages |

### pi → Python 映射

| pi 模块 | Python 对应 | 职责 |
|---|---|---|
| `pi-ai` | `core/providers/` | 多 provider 统一接口 |
| `pi-agent-core` | `core/agent.py` + `core/events.py` | 循环 + 事件流 |
| `RunTool` / `Approve` | `core/tools.py` | 工具执行 + 审批门 |
| `CompactConversation` / `CountTokens` | `core/context.py` | 上下文压缩 + token 计数 |
| 生命周期钩子 | `core/hooks.py` | 扩展点 |
| `SessionManager` | `core/sessions.py` | 会话持久化 |
| `skills` / `extensions` | `skills/` / `extensions/` | 扩展机制 |
| `pi-tui` | `server/` + `ui/` | 我们把 TUI 换成 Web（FastAPI + SSE） |

---

## 3. Agent 核心能力清单（对照检查）

> "核心不能少" —— 逐项对照。🔴 = 删了就不是 agent；🟡 = 成熟度/可用性的关键；⚪ = 可选扩展。

| # | 能力 | 等级 | 计划位置 | 说明 |
|---|---|---|---|---|
| 1 | Agent 循环（LLM ↔ 工具往复，直到收敛） | 🔴 | 阶段 0 | 框架的心脏 |
| 2 | 消息模型（`Message` + `ContentBlock`） | 🔴 | 阶段 0 | user / assistant / tool 三类消息，text / tool_use / tool_result 三类内容块 |
| 3 | 流式解析（文本增量 + tool_call 参数碎片拼接） | 🔴 | 阶段 0 | tool_call 的 JSON 是**分片**到达的，必须增量累积 |
| 4 | Prompt 组装（system + 工具声明 + 历史） | 🔴 | 阶段 0 / 2 | 模型实际看到了什么，是最容易被忽略的核心 |
| 5 | 工具定义 → schema | 🔴 | 阶段 0 / 2 | 阶段 0 手写最小版，阶段 2 用 Pydantic 自动生成 |
| 6 | 工具结果回填消息历史 | 🔴 | 阶段 0 | 不回填，循环就断了 |
| 7 | 单轮多工具调用 | 🔴 | 阶段 2 | 模型一轮可能要求同时调用多个工具 |
| 8 | 工具失败 → 事件回喂模型 | 🔴 | 阶段 0 / 2 | pi 的做法：让模型看到错误并自行恢复 |
| 9 | 终止条件 + 最大轮次兜底 | 🔴 | 阶段 0 | 无 tool_call 即结束；防止死循环 |
| 10 | Provider 可插拔 | 🟡 | 阶段 1 | 换模型不改核心 |
| 11 | 审批门（per-call） | 🟡 | 阶段 2 | 危险工具拦截 |
| 12 | 工具输出截断 | 🟡 | 阶段 3 | 大输出会撑爆上下文窗口 |
| 13 | token 计数 + 上下文压缩 | 🟡 | 阶段 3 | 长对话的必需品 |
| 14 | 会话持久化 | 🟡 | 阶段 3 | 断点续聊 |
| 15 | 错误重试 / 退避（429、网络中断） | 🟡 | 阶段 3 | 真实网络的常态 |
| 16 | 中断 / 取消 | 🟡 | 阶段 3 / 5 | 用户点"停止" |
| 17 | 生命周期钩子 | 🟡 | 阶段 4 | 一切扩展的前提 |
| 18 | skills / extensions | 🟡 | 阶段 4 | 通用性的证明 |
| 19 | trace / 可观测 | 🟡 | 阶段 6 | 每一步可回放 |
| 20 | eval 评测集 | 🟡 | 阶段 6 | 改代码不怕退化 |
| 21 | 子 agent 编排 | ⚪ | 阶段 7+（可选） | pi-durable 的能力，非必须 |
| 22 | 长期记忆 | ⚪ | 扩展 | 可做成 extension |
| 23 | MCP 工具接入 | ⚪ | 扩展 | 生态入口 |
| 24 | 多模态输入 | ⚪ | 扩展 | 看图 / 听音 |

**阶段 0 结束时，1~9 必须全部存在**，否则不算"跑通了一个 agent"。

---

## 4. 目标目录结构

```
miniAgent/
├── pyproject.toml
├── PLAN.md                    # 本文件
├── README.md
├── src/miniagent/
│   ├── core/
│   │   ├── messages.py        # 消息模型：Message / ContentBlock
│   │   ├── events.py          # 类型化事件
│   │   ├── providers/         # 模型适配层（Provider Protocol + 各实现）
│   │   ├── agent.py           # Agent(配置) + stream() 循环
│   │   ├── tools.py           # 工具注册表 + run_tool + approve 门
│   │   ├── context.py         # Transcript / compact / count_tokens / 截断
│   │   ├── hooks.py           # 生命周期钩子
│   │   └── sessions.py        # 会话持久化
│   ├── builtin_tools/         # 通用工具：calculator / web_search / read_file ...
│   ├── skills/                # markdown + yaml 技能
│   ├── extensions/            # 扩展点：注册工具/技能
│   ├── server/                # FastAPI + SSE（流式）
│   └── ui/                    # web 前端
└── examples/                  # 用法示例（不是业务代码）
```

> 通用性的验证方式：框架自带一批通用工具，且任何人能通过 extension 加新工具并立刻可用。

---

## 5. 阶段路线图

| 阶段 | 主题 | 学 pi 的什么 | 交付物 | 状态 |
|---|---|---|---|---|
| **0** | 最小循环 + 事件流 | `pi-agent-core` | 事件、消息模型、Provider(最小)、工具(最小)、循环、CLI | 🚧 进行中 |
| **1** | Provider 抽象 | `pi-ai` | Provider Protocol，接第二家 provider 验证可插拔 | ⬜ |
| **2** | 工具系统 | `RunTool` / `Approve` | 注册表、Pydantic schema、多工具并行、per-call approve、错误成事件 | ⬜ |
| **3** | 上下文管理 | `CompactConversation` | Transcript、输出截断、compact、count_tokens、session、重试、取消 | ⬜ |
| **4** | 可扩展性 | skills / extensions | 生命周期钩子、skills(md+yaml)、extensions 注册工具 | ⬜ |
| **5** | Web 化 | `pi-tui` 的角色 | FastAPI + SSE 流式（含前端取消）+ 前端 | ⬜ |
| **6** | 生产化 | 工程质量 | eval 问题集、trace、默认拒绝的审批策略 | ⬜ |
| **7** | 高级（可选） | `pi-durable` | 子 agent 编排 / 长期记忆 / MCP | ⬜ |

### 阶段依赖关系

```
0 ──> 1 ──> 2 ──> 3 ──> 4 ──> 5 ──> 6 ──> 7(可选)
      (provider 可插拔后才能谈工具)   (有钩子才能做扩展)   (核心稳定了才上 Web)
```

原则：**每阶段都是往骨架上加一层，不推翻重来**。如果一个新需求要求重构，说明前一阶段抽象没做对。

---

## 6. 阶段 0 的详细拆解（当前）

> 目标：跑通一个**结构正确**的最小 agent —— 能对话、能调工具、能流式、能收尾。

| 小步 | 做什么 | 学什么 | 状态 |
|---|---|---|---|
| **0.1** | 项目骨架 + `events.py` | 类型化事件、事件与 UI 解耦 | ✅ 完成 |
| **0.2** | `messages.py`：`Message` + `ContentBlock`（text / tool_use / tool_result） | 消息模型 —— 整个框架的数据基础 | ✅ 完成 |
| **0.3** | `providers`：最小 OpenAI 兼容**流式**调用（`httpx`） | 模型适配层、流式文本增量 | ✅ 完成 |
| **0.4** | `tools.py`（最小版）：1 个工具 + schema + 结果回填 + 失败成事件 | 工具契约 | ✅ 完成 |
| **0.5a** | provider 支持 `tools` + 流式 **tool_call 分片累积** | 流式协议、厂商格式收敛到一处 | ✅ 完成 |
| **0.5b** | `agent.py`：循环 + 工具执行 + 结果回填 + 终止条件 | 核心循环、最难的那块 | ✅ 完成 |
| **0.6** | CLI 入口：把上面串起来，事件渲染到终端 | 事件驱动的好处 | ⬜ |

每步结束都**可运行/可验证**（0.2 可用单测验证序列化，0.3 可单独打一次模型）。

---

## 7. 关键设计决策与理由

| 决策 | 选择 | 理由 |
|---|---|---|
| 是否一上来用 LangChain/LangGraph | **不用** | 引框架学到的是"框架 API"，手写才学到"架构"。阶段 4~5 再评估 |
| 消息模型先手写还是用 SDK 类型 | **手写**（可用 Pydantic） | 自己定义一遍才真正懂 provider 之间差在哪 |
| 事件 `data` 的形状 | 先不定，`dict` 占位 | 形状由实现逼出来，提前设计会设计错 |
| 工具错误 | 产出 `TOOL_RESULT` 事件，不抛异常 | 让模型看到错误并自行恢复（pi 的做法） |
| 第一个 provider | OpenAI 兼容（DeepSeek） | 便宜、国内直连；抽象做好后换/加 Claude 很容易 |
| 依赖 | 最小化：`pydantic` + `httpx` | 学习阶段少一层黑盒；`fastapi/uvicorn` 留到阶段 5 |

---

## 8. 学习方法约定

- 每次只推进**一个小步**，写完解释：对应 pi 的哪个思想、为什么这么设计。
- 写完停下，等消化 / 提问，再继续。
- 优先手写核心，少引框架。
- 遇到设计选择，先问"pi 为什么这么做 / 换我该怎么做"，而不是直接查答案。

---

## 9. 快速开始（随进度更新）

> 目前还没有可运行的入口，阶段 0.6 后补充。

运行环境：本机没有可用的 `python`（Windows 商店占位符），统一用 `uv`：

```bash
uv run python -c "print('ok')"
PYTHONPATH=src uv run python <script>
```
