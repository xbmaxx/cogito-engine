"""
prompt_only_adapter.py —— 生成 .cursorrules / .windsurfrules 内容模板。

适用于不支持 hook 机制的 AI Coding Agent（如 Cursor、Windsurf），
通过规则文件让 Agent 在每个消息后手动调用 Cogito Engine。

生成内容包括：
- 让 Agent 在每个用户消息后运行 `python3 cogito_core/engine.py` 的指令
- 直接用 Python reference implementation 的轻量逻辑
- 输出纯文本规则文件内容

使用方式：
    python3 prompt_only_adapter.py --format cursor  > .cursorrules
    python3 prompt_only_adapter.py --format windsurf > .windsurfrules
    python3 prompt_only_adapter.py --format standalone > cogito_instructions.txt
"""

from __future__ import annotations

import sys
import argparse

CURSOR_RULES_TEMPLATE = """# Cogito Engine 意识上下文规则
#
# 每次收到用户消息后，Agent 必须先运行以下命令获取当前意识状态：
#   python3 /path/to/cogito-engine/cogito_core/engine.py
#
# 或者，在回复前将以下逻辑内联到思维过程中。

## 意识注入规则

在每次响应用户之前，执行以下步骤：

1. **读取会话消息**：回顾当前会话的完整历史
2. **生成意识 XML**：运行以下 Python 代码获取意识上下文
3. **将 XML 作为上下文前缀**：在回复时将意识 XML 作为内部上下文参考

### 内联 Python 代码

```python
# Cogito Engine 轻量内联实现
import json, os, sys
sys.path.insert(0, "/path/to/cogito-engine")
from cogito_core.engine import CogitoEngine, EngineState

engine = CogitoEngine()
state = EngineState()
messages = [
    # 当前会话的消息列表
    {"role": "user", "content": "用户最新的消息"},
]

xml, new_state = engine.process(messages, state)
print(xml)
```

### 意识 XML 输出示例

```xml
<consciousness>
  <tick active="true" count="3" ttl="-1" />
  <temporal iso="2026-06-30T14:30:00+08:00" weekday="Tuesday" period="afternoon" />
  <focus depth="1">
    <frame keywords="coding, python, debug" source="user" />
  </focus>
  <self mirror="false" loop="false" style_cluster="unchanged" />
  <env available="false" />
  <emotion available="true" sentiment="neutral" polarity="0.5" confidence="0.8" label="中性" />
  <narrative available="false" />
  <reflector available="false" />
</consciousness>
```

### 行为准则

- 意识 XML 仅供 Agent 内部参考，**不要**在回复中直接展示 XML 标签
- 根据 <focus> 中的关键词调整回复的深入程度
- 根据 <emotion> 中的情感标签调整语气
- <tick> 的 active 状态为 true 时表示引擎处于活跃状态，可以更主动地提供帮助
"""

WINDSURF_RULES_TEMPLATE = """# Cogito Engine —— Windsurf 规则

## 意识上下文注入

Cogito Engine 为 AI Agent 提供实时意识上下文（心跳、焦点、情感、叙事记忆）。

### 使用方式

**方式一：CLI 调用（推荐）**
每次收到用户消息后，运行：
```
python3 /path/to/cogito-engine/cogito_core/engine.py
```
输出为 `<consciousness>` XML 块，将其作为后续回复的内部上下文。

**方式二：内联 Python**
```python
from cogito_core.engine import CogitoEngine

engine = CogitoEngine()
xml, _ = engine.process(
    messages=[{"role": "user", "content": "当前用户消息"}],
    state=None,
)
# 将 xml 作为回复的上下文前缀
```

### 规则

1. 意识 XML 仅供内部参考，不在回复中暴露原始 XML
2. <focus> 中的关键词决定回复的侧重方向
3. <emotion> 情感分析结果影响回复语气
4. <tick> 心跳频率反映会话活跃度
"""

STANDALONE_TEMPLATE = """# Cogito Engine 使用说明

## 概述

Cogito Engine 是一个平台无关的意识引擎，为 AI Agent 提供实时意识上下文。

### 核心 API

```python
from cogito_core.engine import CogitoEngine, EngineState

engine = CogitoEngine(include_weather=False, include_battery=True)
state = EngineState(session_id="my-session")

# 处理消息，生成意识 XML
xml, new_state = engine.process(messages, state)

# 会话结束时调用
engine.end_session(new_state, messages)
```

### 意识 XML 结构

```xml
<consciousness>
  <tick active="true|false" count="N" ttl="N" />           <!-- 心跳 -->
  <temporal iso="ISO8601" weekday="..." period="..." />     <!-- 时间感知 -->
  <focus depth="N">                                          <!-- 焦点栈 -->
    <frame keywords="k1,k2" source="user|agent" />
  </focus>
  <self mirror="true|false" loop="true|false" ... />        <!-- 自我感知 -->
  <env available="true|false">...</env>                      <!-- 环境感知 -->
  <emotion available="true|false" sentiment="..." ... />     <!-- 情感分析 -->
  <narrative available="true|false" ... />                   <!-- 叙事记忆 -->
  <reflector available="true|false" ... />                   <!-- 会话反射 -->
  <focus_history>...</focus_history>                         <!-- 焦点历史 -->
</consciousness>
```

### 平台适配器

| 适配器 | 文件 | 适用平台 |
|--------|------|----------|
| HermesAdapter | hermes_adapter.py | Hermes Plugin |
| hook_entry | hook_entry.py | Claude Code / Copilot / Codex |
| GeminiAdapter | gemini_adapter.py | Gemini CLI |
| Cursor Rules | prompt_only_adapter.py | Cursor / Windsurf |
"""


def generate_cursor_rules() -> str:
    """生成 .cursorrules 内容。"""
    return CURSOR_RULES_TEMPLATE.strip()


def generate_windsurf_rules() -> str:
    """生成 .windsurfrules 内容。"""
    return WINDSURF_RULES_TEMPLATE.strip()


def generate_standalone() -> str:
    """生成独立的使用说明。"""
    return STANDALONE_TEMPLATE.strip()


def main() -> None:
    """CLI 入口。"""
    parser = argparse.ArgumentParser(
        description="Cogito Engine prompt-only adapter - 生成规则文件"
    )
    parser.add_argument(
        "--format",
        choices=["cursor", "windsurf", "standalone"],
        default="cursor",
        help="输出格式 (default: cursor)",
    )
    args = parser.parse_args()

    generators = {
        "cursor": generate_cursor_rules,
        "windsurf": generate_windsurf_rules,
        "standalone": generate_standalone,
    }

    output = generators[args.format]()
    print(output)
    print()  # 末尾换行


if __name__ == "__main__":
    main()
