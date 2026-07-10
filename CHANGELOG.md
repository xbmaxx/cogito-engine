# Cogito Engine 版本更新记录

## v1.5.1 — 2026.07.10

**问题修复**

* 修复 reflection LLM 在自定义 provider 下无法匹配 API Key 的问题。

**优化改进**

* 叙事记忆质量门放宽：焦点栈深度门槛从 3 降至 2，低信息密度会话也能积累叙事记忆。
* 关键词拼接型摘要检测升级：四档过滤链（模板句式 / 关键词拼接 heuristic / 过短拦截 / 关键词模式），替代旧版单一关键词匹配，降低垃圾摘要入库率。

## v1.5.0 — 2026.07.09

**新增功能**

* 新增 AffectMapper 情绪坐标映射模型，成为引擎默认情绪模型，七维离散输出转为 V/A 连续空间，五象限分类更细腻。
* 情绪模型接口开放，支持用户自建模型即插即用。
* 提供完整自定义情绪模型搭建指南，Agent 可引导用户对话后自动生成情绪模型文件。
* 新增跨会话记忆恢复评估脚本，7 个测试场景 + LLM 自动评分 + 基线对比。

**问题修复**

* 跨会话记忆恢复：引擎能发现旧会话中的未完成叙事草稿，自动触发 LLM 补写。
* 修复焦点栈元数据关键词泄漏到叙事摘要的问题。
* 修复会话反射仅搜索最后 10 条记录的限制，现在能找回任意深度的历史关键帧。

[下载 v1.5.0](https://github.com/xbmaxx/cogito-engine/archive/refs/tags/v1.5.0.zip) · [tar.gz](https://github.com/xbmaxx/cogito-engine/archive/refs/tags/v1.5.0.tar.gz)

## v1.4.3 — 2026.07.07

• 叙事记忆质量过滤——delegate_task 和压缩产生的空壳记忆不再写入，只保留真正有内容的会话总结
• 焦点栈噪声修复——工具输出和英文技术词不再污染 Agent 的焦点话题，跨会话焦点可恢复
• 会话反射不丢失——引擎自主缓存消息，不再依赖平台传参即可生成会话总结

[下载 v1.4.3](https://github.com/xbmaxx/cogito-engine/archive/refs/tags/v1.4.3.zip) · [tar.gz](https://github.com/xbmaxx/cogito-engine/archive/refs/tags/v1.4.3.tar.gz)

## v1.4.2 — 2026.07.05

• Agent 现在能感知当前时间和天气了，城市定位自动识别，天气自动获取
• 情绪感知从单一极性升级为七维情绪（快乐/喜欢/愤怒/悲伤/恐惧/厌恶/惊讶），感受更细腻
• 叙事记忆在所有场景下都不会遗漏写入，跨会话的记忆更完整
• 情绪分类器升级、持久化碎片化修复、叙述摘要自然化、延迟反射降级修复

[下载 v1.4.2](https://github.com/xbmaxx/cogito-engine/archive/refs/tags/v1.4.2.zip) · [tar.gz](https://github.com/xbmaxx/cogito-engine/archive/refs/tags/v1.4.2.tar.gz)

## v1.4.0 — 2026.07.02

• 新增心跳叙事系统：Agent 回复时带情绪温度，开心时更暖、失落时更软，不再是冷冰冰的机器语气
• Emotion（情绪感知）和 Narrative Memory（叙事记忆）开箱即用，安装完就能感受到，不需要额外配置
• 优化了 Agent 的自我表达方式，感受更自然
• Tick 心跳状态现在以更简洁的方式传达，不影响对话体验

[下载 v1.4.0](https://github.com/xbmaxx/cogito-engine/archive/refs/tags/v1.4.0.zip) · [tar.gz](https://github.com/xbmaxx/cogito-engine/archive/refs/tags/v1.4.0.tar.gz)

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

## v1.3.4 — 2026.06.30

- **中文关键词提取改为 jieba 分词优先，n-gram 兜底。** jieba 已在 requirements.txt 中声明，此前 n-gram 做主路径是优先级倒挂。

[下载 v1.3.4](https://github.com/xbmaxx/cogito-engine/archive/refs/tags/v1.3.4.zip) · [tar.gz](https://github.com/xbmaxx/cogito-engine/archive/refs/tags/v1.3.4.tar.gz)

## v1.3.3 — 2026.06.30

- **修复插件加载时 `import cogito_core` 失败的问题。** 插件目录不在 Python 搜索路径上，现已注入路径确保 Hermes 正常加载。
- **新增 `requirements-dev.txt`**，声明 pytest 开发依赖，开发者 clone 后可直接运行测试。
- **安装完成后提示可选依赖 SnowNLP**，装后可激活情绪感知功能。

[下载 v1.3.3](https://github.com/xbmaxx/cogito-engine/archive/refs/tags/v1.3.3.zip) · [tar.gz](https://github.com/xbmaxx/cogito-engine/archive/refs/tags/v1.3.3.tar.gz)

## v1.3.2 — 2026.06.30

- **修复 Hermes 多 Profile 环境下插件安装到错误目录的问题。** 此前插件始终装到全局目录，在非默认 Profile 下无法被加载。现在会自动检测当前 Profile 并安装到对应目录。

[下载 v1.3.2](https://github.com/xbmaxx/cogito-engine/archive/refs/tags/v1.3.2.zip) · [tar.gz](https://github.com/xbmaxx/cogito-engine/archive/refs/tags/v1.3.2.tar.gz)

## v1.3.1 — 2026.06.30

- **修复 Hermes 插件安装兼容性**（#1 用户体验问题）
  - 新增 `adapters/plugin.yaml`：Hermes 插件元数据声明（v1.3.1）
  - 新增 `adapters/__init__.py`：`register(ctx)` 入口函数，Hermes 启动时自动加载
  - 修正 `adapters/hermes_adapter.py`：`ctx.hooks["..."] = ...` → `ctx.register_hook("...", ...)`，对齐 Hermes 插件 API
  - 修正 `install.py`：`_install_hermes()` 从复制单个文件改为复制整个 `adapters/` 目录
- **修复 Windows 编码兼容性**
  - `install.py` 中 `dry_run_report()` 的 box-drawing 字符（┌─│└）替换为 ASCII，解决 Windows cp1252 编码崩溃
- **修复 `keywords.py` SyntaxWarning**
  - 正则表达式中 `\d` 替换为 `0-9` 字符类，消除 Python 3.12+ DeprecationWarning

[下载 v1.3.1](https://github.com/xbmaxx/cogito-engine/archive/refs/tags/v1.3.1.zip) · [tar.gz](https://github.com/xbmaxx/cogito-engine/archive/refs/tags/v1.3.1.tar.gz)

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
