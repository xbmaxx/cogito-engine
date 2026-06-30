"""
focus_stack.py —— 多帧焦点栈。

核心算法来源：白龙马（MIT）
- 每个焦点帧包含话题关键词、命中计数、最后 TICK
- 支持话题重用（hitCount 递增）vs 新话题压栈
- 栈容量有上限（默认 5），满时淘汰最旧的帧

平台无关版本 —— 无 Hermes 依赖。
"""

from __future__ import annotations

from typing import Callable, Optional

MAX_STACK_DEPTH = 5


class FocusStack:
    """多帧焦点栈 —— 维护 LLM 对当前会话话题焦点的感知。

    每个焦点帧是一个 dict：
        {
            "topic": [str, ...],        # 关键词列表
            "hitCount": int,            # 该话题被命中的次数
            "lastSeenTick": int,        # 最后一次命中时的 TICK 计数
            "source": "user" | "agent", # 来源标记
        }

    Attributes:
        stack: 焦点帧列表（栈顶 = stack[-1]）
    """

    def __init__(self) -> None:
        self.stack: list[dict] = []

    def update(
        self,
        topic_keywords: list[str],
        tick_counter: int = 0,
        source: str = "user",
        raw_message: str = "",
        classifier_fn: Optional[Callable] = None,
    ) -> dict:
        """更新焦点栈。

        策略：
        1. 如果新关键词与栈中某帧高度重合（≥50%），则命中该帧
        2. 否则作为新话题压入栈顶
        3. 若栈已满（MAX_STACK_DEPTH），移除最旧的帧

        Args:
            topic_keywords: 新话题的关键词列表
            tick_counter: 当前 TICK 计数
            source: 来源（"user" 或 "agent"）
            raw_message: 原始消息文本（可选，供 classifier_fn 使用）
            classifier_fn: 可选分类器（用于返回结构化分类结果）

        Returns:
            {"action": "hit"|"push"|"replace", "frame": dict, "depth": int}
        """
        if not topic_keywords:
            return {"action": "none", "frame": {}, "depth": len(self.stack)}

        # ── v1 LLM 仲裁（焦点分类器） ──
        classification = None
        if classifier_fn:
            try:
                classification = classifier_fn(
                    topic_keywords, raw_message=raw_message
                )
            except Exception:
                pass

        # ── 尝试命中已有帧 ──
        best_match = self._find_best_match(topic_keywords)

        if best_match is not None:
            # 命中已有帧
            frame = best_match
            # 合并新关键词（去重）
            existing = set(frame["topic"])
            existing.update(topic_keywords)
            frame["topic"] = list(existing)
            frame["hitCount"] += 1
            frame["lastSeenTick"] = tick_counter
            return {"action": "hit", "frame": frame, "depth": len(self.stack)}

        # ── 新话题压栈 ──
        new_frame = {
            "topic": list(topic_keywords),
            "hitCount": 1,
            "lastSeenTick": tick_counter,
            "source": source,
        }

        # 栈满时移除最旧帧
        if len(self.stack) >= MAX_STACK_DEPTH:
            self.stack.pop(0)

        self.stack.append(new_frame)
        return {"action": "push", "frame": new_frame, "depth": len(self.stack)}

    def _find_best_match(self, keywords: list[str]) -> Optional[dict]:
        """在栈中查找与新关键词最匹配的帧。

        匹配规则：Jaccard 相似度 ≥ 0.5 即视为命中。

        Returns:
            最佳匹配帧，若无则返回 None。
        """
        if not self.stack:
            return None

        kw_set = set(keywords)
        best: Optional[dict] = None
        best_score: float = 0.0

        for frame in self.stack:
            frame_set = set(frame["topic"])
            if not frame_set:
                continue
            intersection = kw_set & frame_set
            union = kw_set | frame_set
            score = len(intersection) / len(union) if union else 0
            if score >= 0.5 and score > best_score:
                best_score = score
                best = frame

        return best

    def get_topics(self) -> list[list[str]]:
        """获取栈中所有话题关键词列表。"""
        return [frame["topic"] for frame in self.stack]

    def clear(self) -> None:
        """清空焦点栈。"""
        self.stack.clear()

    @property
    def depth(self) -> int:
        """当前栈深度。"""
        return len(self.stack)
