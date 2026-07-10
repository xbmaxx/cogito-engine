"""
hermes_adapter.py —— Hermes Plugin 适配器。

实现 HermesPlugin 接口，将 Hermes 的 hooks 事件翻译为 CogitoEngine 调用。
支持 deferred reflection：提供 reflection LLM 调用函数给引擎。

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

import json
import logging
import os
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

from cogito_core.engine import CogitoEngine, EngineState

logger = logging.getLogger(__name__)


# ── Reflection LLM 函数构建 ──


# ── 已知 provider 的默认 base_url ──
_KNOWN_PROVIDER_URLS: Dict[str, str] = {
    "deepseek": "https://api.deepseek.com/v1",
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
    "zai": "https://api.z.ai/api",
    "groq": "https://api.groq.com/openai/v1",
    "xai": "https://api.x.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "mistral": "https://api.mistral.ai/v1",
}


# ── 多策略 key 查找 ──


def _load_dotenv(hermes_home: str = "") -> Dict[str, str]:
    """读取 Hermes 的 .env 文件，返回 key→value 映射。

    Hermes 将 API key 存放在 ~/.hermes/.env 中，启动时自动加载到进程环境。
    插件运行在 Hermes 进程内，但 os.environ.get() 可能不包含（取决于加载时机），
    因此直接解析文件作为补充。
    """
    if not hermes_home:
        hermes_home = str(Path.home() / ".hermes")
    env_path = os.path.join(hermes_home, ".env")
    if not os.path.exists(env_path):
        return {}
    result: Dict[str, str] = {}
    try:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and value:
                    result[key] = value
    except Exception:
        pass
    return result


def _find_api_key(
    config: Dict[str, Any],
    provider_name: str,
    model_id: str,
) -> tuple:
    """按优先级查找：custom_providers → 旧版 providers → .env 文件 → 环境变量 → OPENAI_API_KEY。

    Returns:
        (api_key, base_url, effective_model) —— 任一为空字符串表示未找到
    """
    provider_lower = provider_name.lower()

    # ── 策略 1: custom_providers 数组（v0.18+）──
    custom_providers = config.get("custom_providers", [])
    if isinstance(custom_providers, list):
        for cp in custom_providers:
            cp_name = (cp.get("name") or "").lower()
            cp_model = cp.get("model", "")
            # 按名称或模型匹配
            # v1.5.1-fix: strip 'custom:' prefix for custom provider name matching
            cp_provider_stripped = provider_lower.replace("custom:", "", 1)
            if cp_name == provider_lower or cp_name == cp_provider_stripped or cp_model == model_id:
                api_key = cp.get("api_key", "")
                if api_key:
                    return (
                        api_key,
                        cp.get("base_url", ""),
                        cp_model or model_id,
                    )

    # ── 策略 2: 旧版 providers dict ──
    providers = config.get("providers", {})
    if isinstance(providers, dict):
        provider_config = providers.get(provider_name, {})
        if provider_config:
            api_key = provider_config.get("api_key", "")
            if api_key:
                return (
                    api_key,
                    provider_config.get("base_url", ""),
                    provider_config.get("model", model_id),
                )

    # ── 策略 3: Hermes .env 文件 ──
    dotenv = _load_dotenv()
    env_key = dotenv.get(f"{provider_name.upper()}_API_KEY", "")
    if env_key:
        return (env_key, "", model_id)

    # ── 策略 4: 标准环境变量 ──
    api_key = os.environ.get(f"{provider_name.upper()}_API_KEY", "")
    if api_key:
        return (api_key, "", model_id)

    # ── 策略 5: OPENAI_API_KEY 通用变体 ──
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if api_key:
        return (api_key, "", model_id)

    return ("", "", "")


def _build_reflection_llm(config_path: str = "") -> Optional[Callable[[str], str]]:
    """从 Hermes 配置构建 reflection LLM 调用函数。

    读取当前接入的 model/provider，按优先级查找 API 密钥：
      1. custom_providers 数组（v0.18+）
      2. config["providers"] dict（旧版格式）
      3. ~/.hermes/.env 文件（Hermes 官方凭证存储）
      4. {PROVIDER}_API_KEY 环境变量
      5. OPENAI_API_KEY 通用 fallback

    不写死模型——由用户当前 Hermes 配置决定。

    Args:
        config_path: Hermes config.yaml 路径，默认 ~/.hermes/config.yaml

    Returns:
        callable 或 None（配置不可用时）
    """
    if not config_path:
        config_path = str(Path.home() / ".hermes" / "config.yaml")

    if not os.path.exists(config_path):
        logger.debug("reflection LLM: 无 config.yaml，跳过")
        return None

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
    except Exception as exc:
        logger.debug("reflection LLM: 读取 config 失败: %s", exc)
        return None

    # 获取当前 provider/model
    model_config = config.get("model", {})
    if not isinstance(model_config, dict):
        logger.debug("reflection LLM: model 配置格式异常")
        return None

    provider_name = model_config.get("provider", "")
    model_id = model_config.get("default", "")
    if not provider_name:
        logger.debug("reflection LLM: 未找到 model.provider")
        return None

    # 多策略查找
    api_key, base_url, effective_model = _find_api_key(config, provider_name, model_id)
    if not api_key:
        logger.debug(
            "reflection LLM: 未找到 %s 的 API key（检查过 config + env）",
            provider_name,
        )
        return None

    # 确定 base_url
    if not base_url:
        base_url = _KNOWN_PROVIDER_URLS.get(provider_name.lower(), "https://api.openai.com/v1")

    logger.info(
        "reflection LLM: 启用 deferred reflection（provider=%s, model=%s）",
        provider_name, effective_model,
    )

    return _make_llm_callable(api_key, base_url, effective_model)


# ── 四层 Fallback：通用 reflection LLM（适用所有 agent）──


# Layer 2 provider 映射：环境变量 → (base_url, model)
_UNIVERSAL_PROVIDER_MAP: Dict[str, tuple] = {
    "DEEPSEEK_API_KEY": ("https://api.deepseek.com/v1", "deepseek-chat"),
    "OPENAI_API_KEY": ("https://api.openai.com/v1", "gpt-4o-mini"),
    "OPENROUTER_API_KEY": ("https://openrouter.ai/api/v1", "gpt-4o-mini"),
    "ANTHROPIC_API_KEY": ("https://api.anthropic.com", "claude-3-haiku-20240307"),
    "GEMINI_API_KEY": ("https://generativelanguage.googleapis.com/v1beta/openai/", "gemini-2.0-flash"),
    "GOOGLE_API_KEY": ("https://generativelanguage.googleapis.com/v1beta/openai/", "gemini-2.0-flash"),
}


def _build_universal_reflection_llm() -> Optional[Callable[[str], str]]:
    """构建通用 reflection LLM——适用于所有 agent adapter。

    四层 Fallback 链：
      Layer 1: COGITO_LLM_API_KEY + COGITO_LLM_BASE_URL + COGITO_LLM_MODEL（专用变量）
      Layer 2: DEEPSEEK/OPENAI/ANTHROPIC/GEMINI_API_KEY（自动推导）
      Layer 3: 无 key → 返回 None（engine 跳过 LLM 增强）
      Layer 4: LLM 调用失败 → 抛异常（调用方处理 pending）

    Returns:
        callable 或 None（所有 key 都不可用时）
    """
    # ── Layer 1: 专用环境变量 ──
    cogito_key = os.environ.get("COGITO_LLM_API_KEY", "")
    cogito_url = os.environ.get("COGITO_LLM_BASE_URL", "")
    cogito_model = os.environ.get("COGITO_LLM_MODEL", "")
    if cogito_key and cogito_url and cogito_model:
        logger.info("reflection LLM: Layer 1 命中（COGITO_LLM_*, model=%s）", cogito_model)
        return _make_llm_callable(cogito_key, cogito_url.rstrip("/"), cogito_model)

    # ── Layer 2: 复用已有 API Key ──
    for env_var, (base_url, model) in _UNIVERSAL_PROVIDER_MAP.items():
        api_key = os.environ.get(env_var, "")
        if api_key:
            logger.info(
                "reflection LLM: Layer 2 命中（env=%s, model=%s）",
                env_var, model,
            )
            return _make_llm_callable(api_key, base_url.rstrip("/"), model)

    # ── Layer 3: 无 key ──
    logger.debug("reflection LLM: 所有 key 均不可用（Layer 3）")
    return None


def _make_llm_callable(api_key: str, base_url: str, model: str) -> Callable[[str], str]:
    """构造 LLM callable（自动降级：先试非流式，400→streaming SSE）。"""
    def _llm(prompt: str) -> str:
        endpoint = f"{base_url.rstrip('/')}/chat/completions"
        payload_bytes = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 600,
            "temperature": 0.3,
        }).encode("utf-8")

        req = urllib.request.Request(endpoint, data=payload_bytes, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        })

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            # 流式降级：如果 API 只支持 streaming（如 Copilot/Tencent WorkBuddy）
            if exc.code == 400 and "stream" in body.lower():
                payload_stream = json.dumps({
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 600,
                    "temperature": 0.3,
                    "stream": True,
                }).encode("utf-8")

                req2 = urllib.request.Request(endpoint, data=payload_stream, headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "text/event-stream",
                })

                with urllib.request.urlopen(req2, timeout=60) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")

                # 解析 SSE data: 行
                text_parts = []
                for line in raw.split("\n"):
                    line = line.strip()
                    if line.startswith("data: ") and line != "data: [DONE]":
                        try:
                            chunk = json.loads(line[6:])
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                text_parts.append(content)
                        except json.JSONDecodeError:
                            pass

                result = "".join(text_parts)
                if result:
                    return result

            # 所有方式都失败，向上抛
            raise

    return _llm


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

        # 构建 reflection LLM（从 Hermes config 读取当前模型）
        reflection_llm = _build_reflection_llm()
        # Fallback: 当 config 匹配不到 key 时，尝试通用环境变量探测
        if reflection_llm is None:
            reflection_llm = _build_universal_reflection_llm()

        self.engine = CogitoEngine(
            include_weather=include_weather,
            include_battery=include_battery,
            include_resources=include_resources,
            include_emotion=include_emotion,
            include_narrative=include_narrative,
            reflection_llm=reflection_llm,
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
                # v1.5.10: 尝试从 state.json 恢复上一 session 的焦点栈
                from cogito_core.persistence import load_state as _load_state
                saved = _load_state()
                if saved:
                    state = EngineState.from_dict(saved, session_id=session_id)
                    logger.debug("pre_llm_call: 从 state.json 恢复焦点栈 (depth=%d)", state.focus_stack.depth)
                else:
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

            # 执行收尾（messages 传递给引擎用于 keyframe 提取和 deferred reflection）
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


if __name__ == "__main__":
    _demo()
