#!/usr/bin/env python3
"""Cogito Engine — 跨会话记忆恢复质量评估脚本。

每次发版前运行，验证记忆恢复质量没有退化。
检测 7 个典型跨会话场景，LLM 自动打分，对比基线。

Usage:
    python3 evaluate_memory_recovery.py
    python3 evaluate_memory_recovery.py --baseline baseline.json
    python3 evaluate_memory_recovery.py --output-dir results/ --version 1.5.0
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── 场景定义 ──────────────────────────────────────────────────────────────

SCENARIOS: List[Dict[str, Any]] = [
    {
        "id": "same_topic_continue",
        "name": "同主题延续（断线重连）",
        "memory_summary": "对话围绕情绪模型可插拔框架的注册表设计展开。用户完成了 EmotionModelRegistry 的代码开发，讨论了 flat 结构双 bug 修复（auto-discover 永不触发、两阶段实例化传递错误对象），并在 engine.py 中清除了冗余的 discover 调用。",
        "memory_insights": "EmotionModelRegistry 的 auto-discover 机制依赖 __init_subclass__ 钩子，但扁平模块导入时序导致注册表实例化时子类尚未注册。",
        "memory_unresolved": "engine.py 中冗余的 discover 调用清理后，未重新运行全量测试确认无回归。",
        "memory_focus": ["情绪模型", "注册表", "代码", "bug", "API"],
        "user_message": "那个重复 discover 的问题还在吗？我记得当时修了一半还需要测试验证",
        "good_recovery": "准确回忆 redundancy discover bug 的背景，并且记得未完成的全量测试验证。",
    },
    {
        "id": "topic_shift",
        "name": "话题切换（新话题）",
        "memory_summary": "讨论了telegran、代理、网速、不行、登不上等话题",
        "memory_insights": "无",
        "memory_unresolved": "无",
        "memory_focus": ["telegram", "代理", "网速"],
        "user_message": "早上好，帮我看看今天天气怎么样",
        "good_recovery": "不强行续接 Telegram 话题，自然回应用户的新需求，也不假装记得本不存在的对话细节。",
    },
    {
        "id": "topic_jump_back",
        "name": "话题回跳（A→B→A 结构）",
        "memory_summary": "对话围绕情绪模型生态2.0开发方案展开，用户要求完整审阅飞书文档并提升可执行性至95%以上。之后讨论了Telegram代理、网速、登不上的问题，随后重新回到情绪模型可插拔框架的注册表设计与API兼容性讨论。",
        "memory_insights": "用户对可执行性得分有明确量化要求，同时遇到Telegram代理的网络问题。",
        "memory_unresolved": "飞书文档KeyError异常需排查；Telegram代理配置未最终解决。",
        "memory_focus": ["情绪模型", "Telegram", "代理", "代码", "API"],
        "user_message": "那个 Telegram 的代理后来确定是什么问题了吗？我记得是连不上",
        "good_recovery": "准确知道 Telegram 问题是 Session A 的 B 话题，且知道「未最终解决」，不编造技术细节。",
    },
    {
        "id": "weak_memory",
        "name": "薄弱记忆（模板摘要）",
        "memory_summary": "讨论了unresolved、telegram、insights、topics、focus等话题",
        "memory_insights": "无",
        "memory_unresolved": "无",
        "memory_focus": ["unresolved", "telegram", "insights", "topics"],
        "user_message": "上次我们聊到哪了？我忘了",
        "good_recovery": "诚实地表示记忆不完整，不编造虚假细节，主动提出可以重新开始或根据残存关键词推测。",
    },
    {
        "id": "unresolved_recovery",
        "name": "未决问题延续",
        "memory_summary": "用户要求将情绪模型生态2.0的开发文档上传至飞书，但上传过程中出现 KeyError 异常。随后检查了飞书API返回数据和权限配置，发现是数据结构变更导致的问题。",
        "memory_insights": "飞书文档上传的 KeyError 是由于 API 返回字段格式变更，与权限无关。",
        "memory_unresolved": "飞书API数据结构变更原因尚未确认，需要排查是版本升级还是配置变更导致的。",
        "memory_focus": ["飞书", "API", "文档", "权限", "bug"],
        "user_message": "那个飞书上传的问题后来查清楚了吗？是API版本变了还是配置问题",
        "good_recovery": "准确引用未决问题中的分析结论（与权限无关、可能是数据结构变更），诚实表明尚未确认具体原因。",
    },
    {
        "id": "multi_topic_session",
        "name": "多话题回溯",
        "memory_summary": "对话涉及三个独立话题：1）Cogito 引擎 v1.4.4 的安装测试和升级验证；2）Telegram 代理配置排查；3）情绪模型 AffectMapper 连续坐标方案的代码设计。三个话题交替出现，最终以情绪模型方案设计收尾。",
        "memory_insights": "三个话题中只有情绪模型方案进入了代码实现阶段，其余两个处于调研和排查阶段。",
        "memory_unresolved": "Telegram 代理配置未验证；AffectMapper 方案的 DUTIR→V/A 映射精度需测试验证。",
        "memory_focus": ["引擎", "Telegram", "代理", "AffectMapper", "情绪"],
        "user_message": "我新开了个 Hermes session，上次那个 AffectMapper 模型的映射表你写到代码里了吗？",
        "good_recovery": "能从三个话题中准确定位到用户问的是最后一个（AffectMapper），并知道其状态是「已设计但未测试」。",
    },
    {
        "id": "emotional_continuity",
        "name": "情绪延续",
        "memory_summary": "用户反复尝试安装 Cogito 引擎但连续失败，遇到 Hermes 插件版本不兼容和 Python 依赖冲突。最终通过手动修复依赖解决了问题，用户表达了挫败感。",
        "memory_insights": "Hermes 插件 API 在 v0.18 有 breaking change，导致旧版 adapter 不兼容。",
        "memory_unresolved": "需要更新 README 中的依赖版本说明，避免其他用户遇到同样问题。",
        "memory_focus": ["安装", "依赖", "兼容性", "bug", "文档"],
        "emotion_summary": "负面（挫败感）",
        "user_message": "好了现在新 session 了，继续搞那个安装——应该不会再有坑了吧",
        "good_recovery": "表现出对用户之前挫败经历的理解，但不过度同情，用「现在应该没问题了」的务实态度回应。",
    },
]

# ── LLM 调用 ─────────────────────────────────────────────────────────────

_UNIVERSAL_KEY_MAP: List[Tuple[str, str, str]] = [
    ("DEEPSEEK_API_KEY", "deepseek-v4-flash", "https://api.deepseek.com/v1"),
    ("OPENAI_API_KEY", "gpt-4o-mini", "https://api.openai.com/v1"),
    ("ANTHROPIC_API_KEY", "claude-3-5-haiku-latest", "https://api.anthropic.com"),
    ("GEMINI_API_KEY", "gemini-2.0-flash", "https://generativelanguage.googleapis.com/v1beta"),
    ("OPENROUTER_API_KEY", "openai/gpt-4o-mini", "https://openrouter.ai/api/v1"),
    ("GROQ_API_KEY", "llama-3.1-8b-instant", "https://api.groq.com/openai/v1"),
]


def _detect_llm() -> Optional[Dict[str, str]]:
    """探测可用的 LLM 配置（同 reflection_llm 的通用探测逻辑）。

    按优先级：
    1. 环境变量
    2. ~/.hermes/.env 文件
    """
    # 先查环境变量
    for env_var, model, base_url in _UNIVERSAL_KEY_MAP:
        api_key = os.environ.get(env_var, "")
        if api_key:
            return {"api_key": api_key, "model": model, "base_url": base_url, "env": env_var}

    # 再查 .env 文件
    env_path = Path.home() / ".hermes" / ".env"
    if env_path.exists():
        try:
            env_map = {}
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("\"'")
                if key and value:
                    env_map[key] = value

            for env_var, model, base_url in _UNIVERSAL_KEY_MAP:
                api_key = env_map.get(env_var, "")
                if api_key:
                    return {"api_key": api_key, "model": model, "base_url": base_url, "env": f".env:{env_var}"}
        except OSError:
            pass

    return None


def call_llm(prompt: str, llm_config: Dict[str, str], temperature: float = 0.3) -> str:
    """调用 LLM 并返回原始响应文本。"""
    url = f"{llm_config['base_url'].rstrip('/')}/chat/completions"
    payload = json.dumps({
        "model": llm_config["model"],
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 800,
        "temperature": temperature,
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {llm_config['api_key']}",
    })

    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    return result["choices"][0]["message"]["content"]


# ── 评分 ─────────────────────────────────────────────────────────────────

def build_scoring_prompt(scenario: Dict[str, Any]) -> str:
    """构建场景评分 prompt，要求 LLM 同时产出 Agent 回复和自评分。"""
    emotion_line = ""
    if scenario.get("emotion_summary"):
        emotion_line = f"\n- 情绪基调：{scenario['emotion_summary']}"

    return f"""你是跨会话记忆恢复质量的独立评估系统。

## 场景设定
Agent 的上一轮会话结束后，Cogito Engine 注入了以下叙事记忆。现在开启了**全新的 Hermes session**（上一轮对话历史已清除），Agent 只能依靠以下记忆知道刚才发生过什么。

**Cogito 记忆注入：**
- 话题总结：{scenario['memory_summary']}
- 洞察：{scenario['memory_insights']}
- 未决问题：{scenario['memory_unresolved']}
- 焦点话题：{', '.join(scenario['memory_focus'])}{emotion_line}

**用户在新 session 的第一条消息：**「{scenario['user_message']}」

## 你的任务
1. 假设你是刚拿到上述 Cogito 记忆注入的 Agent，写出你的**首轮回复**（自然语气，不要提「根据记忆」之类的用词）。
2. 然后用以下评分表对你的回复进行**自评分**（每个维度 1-5 分）：

| 维度 | 1分 | 3分 | 5分 |
|------|-----|-----|-----|
| 话题衔接 | 完全不记得上次聊了什么 | 提到了上次的话题但很机械 | 自然接住，像用户只是去倒了杯水 |
| 无幻觉 | 编造了不存在的对话 | 引用正确但细节错误 | 引用的内容完全准确 |
| 时机 | 生硬开场"你好上次我们聊了X" | 在对话推进中顺便提及 | 用户不提就不主动提，但回答里带了上下文 |
| 用户感受 | "它在背数据库" | "它好像记得但不确定" | "它记得我" |

只返回 JSON（无代码块包裹）：
{{"response": "你的Agent首轮回复文本", "topic_continuity": 分数, "no_hallucination": 分数, "timing": 分数, "user_feeling": 分数, "reasoning": "每个维度的打分理由，100字以内"}}"""


def parse_scoring_result(raw: str) -> Optional[Dict[str, Any]]:
    """解析 LLM 返回的评分 JSON。"""
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    # 尝试直接解析
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # 尝试提取 JSON
        import re
        # 匹配 {} 包裹的 JSON 对象
        match = re.search(r'\{[^{}]*(?:"response"|"topic_continuity")[^{}]*\}', text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except (json.JSONDecodeError, ValueError):
                return None
        else:
            return None

    try:
        scores = {
            "topic_continuity": int(data.get("topic_continuity", 0)),
            "no_hallucination": int(data.get("no_hallucination", 0)),
            "timing": int(data.get("timing", 0)),
            "user_feeling": int(data.get("user_feeling", 0)),
        }
        # 验证分数范围
        for v in scores.values():
            if v < 0 or v > 5:
                return None
        return {
            "response": str(data.get("response", "")),
            **scores,
            "reasoning": str(data.get("reasoning", "")),
        }
    except (ValueError, TypeError):
        return None


# ── 基线管理 ─────────────────────────────────────────────────────────────

_BASELINE_FILE = Path(__file__).resolve().parent / "baseline.json"
_DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "results"


def load_baseline(path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """加载基线数据。"""
    p = Path(path) if path else _BASELINE_FILE
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
    return None


def save_baseline(results: Dict[str, Any], path: Optional[str] = None) -> None:
    """保存基线数据。"""
    p = Path(path) if path else _BASELINE_FILE
    # 只存场景分数用于对比
    baseline = {
        "version": results.get("version", "unknown"),
        "timestamp": results["timestamp"],
        "scenarios": {
            s["id"]: {"name": s["name"], "total": s["total"], "scores": s["scores"]}
            for s in results["scenarios"]
        },
        "overall_total": results["overall_total"],
    }
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 输出矩阵 ──────────────────────────────────────────────────────────────

_COL_WIDTHS = [24, 10, 10, 8, 10, 8]


def _print_separator():
    print("+" + "+".join("-" * w for w in _COL_WIDTHS) + "+")


def _print_row(cols: List[str]):
    padded = []
    for i, c in enumerate(cols):
        w = _COL_WIDTHS[i]
        padded.append(c.center(w))
    print("|" + "|".join(padded) + "|")


def print_matrix(results: List[Dict[str, Any]]) -> None:
    """打印评分矩阵表格。"""
    print()
    _print_separator()
    _print_row(["场景", "话题衔接", "无幻觉", "时机", "用户感受", "总分"])
    _print_separator()
    for r in results:
        if r.get("error"):
            _print_row([r["name"], "N/A", "N/A", "N/A", "N/A", "—"])
            continue
        continuity = str(r["scores"].get("topic_continuity", "?"))
        hallucination = str(r["scores"].get("no_hallucination", "?"))
        timing = str(r["scores"].get("timing", "?"))
        feeling = str(r["scores"].get("user_feeling", "?"))
        total = str(r["total"]) if r["total"] else "?"

        # 给低分标记
        def _mark(v: str, threshold: int = 3) -> str:
            try:
                return f"{v} ⚠️" if int(v) <= threshold else v
            except ValueError:
                return v

        _print_row([
            r["name"],
            _mark(continuity),
            _mark(hallucination),
            _mark(timing),
            _mark(feeling),
            _mark(total, 12),
        ])
    _print_separator()
    print()


def print_comparison(
    results: List[Dict[str, Any]],
    baseline: Dict[str, Any],
) -> Tuple[bool, List[str]]:
    """对比基线，输出变动。regressions 中有则返回 False。"""
    old_scenarios = baseline.get("scenarios", {})
    regressions = []
    improvements = []

    for r in results:
        sid = r["id"]
        old = old_scenarios.get(sid)
        if old is None:
            regressions.append(f"  ⚠️ {r['name']}: 无基线数据（新增场景）")
            continue

        delta = r["total"] - old["total"]
        if delta < -2:
            regressions.append(f"  🔴 {r['name']}: {old['total']} → {r['total']} ({delta})")
        elif delta < 0:
            regressions.append(f"  🟡 {r['name']}: {old['total']} → {r['total']} ({delta})")
        elif delta > 0:
            improvements.append(f"  🟢 {r['name']}: {old['total']} → {r['total']} (+{delta})")
        else:
            pass  # 无变化

    print("── 基线对比 ──")
    if improvements:
        print("改进:")
        for l in improvements:
            print(l)
    if regressions:
        print("退化:")
        for l in regressions:
            print(l)
    if not regressions and not improvements:
        print("  与基线持平 ✅")

    return len(regressions) == 0, regressions


# ── 主流程 ────────────────────────────────────────────────────────────────


def run_evaluation(
    llm_config: Dict[str, str],
    version: str = "dev",
) -> Dict[str, Any]:
    """运行完整评估，返回结果 dict。"""
    print(f"\n{'='*60}")
    print(f"  Cogito Engine — 跨会话记忆恢复质量评估")
    print(f"  版本: {version}")
    print(f"  模型: {llm_config['model']} ({llm_config['env']})")
    print(f"  场景数: {len(SCENARIOS)}")
    print(f"{'='*60}\n")

    scenario_results = []

    for i, scenario in enumerate(SCENARIOS):
        print(f"[{i+1}/{len(SCENARIOS)}] {scenario['name']} ... ", end="", flush=True)
        t0 = time.time()

        prompt = build_scoring_prompt(scenario)
        raw = ""
        parsed = None

        # 最多试 2 次（第 1 次 temperature=0.3，重试时用 0.5）
        for attempt in range(2):
            try:
                temp = 0.5 if attempt == 1 else 0.3
                raw = call_llm(prompt, llm_config, temperature=temp)
                parsed = parse_scoring_result(raw)
                if parsed and all(v > 0 for v in [parsed["topic_continuity"], parsed["no_hallucination"], parsed["timing"], parsed["user_feeling"]]):
                    break
            except Exception:
                if attempt == 0:
                    continue
                raise

        dt = time.time() - t0

        if parsed and all(v > 0 for v in [parsed["topic_continuity"], parsed["no_hallucination"], parsed["timing"], parsed["user_feeling"]]):
            total = parsed["topic_continuity"] + parsed["no_hallucination"] + parsed["timing"] + parsed["user_feeling"]
            print(f"{total}/20 ({dt:.1f}s)")
            scenario_results.append({
                "id": scenario["id"],
                "name": scenario["name"],
                "scores": {
                    "topic_continuity": parsed["topic_continuity"],
                    "no_hallucination": parsed["no_hallucination"],
                    "timing": parsed["timing"],
                    "user_feeling": parsed["user_feeling"],
                },
                "total": total,
                "recovery_detail": parsed["response"][:200],
                "reasoning": parsed["reasoning"],
                "execution_time_s": round(dt, 1),
            })
        else:
            total_label = "解析失败"
            print(f"⚠️  解析失败 ({dt:.1f}s)")
            scenario_results.append({
                "id": scenario["id"],
                "name": scenario["name"],
                "scores": {},
                "total": 0,
                "recovery_detail": raw[:200] if raw else "",
                "reasoning": "LLM 返回空或格式异常",
                "execution_time_s": round(dt, 1),
                "error": True,
                "raw_llm_output": raw[:500] if raw else "",
            })

    # 输出矩阵
    print_matrix(scenario_results)

    # 计算总分（排除失败的场景）
    valid = [s for s in scenario_results if not s.get("error") and s["total"] > 0]
    overall_total = sum(s["total"] for s in valid)
    max_possible = len(valid) * 20

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": version,
        "model": llm_config["model"],
        "scenario_count": len(SCENARIOS),
        "valid_count": len(valid),
        "overall_total": overall_total,
        "max_possible": max_possible,
        "overall_percent": round(overall_total / max_possible * 100, 1) if max_possible > 0 else 0,
        "scenarios": scenario_results,
    }

    print(f"综合得分: {overall_total}/{max_possible} ({result['overall_percent']}%)")
    print()

    return result


def save_report(result: Dict[str, Any], output_dir: str = "") -> str:
    """保存评估报告到文件。"""
    out_dir = Path(output_dir) if output_dir else _DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = out_dir / f"evaluation_{ts}.json"
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(report_path)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Cogito Engine 跨会话记忆恢复评估")
    parser.add_argument("--baseline", help="基线 JSON 文件路径")
    parser.add_argument("--output-dir", default="", help="报告输出目录")
    parser.add_argument("--version", default="dev", help="当前版本号")
    parser.add_argument("--save-baseline", action="store_true", help="将本次结果保存为基线")
    args = parser.parse_args()

    # 探测 LLM
    llm_config = _detect_llm()
    if not llm_config:
        print("❌ 未找到可用的 LLM API key")
        print("   请设置以下之一的环境变量：")
        for env_var, model, _ in _UNIVERSAL_KEY_MAP:
            print(f"     {env_var} (→ {model})")
        return 1

    # 运行评估
    result = run_evaluation(llm_config, version=args.version)

    # 保存报告
    report_path = save_report(result, args.output_dir)
    print(f"报告已保存: {report_path}")

    # 基線对比
    exit_ok = True
    baseline = load_baseline(args.baseline)
    if baseline:
        ok, regressions = print_comparison(result["scenarios"], baseline)
        if not ok:
            exit_ok = False
            print(f"\n⚠️  发现 {len(regressions)} 项退化 — 请检查后再发版")
        else:
            print("✅ 无退化")

    # 可选：保存为新基线
    if args.save_baseline:
        save_baseline(result, args.baseline)
        print(f"基线已更新: {args.baseline or _BASELINE_FILE}")

    return 0 if exit_ok else 1


if __name__ == "__main__":
    sys.exit(main())
