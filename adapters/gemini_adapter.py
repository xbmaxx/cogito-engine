"""
gemini_adapter.py —— Gemini CLI BeforeModel hook 适配器。

Gemini CLI 的 BeforeModel hook 机制：
- stdin 读取 Gemini JSON 上下文
- 提取用户消息
- 调 CogitoEngine.process()
- stdout 返回修改后的 model input（将 XML 注入为前缀）

Gemini CLI hook 配置示例 (.gemini/settings.json)：
{
  "hooks": {
    "BeforeModel": {
      "command": "python3 /path/to/adapters/gemini_adapter.py"
    }
  }
}

输入 JSON 格式 (Gemini CLI 传给 hook)：
{
  "messages": [
    {"role": "user", "parts": [{"text": "用户消息"}]},
    {"role": "model", "parts": [{"text": "模型回复"}]}
  ]
}

输出 JSON 格式 (hook 返回给 Gemini CLI)：
{
  "messages": [
    {"role": "user", "parts": [{"text": "<consciousness>...</consciousness>\\n\\n用户消息"}]}
  ]
}
"""

from __future__ import annotations

import json
import sys
import os
import argparse
from typing import Any, Dict, List, Optional

# 确保能找到 cogito_core
sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    ),
)

from cogito_core.engine import CogitoEngine, EngineState


class GeminiAdapter:
    """Gemini CLI BeforeModel hook 适配器。

    封装了 Gemini hook 的完整生命周期：
    - parse_input(): 解析 stdin JSON
    - process(): 调 engine.process() 生成 XML
    - inject(): 将 XML 注入 Gemini 消息格式
    - end_session(): 会话结束收尾
    """

    def __init__(
        self,
        include_weather: bool = False,
        include_battery: bool = True,
        include_resources: bool = True,
    ) -> None:
        self.engine = CogitoEngine(
            include_weather=include_weather,
            include_battery=include_battery,
            include_resources=include_resources,
        )
        self.state = EngineState()

    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """处理 Gemini hook 输入，返回修改后的 model input。"""
        messages = gemini_messages_to_standard(data.get("messages", []))
        xml, self.state = self.engine.process(messages, self.state)
        return inject_xml_into_gemini_input(data, xml)

    def end_session(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """会话结束时的收尾操作。"""
        messages = gemini_messages_to_standard(data.get("messages", []))
        self.engine.end_session(state=self.state, messages=messages)
        return {
            "messages": data.get("messages", []),
            "end_session": True,
        }


def parse_gemini_input() -> Dict[str, Any]:
    """从 stdin 读取 Gemini CLI 传入的 hook JSON。"""
    raw = sys.stdin.read()
    if not raw.strip():
        return {"messages": []}
    return json.loads(raw)


def gemini_messages_to_standard(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """将 Gemini 消息格式转换为标准 messages 格式。

    Gemini 格式: {"role": "user", "parts": [{"text": "..."}]}
    标准格式:    {"role": "user", "content": "..."}
    """
    result = []
    for msg in messages:
        role = msg.get("role", "user")
        # 映射 Gemini role → 标准 role
        role_map = {"model": "assistant", "user": "user", "system": "system"}
        std_role = role_map.get(role, role)

        parts = msg.get("parts", [])
        content = ""
        for part in parts:
            if isinstance(part, dict) and "text" in part:
                content += part["text"] + "\n"
        content = content.strip()

        result.append({"role": std_role, "content": content})

    return result


def inject_xml_into_gemini_input(
    original: Dict[str, Any], xml: str
) -> Dict[str, Any]:
    """将意识 XML 注入到 Gemini 消息的最前面。

    策略：将 XML 文本作为第一条用户消息的文本前缀注入。
    """
    # 深拷贝原始输入
    modified = json.loads(json.dumps(original))

    messages = modified.get("messages", [])
    if not messages:
        # 创建新消息
        modified["messages"] = [
            {
                "role": "user",
                "parts": [{"text": xml}],
            }
        ]
        return modified

    # 在第一条用户消息前插入 XML
    for msg in messages:
        if msg.get("role") == "user":
            parts = msg.get("parts", [])
            if parts and isinstance(parts[0], dict) and "text" in parts[0]:
                parts[0]["text"] = f"{xml}\n\n{parts[0]['text']}"
            else:
                parts.insert(0, {"text": xml})
            break
    else:
        # 没有用户消息，插入一条
        messages.insert(0, {"role": "user", "parts": [{"text": xml}]})

    return modified


def main() -> None:
    """Gemini hook 主入口。"""
    parser = argparse.ArgumentParser(
        description="Cogito Engine Gemini CLI BeforeModel hook"
    )
    parser.add_argument(
        "--session-end",
        action="store_true",
        help="触发 end_session 而非 process",
    )
    parser.add_argument(
        "--inject-strategy",
        choices=["prefix_user", "new_system"],
        default="prefix_user",
        help="XML 注入策略 (default: prefix_user)",
    )
    args = parser.parse_args()

    # 读取 Gemini 输入
    data = parse_gemini_input()
    messages = gemini_messages_to_standard(data.get("messages", []))

    # 创建引擎
    engine = CogitoEngine(
        include_weather=False,
        include_battery=True,
        include_resources=True,
    )

    if args.session_end:
        # 会话结束模式
        state = EngineState()
        engine.end_session(state=state, messages=messages)
        # 返回空消息（不修改 model input）
        result = {
            "messages": data.get("messages", []),
            "end_session": True,
        }
        print(json.dumps(result, ensure_ascii=False))

    else:
        # 正常 process 模式
        state = EngineState()
        xml, _new_state = engine.process(messages, state)

        if args.inject_strategy == "new_system":
            # 创建独立的 system 消息
            modified = json.loads(json.dumps(data))
            msgs = modified.get("messages", [])
            msgs.insert(0, {"role": "system", "parts": [{"text": xml}]})
            modified["messages"] = msgs
        else:
            # 默认：注入到第一条用户消息前缀
            modified = inject_xml_into_gemini_input(data, xml)

        print(json.dumps(modified, ensure_ascii=False))


if __name__ == "__main__":
    main()
