"""
crystallization.py —— 技能结晶引擎。

从叙事记忆的高 α 值模式中自动检测、固化、注入技能。

核心流程：
1. detect_candidates() — 从 narratives 扫描达标候选项
2. crystallize() — 将候选项写入共享持久化
3. load_skills() — 按 profile/置信度加载
4. match_context() — 按当前焦点话题匹配候选技能
5. inject_skills() — 生成 XML 注入片段
"""

from __future__ import annotations

import json
import logging
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .persistence import get_cogito_home
from .focus_sequence import _is_garbage_keyword

logger = logging.getLogger(__name__)

# ── 持久化路径 ──

# 本地覆盖（测试用）——不改 persistence 全局，避免破坏测试隔离
_LOCAL_CRYSTALLIZED_DIR: Optional[Path] = None

CRYSTALLIZED_FILE = "skills.jsonl"
MAX_SKILLS_PER_PROFILE = 50


def _set_crystallized_dir(path: Optional[str]) -> None:
    """重设结晶目录（测试用，仅影响本模块，不改 persistence 全局）。

    传 None 清空本地覆盖，回退到 persistence 统一目录。
    """
    global _LOCAL_CRYSTALLIZED_DIR
    _LOCAL_CRYSTALLIZED_DIR = Path(path) if path is not None else None


def _crystallized_file() -> Path:
    """返回结晶技能文件路径。本地覆盖优先，回退到 persistence 统一目录。"""
    if _LOCAL_CRYSTALLIZED_DIR is not None:
        d = _LOCAL_CRYSTALLIZED_DIR
    else:
        d = get_cogito_home() / "crystallized"
    d.mkdir(parents=True, exist_ok=True)
    return d / CRYSTALLIZED_FILE


# ── 数据类 ──


@dataclass
class CrystallizationCandidate:
    """结晶候选项——从 narratives 中检测到的可结晶模式。

    Attributes:
        topic: 话题关键词
        sessions: 出现的 session ID 列表
        avg_alpha: 平均 α 评分
        evidence_count: 出现的次数
        pattern: 检测到的模式描述
        suggested_approach: 建议的行为指引
    """
    topic: str
    sessions: List[str] = field(default_factory=list)
    avg_alpha: float = 0.0
    evidence_count: int = 0
    pattern: str = ""
    suggested_approach: str = ""

    @property
    def confidence(self) -> float:
        """置信度：基于 evidence_count 和 avg_alpha 的加权值。"""
        # alpha 贡献度 0.6，count 贡献度 0.4
        alpha_score = min(1.0, max(0.0, self.avg_alpha))
        count_score = min(1.0, self.evidence_count / 10.0)
        return round(alpha_score * 0.6 + count_score * 0.4, 4)


@dataclass
class CrystallizedSkill:
    """已固化的技能。

    Attributes:
        skill_name: 技能名称
        trigger: 触发词（用于语境匹配）
        pattern: 检测到的模式描述
        suggested_approach: 自动行为建议
        confidence: 置信度 [0, 1]
        evidence_count: 证据条数
        profile: 归属 profile 标签
        created_at: 创建时间
    """
    skill_name: str
    trigger: str
    pattern: str
    suggested_approach: str
    confidence: float = 0.5
    evidence_count: int = 0
    profile: str = "default"
    created_at: str = ""


# ── 法则 1: 候选项检测 ──


def detect_candidates(
    narratives: List[Dict[str, Any]],
    min_alpha: float = 0.7,
    min_count: int = 3,
) -> List[CrystallizationCandidate]:
    """从叙事数据检测结晶候选项。

    策略：
    1. 按话题（focus_topics）聚合叙事条目
    2. 每个话题计算平均 α 值和累计出现次数
    3. α ≥ min_alpha 且出现 ≥ min_count 次 → 候选项

    Args:
        narratives: narrative 条目列表（每项应含 alpha 字段）
        min_alpha: α 评分阈值（默认 0.7）
        min_count: 最低出现次数（默认 3）

    Returns:
        按置信度降序排列的候选项列表
    """
    if not narratives:
        return []

    # 按焦点话题聚合
    topic_data: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "alphas": [],
        "sessions": set(),
        "insights": [],
    })

    for n in narratives:
        alpha = n.get("alpha", 0.0)
        # NaN 保护
        if alpha is None or (isinstance(alpha, float) and math.isnan(alpha)):
            alpha = 0.0
        alpha = max(0.0, min(1.0, float(alpha)))

        sid = n.get("session_id", "")
        insight = n.get("insights", "")

        for t in n.get("focus_topics", []):
            t_str = str(t).strip()
            if not t_str or len(t_str) <= 1:
                continue
            # 过滤 ngram 碎片：无 jieba 时产生的字符碎片（如 "已重启，" "看下新"）
            if _is_garbage_keyword(t_str):
                continue
            topic_data[t_str]["alphas"].append(alpha)
            if sid:
                topic_data[t_str]["sessions"].add(sid)
            if insight:
                topic_data[t_str]["insights"].append(insight)

    candidates: List[CrystallizationCandidate] = []
    for topic, data in topic_data.items():
        count = len(data["sessions"])  # 按 session 去重计数
        if count < min_count:
            continue
        avg_alpha = sum(data["alphas"]) / len(data["alphas"]) if data["alphas"] else 0.0
        if avg_alpha < min_alpha:
            continue

        # 从 insights 构建 pattern 和 suggested_approach
        pattern = f"用户频繁遇到与 {topic} 相关的问题——最近出现了 {count} 次"
        combined_insights = [ins for ins in data["insights"] if ins]
        if combined_insights:
            # 取最常见的 insight
            insight_counts = Counter(combined_insights)
            most_common_insight = insight_counts.most_common(1)[0][0]
            suggested_approach = f"当用户提到 {topic} 时，{most_common_insight[:60]}"
        else:
            suggested_approach = f"当用户提到 {topic} 时，主动询问是否需要协助"

        candidates.append(CrystallizationCandidate(
            topic=topic,
            sessions=list(data["sessions"]),
            avg_alpha=round(avg_alpha, 4),
            evidence_count=count,
            pattern=pattern,
            suggested_approach=suggested_approach,
        ))

    # 按置信度降序
    candidates.sort(key=lambda c: c.confidence, reverse=True)
    return candidates


# ── 法则 2: 结晶落库 ──


def _generate_skill_name(cand: CrystallizationCandidate) -> str:
    """根据候选项生成技能名称。"""
    return f"{cand.topic}处理方案"


def _serialize_skill(skill: CrystallizedSkill) -> Dict[str, Any]:
    return {
        "skill_name": skill.skill_name,
        "trigger": skill.trigger,
        "pattern": skill.pattern,
        "suggested_approach": skill.suggested_approach,
        "confidence": skill.confidence,
        "evidence_count": skill.evidence_count,
        "profile": skill.profile,
        "created_at": skill.created_at or datetime.now(timezone.utc).isoformat(),
    }


def _deserialize_skill(data: Dict[str, Any]) -> CrystallizedSkill:
    return CrystallizedSkill(
        skill_name=data.get("skill_name", ""),
        trigger=data.get("trigger", ""),
        pattern=data.get("pattern", ""),
        suggested_approach=data.get("suggested_approach", ""),
        confidence=float(data.get("confidence", 0.5)),
        evidence_count=int(data.get("evidence_count", 0)),
        profile=data.get("profile", "default"),
        created_at=data.get("created_at", ""),
    )


def _is_duplicate(skill: CrystallizedSkill) -> bool:
    """检查是否已有相同模式的结晶（按 profile + trigger 去重）。"""
    existing = load_skills(profile=skill.profile)
    for s in existing:
        if s.trigger == skill.trigger and s.skill_name == skill.skill_name:
            return True
    return False


def crystallize(
    cand: CrystallizationCandidate,
    profile: str = "default",
) -> Optional[CrystallizedSkill]:
    """将结晶候选项固化为技能并写入持久化。

    写入 ~/.cogito/crystallized/skills.jsonl，每条带 profile 标签。
    重复检测：同一 profile + trigger + skill_name 不重复写入。

    Args:
        cand: 候选项
        profile: 归属 profile 标签

    Returns:
        CrystallizedSkill 成功时，None 表示已存在重复。
    """
    skill = CrystallizedSkill(
        skill_name=_generate_skill_name(cand),
        trigger=cand.topic,
        pattern=cand.pattern,
        suggested_approach=cand.suggested_approach,
        confidence=cand.confidence,
        evidence_count=cand.evidence_count,
        profile=profile,
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    if _is_duplicate(skill):
        logger.debug("结晶技能已存在: %s/%s", profile, skill.skill_name)
        return None

    try:
        fp = _crystallized_file()
        with open(fp, "a", encoding="utf-8") as f:
            f.write(json.dumps(_serialize_skill(skill), ensure_ascii=False) + "\n")

        # 修剪到 MAX_SKILLS_PER_PROFILE
        _trim_profile(profile)

        return skill
    except Exception as exc:
        logger.error("写入结晶技能失败: %s", exc)
        return None


def _trim_profile(profile: str) -> None:
    """修剪指定 profile 的结晶数到 MAX_SKILLS_PER_PROFILE。"""
    all_skills = _load_all_skills()
    filtered = [s for s in all_skills if s.profile != profile]
    profile_skills = [s for s in all_skills if s.profile == profile]
    profile_skills.sort(key=lambda s: s.confidence, reverse=True)
    kept = profile_skills[:MAX_SKILLS_PER_PROFILE]
    all_kept = filtered + kept
    try:
        fp = _crystallized_file()
        with open(fp, "w", encoding="utf-8") as f:
            for s in all_kept:
                f.write(json.dumps(_serialize_skill(s), ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.error("修剪结晶技能失败: %s", exc)


def _load_all_skills() -> List[CrystallizedSkill]:
    """加载所有结晶技能（不按 profile 过滤）。"""
    fp = _crystallized_file()
    if not fp.exists():
        return []
    try:
        with open(fp, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return [
            _deserialize_skill(json.loads(line))
            for line in lines if line.strip()
        ]
    except Exception as exc:
        logger.error("加载结晶技能失败: %s", exc)
        return []


# ── 法则 3: 按 Profile 加载 ──


def load_skills(
    profile: str = "default",
    min_confidence: float = 0.0,
) -> List[CrystallizedSkill]:
    """按 profile 加载结晶技能。

    Args:
        profile: profile 标签（精确匹配）
        min_confidence: 最低置信度阈值

    Returns:
        按置信度降序排列的技能列表
    """
    all_skills = _load_all_skills()
    filtered = [
        s for s in all_skills
        if s.profile == profile and s.confidence >= min_confidence
    ]
    filtered.sort(key=lambda s: s.confidence, reverse=True)
    return filtered


# ── 法则 4: 语境匹配 ──


def match_context(
    skills: List[CrystallizedSkill],
    focus_topics: List[str],
) -> List[CrystallizedSkill]:
    """按当前焦点话题匹配结晶技能。

    匹配规则：skill.trigger 是 focus_topics 中任一话题的子串，
    或 focus_topics 中任一话题包含 skill.trigger。

    Args:
        skills: 待匹配的技能列表（全部 profile）
        focus_topics: 当前对话的焦点话题列表

    Returns:
        匹配的技能列表，按置信度降序
    """
    if not skills or not focus_topics:
        return []

    matched: List[CrystallizedSkill] = []
    focus_text = " ".join(focus_topics).lower()
    trigger_combined = " ".join(focus_topics).lower()

    for s in skills:
        trigger_lower = s.trigger.lower()
        # 双向子串匹配
        if trigger_lower in focus_text or any(
            t.lower() in trigger_lower for t in focus_topics
        ):
            matched.append(s)

    matched.sort(key=lambda s: s.confidence, reverse=True)
    return matched


# ── 法则 5: 注入 XML 生成 ──


def inject_skills(
    skills: List[CrystallizedSkill],
    max_count: int = 3,
) -> str:
    """将结晶技能格式化为 XML 注入片段。

    格式：
        <crystallized_skills count="N">
            <crystallized_skill confidence="0.85">
                <skill_name>端口排查方案</skill_name>
                <trigger>Docker端口</trigger>
                <pattern>端口冲突 → 日志排查</pattern>
                <suggested_approach>主动询问是否需要端口映射检查</suggested_approach>
            </crystallized_skill>
        </crystallized_skills>

    Args:
        skills: 结晶技能列表（已按语境/置信度筛选）
        max_count: 最大注入数量（默认 3）

    Returns:
        XML 字符串，空列表时返回 ""。
    """
    if not skills:
        return ""

    # 按置信度降序排列，取 top-N
    sorted_skills = sorted(skills, key=lambda s: s.confidence, reverse=True)
    selected = sorted_skills[:max_count]

    parts: List[str] = []
    parts.append(f'<crystallized_skills count="{len(selected)}">')
    for s in selected:
        parts.append(f'  <crystallized_skill confidence="{s.confidence:.2f}">')
        parts.append(f'    <skill_name>{_xml_escape(s.skill_name)}</skill_name>')
        parts.append(f'    <trigger>{_xml_escape(s.trigger)}</trigger>')
        parts.append(f'    <pattern>{_xml_escape(s.pattern[:120])}</pattern>')
        parts.append(
            f'    <suggested_approach>{_xml_escape(s.suggested_approach[:120])}</suggested_approach>'
        )
        parts.append('  </crystallized_skill>')
    parts.append('</crystallized_skills>')

    return '\n'.join(parts)


def _xml_escape(text: str) -> str:
    """简易 XML 转义。"""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


# ── 工具模式→结晶 桥接 ──


def detect_tool_patterns(
    traces: List[Dict[str, Any]],
    min_failure_rate: float = 0.30,
    min_count: int = 5,
    min_fallback_count: int = 2,
) -> List[CrystallizationCandidate]:
    """从工具调用记录检测可结晶的工具使用模式。

    检测三类模式，输出 CrystallizationCandidate 供结晶管线使用：

    1. **高失败率工具**：某工具失败率 > min_failure_rate 且调用 ≥ min_count
       → 候选: topic="skill_manage", pattern="失败率52.9%", approach="先 skills_list 再调用"

    2. **稳定降级链**：工具 A 失败后自动切工具 B 成功 ≥min_fallback_count 次
       → 候选: topic="skill_manage→skills_list", pattern="降级已稳定2次"

    3. **全局异常**：当前会话成功率偏离全局基线 >15%
       → 候选: topic="工具链波动", pattern="偏离基线X%", approach="策略切换建议"

    Args:
        traces: 工具调用记录列表（至少含 tool_name、status 字段）
        min_failure_rate: 失败率阈值（默认 0.30）
        min_count: 最低调用次数才有统计意义（默认 5）
        min_fallback_count: 降级链最低出现次数（默认 2）

    Returns:
        CrystallizationCandidate 列表，空列表时表示无模式
    """
    if not traces:
        return []

    total = len(traces)

    # ── 1. 工具统计 ──
    tool_total: Dict[str, int] = {}
    tool_fail: Dict[str, int] = {}
    for t in traces:
        name = t.get("tool_name", "")
        if not name:
            continue
        tool_total[name] = tool_total.get(name, 0) + 1
        if t.get("status") != "ok":
            tool_fail[name] = tool_fail.get(name, 0) + 1

    candidates: List[CrystallizationCandidate] = []

    # ── 2. 高失败率工具 ──
    for tool_name, total_calls in tool_total.items():
        if total_calls < min_count:
            continue
        failures = tool_fail.get(tool_name, 0)
        failure_rate = failures / total_calls
        if failure_rate < min_failure_rate:
            continue

        approach_map = {
            "skill_manage": "先调用 skills_list 确认 skill 存在，再执行 skill_manage。或直接用 patch 编辑文件替代",
            "memory": "先读取 memory 确认容量（memory_char_limit），防止超限写入失败",
            "write_file": "确认目标目录存在且可写；大文件写入分步进行，每步验证",
            "execute_code": "代码逻辑问题导致执行失败；先在终端验证语法，再用 execute_code",
            "patch": "old_string 不唯一导致匹配失败；增加上下文或使用 replace_all=true",
            "skill_view": "skill 名可能拼写错误；先 skills_list 确认正确名称",
            "read_file": "确认路径有效性后再读取；大文件用 offset/limit 分批",
        }
        approach = approach_map.get(
            tool_name,
            f"{tool_name} 失败率 {failure_rate:.0%}——优先用更稳定的替代方案",
        )

        candidates.append(CrystallizationCandidate(
            topic=tool_name,
            sessions=[],
            avg_alpha=min(0.75, 0.4 + failure_rate * 0.7),
            evidence_count=total_calls,
            pattern=f"工具 {tool_name} 失败率 {failure_rate:.0%}（{failures}/{total_calls}）",
            suggested_approach=approach,
        ))

    # ── 3. 降级链: A失败→B成功 ──
    fallback_pairs: Dict[tuple, int] = {}
    prev_status = "ok"
    prev_tool = ""
    for t in traces:
        name = t.get("tool_name", "")
        if not name:
            continue
        status = t.get("status", "ok")
        if prev_status != "ok" and status == "ok" and prev_tool and prev_tool != name:
            key = (prev_tool, name)
            fallback_pairs[key] = fallback_pairs.get(key, 0) + 1
        prev_status = status
        prev_tool = name

    for (src, dst), cnt in fallback_pairs.items():
        if cnt < min_fallback_count:
            continue

        topic = f"{src}→{dst}"
        candidates.append(CrystallizationCandidate(
            topic=topic,
            sessions=[],
            avg_alpha=min(0.70, 0.45 + cnt * 0.10),
            evidence_count=cnt,
            pattern=f"工具 {src} 失败后自动降级到 {dst}——已稳定出现 {cnt} 次",
            suggested_approach=f"{src} 调用失败时，优先尝试 {dst} 作为降级方案，避免重复失败",
        ))

    # ── 4. 全局异常 ──
    ok_count = sum(1 for t in traces if t.get("status") == "ok")
    session_rate = ok_count / total if total > 0 else 1.0

    try:
        from .tool_trace import load_traces
        all_traces = load_traces(k=1000)
        all_ok = sum(1 for t in all_traces if t.get("status") == "ok")
        all_total = len(all_traces)
        baseline_rate = all_ok / all_total if all_total > 0 else 1.0
    except Exception:
        baseline_rate = 0.88  # 默认基线

    deviation = abs(session_rate - baseline_rate)
    if deviation > 0.15 and total >= 10:
        direction = "上升" if session_rate < baseline_rate else "下降"
        candidates.append(CrystallizationCandidate(
            topic="工具链波动",
            sessions=[],
            avg_alpha=0.50,
            evidence_count=total,
            pattern=(
                f"当前会话成功率 {session_rate:.0%}，偏离全局基线 {baseline_rate:.0%} "
                f"（{direction}{deviation:.0%}）"
            ),
            suggested_approach=(
                "全局成功率偏离基线——建议切换策略："
                "减少危险工具使用（如 patch/skill_manage），"
                "优先用稳定工具（read_file/search_files/terminal）"
            ) if session_rate < baseline_rate else "",
        ))

    # 按置信度降序
    candidates.sort(key=lambda c: c.confidence, reverse=True)
    return candidates
