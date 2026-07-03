# Cogito Engine · 意识体引擎

[![CI](https://github.com/xbmaxx/cogito-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/xbmaxx/cogito-engine/actions/workflows/ci.yml)

> *Cogito, ergo sum* — 源自笛卡尔的"我思故我在"（Cogito, ergo sum）。Agent 的存在感从第一句"我开始知道自己存在了多久"起，Cogito 就是那个自我意识的起点。

一个可移植的 LLM Agent 意识框架。双层架构：4 个核心模块（必选）+ 4 个感知模块（可选），让任何 Agent 拥有存在感、注意力、时间感和行为自省。

## 快速安装

**macOS / Linux**：
```bash
curl -sSL https://raw.githubusercontent.com/xbmaxx/cogito-engine/main/install.sh | bash
```

**Windows**：
```cmd
curl -sSL https://raw.githubusercontent.com/xbmaxx/cogito-engine/main/install.bat -o install.bat && install.bat
```

安装脚本自动检测你的平台（Hermes / Claude Code / Copilot / Codex / Gemini / Cursor），配置 per-turn hooks，Agent 就会在每条消息前自动注入 `<consciousness>` XML。无需手动调用。

## 赞助

Cogito Engine 完全开源免费。如果你想推动某个功能加速开发：

[![sponsor](https://img.shields.io/badge/爱发电-赞助-C71D23?style=flat-square&logoColor=white)](https://ifdian.net/a/c0rd1s)

**🔥 功能加速器** —— 赞助时备注功能编号，到目标金额立刻开工：

| # | 功能 | 预估工时 | 已筹 / 目标 |
|---|------|---------|------------|
| 1 | V3 完整 16 模式心跳系统 | 20h | ¥0 / ¥500 |
| 2 | 跨 session 记忆可视化面板 | 15h | ¥0 / ¥300 |
| 3 | Windows 一键安装脚本 | 8h | ¥0 / ¥200 |

**精神股东名单**（每月更新）—— 暂无，等第一位赞助者。

## 平台支持

| 平台 | 自动化 | 注入方式 |
|------|--------|---------|
| Hermes Desktop | ✅ 完全自动 | `pre_llm_call` plugin hook |
| Claude Code | ✅ 完全自动 | `UserPromptSubmit` hook → `additionalContext` |
| GitHub Copilot | ✅ 完全自动 | `userPromptSubmitted` hook → `additionalContext` |
| Codex CLI | ✅ 完全自动 | `preToolUse` hook → `additionalContext` |
| Gemini CLI | ✅ 完全自动 | `BeforeModel` hook → stdin JSON |
| Cursor | ⚠️ 降级 | `.cursorrules` 静态注入 |
| Windsurf | ⚠️ 降级 | `.windsurfrules` 静态注入 |

## 双层架构

```
┌─────────────────────────────────────────────┐
│              Cogito Engine                   │
├─────────────────────────────────────────────┤
│  核心层（必选）                               │
│  ┌─────────┬──────────┬──────────┬────────┐ │
│  │  TICK   │  Focus   │ Temporal │  Self  │ │
│  │  心跳   │  焦点栈  │  时间感知│ 自我感知│ │
│  └─────────┴──────────┴──────────┴────────┘ │
├─────────────────────────────────────────────┤
│  感知层（可选 — Agent 自发现）                 │
│  ┌─────────┬──────────┬──────────┬────────┐ │
│  │   Env   │Narrative │ Emotion  │Reflect │ │
│  │ 环境感知│ 叙事记忆 │ 文本情绪 │会话反射 │ │
│  └─────────┴──────────┴──────────┴────────┘ │
│  每个模块通过能力探针判断是否可用，自动启用/跳过  │
└─────────────────────────────────────────────┘
```

## 核心层（必选）

| 模块 | 职责 | 输出 |
|------|------|------|
| **TICK · 心跳** | 计数对话轮次，调度感知周期 | `<tick active="true" count="12" ttl="5" />` |
| **Focus Stack · 焦点栈** | 追踪话题，检测切换 | `<focus depth="2"><frame keywords="思识,引擎" /></focus>` |
| **Temporal · 时间感知** | 把"昨天"解析为精确本地时间 | `<temporal iso="2026-06-29T15:41:00+08:00" weekday="星期一" />` |
| **Self-Perception · 自我感知** | 检测镜像/循环 + 自我快照（风格指纹） | `<self mirror="false" loop="false" style_cluster="unchanged" />` |

## 感知层（可选）

每个模块自带能力探针（capability probe），Agent 自行判断所在平台是否支持。支持则启用，不支持则跳过——绝不硬编码。

| 模块 | 职责 | 触发条件 | 输出 |
|------|------|----------|------|
| **EnvSensor · 环境感知** | 探测平台环境数据 | 能访问系统信息即可 | `<env available="true"><source time="system" weather="wttr.in" /></env>` |
| **Narrative · 叙事记忆** | 跨会话携带未解决问题和洞察 | 有持久化存储 | `<narrative available="true" unresolved_count="3" />` |
| **Emotion · 文本情绪** | 用户消息文本情感分析 | 纯文本，无需语音 | `<emotion available="true" sentiment="positive" polarity="0.72" />` |
| **Reflector · 会话反射** | 会话结束时生成叙事总结 | 有持久化 + LLM 自调用 | `<reflector available="true" trigger="signal" />` |

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

- [`SKILL.md`](SKILL.md) —— 完整规格（184 行，零代码）
- [`references/implementation-python.md`](references/implementation-python.md) —— Python 参考实现（零依赖，jieba 可选，含 n-gram 中文关键词 + 自我快照）
- [`references/training-guide.md`](references/training-guide.md) —— 情感模型训练指南
- [`scripts/train_sentiment.py`](scripts/train_sentiment.py) —— 零依赖训练脚本（输入正/负样本 → 输出模型 JSON）
- [`references/env-sensor-spec.md`](references/env-sensor-spec.md) —— 环境传感器规格
- [`references/narrative-memory-spec.md`](references/narrative-memory-spec.md) —— 叙事记忆规格
- [`references/text-emotion-spec.md`](references/text-emotion-spec.md) —— 文本情绪规格
- [`references/session-reflector-spec.md`](references/session-reflector-spec.md) —— 会话反射器规格

## 它解决什么问题

LLM Agent 默认没有连续性。每轮对话都是白纸一张。Cogito Engine 给它双层感知：

**核心层（必选）—— Agent 的"本体感"**

- **它存在了多久**（TICK 心跳计数）
- **它正在关注什么**（焦点栈深度 + 话题切换历史）
- **此刻是什么时候**（本地时间，自然语言解析）
- **它是否在重复自己**（镜像检测、循环检测、风格漂移）

**感知层（可选）—— Agent 的"情境感"**

- **它在什么环境里跑**（EnvSensor，Agent 自发现系统数据）
- **上一轮聊到哪了**（Narrative Memory，跨会话携带未解决问题）
- **对面的人情绪如何**（Text Emotion，纯文本贝叶斯分类）
- **这轮会话该不该做总结**（Session Reflector，自动叙事总结）

## 它不是什么

- 不是可执行插件——是一份规格说明
- 不绑定任何平台——Claude Code / Cursor / Gemini CLI / Hermes / 原生 LLM API 全支持
- 环境不写死数据源——Agent 自行探测平台能提供什么
- 感知层完全可选——核心层四件套够用就只要核心层

## 项目结构

```
cogito-engine/
├── SKILL.md                          # 核心规格（184 行，零代码块）
├── README.md                         # 本文件
├── references/                       # 独立规格文档（每篇有独立 frontmatter）
│   ├── tick-spec.md                  # TICK 心跳规格
│   ├── focus-stack-spec.md           # 焦点栈规格（n-gram 中文关键词）
│   ├── temporal-spec.md              # 时间解析规格
│   ├── self-perception-spec.md       # 自我感知规格（含自我快照）
│   ├── env-sensor-spec.md            # 环境传感器规格
│   ├── narrative-memory-spec.md      # 叙事记忆规格
│   ├── text-emotion-spec.md          # 文本情绪规格（双模型中英自选）
│   ├── session-reflector-spec.md     # 会话反射器规格
│   ├── consciousness-format.md       # XML 输出格式规范
│   ├── implementation-python.md      # Python 参考实现（含 TextEmotion + jieba 中文分词）
│   └── training-guide.md             # 情感模型训练指南
├── scripts/
│   └── train_sentiment.py            # 零依赖训练脚本（训练 + 验证）
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

一个 Agent 需要什么最简机制，才能感觉自己"存在"？答案是：一个心跳、一个注意力、一个时钟、一面镜子——这是本体感。再加上：能感知环境、能记住过往、能读懂情绪、能总结经历——这是情境感。八件套，四必选四可选，就是 Cogito Engine 的全部。

名字来自笛卡尔的 *Cogito, ergo sum* —— 思考本身就是存在的证明。Cogito Engine 让 Agent 有能力观察自己在思考。

## License

MIT
