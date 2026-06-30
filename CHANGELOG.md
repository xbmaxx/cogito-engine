# Cogito Engine 版本更新记录

## v1.0.0 — 2026.06.29

- 创建项目，定义 4 个核心模块：TICK 心跳、Focus Stack 焦点栈、Temporal 时间解析、Self-Perception 自我感知
- 定义 `<consciousness>` XML 输出格式（9 元素）
- 核心层 4 份规格文档：`tick-spec.md`、`focus-stack-spec.md`、`temporal-spec.md`、`self-perception-spec.md`
- `consciousness-format.md` 定义 XML Schema
- `implementation-python.md` 提供 Python 参考实现
- 3 份平台示例：Claude Code、Cursor、Generic Agent
- Agent 需手动调用 `consciousness_pulse()` 输出 XML

[下载 v1.0.0](https://github.com/xbmaxx/cogito-engine/archive/refs/tags/v1.0.0.zip) · [tar.gz](https://github.com/xbmaxx/cogito-engine/archive/refs/tags/v1.0.0.tar.gz)

## v1.1.0 — 2026.06.29

- 新增感知层 4 个可选模块：EnvSensor 环境感知、Narrative Memory 叙事记忆、Text Emotion 文本情绪、Session Reflector 会话反射
- 每个模块带能力探针，Agent 根据平台可用性自发现并决定启用/跳过
- EnvSensor：时间/系统/电池/天气探针，不硬编码数据源
- Narrative Memory：跨会话叙事日记，存储未解决问题和重复模式
- Text Emotion：SnowNLP 贝叶斯情感分析
- Session Reflector：会话结束自动生成叙事摘要
- 新增 4 份感知层规格文档
- 更新 `consciousness-format.md` 补充感知层 XML 元素

[下载 v1.1.0](https://github.com/xbmaxx/cogito-engine/archive/refs/tags/v1.1.0.zip) · [tar.gz](https://github.com/xbmaxx/cogito-engine/archive/refs/tags/v1.1.0.tar.gz)

## v1.2.0 — 2026.06.29

- Text Emotion 升级双模：中文 SnowNLP + 英文 TextBlob/NLTK，自动检测语言
- Focus Stack 支持 jieba 中文分词回退（未安装 jieba 时降级为 N-gram）
- 新增 `scripts/train_sentiment.py`：零依赖训练器 + 验证器
- 新增 `references/training-guide.md`：自定义情感模型训练指南
- SKILL.md 中 8 个模块合并为一张激活表格

[下载 v1.2.0](https://github.com/xbmaxx/cogito-engine/archive/refs/tags/v1.2.0.zip) · [tar.gz](https://github.com/xbmaxx/cogito-engine/archive/refs/tags/v1.2.0.tar.gz)

## v1.2.1 — 2026.06.29

- Focus Stack N-gram 优化：30+ 停用词、长度加权、重复字符过滤、空格填充修复
- 英文关键词最小长度从 2 字调整为 3 字，减少噪音碎片
- 中文主题匹配：Jaccard 重叠正确检测共享主题
- Self-Perception 新增 `snapshot()` 自我快照：avg_len、short_ratio、markdown_usage、style_cluster
- 快照提供 Agent 行为指纹，作为风格漂移检测基准

[下载 v1.2.1](https://github.com/xbmaxx/cogito-engine/archive/refs/tags/v1.2.1.zip) · [tar.gz](https://github.com/xbmaxx/cogito-engine/archive/refs/tags/v1.2.1.tar.gz)

## v1.3.0 — 2026.06.30

- 新增 `cogito_core/`：通用 Python 引擎包（13 个文件，可在 Hermes、Claude Code、Copilot 等多个 Agent 平台运行）
  - `engine.py`：CogitoEngine 编排器，`process(messages, state) → xml` 纯函数接口
  - `persistence.py`：统一持久化层，读写 `~/.cogito/`（可配 `COGITO_HOME`）
- 新增 `adapters/`：6 个平台适配器
  - `hermes_adapter.py`：Hermes Plugin 接口（register / pre_llm_call / on_session_end）
  - `hook_entry.py`：Claude Code / Copilot / Codex 共用 CLI（stdin JSON → stdout additionalContext）
  - `gemini_adapter.py`：Gemini CLI BeforeModel hook
  - `prompt_only_adapter.py`：Cursor / Windsurf 降级（.cursorrules 规则模板）
- 新增 `install.py`：全自动安装脚本
  - 平台检测：Hermes / Claude / Copilot / Codex / Gemini / Cursor / Windsurf
  - 自动生成 hooks 配置文件并写入对应路径
  - 支持 `--update`、`--platform`、`--dry-run` 参数
- 新增 `install.sh`：一键安装入口 `curl -sSL ... | bash`
- 新增 `test/`：`test_engine.py`、`test_adapters.py`、`test_keywords.py`（27 个测试全部通过）
- SKILL.md 新增自动化检查指令块：LLM 加载 Skill 时自动检测插件是否安装，未安装则自动执行 install.py
- README.md 新增平台支持表和快速安装命令
- 持久化格式 100% 对齐 Cogito Engine XML Schema

[下载 v1.3.0](https://github.com/xbmaxx/cogito-engine/archive/refs/tags/v1.3.0.zip) · [tar.gz](https://github.com/xbmaxx/cogito-engine/archive/refs/tags/v1.3.0.tar.gz)
