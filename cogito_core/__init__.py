"""
cogito_core —— 平台无关的意识引擎核心包。

从 hermes_consciousness 插件提取，移除所有 Hermes 特定依赖，
保留核心算法逻辑。

核心组件：
- CogitoEngine: 主编排器，process(messages, state) → (xml, new_state)
- Ticker: TICK 自适应心跳调度器
- FocusStack: 多帧焦点栈
- Temporal: 相对时间词解析
- SelfPerception: 自我感知（镜像/循环/风格检测）
- TextEmotionDetector: 文本情感分析（SnowNLP）
- NarrativeStore: 叙事记忆存储
- SessionReflector: 会话反射
- EnvSensor: 环境传感器（跨平台）
- Persistence: 统一持久化层 (~/.cogito/)
"""

# ── 主入口 ──
from .engine import CogitoEngine, EngineState

# ── 核心模块 ──
from .ticker import Ticker
from .focus_stack import FocusStack

# ── 感知模块 ──
from .temporal import (
    parse_relative_time,
    get_time_window,
    get_period,
)
from .self_perception import (
    compute_self_perception,
    compute_style_diversity,
    compute_style_distribution,
)
from .text_emotion import TextEmotionDetector, quick_sentiment
from .emotion_classifier import EmotionClassifier
from .emotion_protocol import EmotionClassifierProtocol, is_valid_model, enrich_legacy_fields
from .emotion_registry import EmotionModelRegistry

# ── 记忆模块 ──
from .keyframe_extractor import KeyframeExtractor, estimate_conversation_rounds
from .narrative_store import NarrativeStore
from .session_reflector import SessionReflector

# ── 持久化 ──
from . import persistence

# ── 环境传感器 ──
from .env_sensor import get_snapshot as get_env_snapshot

# ── KnowledgeBridge ──
from .knowledge_provider import KnowledgeProvider
from .fact_store_provider import FactStoreProvider

__all__ = [
    # 引擎
    "CogitoEngine",
    "EngineState",
    # 核心
    "Ticker",
    "FocusStack",
    # 感知
    "parse_relative_time",
    "get_time_window",
    "get_period",
    "compute_self_perception",
    "compute_style_diversity",
    "compute_style_distribution",
    "TextEmotionDetector",
    "quick_sentiment",
    "EmotionClassifierProtocol",
    "is_valid_model",
    "enrich_legacy_fields",
    "EmotionModelRegistry",
    "EmotionClassifier",
    "get_env_snapshot",
    # KnowledgeBridge
    "KnowledgeProvider",
    "FactStoreProvider",
    # 记忆
    "KeyframeExtractor",
    "estimate_conversation_rounds",
    "NarrativeStore",
    "SessionReflector",
    # 持久化
    "persistence",
]

__version__ = "1.5.3"
