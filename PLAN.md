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
| **0** | 最小循环 + 事件流 | `pi-agent-core` | 事件、消息模型、Provider(最小)、工具(最小)、循环、CLI | ✅ 完成 |
| **1** | Provider 抽象 | `pi-ai` | Provider Protocol，接第二家 provider 验证可插拔 | ✅ 完成 |
| **2** | 工具系统 | `RunTool` / `Approve` | 注册表、Pydantic schema、多工具并行、per-call approve、错误成事件 | 🚧 进行中 |
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

## 6. 阶段 0 的详细拆解（已完成）

> 目标：跑通一个**结构正确**的最小 agent —— 能对话、能调工具、能流式、能收尾。

| 小步 | 做什么 | 学什么 | 状态 |
|---|---|---|---|
| **0.1** | 项目骨架 + `events.py` | 类型化事件、事件与 UI 解耦 | ✅ 完成 |
| **0.2** | `messages.py`：`Message` + `ContentBlock`（text / tool_use / tool_result） | 消息模型 —— 整个框架的数据基础 | ✅ 完成 |
| **0.3** | `providers`：最小 OpenAI 兼容**流式**调用（`httpx`） | 模型适配层、流式文本增量 | ✅ 完成 |
| **0.4** | `tools.py`（最小版）：1 个工具 + schema + 结果回填 + 失败成事件 | 工具契约 | ✅ 完成 |
| **0.5a** | provider 支持 `tools` + 流式 **tool_call 分片累积** | 流式协议、厂商格式收敛到一处 | ✅ 完成 |
| **0.5b** | `agent.py`：循环 + 工具执行 + 结果回填 + 终止条件 | 核心循环、最难的那块 | ✅ 完成 |
| **0.6** | CLI 入口：把上面串起来，事件渲染到终端 | 事件驱动的好处 | ✅ 完成 |

每步结束都**可运行/可验证**（0.2 可用单测验证序列化，0.3 可单独打一次模型）。
阶段 0 已用真实模型（DeepSeek）验证：模型正确调用 `calculator`、结果回填、二次作答。

---

## 7. 阶段 1 的详细拆解（已完成）

> 目标：证明「换模型不改核心」。新增 Anthropic provider，**核心文件零改动**。
> 不需要真实的 Anthropic key：用 `httpx.MockTransport` 验证协议翻译即可；有 key 再实跑一次。

| 小步 | 做什么 | 学什么 | 状态 |
|---|---|---|---|
| **1.1** | `anthropic_provider.py` 请求翻译：规范 `Message`/`Tool` → Anthropic 格式（system 拆成顶层参数、tool_result 放进 user 消息、tools 用 `input_schema`） | 两家协议的结构差异 | ✅ 完成 |
| **1.2** | Anthropic 流式解析：`content_block_delta` / `input_json_delta` / `error` 事件，工具参数按 block index 累积 | 另一套流式协议 | ✅ 完成 |
| **1.3** | 一致性验证：同一 `Agent` + `calculator`，两个 provider 用 MockTransport 跑，产出的规范事件序列等价 | 抽象是否真的中立（验收标准） | ✅ 完成 |
| **1.4** | CLI `--provider openai\|anthropic`，README 更新 | 运行时切换实现 | ✅ 完成 |

**验收标准（1.3）：`core/agent.py`、`core/tools.py`、`core/messages.py` 一行不改**，只是换一个构造参数。

---

## 8. 阶段 2 的详细拆解（当前）

> 目标：把工具从「手写字典」升级成「类型驱动的契约」，并补上并发与审批。
> 核心验收：工具作者只写一个带类型注解的函数，不手写 JSON Schema。

| 小步 | 做什么 | 学什么 | 状态 |
|---|---|---|---|
| **2.1** | Pydantic 声明式工具：`Tool.from_function()`（或 `@tool` 装饰器）从函数签名 + 类型注解 + docstring 自动生成 JSON Schema；`calculator` 迁移，行为不变 | schema 由类型驱动，手写与实现不再漂移 | ✅ 完成 |
| **2.2** | 执行前参数校验：用 Pydantic 校验模型给的参数；失败 → `is_error=True` 结果块（含可读字段错误），handler 不执行 | 输入边界、错误成数据 | ⬜ |
| **2.3** | 单轮多工具并行执行：同一轮多个 `tool_call` 用 `asyncio.gather` 并发；结果按 `tool_use_id` 对齐；单个失败不影响其他 | 并发、顺序保持、异常隔离 | ⬜ |
| **2.4** | per-call 审批门：`Agent(approve=...)`，签名 `(tool, arguments) -> bool`；拒绝 → `is_error=True` 结果块；CLI 加 `--ask-approval` | 危险操作拦截、审批不打断事件流 | ⬜ |
| **2.5** | 阶段验收：`tests/tools.py` 覆盖 schema 生成 / 校验失败 / 并行 / 审批拒绝；README + PLAN 更新 | 回归门禁 | ⬜ |

**验收标准（2.5）**

- 新增工具只需写函数和类型注解，schema 自动生成且与实现一致
- 参数错误、审批拒绝都表现为结果块，Agent 循环不崩
- 并行执行耗时 ≈ 最慢的那个工具，而不是逐个累加
- 现有 CLI 与真实模型行为不变（calculator 仍可正常调用）

**本阶段的预期决策**

- schema 用 Pydantic 的 `model_json_schema()` 生成，统一去掉 `title`、补 `additionalProperties: false`
- 校验失败的错误文本要短、可读 —— 它是给模型看的，不是给栈追踪看的
- 并行只发生在**同一轮的多个工具之间**；轮与轮之间仍然串行（下一轮依赖上一轮结果）
- 审批在"调用前"；工具内部的细粒度权限不归这里管
- 默认策略：本阶段默认放行，阶段 6 再收紧为默认拒绝（对应 pi 的 `--no-approve`）

---

## 9. 关键设计决策与理由

| 决策 | 选择 | 理由 |
|---|---|---|
| 是否一上来用 LangChain/LangGraph | **不用** | 引框架学到的是"框架 API"，手写才学到"架构"。阶段 4~5 再评估 |
| 消息模型先手写还是用 SDK 类型 | **手写**（可用 Pydantic） | 自己定义一遍才真正懂 provider 之间差在哪 |
| 事件 `data` 的形状 | 先不定，`dict` 占位 | 形状由实现逼出来，提前设计会设计错 |
| 工具错误 | 产出 `TOOL_RESULT` 事件，不抛异常 | 让模型看到错误并自行恢复（pi 的做法） |
| 第一个 provider | OpenAI 兼容（DeepSeek） | 便宜、国内直连；抽象做好后换/加 Claude 很容易 |
| 依赖 | 最小化：`pydantic` + `httpx` | 学习阶段少一层黑盒；`fastapi/uvicorn` 留到阶段 5 |


---

## 10. 学习方法约定

- 每次只推进**一个小步**，写完解释：对应 pi 的哪个思想、为什么这么设计。
- 写完停下，等消化 / 提问，再继续。
- 优先手写核心，少引框架。
- 遇到设计选择，先问"pi 为什么这么做 / 换我该怎么做"，而不是直接查答案。
- **每进入一个新阶段，先在 PLAN 里写出该阶段的详细拆解**（像阶段 0 / 1 这样），再开始第一步。

---

## 11. 快速开始（随进度更新）

运行环境：本机没有可用的 `python`（Windows 商店占位符），统一用 `uv`：

```bash
uv sync
uv run miniagent "2*(3+4) 等于多少？"          # 需要 OPENAI_API_KEY
uv run python -c "print('ok')"
PYTHONPATH=src uv run python <script>
```

阶段 0 已完成：`events → messages → provider → tools → agent loop → CLI`
九项核心能力（#1~9）全部就位。

阶段 1 已完成：OpenAI 兼容 + Anthropic 两个 provider，同一 `Agent` 跑出等价事件
（`uv run python tests/provider_consistency.py`），核心代码零改动。

当前阶段 2：工具系统 —— Pydantic 自动 schema、参数校验、并行执行、审批门。
