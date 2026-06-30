"""
hermes_adapter.py —— Hermes Plugin 适配器。

实现 HermesPlugin 接口，将 Hermes 的 hooks 事件翻译为 CogitoEngine 调用。

接口：
    register(ctx):  注册 tools + hooks
    _pre_llm_call(ctx):  调 CogitoEngine.process()，注入意识 XML
    _on_session_end(ctx): 调 CogitoEngine.end_session()

使用方式（在 Hermes 插件中）：
    from cogito_engine.adapters import HermesAdapter
    adapter = HermesAdapter()
    # Hermes 框架会自动调用 register / _pre_llm_call / _on_session_end
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from cogito_core.engine import CogitoEngine, EngineState

logger = logging.getLogger(__name__)

# XML 注入策略：
# 1) "prefix": 在最新的用户消息前插入 XML 作为 system 消息
# 2) "prepend_system": 将 XML 插入到 messages 最前面的一条 system 消息中
XML_INJECT_STRATEGY = "prepend_system"


def _load_state_from_ctx(ctx: Any, session_id: str = "") -> EngineState:
    """从 Hermes 上下文中恢复引擎状态。

    Hermes ctx.state 是 dict-like 对象，存储插件的持久化数据。
    """
    raw = {}
    try:
        raw = ctx.state.get("cogito_engine", {})
    except Exception:
        pass
    if not isinstance(raw, dict):
        raw = {}
    return EngineState.from_dict(raw, session_id=session_id)


def _save_state_to_ctx(ctx: Any, state: EngineState) -> None:
    """将引擎状态持久化回 Hermes 上下文。"""
    try:
        ctx.state["cogito_engine"] = state.to_dict()
    except Exception as exc:
        logger.warning("保存引擎状态到 ctx 失败: %s", exc)


def _extract_user_text(messages: List[Dict[str, Any]]) -> str:
    """从消息列表中提取最后一条用户文本（用于注入后替换）。"""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                # 处理多模态 content blocks
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        return block.get("text", "")
    return ""


def _inject_xml_prefix(messages: List[Dict[str, Any]], xml: str) -> List[Dict[str, Any]]:
    """将意识 XML 注入到消息列表：替换最后一条用户消息为 XML + 原文。"""
    import copy
    result = copy.deepcopy(messages)

    user_text = _extract_user_text(messages)
    if not user_text:
        # 无用户文本，在开头插入 system 消息
        result.insert(0, {"role": "system", "content": xml})
        return result

    # 找到最后一条用户消息并前置 XML
    for i in range(len(result) - 1, -1, -1):
        if result[i].get("role") == "user":
            content = result[i].get("content", "")
            if isinstance(content, str):
                result[i]["content"] = f"{xml}\n\n{content}"
            elif isinstance(content, list):
                result[i]["content"] = [
                    {"type": "text", "text": f"{xml}\n\n{user_text}"}
                ]
            break

    return result


def _inject_xml_prepend_system(
    messages: List[Dict[str, Any]], xml: str
) -> List[Dict[str, Any]]:
    """将 XML 插入到消息列表的第一条 system 消息中。"""
    import copy
    result = copy.deepcopy(messages)

    # 查找第一条 system 消息
    for msg in result:
        if msg.get("role") == "system":
            content = msg.get("content", "")
            if isinstance(content, str):
                msg["content"] = f"{xml}\n\n{content}"
            return result

    # 没有 system 消息，插入一条
    result.insert(0, {"role": "system", "content": xml})
    return result


# ── HermesAdapter 主类 ──


class HermesAdapter:
    """Hermes Plugin 适配器。

    生命周期：
        1. Hermes 加载插件 → register(ctx) 被调用
        2. 每次 LLM 调用前 → _pre_llm_call(ctx) 被调用
        3. 会话结束时 → _on_session_end(ctx) 被调用
    """

    def __init__(
        self,
        include_weather: bool = False,
        include_battery: bool = True,
        include_resources: bool = True,
        inject_strategy: str = XML_INJECT_STRATEGY,
    ) -> None:
        self.engine = CogitoEngine(
            include_weather=include_weather,
            include_battery=include_battery,
            include_resources=include_resources,
        )
        self.inject_strategy = inject_strategy

    # ── HermesPlugin 接口 ──

    def register(self, ctx: Any) -> None:
        """Hermes 插件注册入口。

        在插件加载时调用，用于：
        - 验证引擎可用
        - 注册自定义 tools（可选，此处保留空壳）
        - 注入 hooks 到 ctx
        """
        logger.info("HermesAdapter 已注册，session_id=%s", getattr(ctx, "session_id", "N/A"))

        # 注册 hook 回调
        ctx.register_hook("pre_llm_call", self._pre_llm_call)
        ctx.register_hook("on_session_end", self._on_session_end)

        # 可选：注册 tools（让 Agent 能主动触发感知）
        # 此处可扩展 register_cogito_tools(ctx)

    def _pre_llm_call(self, ctx: Any) -> None:
        """pre_llm_call hook：在 LLM 调用前注入意识上下文。

        1. 从 ctx 获取 messages 和 session_id
        2. 恢复/创建引擎状态
        3. 调用 engine.process() 生成 XML
        4. 将 XML 注入 messages
        5. 更新 ctx.messages 和状态
        """
        try:
            messages = ctx.messages
            if not messages:
                return

            session_id = getattr(ctx, "session_id", "")
            state = _load_state_from_ctx(ctx, session_id=session_id)

            # 调用引擎处理
            xml, new_state = self.engine.process(messages, state)

            if not xml or xml.strip() == "<consciousness>" or not xml.strip():
                # 引擎未产出有效 XML（例如重复注入被跳过）
                _save_state_to_ctx(ctx, new_state)
                return

            # 注入 XML
            if self.inject_strategy == "prefix":
                ctx.messages = _inject_xml_prefix(messages, xml)
            else:
                ctx.messages = _inject_xml_prepend_system(messages, xml)

            # 保存状态
            _save_state_to_ctx(ctx, new_state)

            logger.debug(
                "pre_llm_call: XML 已注入 (%d chars), tick=%d",
                len(xml),
                new_state.ticker.tick_counter,
            )

        except Exception as exc:
            logger.error("pre_llm_call 失败: %s", exc, exc_info=True)

    def _on_session_end(self, ctx: Any) -> Optional[Dict[str, Any]]:
        """on_session_end hook：会话结束时的收尾操作。

        1. 恢复引擎状态
        2. 调用 engine.end_session(state, messages)
        3. 返回反射数据（如有）
        4. 持久化最终状态

        Returns:
            反射数据字典，或 None（如无数据）
        """
        try:
            messages = ctx.messages
            session_id = getattr(ctx, "session_id", "")
            state = _load_state_from_ctx(ctx, session_id=session_id)

            # 生成焦点摘要（从焦点栈中提取）
            focus_summary = ""
            if state.focus_stack.stack:
                topics = [
                    ", ".join(f["topic"]) for f in state.focus_stack.stack
                ]
                focus_summary = " | ".join(topics)

            # 执行收尾
            self.engine.end_session(
                state=state,
                messages=messages,
                focus_summary=focus_summary,
            )

            # 读取最新反射
            reflection = None
            try:
                latest = self.engine.session_reflector.load_recent(1)
                if latest:
                    reflection = latest[0]
            except Exception:
                pass

            # 最终状态持久化
            _save_state_to_ctx(ctx, state)

            logger.info(
                "on_session_end: 会话结束，tick=%d",
                state.ticker.tick_counter,
            )

            return reflection

        except Exception as exc:
            logger.error("on_session_end 失败: %s", exc, exc_info=True)
            return None


# ── 独立测试入口 ──

def _demo() -> None:
    """命令行演示。"""
    adapter = HermesAdapter()
    print(f"HermesAdapter 已创建，引擎: {adapter.engine}")
    print(f"注入策略: {adapter.inject_strategy}")

    # 模拟消息
    test_msgs = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "今天天气怎么样？帮我写一段代码。"},
    ]
    state = EngineState(session_id="demo")
    xml, new_state = adapter.engine.process(test_msgs, state)
    print(f"\n生成的意识 XML ({len(xml)} chars):")
    print(xml)


if __name__ == "__main__":
    _demo()
