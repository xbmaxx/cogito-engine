# 自定义情绪模型搭建指南

本文档面向**模型作者**——你想为 Cogito 引擎编写一个自己的情绪模型。

完成本文后你将：
- 写一个 Python 文件暴露 `Classifier` 类
- 放到 `~/.cogito/emotion_models/<name>/` 目录下
- 引擎自动发现，即放即用

无需学习 Hermes 插件体系，无需接触任何上层框架。

---

## 前置知识

- 基本 Python 编程
- 理解文本情绪分类的任务概念（输入文本 → 输出情绪维度）
- 阅读过 [情绪模型协议](./text-emotion-spec.md)（理解 classify() 返回格式）

---

## Step 0：理解协议

引擎只要求模型文件暴露一个 `Classifier` 类，实现两个方法：

```python
class Classifier:
    """情绪分类器。"""

    MODEL_NAME = "my_model"      # 可选：模型标识
    MODEL_DIMS = ["joy", "sad"]  # 可选：维度列表

    def is_available(self) -> bool:
        """返回模型是否可用（词典/依赖加载成功）。"""
        return True

    def classify(self, text: str) -> dict:
        """对文本分类，返回以下字段。

        Returns:
            available (bool): 模型是否可用
            emotions (dict[str, float]): 各维度概率
            dominant (str): 主导情绪标签
            confidence (float): 置信度 [0, 1]
            method (str): 模型标识
        """
        emotions = {"joy": 0.8, "sad": 0.2}
        return {
            "available": True,
            "emotions": emotions,
            "dominant": max(emotions, key=emotions.get),
            "confidence": 0.75,
            "method": "my_model",
        }
```

引擎会自动为结果添加 `label`、`label_cn`、`sentiment`、`polarity` 等旧版兼容字段，模型无需自行处理。

---

## Step 1：创建模型目录

```bash
mkdir -p ~/.cogito/emotion_models/my_model
cd ~/.cogito/emotion_models/my_model
```

目录名（`my_model`）将成为模型注册名。

---

## Step 2：编写分类器

创建 `my_model_classifier.py`：

```python
"""my_model_classifier.py —— 我的自定义情绪模型。"""

import json
from pathlib import Path
from typing import Any, Dict


MODEL_NAME = "my_model"
MODEL_DIMS = ["joy", "sad", "anger", "fear"]


class Classifier:
    """自定义情绪分类器。"""

    MODEL_NAME = MODEL_NAME
    MODEL_DIMS = MODEL_DIMS

    def __init__(self, dict_path: str = None) -> None:
        """初始化模型。

        引擎会在实例化时传入 dict_path（如果有同名 dict.json）。
        dict_path 可能为 None，模型必须处理这种情况。
        """
        self._available = False
        self._dict = {}
        if dict_path and Path(dict_path).exists():
            try:
                self._dict = json.loads(
                    Path(dict_path).read_text(encoding="utf-8")
                )
                self._available = True
            except Exception:
                pass
        else:
            # 无词典也可以运行（比如用 LLM 或规则引擎）
            self._available = True

    def is_available(self) -> bool:
        return self._available

    def classify(self, text: str) -> Dict[str, Any]:
        # 你的分类逻辑写在这里
        # 下面是一个示例：基于关键词的简单规则
        emotions = {dim: 0.0 for dim in self.MODEL_DIMS}
        text_lower = text.lower()

        # 示例规则
        if "happy" in text_lower or "great" in text_lower:
            emotions["joy"] = 0.9
        if "sad" in text_lower or "miss" in text_lower:
            emotions["sad"] = 0.8
        if "angry" in text_lower or "furious" in text_lower:
            emotions["anger"] = 0.85
        if "scared" in text_lower or "afraid" in text_lower:
            emotions["fear"] = 0.75

        # 如果有词典数据，可以叠加词典权重
        if self._dict:
            for word, weight in self._dict.items():
                if word in text_lower:
                    # 叠加词典权重到对应维度（示例逻辑）
                    pass

        dominant = max(emotions, key=emotions.get)
        # 如果所有值都为 0，返回 "none"
        if all(v == 0.0 for v in emotions.values()):
            dominant = "none"

        return {
            "available": True,
            "emotions": {k: round(v, 4) for k, v in emotions.items()},
            "dominant": dominant,
            "confidence": round(
                max(emotions.values()) if dominant != "none" else 0.0, 4
            ),
            "method": self.MODEL_NAME,
        }
```

---

## Step 3：提供词典（可选）

创建 `my_model_dict.json`：

```json
{
    "__META__": {
        "name": "My Custom Model",
        "version": "1.0.0",
        "description": "基于关键词的情绪分类器"
    },
    "wonderful": {"dim": "joy", "weight": 0.8},
    "terrible": {"dim": "sad", "weight": 0.7},
    "horrible": {"dim": "anger", "weight": 0.9}
}
```

`__META__` 为可选元信息字段。引擎目前暂不读取 `__META__` 中的 `active` 标记（预留 v1.5.2）。

---

## Step 4：声明依赖（可选）

如果模型需要额外的 Python 包，创建 `requirements.txt`：

```text
jieba>=0.42.1
scikit-learn>=1.0
```

**引擎不自动安装依赖**，仅日志警告。模型作者需告知用户手动安装。

---

## Step 5：验证模型

```python
# 手动测试
from cogito_core.emotion_registry import EmotionModelRegistry
from pathlib import Path

registry = EmotionModelRegistry()
registry.discover([Path.home() / ".cogito" / "emotion_models"])

# 查看已注册模型
print(registry.list_models())

# 测试分类
result = registry.classify_with_fallback("我今天很开心")
print(result)
```

或直接在引擎中验证：

```python
from cogito_core import CogitoEngine
engine = CogitoEngine(emotion_model="my_model")
xml, state = engine.process(
    messages=[{"role": "user", "content": "我今天很开心"}],
    state=None,
)
print(xml)
```

---

## Step 6：在引擎中切换模型

### Hermes 环境下

```python
# 在 CogitoEngine 初始化时指定
engine = CogitoEngine(
    ...,
    emotion_model="my_model",
)
```

### 运行时切换

```python
engine.emotion_registry.set_active("my_model")
```

---

## 验收清单

- [ ] `~/.cogito/emotion_models/<name>/` 目录存在
- [ ] `<name>_classifier.py` 存在，暴露 `Classifier` 类
- [ ] `Classifier` 实现了 `is_available()` 和 `classify()`
- [ ] `classify()` 返回 `available`、`emotions`、`dominant`、`confidence`、`method`
- [ ] 模型文件可以被 `from cogito_core.emotion_registry import EmotionModelRegistry` 自动发现
- [ ] `emotion_model="<name>"` 参数能正常切换

---

## 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| 模型未被加载 | 文件名格式不对 | 文件名必须是 `<name>_classifier.py` |
| classify 返回空 | 未处理 dict_path 为 None 的情况 | 检查 __init__ 中对 dict_path 的判断 |
| 标签全是中性 | enrich_legacy_fields 不认识你的 dominant 值 | dominant 使用协议中预定义的标签，或模型自身提供 label 字段 |
| 模型不稳定 | 依赖未安装 | 在 requirements.txt 中声明，手动 pip install |
