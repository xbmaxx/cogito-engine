"""
focus_sequence.py —— 焦点序列检测引擎。

三大序列检测规则（纯规则，不调 LLM）：

1. 焦点对重复 — 两个焦点在不同 session 先后出现 ≥3 次 → 习惯路径
2. 情绪-焦点关联 — 某焦点出现时情绪强度 > 0.7，≥3 次 → 痛点标记
3. 路径跳转 — 焦点序列 A→B→C 连续出现 ≥2 次 → 工作流模式
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── 数据类 ──


@dataclass
class FocusPoint:
    """从 narrative 提取的单个焦点数据点。"""
    topic: str
    session_id: str
    timestamp: str = ""
    emotion_intensity: float = 0.0
    focus_depth: int = 0


@dataclass
class DetectedPattern:
    """检测到的序列模式。"""
    pattern_type: str       # "focus_pair" | "emotion_correlation" | "path_jump"
    description: str        # 自然语言描述
    count: int              # 出现次数
    confidence: float       # 置信度 [0, 1]
    topics: List[str] = field(default_factory=list)
    avg_emotion: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.pattern_type,
            "description": self.description,
            "count": self.count,
            "confidence": self.confidence,
            "topics": self.topics,
            "avg_emotion": self.avg_emotion,
        }


# ── 辅助函数 ──


def _normalize_topic_pair(a: str, b: str) -> Tuple[str, str]:
    """将话题对标准化为 (小, 大) 顺序，确保 'Docker,端口' 和 '端口,Docker' 是同一个对。"""
    if a == b:
        return (a, a)
    return (a, b) if a < b else (b, a)


def _calc_confidence(count: int, min_count: int, max_expected: int = 10) -> float:
    """根据出现次数计算置信度。

    min_count 时 ~0.5，max_expected 时 ~1.0。
    """
    raw = (count - min_count + 1) / (max_expected - min_count + 1)
    return max(0.0, min(1.0, raw))


# ── 焦点点提取 ──


def extract_focus_points(
    narratives: List[Dict[str, Any]],
) -> List[FocusPoint]:
    """从 narratives 提取所有焦点数据点。

    Args:
        narratives: persistence.load_narrative_since() 格式的条目列表

    Returns:
        展开的 FocusPoint 列表（每条 narrative 的每个 topic 一个点）
    """
    points: List[FocusPoint] = []
    for n in narratives:
        sid = n.get("session_id", "")
        ts = n.get("timestamp", "")
        for t in n.get("focus_topics", []):
            t_str = str(t).strip()
            if not t_str or len(t_str) <= 1:
                continue
            points.append(FocusPoint(
                topic=t_str,
                session_id=sid,
                timestamp=ts,
            ))
    return points


# ── 法则 1: 焦点对重复 ──


def detect_focus_pairs(
    narratives: List[Dict[str, Any]],
    min_count: int = 3,
) -> List[DetectedPattern]:
    """检测跨 session 焦点对重复模式。

    策略：
    1. 对每个 session，计算其焦点话题列表
    2. 找出所有跨 session 的焦点两两组合
    3. 出现 ≥min_count 次的即为习惯路径

    Args:
        narratives: narrative 条目列表
        min_count: 最低出现次数（默认 3）

    Returns:
        按 count 降序排列的 DetectedPattern 列表
    """
    if len(narratives) < min_count:
        return []

    # 按 session 分组
    session_topics: Dict[str, set] = {}
    session_order: List[str] = []
    for n in narratives:
        sid = n.get("session_id", "")
        if sid not in session_topics:
            session_topics[sid] = set()
            session_order.append(sid)
        topics = n.get("focus_topics", [])
        for t in topics:
            t_str = str(t).strip()
            if t_str and len(t_str) > 1:
                session_topics[sid].add(t_str)

    # 统计跨 session 焦点对
    pair_counts: Counter = Counter()
    pair_sessions: Dict[Tuple[str, str], set] = defaultdict(set)

    for sid, topics in session_topics.items():
        topic_list = sorted(topics)
        for i in range(len(topic_list)):
            for j in range(i + 1, len(topic_list)):
                pair = _normalize_topic_pair(topic_list[i], topic_list[j])
                if pair[0] != pair[1]:
                    pair_counts[pair] += 1
                    pair_sessions[pair].add(sid)

    # 过滤并排序
    results: List[DetectedPattern] = []
    for pair, count in pair_counts.most_common():
        if count >= min_count:
            results.append(DetectedPattern(
                pattern_type="focus_pair",
                description=f"你反复同时提到{pair[0]}和{pair[1]}——最近经常出现",
                count=count,
                confidence=_calc_confidence(count, min_count),
                topics=[pair[0], pair[1]],
            ))

    return results


# ── 法则 2: 情绪-焦点关联 ──


def detect_emotion_correlations(
    narratives: List[Dict[str, Any]],
    emotion_data: Optional[List[Dict[str, Any]]] = None,
    threshold: float = 0.7,
    min_count: int = 3,
) -> List[DetectedPattern]:
    """检测情绪与焦点的关联模式。

    策略：
    1. 用于各 session 的情绪数据匹配到 narrative
    2. 计算每个焦点话题的平均情绪强度
    3. 平均强度 > threshold 且出现 ≥min_count 次 → 痛点标记

    Args:
        narratives: narrative 条目列表
        emotion_data: 情绪数据列表（与 narrative 一一对应或按时间匹配）
            每项包含 {"sentiment": float}，sentiment ∈ [0, 1]
        threshold: 情绪强度阈值（默认 0.7）
        min_count: 最低出现次数（默认 3）

    Returns:
        按 avg_emotion 降序排列的 DetectedPattern 列表
    """
    if not narratives or not emotion_data or len(narratives) < min_count:
        return []
    if len(emotion_data) < min_count:
        return []

    # 将 emotion_data 与 narratives 配对
    topic_emotions: Dict[str, List[float]] = defaultdict(list)
    topic_sessions: Dict[str, set] = defaultdict(set)

    min_len = min(len(narratives), len(emotion_data))
    for i in range(min_len):
        n = narratives[i]
        sentiment = float(emotion_data[i].get("sentiment", 0.5))
        sid = n.get("session_id", "")
        for t in n.get("focus_topics", []):
            t_str = str(t).strip()
            if t_str and len(t_str) > 1:
                topic_emotions[t_str].append(sentiment)
                topic_sessions[t_str].add(sid)

    # 停用词过滤：常见/无意义的话题不参与情绪关联
    _STOP_FOCUS_WORDS = frozenset({
        "其他", "其它", "问题", "测试", "示例", "例子",
    })

    results: List[DetectedPattern] = []
    for topic, emos in topic_emotions.items():
        if topic in _STOP_FOCUS_WORDS:
            continue
        if len(emos) < min_count:
            continue
        avg_emo = sum(emos) / len(emos)
        if avg_emo > threshold:
            # 情绪强度 = 离中性(0.5)的距离 × 2
            emotion_intensity = abs(avg_emo - 0.5) * 2
            if emotion_intensity > 0.4:  # 强度至少 0.4 才有意义
                results.append(DetectedPattern(
                    pattern_type="emotion_correlation",
                    description=f"提到{topic}时情绪波动明显（强度{emotion_intensity:.2f}）",
                    count=len(emos),
                    confidence=min(1.0, emotion_intensity),
                    topics=[topic],
                    avg_emotion=round(avg_emo, 4),
                ))

    # 按 avg_emotion 降序
    results.sort(key=lambda p: p.avg_emotion, reverse=True)
    return results


# ── 法则 3: 路径跳转 ──


def detect_path_jumps(
    narratives: List[Dict[str, Any]],
    min_count: int = 2,
) -> List[DetectedPattern]:
    """检测跨 session 的焦点接力模式。

    策略：
    相邻 session 之间的话题重叠→接力链检测。
    当某个话题对在 2+ 个相邻转换中出现 → 工作流模式。

    Args:
        narratives: narrative 条目列表，按时间顺序
        min_count: 最低出现次数（默认 2）

    Returns:
        按 count 降序排列的 DetectedPattern 列表
    """
    if len(narratives) < 3:
        return []

    # 按 session 聚合话题（保持时间顺序）
    ordered_sessions: List[Dict[str, Any]] = []
    seen_sids: set = set()
    for n in narratives:
        sid = n.get("session_id", "")
        if sid not in seen_sids:
            seen_sids.add(sid)
            ordered_sessions.append({
                "session_id": sid,
                "focus_topics": set(),
            })
        # 更新最后出现的 session 的话题集
        for t in n.get("focus_topics", []):
            t_str = str(t).strip()
            if t_str and len(t_str) > 1:
                ordered_sessions[-1]["focus_topics"].add(t_str)

    if len(ordered_sessions) < 2:
        return []

    # 检测相邻 session 之间的话题接力
    # 接力定义为：前一个 session 的某个话题与下一个 session 的某个话题有相同
    # 我们检测连续的话题对 (prev_topic, next_topic)
    jump_pairs: Counter = Counter()

    for i in range(len(ordered_sessions) - 1):
        prev_topics = ordered_sessions[i]["focus_topics"]
        next_topics = ordered_sessions[i + 1]["focus_topics"]
        prev_sid = ordered_sessions[i]["session_id"]
        next_sid = ordered_sessions[i + 1]["session_id"]

        for pt in prev_topics:
            for nt in next_topics:
                if pt != nt:
                    pair = _normalize_topic_pair(pt, nt)
                    jump_pairs[pair] += 1

    # 合并为路径链描述
    results: List[DetectedPattern] = []
    seen_pairs_for_path: set = set()

    for pair, count in jump_pairs.most_common():
        if count >= min_count and pair not in seen_pairs_for_path:
            seen_pairs_for_path.add(pair)
            results.append(DetectedPattern(
                pattern_type="path_jump",
                description=(
                    f"你经常从{pair[0]}聊到{pair[1]}——"
                    f"这可能是一个固定工作流"
                ),
                count=count,
                confidence=_calc_confidence(count, min_count),
                topics=[pair[0], pair[1]],
            ))

    return results


# ── 综合管道 ──


def build_sequence_patterns(
    narratives: List[Dict[str, Any]],
    emotion_data: Optional[List[Dict[str, Any]]] = None,
    pair_min: int = 3,
    emotion_min: int = 3,
    path_min: int = 2,
) -> List[DetectedPattern]:
    """综合运行三类序列检测，返回合并结果。

    Args:
        narratives: narrative 条目列表
        emotion_data: 可选的情绪数据
        pair_min: 焦点对最低次数（默认 3）
        emotion_min: 情绪关联最低次数（默认 3）
        path_min: 路径跳转最低次数（默认 2）

    Returns:
        合并的 DetectedPattern 列表，按置信度降序
    """
    if len(narratives) < 3:
        return []

    results: List[DetectedPattern] = []

    results.extend(detect_focus_pairs(narratives, min_count=pair_min))
    if emotion_data:
        results.extend(detect_emotion_correlations(
            narratives, emotion_data,
            threshold=0.7, min_count=emotion_min,
        ))
    results.extend(detect_path_jumps(narratives, min_count=path_min))

    # 按置信度降序
    results.sort(key=lambda p: p.confidence, reverse=True)
    return results


# ── XML 格式化 ──


def format_patterns_for_xml(patterns: List[DetectedPattern]) -> str:
    """将序列模式列表格式化为 XML 片段。

    格式：
        <recurring_patterns importance="N.NN">
            <pattern count="N">
                <focus_pair>A, B</focus_pair>
                <signal>描述文本</signal>
            </pattern>
        </recurring_patterns>

    Args:
        patterns: DetectedPattern 列表

    Returns:
        XML 字符串，空列表时返回 ""。
    """
    if not patterns:
        return ""

    avg_confidence = sum(p.confidence for p in patterns) / len(patterns)

    parts: List[str] = []
    parts.append(f'<recurring_patterns importance="{avg_confidence:.2f}">')

    for p in patterns:
        parts.append(f'  <pattern count="{p.count}">')
        if p.pattern_type == "focus_pair" and len(p.topics) >= 2:
            parts.append(f'    <focus_pair>{p.topics[0]}, {p.topics[1]}</focus_pair>')
            if p.avg_emotion > 0:
                parts.append(f'    <avg_emotion>{p.avg_emotion:.2f}</avg_emotion>')
        elif p.pattern_type == "emotion_correlation" and p.topics:
            parts.append(f'    <focus_pair>{p.topics[0]}</focus_pair>')
            if p.avg_emotion > 0:
                parts.append(f'    <avg_emotion>{p.avg_emotion:.2f}</avg_emotion>')
        elif p.pattern_type == "path_jump" and len(p.topics) >= 2:
            parts.append(f'    <focus_pair>{p.topics[0]} → {p.topics[1]}</focus_pair>')
        parts.append(f'    <signal>{p.description}</signal>')
        parts.append('  </pattern>')

    parts.append('</recurring_patterns>')
    return '\n'.join(parts)
