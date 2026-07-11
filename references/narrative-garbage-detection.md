---
title: 叙事记忆垃圾摘要检测
version: 1.0
---

# 4 档垃圾摘要检测设计

## 背景

reflection LLM 静默失败时（custom provider 找不到 API key、模型名不匹配等），引擎 fallback 到关键词拼接，产出类似 `"讨论了agent、task、skill、session等话题"` 的垃圾摘要。这些摘要没有实际语义价值，进入叙事记忆后会污染跨会话上下文。

## 4 档检测链（按执行顺序）

### 档 1 — 正则模板匹配

```python
_GARBAGE_TEMPLATES = [
    r"讨论了?.+等话题",
    r"涉及了?.+等方?面?",
    r"关于.+等内容",
    r"主要讨论了?",
    r"本期.+涉及",
    r"[^，。]*?等多[^，。]*",  # "agent、task、skill 等多种/多个…"
]
```

覆盖所有已知的关键词拼接模板句式。中文句首动词 + 逗号枚举 + "等"结尾。

### 档 2 — 关键词拼接 heuristic

**条件**（三条件同时满足才判垃圾）：
1. 文本长度 < 80 字符
2. 逗号/分句符（`，`, `,`, `、`）≥ 2 个
3. **无中文动词特征词**

```python
_CHINESE_VERB_MARKERS = {
    "了", "过", "进行", "完成", "需要", "发现", "确认",
    "建议", "修复", "优化", "添加", "删除", "修改",
    "分析", "验证", "对比", "测试", "排查",
    "解决", "提出", "决定", "计划", "准备", "正在",
}
```

**设计思路**：中文动词是语义"锚点"。`"发现了 bug"`、`"修复了问题"`、`"确认了方案"`——有这些词说明文本有真实叙事结构。纯关键词拼接不可能有这些词。

为什么不用英文动词检测：英文动词形态变化多（fix/fixed/fixing/fixes），中文动词形态稳定，判断成本低且可靠。

### 档 3 — 过短拦截

`len(text) < 15` → 直接判垃圾。任何有实际意义的叙事摘要至少需要 15 个字符。

### 档 4 — 原有关键词集匹配

沿用 `_GARBAGE_PATTERNS`：
- `{user, one, skills, via, session}` — delegate_task 子代理关键词
- `{checkpoint, Generate, context, summary}` — context 压缩关键词

≥ 3 个命中即判垃圾。

## 测试套件

```python
tests = [
    # 应拦截
    ("讨论了agent、task、skill等话题", True, "模板"),
    ("涉及了用户、服务、系统、配置等几个方面", True, "模板"),
    ("关于deepseek、provider、reflection、llm等内容", True, "模板"),
    ("主要讨论了服务架构和缓存策略", True, "模板"),
    ("本期内容涉及了agent、saas、task等", True, "模板"),
    ("模型部署、服务优化、API网关、数据同步等多种方案", True, "模板"),
    ("user, tool, session, task", True, "关键词拼接"),
    ("agent、task、skill、session", True, "关键词拼接"),
    ("a b c", True, "过短"),
    ("checkpoint Generate context summary", True, "关键词集"),
    ("user one skills via session", True, "关键词集"),
    
    # 应放行
    ("用户在测试中发现Cogito Engine的tick不增长，排查发现是Bridge Worker不触发pre_llm_call导致的，建议在install.py中加入Studio自动检测逻辑", False, "正常"),
    ("确认了WorkBuddy API的deepseek有降智问题，输出偏少切回原生后效果明显提升", False, "正常"),
    ("测试完毕，所有8个模块功能正常", False, "正常"),
]
```

## 边界情况

| 情况 | 处理 |
|------|------|
| 空文本 | 直接 False（不拦截空值） |
| 纯英文 | 档 2 检测逗号，档 4 检测关键词集 |
| 中英文混合 | 档 1 模板 + 档 2 中文动词同时生效 |
| 极短但含动词（"测试完毕"） | 档 2 不拦截（有中文动词），档 3 不拦截（长度 ≥ 15 通过） |
| 纯标点符号 | 档 2 逗号≥2 + 无动词 → 拦截 |

## 历史

- **v1.5.0 之前**：简单字符串匹配（`startswith("讨论了")` / `"等话题" in text`）
- **v1.5.1**：被错误移除（以为不需要，实则 reflection LLM 静默失败路径未修）
- **v1.5.2**：4 档检测链替代，覆盖更全面
