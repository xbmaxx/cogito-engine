"""
hermes_adapter.py —— Hermes Plugin 适配器。

实现 HermesPlugin 接口，将 Hermes 的 hooks 事件翻译为 CogitoEngine 调用。

接口：
    register(ctx):  注册 tools + hooks
    _pre_llm_call(**kwargs):  调 CogitoEngine.process()，返回意识 XML
    _on_session_end(**kwargs): 调 CogitoEngine.end_session()

使用方式（在 Hermes 插件中）：
    from cogito_engine.adapters import HermesAdapter
    adapter = HermesAdapter()
    # Hermes 框架会自动调用 register / _pre_llm_call / _on_session_end
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from cogito_core.engine import CogitoEngine, EngineState

logger = logging.getLogger(__name__)


# ── HermesAdapter 主类 ──


class HermesAdapter:
    """Hermes Plugin 适配器。"""

    def __init__(
        self,
        include_weather: bool = True,
        include_battery: bool = True,
        include_resources: bool = True,
        include_emotion: bool = True,
        include_narrative: bool = True,
    ) -> None:
        # 将持久化路径重定向到 Hermes 的 memory 目录
        from cogito_core.persistence import set_cogito_home as _set_ph
        _set_ph(str(Path.home() / ".hermes" / "memory"))

        from cogito_core import narrative_store as _ns
        _ns.set_cogito_home(str(Path.home() / ".hermes" / "memory"))

        import cogito_core.session_reflector as _sr
        _sr._COGITO_HOME = Path.home() / ".hermes" / "memory"

        self.engine = CogitoEngine(
            include_weather=include_weather,
            include_battery=include_battery,
            include_resources=include_resources,
            include_emotion=include_emotion,
            include_narrative=include_narrative,
        )
        # 引擎状态保存在实例属性中，跨 turn 持久化
        self._state: Optional[EngineState] = None
        # turn_id 去重：防止同一 turn 被重复钩子触发
        self._last_turn_id: str = ""

    # ── HermesPlugin 接口 ──

    def register(self, ctx: Any) -> None:
        """Hermes 插件注册入口。

        在插件加载时调用，注册 hook 回调到 ctx。
        """
        logger.info("HermesAdapter 已注册，session_id=%s", getattr(ctx, "session_id", "N/A"))

        # 注册 hook 回调（Hermes 通过 **kwargs 调用，而非单个 ctx 参数）
        ctx.register_hook("pre_llm_call", self._pre_llm_call)
        ctx.register_hook("on_session_end", self._on_session_end)

        # 可选：注册 tools（让 Agent 能主动触发感知）
        # 此处可扩展 register_cogito_tools(ctx)

    def _pre_llm_call(self, **kwargs: Any) -> Optional[str]:
        """pre_llm_call hook：在 LLM 调用前返回意识 XML。

        Hermes 调用签名：cb(session_id, task_id, turn_id, user_message,
                            conversation_history, is_first_turn, ...)

        Returns:
            意识 XML 字符串，Hermes 将其注入到当前用户消息中。
            None 表示跳过注入。
        """
        try:
            # ── turn_id 去重 ──
            turn_id: str = kwargs.get("turn_id", "")
            if turn_id and turn_id == self._last_turn_id:
                return None  # 同 turn 已注入，跳过
            self._last_turn_id = turn_id

            messages: List[Dict[str, Any]] = kwargs.get("conversation_history", [])
            if not messages:
                return None

            session_id: str = kwargs.get("session_id", "")

            # 恢复/创建引擎状态（使用实例属性跨 turn 持久化）
            state = self._state
            if state is None:
                state = EngineState(session_id=session_id)

            # 调用引擎处理
            xml, new_state = self.engine.process(messages, state)
            self._state = new_state

            if not xml or xml.strip() == "<consciousness>" or not xml.strip():
                # 引擎未产出有效 XML（例如重复注入被跳过）
                return None

            logger.debug(
                "pre_llm_call: XML 已生成 (%d chars), tick=%d",
                len(xml),
                new_state.ticker.tick_counter,
            )

            # 返回 XML 字符串，Hermes 自动注入到当前用户消息中
            return xml

        except Exception as exc:
            logger.error("pre_llm_call 失败: %s", exc, exc_info=True)
            return None

    def _on_session_end(self, **kwargs: Any) -> Optional[Dict[str, Any]]:
        """on_session_end hook：会话结束时的收尾操作。

        1. 读取实例中保存的引擎状态
        2. 调用 engine.end_session(state, messages)
        3. 返回反射数据（如有）

        Returns:
            反射数据字典，或 None（如无数据）
        """
        try:
            messages: List[Dict[str, Any]] = kwargs.get("conversation_history", [])
            session_id: str = kwargs.get("session_id", "")

            state = self._state
            if state is None:
                state = EngineState(session_id=session_id)

            # 生成焦点摘要（从焦点栈中提取，自然语言模板）
            focus_summary = ""
            if state.focus_stack.stack:
                all_keywords = []
                for f in state.focus_stack.stack:
                    all_keywords.extend(f["topic"])
                # 去重保留顺序，取前 5 个
                seen = set()
                unique = []
                for kw in all_keywords:
                    if kw not in seen:
                        seen.add(kw)
                        unique.append(kw)
                        if len(unique) >= 5:
                            break
                focus_summary = "讨论了" + "、".join(unique)
                if len(all_keywords) > 5:
                    focus_summary += "等话题"

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

            # 清除实例状态
            self._state = None

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
