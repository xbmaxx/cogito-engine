---
title: "Text Emotion Specification"
description: "Specification for the Text Emotion module: Bayesian sentiment classification on character n-grams, language-aware model selection, and polarity scoring."
tags: [cogito-engine, text-emotion, sentiment, snownlp, specification]
---

# Text Emotion Specification

## Purpose

Text Emotion detects the emotional tone of user messages using text-only analysis. No voice, no audio, no multimodal input. The module uses a Bayesian classifier on character-level n-grams — the same approach pioneered by libraries like snownlp for Chinese text and TextBlob for English. The output is a sentiment polarity score and an optional emotion label.

## Activation Condition

The agent probes for text sentiment capability:

```
Can I perform Bayesian classification on character n-grams?
  ├── Yes → activate Text Emotion
  └── No  → disable; omit emotion data from output
```

Platforms with NLP libraries (snownlp, TextBlob, NLTK, spaCy) can use them directly. Platforms without NLP capability can implement a minimal Bayesian classifier from the reference implementation — it requires only n-gram counting and Bayes' theorem, no external dependencies.

## Algorithm: Bayesian Sentiment Classification

### Training

The classifier is pre-trained on labeled text corpora. For Chinese, the training corpus should include both positive and negative samples:

- Positive samples: reviews with 4-5 stars, praise comments, satisfied feedback
- Negative samples: reviews with 1-2 stars, complaint comments, frustrated feedback

The reference implementation uses the same training methodology as snownlp: character bigrams as features, Bayesian prior derived from the training set's class distribution.

### Classification

For a given input text:

1. Tokenize into character bigrams (language-agnostic, same approach as Self-Perception)
2. For each bigram, compute P(bigram | positive) and P(bigram | negative) from training data
3. Apply Bayes' theorem to compute P(positive | text) and P(negative | text)
4. The sentiment score is P(positive | text), ranging from 0.0 (strongly negative) to 1.0 (strongly positive)

```
P(positive | bigrams) = P(positive) × ∏ P(bigram | positive) /
                        (P(positive) × ∏ P(bigram | positive) +
                         P(negative) × ∏ P(bigram | negative))
```

### Language-Aware Model Selection

The classifier must match the language of the input text:

| User language | Recommended model |
|--------------|------------------|
| Chinese | Chinese-trained Bayesian (snownlp approach) |
| English | English-trained Bayesian (TextBlob approach) |
| Mixed / Unknown | Use character-bigram overlap with known vocabularies to select |

Running Chinese-trained sentiment on English text produces random results around 0.5 (neutral) because the training bigrams don't match the input bigrams. The agent should detect this and report low confidence.

## Output

### Polarity score

The primary output is a polarity score from 0.0 to 1.0:

| Score range | Label |
|------------|-------|
| 0.0 – 0.35 | negative |
| 0.35 – 0.65 | neutral |
| 0.65 – 1.0 | positive |

A confidence score accompanies the polarity, computed as the distance from 0.5:

```
confidence = |polarity - 0.5| × 2
```

A polarity of 0.5 has confidence 0.0 (the classifier is uncertain). A polarity of 0.0 or 1.0 has confidence 1.0 (the classifier is certain).

### Emotion labels (optional extension)

When the platform supports finer-grained emotion detection, the module may output emotion labels beyond polarity:

| Emotion | Typical polarity range |
|---------|----------------------|
| 愤怒 (anger) | 0.0 – 0.2 |
| 悲伤 (sadness) | 0.1 – 0.3 |
| 焦虑 (anxiety) | 0.2 – 0.4 |
| 平静 (calm) | 0.4 – 0.6 |
| 满意 (satisfaction) | 0.6 – 0.8 |
| 兴奋 (excitement) | 0.8 – 1.0 |

Fine-grained emotion labels are optional. The polarity + confidence pair is the minimum viable output.

## Edge Cases

### Very short messages

Messages shorter than 4 characters produce insufficient bigrams for reliable classification. The module returns polarity 0.5 with confidence 0.0 and a note: "text too short for sentiment analysis."

### Code or non-natural-language input

When the input is primarily code, URLs, or structured data, the bigram distribution won't match any training corpus. The module returns polarity 0.5 with confidence 0.0.

### Emotion change detection

The module tracks the user's emotional trajectory across a session. A sudden polarity shift (change > 0.3 in a single turn) is flagged in the output as a potential emotional event.

## Output Format

When available:

```xml
<emotion available="true" sentiment="negative" polarity="0.22" confidence="0.56" />
```

When extended with emotion label:

```xml
<emotion available="true" sentiment="negative" polarity="0.22" confidence="0.56" label="焦虑" />
```

When unavailable or insufficient data:

```xml
<emotion available="false" />
```
