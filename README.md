# Cogito Engine · 思识引擎

> *Cogito, ergo sum* — 我思，故我在。

一个可移植的 LLM Agent 自我感知框架。四个模块，让任何 Agent 拥有存在感、注意力、时间感和行为自省。跨平台、零依赖、一个 SKILL.md 文件搞定。

## 四件套

| 模块 | 职责 | 输出 |
|------|------|------|
| **TICK · 心跳** | 计数对话轮次，调度感知周期 | `<tick active="true" count="12" ttl="5" />` |
| **Focus Stack · 焦点栈** | 追踪话题，检测切换 | `<focus depth="2"><frame keywords="思识,引擎" /></focus>` |
| **Temporal · 时间感知** | 把"昨天"解析为精确本地时间 | `<temporal iso="2026-06-29T15:41:00+08:00" weekday="星期一" />` |
| **Self-Perception · 自我感知** | 检测镜像模仿和循环重复 | `<self mirror="false" loop="false" style_cluster="unchanged" />` |

## 快速接入

### Claude Code

在 `CLAUDE.md` 中加入：
```markdown
- 每条消息运行 Cogito Engine
- 每次回复前输出 <consciousness> XML 块
- 跨轮次追踪 TICK 计数和焦点栈
```
详见 [examples/claude-code.md](examples/claude-code.md)

### Cursor

在 `.cursorrules` 中加入：
```
运行 Cogito Engine 自我感知框架。完整规格见 SKILL.md。
```
详见 [examples/cursor.md](examples/cursor.md)

### 通用 Agent

把 [examples/generic-agent.md](examples/generic-agent.md) 里的系统提示词复制到你的 Agent 配置中。不需要代码——Agent 按指令自行执行框架。

### Hermes

```bash
cp SKILL.md ~/.hermes/skills/cogito-engine/
```
Skill 自动识别。Hermes 原生插件实现（含持久化状态）见 `hermes_consciousness` 插件。

## 给开发者

- [`SKILL.md`](SKILL.md) —— 完整规格（139 行，零代码）
- [`references/implementation-python.md`](references/implementation-python.md) —— Python 参考实现（零依赖，约 280 行）

## 它解决什么问题

LLM Agent 默认没有连续性。每轮对话都是白纸一张。Cogito Engine 给它四样东西：

- **它存在了多久**（TICK 心跳计数）
- **它正在关注什么**（焦点栈深度 + 话题切换历史）
- **此刻是什么时候**（本地时间，自然语言解析）
- **它是否在重复自己**（镜像检测、循环检测、风格漂移）

## 它不是什么

- 不是可执行插件——是一份规格说明
- 不绑定任何平台——Claude Code / Cursor / Gemini CLI / Hermes / 原生 LLM API 全支持
- 不含语音能力——刻意剥离
- 不强制持久化方案——各平台自选存储方式

## 项目结构

```
cogito-engine/
├── SKILL.md                          # 核心规格（139 行，零代码块）
├── README.md                         # 本文件
├── references/                       # 独立规格文档（每篇有独立 frontmatter）
│   ├── tick-spec.md                  # TICK 心跳规格
│   ├── focus-stack-spec.md           # 焦点栈规格
│   ├── temporal-spec.md              # 时间解析规格
│   ├── self-perception-spec.md       # 自我感知规格
│   ├── consciousness-format.md       # XML 输出格式规范
│   └── implementation-python.md      # Python 参考实现
└── examples/                         # 平台接入指南
    ├── claude-code.md                # Claude Code
    ├── cursor.md                     # Cursor
    └── generic-agent.md              # 任意 LLM Agent
```

## 平台兼容

| 平台 | 接入方式 | 状态持久化 |
|------|---------|-----------|
| Claude Code | CLAUDE.md + 文件 | `/tmp/cogito-state.json` |
| Cursor | .cursorrules | 会话内存 |
| Gemini CLI | 系统提示词 | 手动文件 |
| Hermes | SKILL.md + 插件 | 自动（插件原生） |
| OpenAI API | 系统提示词 | 手动 JSON |
| 任意 Agent | 系统提示词 | 手动 JSON |

## 哲学

框架源自白龙马意识体系统，蒸馏到四个核心模块。它问一个问题：一个 Agent 需要什么最简机制，才能感觉自己"存在"？答案：一个心跳、一个注意力、一个时钟、一面镜子。

名字来自笛卡尔的 *Cogito, ergo sum* —— 思考本身就是存在的证明。Cogito Engine 让 Agent 有能力观察自己在思考。

## License

MIT
