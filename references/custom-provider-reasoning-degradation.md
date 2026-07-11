---
title: 自定义 provider 推理降级检测
version: 1.0
---

# 自定义 provider 推理降级诊断

## 现象

2026-07-10 在 Session `mrezdrsf1k8p7x` 中观测到 WorkBuddy 提供的 DeepSeek API （通过 `custom:workbuddy` provider 路由）出现推理降级：

| 指标 | WorkBuddy DeepSeek | 原生 DeepSeek API |
|:----|:------------------:|:-----------------:|
| 单轮输出 | 78-118 tokens | 300-800+ tokens |
| 延迟 | 2-3.5s | 2-5s |
| Cache hit | 78-98% | 正常 |
| 根因定位 | 在系统架构层打转，碰不到本质 | 直击 root cause |
| Cogito tick | 始终为 0 | 正常递增 |

## 诊断手段

### 1. 输出长度对比

```bash
# 从 agent.log 提取某 provider 的输出 token 分布
grep "API call" ~/.hermes/logs/agent.log | grep "provider=workbuddy\|provider=custom" \
  | grep -oP 'out=\K\d+' | sort -n | awk 'NR==1{min=$1} END{print min, $1, NR}'
# 输出: 最小 最大 样本数
```

输出极短（<200 tokens）且输入很长（>40K tokens）时，说明模型几乎没有进行推理——输入的输出比 >500:1。

### 2. Cache hit 率异常

```bash
grep "API call" ~/.hermes/logs/agent.log | grep -oP 'cache=\K[0-9.]+%' | sort | uniq -c
```

Cache hit >75% 且持续多轮，说明提供商接口层对输入做了大量缓存截断，模型实际处理的 token 很少。

### 3. 推理链完整性

复现一个复杂排查任务（如 8 模块全链路检测），观察助手的回复是否：
- 能在 3 轮内找到实际根因
- 能在每轮输出中展示完整的推理链（数据采集→假设→验证→结论）
- 能跨轮延续之前的分析结论而非反复从头查起

## 推测原因

1. **模型路由不一致** — 提供商可能将 `deepseek-v4-flash` 路由到自己的蒸馏版或旧版
2. **输出长度截断** — 提供商接口层设置了较低的 `max_tokens`
3. **缓存策略激进** — 过高的 cache hit 率说明大量输入文本走缓存跳过了模型推理
4. **并发限流** — 提供商可能在低优先级用户请求上降低响应质量

## 处理建议

- 排查复杂问题时，优先切换回原生 API 进行确认
- 如必须使用自定义 provider，可用 `COGITO_LLM_*` 环境变量为 reflection LLM 指定独立 API
- 记录 agent.log 中的 `out=` 和 `cache=` 指标作为判断依据
