# reflection_llm Provider Pitfall — Evidence Chain

> Session: 2026-07-10, provider `custom:workbuddy`, model `deepseek-v4-pro`

## Diagnostic flow

1. **Symptom**: narrative.jsonl has 35 completed entries (pending=false) but recent ones have keyword-stub summaries ("讨论了saas、agent、服务器、做一套、部署等话题") with empty insights/unresolved
2. **Check**: `grep "reflection LLM:" agent.log` → "未找到 custom:workbuddy 的 API key"
3. **Root cause**: `_find_api_key()` mismatch — `provider_name = "custom:workbuddy"` vs `custom_providers[0].name = "workbuddy"` → `"custom:workbuddy" != "workbuddy"` → all 5 strategies fail → `_build_reflection_llm()` returns `None`
4. **Missed opportunity**: `_build_universal_reflection_llm()` exists and scans `DEEPSEEK_API_KEY` (which IS set in `.env`) — but it's never called

## Key file evidence

- `adapters/hermes_adapter.py` L299-309: `HermesAdapter.__init__` calls only `_build_reflection_llm()`, never `_build_universal_reflection_llm()`
- `adapters/hermes_adapter.py` L142-240: `_build_reflection_llm()` → `_find_api_key()` with 5 strategies, none handle `custom:` prefix
- `adapters/hermes_adapter.py` L242-281: `_build_universal_reflection_llm()` — fully implemented, scans common env vars
- `~/.hermes/.env`: `DEEPSEEK_API_KEY=sk-...` is present and valid (verified with curl → 200)

## Timeline

| Date | Event |
|------|-------|
| v1.4.0-v1.4.3 | Worked — provider was likely `deepseek` (matched strategy 2 or 4) |
| v1.5.0 (2026-07-09) | Broke — provider changed to `custom:workbuddy`, `_find_api_key` couldn't match |
| 2026-07-10 | Diagnosed — narrative quality degraded for ~24h |

## Quality comparison

Before v1.5.0 (with reflection LLM):
```json
{
  "summary": "用户批评助手之前提出的'查看心跳'建议偏离了用户真实需求...",
  "insights": "用户认为技术讨论应直接围绕用户实际体验...",
  "unresolved": "改动对情绪模型的具体影响程度...",
  "emotion_summary": "负面"
}
```

## 附：custom: provider 降智诊断信号（WorkBuddy 案例）

2026-07-10 实测：同一模型（deepseek-v4-flash）在原生 API vs WorkBuddy 代理下表现差异显著。

**agent.log 信号**（grep session_id 对比）：

```
# WorkBuddy（降智）
in=49021 out=93 total=49114 latency=2.1s cache=47872/49021 (98%)
in=64396 out=118 total=64514 latency=3.5s cache=49920/64396 (78%)

# 原生 DeepSeek（正常）
in=50149 out=477 total=50626 latency=8.2s cache=49024/50149 (2%)
```

**判断标准**：
- `out < 150` + `cache > 75%` = 强降智信号
- 推理在系统层原地打转、无法触及根因 = 输出长度不足以支撑因果链

**建议处置**：确认后在 chat 配置中切回原生 API provider。

---

## 2026-07-11 更新：完整诊断流程 + COGITO_LLM 修复

### 场景

用户在 Desktop GUI 新会话中问"记得上次聊什么吗？"——Agent 回答不出来，只能 session_search。用户质疑"叙事记忆每次都不起作用"。

### 诊断步骤

1. **检查 narrative 状态**：`cat ~/.hermes/memory/narrative.jsonl | grep pending | wc -l` → 25/50 pending，全为 `pending: true`

2. **检查 reflection_llm 配置**：
```python
import yaml, os
c = yaml.safe_load(open(os.path.expanduser("~/.hermes/config.yaml")))
print(f"provider={c['model'].get('provider')}, model={c['model'].get('default')}")
# → provider=custom:workbuddy, model=deepseek-v4-flash
for cp in c.get('custom_providers',[]):
    print(f"  name={cp.get('name')}, model={cp.get('model')}, key={'SET' if cp.get('api_key') else 'NONE'}")
# → name=workbuddy, model=deepseek-v4-pro, key=SET  ← NAMING MISMATCH
for env in ['COGITO_LLM_API_KEY','DEEPSEEK_API_KEY','OPENAI_API_KEY']:
    print(f"  {env}={'SET' if os.environ.get(env) else 'NONE'}")
# → all NONE
```

3. **根因确认**：`provider="custom:workbuddy"` vs `name="workbuddy"` → 不匹配。且所有环境变量均未设置 → `self._reflection_llm = None`

4. **三种修复方案**：

   | 方案 | 命令/改动 | 优点 | 缺点 |
   |------|-----------|------|------|
   | COGITO_LLM 环境变量 | `export COGITO_LLM_API_KEY=... COGITO_LLM_BASE_URL=... COGITO_LLM_MODEL=...` | 最快，无需改代码 | 仅当前 shell 生效 |
   | 修复 _find_api_key | 在 `cp_name == provider_lower` 前 strip "custom:" 前缀 | 根治 | 需重新 install |
   | 切回原生 provider | config: `provider: deepseek` | 顺便解决 WorkBuddy 降智问题 | 失去 Copilot 代理能力 |

### 用户侧影响

当 reflection_llm=None 时：
- `_run_deferred_reflection()` 条件不满足 → 所有 narratives 永久 `pending: true`
- `_generate_self_reflection()` 返回 `""` → 自主反思空
- `continuation_hint` 需要的 `last_summary` 为空 → 续接提示不生成
- 三个用户侧功能（人味输出、自主反思、续接提示）代码完整，但管线数据为零

**关键教训**：叙事数据存在（非空文件）但全部 pending，与"数据不存在"是两种完全不同的诊断信号。后者是管线未启动/未写入，前者是写入正常但 LLM 增强步骤从未执行。
