"""
emotion_registry.py —— 情绪模型注册表 + 目录发现 + 降级链。

职责：
1. 预注册内置 DUTIR（始终可用，不可卸载）
2. 扫描用户路径 ~/.cogito/emotion_models/ 发现 *_classifier.py
3. 惰性实例化 + 异常隔离（单个模型崩溃不影响其他）
4. classify_with_fallback() 标准降级链：active → dutir → quick_sentiment → 中性
5. 用户同名模型覆盖内置

零新增外部依赖（importlib / typing / pathlib / logging 均为 stdlib）。
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type

from .emotion_protocol import enrich_legacy_fields, is_valid_model
from .affect_mapper_classifier import Classifier as AffectMapper

logger = logging.getLogger(__name__)


class EmotionModelRegistry:
    """情绪模型注册表。

    预注册内置 DUTIR，然后扫描用户目录发现额外模型。
    所有 classify 调用走 classify_with_fallback() 统一入口，
    自动异常隔离 + 降级。

    Attributes:
        _classes: {model_name: (Classifier类, dict_path)}
        _instances: {model_name: Classifier实例}（惰性创建）
        _active_name: 当前活跃模型名（默认 "dutir"）
        _fallback_order: 降级链路顺序
    """

    def __init__(self) -> None:
        self._classes: Dict[str, Tuple[Type, Optional[str]]] = {}
        self._instances: Dict[str, object] = {}
        self._active_name: str = "affect_mapper"
        self._fallback_order = ["dutir", "quick_sentiment"]

        # 预注册内置 DUTIR（始终可用，不可卸载）
        from .emotion_classifier import EmotionClassifier
        self._register_builtin("dutir", EmotionClassifier)
        logger.info("内置模型 dutir 已预注册")

        # 预注册内置 AffectMapper（始终可用，可被用户同名模型覆盖）
        self._register_builtin("affect_mapper", AffectMapper)
        logger.info("内置模型 affect_mapper 已预注册")

        # 自动发现用户模型（目录存在才扫）
        user_model_path = Path.home() / ".cogito" / "emotion_models"
        if user_model_path.exists():
            self.discover([user_model_path])

    # ── 目录发现 ──

    def discover(self, search_paths: Optional[List[Path]] = None) -> None:
        """扫描用户路径发现 *_classifier.py 模型。

        只扫用户模型目录（内置 DUTIR 已预注册，不走此处）。
        同名模型覆盖已注册的（含内置，用户优先）。

        Args:
            search_paths: 用户模型目录路径列表，如 [Path.home() / ".cogito" / "emotion_models"]
        """
        for path in search_paths or []:
            if not path.exists() or not path.is_dir():
                logger.warning("模型目录不存在或非目录: %s", path)
                continue
            for py_file in sorted(path.glob("*_classifier.py")):
                prefix = py_file.stem.replace("_classifier", "").strip("_")
                if not prefix:
                    logger.warning("无效文件名格式: %s（跳过）", py_file.name)
                    continue
                json_file = py_file.parent / f"{prefix}_dict.json"

                # importlib 动态加载
                try:
                    spec = importlib.util.spec_from_file_location(
                        f"emotion_model_{prefix}", py_file,
                    )
                    if spec is None or spec.loader is None:
                        logger.warning("无法创建加载 spec: %s", py_file)
                        continue
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                except Exception as exc:
                    logger.warning("加载模型 %s 失败: %s", prefix, exc)
                    continue

                # 协议校验
                if not is_valid_model(mod):
                    logger.warning("模型 %s 不符合协议（缺少 classify/is_available），跳过", prefix)
                    continue

                # 注册（同名覆盖——用户优先于内置）
                dict_path = str(json_file) if json_file.exists() else None
                overwriting = prefix == "dutir"
                self._classes[prefix] = (mod.Classifier, dict_path)
                # 覆盖时清除缓存的实例
                self._instances.pop(prefix, None)
                logger.info(
                    "注册模型: %s%s",
                    prefix,
                    "（覆盖内置）" if overwriting else "",
                )

    # ── 活跃模型管理 ──

    def get_active(self) -> Optional[object]:
        """返回当前活跃模型实例（惰性创建）。"""
        return self._get_or_create(self._active_name)

    def set_active(self, name: str) -> bool:
        """切换活跃模型。

        Args:
            name: 模型名（必须在 _classes 中）

        Returns:
            True 切换成功，False 模型不存在
        """
        if name not in self._classes:
            logger.warning("尝试切换到未注册模型: %s", name)
            return False
        logger.info("情绪模型切换: %s → %s", self._active_name, name)
        self._active_name = name
        return True

    @property
    def active_name(self) -> str:
        """当前活跃模型名。"""
        return self._active_name

    def list_models(self) -> Dict[str, dict]:
        """列出所有已注册模型及其元信息。"""
        result: Dict[str, dict] = {}
        for name, (cls, dict_path) in self._classes.items():
            result[name] = {
                "name": getattr(cls, "MODEL_NAME", name),
                "dims": getattr(cls, "MODEL_DIMS", []),
                "has_dict": dict_path is not None,
                "active": (name == self._active_name),
            }
        return result

    # ── 分类入口（带降级链）──

    def classify_with_fallback(self, text: str) -> Dict[str, Any]:
        """情绪分类主入口，带自动降级。

        链路：active → dutir → quick_sentiment → 中性兜底。
        每步异常隔离（try/except），崩溃不传播。

        Args:
            text: 输入文本

        Returns:
            dict 含全量字段（通过 enrich_legacy_fields 保证）
        """
        # 阶段 1：优先 active 模型
        result = self._try_classify(self._active_name, text)
        if result:
            return enrich_legacy_fields(result)

        # 阶段 2：fallback（排除 active 自身）
        for name in self._fallback_order:
            if name == self._active_name:
                continue  # 跳过 active（已试过）
            if name == "quick_sentiment":
                from .text_emotion import quick_sentiment
                qs_result = quick_sentiment(text)
                return enrich_legacy_fields(qs_result)
            result = self._try_classify(name, text)
            if result:
                return enrich_legacy_fields(result)

        # 阶段 3：终极中性兜底
        logger.warning("所有情绪模型 classify 失败，返回中性兜底")
        return enrich_legacy_fields({
            "available": True,
            "emotions": {},
            "dominant": "none",
            "confidence": 0.0,
            "method": "none",
        })

    # ── 内部方法 ──

    def _try_classify(self, name: str, text: str) -> Optional[Dict[str, Any]]:
        """单次 classify，异常隔离。

        Args:
            name: 模型名
            text: 输入文本

        Returns:
            classify 结果，或 None（模型不可用 / 异常）
        """
        instance = self._get_or_create(name)
        if instance is None:
            return None
        if not callable(getattr(instance, "is_available", None)):
            return None
        try:
            if not instance.is_available():
                logger.debug("模型 %s 标记为不可用", name)
                return None
        except Exception:
            return None

        try:
            result = instance.classify(text)
            if not isinstance(result, dict):
                logger.warning("模型 %s classify 返回非 dict: %s", name, type(result))
                return None
            return result
        except Exception as exc:
            logger.warning("模型 %s classify 异常: %s", name, exc)
            return None

    def _get_or_create(self, name: str) -> Optional[object]:
        """惰性获取或创建模型实例。

        实例化失败 → 返回 None（触发降级链兜底），不崩溃。

        兼容 dict_path 参数：模型可以接受或忽略 dict_path。
        """
        if name in self._instances:
            return self._instances[name]

        entry = self._classes.get(name)
        if entry is None:
            return None

        cls, dict_path = entry
        try:
            # 优先传 dict_path（内置 DUTIR 和规范模型包支持）
            instance = cls(dict_path=dict_path)
        except TypeError:
            # 用户模型不含 dict_path 参数 → 无参构造
            try:
                instance = cls()
            except Exception as exc:
                logger.warning("实例化模型 %s 失败: %s", name, exc)
                return None
        except Exception as exc:
            logger.warning("实例化模型 %s 失败: %s", name, exc)
            return None

        self._instances[name] = instance
        return instance

    def _register_builtin(self, name: str, cls: Type) -> None:
        """注册内置模型。

        内置模型在 __init__ 时注册，始终可用。
        如果用户目录发现同名模型，会覆盖此注册。
        """
        self._classes[name] = (cls, None)
        logger.debug("内置模型已注册: %s", name)
