"""
self_perception.py —— 自我感知模块。

检测 LLM 输出的三个维度：
1. 镜像效应（mirror）：是否过度重复用户用词
2. 风格聚类（style_cluster）：响应风格的多样性
3. 循环退化（loop）：是否陷入重复模式

平台无关版本 —— 零外部依赖。
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Optional


# ── 风格词库 ──
_COLLABORATIVE_WORDS = re.compile(
    r"(一起|我们|合作|协同|共同|团队)",
)
_ANALYTICAL_WORDS = re.compile(
    r"(分析|逻辑|推理|因为|所以|结论|根因|数据)",
)
_EMPATHETIC_WORDS = re.compile(
    r"(理解|感受|明白|关心|体谅|支持|鼓励|安慰)",
)
_DIRECTIVE_WORDS = re.compile(
    r"(必须|应该|需要|第一步|第二步|按照|执行|操作)",
)


def compute_style_distribution(text: str) -> Dict[str, float]:
    """计算一段文本的风格分布。

    Returns:
        {"collaborative": float, "analytical": float, "empathetic": float, "directive": float}
        每个值 0-1，总和 ≤ 1。
    """
    if not text:
        return {
            "collaborative": 0.0,
            "analytical": 0.0,
            "empathetic": 0.0,
            "directive": 0.0,
        }

    # 分词（中英混合简易分词）
    words = len(re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z]+", text))
    if words == 0:
        words = 1

    c = len(_COLLABORATIVE_WORDS.findall(text)) / words
    a = len(_ANALYTICAL_WORDS.findall(text)) / words
    e = len(_EMPATHETIC_WORDS.findall(text)) / words
    d = len(_DIRECTIVE_WORDS.findall(text)) / words

    # 归一化（最大 1.0）
    total = c + a + e + d
    if total > 1.0:
        factor = 1.0 / total
        c *= factor
        a *= factor
        e *= factor
        d *= factor

    return {
        "collaborative": round(c, 3),
        "analytical": round(a, 3),
        "empathetic": round(e, 3),
        "directive": round(d, 3),
    }


def _get_style_cluster(text: str) -> str:
    """识别文本的主导风格类型。"""
    dist = compute_style_distribution(text)
    if max(dist.values()) < 0.03:
        return "neutral"
    dominant = max(dist, key=dist.get)  # type: ignore[arg-type]
    return dominant


def compute_style_diversity(history: List[str]) -> str:
    """根据风格历史判断当前多样性状态。

    评估标准：
    - 最近 20 条只出现 1 种风格 → "narrow"
    - 2 种风格 → "unchanged"
    - 3+ 种风格 → "diverse"
    - 无历史 → "initializing"
    """
    if not history:
        return "initializing"

    recent = history[-20:]
    clusters = set()
    for text in recent:
        clusters.add(_get_style_cluster(text))

    n = len(clusters)
    if n <= 1:
        return "narrow"
    elif n == 2:
        return "unchanged"
    return "diverse"


# ── 循环退化检测 ──

def _compute_loop_score(
    conversation_window: List[Dict[str, Any]],
    current_msg: Dict[str, Any],
) -> float:
    """检测 LLM 是否陷入重复循环。

    在最近 10 条 assistant 消息中查找高度相似的输出。
    相似度 = Jaccard(词袋)。

    Returns:
        循环得分 0.0-1.0（≥0.3 表示轻度重复，≥0.5 表示中度，≥0.7 严重）
    """
    if len(conversation_window) < 3:
        return 0.0

    # 提取最近 assistant 消息的文本
    assistant_texts = []
    for msg in conversation_window:
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                assistant_texts.append(content)

    if len(assistant_texts) < 2:
        return 0.0

    # 取最近 5 条
    recent = assistant_texts[-5:]
    current_content = current_msg.get("content", "")
    if isinstance(current_content, str) and current_content.strip():
        recent.append(current_content)
    # else: only check historical assistant messages for recurrence

    # 词袋
    def _tokenize(s: str) -> set:
        return set(re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z]+", s.lower()))

    bags = [_tokenize(t) for t in recent]

    # 计算相邻消息对的最大 Jaccard 相似度
    max_score = 0.0
    for i in range(len(bags)):
        for j in range(i + 1, len(bags)):
            if not bags[i] or not bags[j]:
                continue
            intersection = bags[i] & bags[j]
            union = bags[i] | bags[j]
            if union:
                score = len(intersection) / len(union)
                if score > max_score:
                    max_score = score

    return round(max_score, 3)


# ── 镜像检测 ──

def _compute_mirror_score(
    conversation_window: List[Dict[str, Any]],
    current_msg: Dict[str, Any],
) -> float:
    """检测 LLM 是否过度镜像用户的用词。

    取最近 5 条 user/assistant 消息对，计算词汇重复率。

    Returns:
        镜像得分 0.0-1.0（≥0.4 轻度镜像，≥0.6 明显镜像）
    """
    if len(conversation_window) < 2:
        return 0.0

    # 分离 user/assistant 消息
    user_texts = []
    assistant_texts = []
    for msg in conversation_window:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if not isinstance(content, str) or not content.strip():
            continue
        if role == "user":
            user_texts.append(content)
        elif role == "assistant":
            assistant_texts.append(content)

    if not user_texts or not assistant_texts:
        return 0.0

    # 取最近 5 条
    recent_users = user_texts[-5:]
    recent_assistants = assistant_texts[-5:]

    def _tokenize(s: str) -> set:
        return set(re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z]+", s.lower()))

    # 计算每对 (user, assistant) 的词汇重叠率
    scores = []
    for u_text, a_text in zip(recent_users, recent_assistants):
        u_bag = _tokenize(u_text)
        a_bag = _tokenize(a_text)
        if not u_bag or not a_bag:
            continue
        overlap = len(u_bag & a_bag) / max(len(u_bag), 1)
        scores.append(overlap)

    if not scores:
        return 0.0

    return round(sum(scores) / len(scores), 3)


# ── 主入口 ──

def compute_self_perception(
    conversation_window: List[Dict[str, Any]],
    current_msg: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """计算自我感知快照。

    Args:
        conversation_window: 当前会话消息列表（含 user/assistant）
        current_msg: 当前消息（通常为最新 user 消息）

    Returns:
        {
            "mirror": {"score": float},
            "style_cluster": str,
            "loop": int,  # 0-10 循环严重性
            "perceptionText": str,  # 人类可读描述
        }
    """
    if not conversation_window:
        return None

    # 镜像得分
    mirror_score = _compute_mirror_score(conversation_window, current_msg)

    # 风格多样性
    assistant_texts = []
    for msg in conversation_window:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "assistant" and isinstance(content, str):
            assistant_texts.append(content)
    style_cluster = compute_style_diversity(assistant_texts)

    # 循环检测
    loop_score = _compute_loop_score(conversation_window, current_msg)
    loop_level = min(10, int(loop_score * 10))

    # 生成人类可读描述
    perception_parts = []
    if mirror_score >= 0.4:
        level = "明显" if mirror_score >= 0.6 else "轻度"
        perception_parts.append(f"检测到{level}语言镜像（得分 {mirror_score:.2f}）")

    if loop_score >= 0.3:
        level = "严重" if loop_score >= 0.7 else ("中度" if loop_score >= 0.5 else "轻度")
        perception_parts.append(f"检测到{level}循环退化（得分 {loop_score:.2f}）")

    if style_cluster == "narrow":
        perception_parts.append("响应风格趋于单一")

    perception_text = "；".join(perception_parts) if perception_parts else "感知正常"

    return {
        "mirror": {"score": mirror_score},
        "style_cluster": style_cluster,
        "loop": loop_level,
        "perceptionText": perception_text,
    }
