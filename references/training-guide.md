---
title: "Sentiment Training Guide"
description: "How to prepare training data, run the sentiment training script, and replace the default model with a custom one. Covers Chinese, English, and mixed-language data preparation."
tags: [cogito-engine, training, sentiment, text-emotion, customization]
---

# Sentiment Training Guide

## When to train a custom model

The default Chinese and English sentiment models shipped with Cogito Engine cover general-purpose text. Train a custom model when:

- Your domain vocabulary differs from general text (medical, legal, gaming, finance)
- The default model produces polarity scores consistently near 0.5 on your input
- You want language-specific nuance (e.g., Cantonese sentiment differs from Mandarin)
- You're serving a multilingual audience with mixed-language messages

## Step 1: Prepare training data

Create two plain-text files:

```
training/
├── pos.txt    # One positive sample per line
└── neg.txt    # One negative sample per line
```

**Data quality rules:**

- Minimum 100 lines per file for usable results; 500+ recommended
- Each line is one complete message, review, or comment
- Strip emoji, URLs, and markdown — keep only natural-language text
- Keep lines under 200 characters for training efficiency

**Example `pos.txt` (Chinese):**

```
这个功能太好用了，效率提升很多
感谢你帮我解决这个问题，非常专业
我就喜欢这种简洁的设计
服务态度很好，回复也快
```

**Example `neg.txt` (Chinese):**

```
等了半天没反应，太慢了
这个功能完全不符合我的需求
界面太复杂了，根本不知道怎么用
试了几次都不行，放弃了
```

## Step 2: Run the training script

```bash
python scripts/train_sentiment.py \
  --pos training/pos.txt \
  --neg training/neg.txt \
  --output my_sentiment_model.json \
  --language zh
```

Options:

| Flag | Default | Description |
|------|---------|-------------|
| `--pos` | (required) | Path to positive samples file |
| `--neg` | (required) | Path to negative samples file |
| `--output` | `sentiment_model.json` | Output model file path |
| `--language` | `auto` | `zh`, `en`, or `auto` (detect from character distribution) |
| `--min-count` | `2` | Minimum bigram occurrence to include in model |
| `--smooth` | `0.1` | Laplace smoothing factor |

The script outputs a JSON file containing character-level bigram → polarity mappings:

```json
{
  "language": "zh",
  "prior_positive": 0.52,
  "total_bigrams": 2841,
  "bigrams": {
    "很好": {"positive": 47, "negative": 3, "polarity": 0.94},
    "用了": {"positive": 12, "negative": 18, "polarity": 0.40},
    "不行": {"positive": 2, "negative": 31, "polarity": 0.06}
  }
}
```

## Step 3: Validate the model

Run the validation script with test data:

```bash
python scripts/train_sentiment.py \
  --model my_sentiment_model.json \
  --validate validation.txt
```

Where `validation.txt` uses the format:

```
1 这个产品真的很好用
0 完全不符合预期，很失望
1 客服态度特别好
0 界面太乱了找不到功能
```

The first character of each line is the expected label: `1` for positive, `0` for negative, followed by a space and the text.

The validation output reports accuracy, precision, recall, and F1 score.

Target: accuracy > 0.75 for general use. Below 0.65, add more training data or check for data quality issues.

## Step 4: Replace the default model

Copy your trained model into the Cogito Engine implementation:

```python
# Replace the built-in models with your custom one
engine = CogitoEngine()
engine.text_emotion.load_model("my_sentiment_model.json")
```

Or replace the default model file so all instances use it:

```bash
cp my_sentiment_model.json sentiment_model_zh.json
```

## Troubleshooting

| Problem | Likely cause | Fix |
|---------|-------------|-----|
| All polarity scores near 0.5 | Training data too small or balanced | Add more samples, check for label imbalance |
| Consistent wrong direction | Negative samples mislabeled | Audit `neg.txt` for actually-positive text |
| High accuracy on val but bad on real | Validation data from same distribution as training | Hold out validation data from a different source |
| Script fails on large files | Memory usage | Split into batches of 5000 lines |
