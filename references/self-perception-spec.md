---
title: "Self-Perception Specification"
description: "Specification for the Self-Perception module: character bigram algorithm, Jaccard similarity thresholds, mirror vs loop detection, style cluster analysis, and self-correction guidance."
tags: [cogito-engine, self-perception, mirror-detection, loop-detection, specification]
---

# Self-Perception Specification

## Purpose

The Self-Perception module gives the agent awareness of its own behavioral patterns. It computes similarity between consecutive responses, detects when the agent is mirroring the user or looping on itself, and tracks broader style patterns. The output is a perception snapshot — a text description of what the agent notices about itself.

## Core Algorithm: Character Bigrams

The module tokenizes text into character-level bigrams (pairs of adjacent characters). This approach is language-agnostic — it works equally well on English, Chinese, code, and mixed-language text.

```
Input:  "Hello"
Bigrams: ["He", "el", "ll", "lo"]
```

Chinese text:

```
Input:  "你好世界"
Bigrams: ["你好", "好世", "世界"]
```

The bigram representation captures both content and style. Similar bigram distributions indicate similar phrasing patterns.

## Similarity Metric: Jaccard Index

Similarity between two texts is the Jaccard index of their bigram sets:

```
J(A, B) = |A ∩ B| / |A ∪ B|
```

Range: 0.0 (completely dissimilar) to 1.0 (identical bigram sets).

## Detection Thresholds

### Mirror Detection

Mirroring occurs when the agent unconsciously copies the user's phrasing.

| Input | Compared against | Threshold | Behavior |
|-------|-----------------|-----------|----------|
| Agent's last response | User's last message | > 0.4 | Mirror detected |

A mirror score above 0.4 suggests the agent is echoing the user rather than generating original content. The perception reports this as a warning.

### Loop Detection

Looping occurs when the agent repeats its own previous output.

| Input | Compared against | Threshold | Behavior |
|-------|-----------------|-----------|----------|
| Agent's last response | Agent's previous response | > 0.6 | Loop detected |

A loop score above 0.6 suggests the agent is stuck in a repetitive pattern. This is a stronger signal than mirroring — looping indicates the agent has lost creative diversity.

### Style Cluster Detection

Beyond single-turn comparisons, the module tracks whether the agent's response style is changing over time.

Compare the current response against a rolling window of the last 3–5 responses. If all pairwise similarities exceed 0.5, the cluster is "narrow" — the agent may be in a stylistic rut. If similarities vary widely (some < 0.3, some > 0.5), the cluster is "diverse" — the agent is varying its expression.

## Perception Snapshot

The module produces a human-readable perception text:

```
Self-perception: mirror=0.35 (below threshold), loop=0.12 (below threshold), style_cluster=unchanged.
Confidence in current response pattern: high. No behavioral flags.
```

When mirror or loop is detected:

```
Self-perception: mirror=0.52 (ABOVE THRESHOLD). Agent is echoing user phrasing. Consider rephrasing in a distinct voice.
```

## Minimum Data Requirement

Both mirror and loop detection require at least 2 agent responses to compare. With fewer than 2 responses:

```
Self-perception: mirror=N/A (insufficient data), loop=N/A (insufficient data), style_cluster=initializing.
```

## Exact Match vs Similarity

An exact match (Jaccard = 1.0) between two consecutive agent responses is a special case. The module reports this as "exact duplicate" rather than "loop" because the semantic implication is different — it may indicate a bug, a retry, or intentional repetition. Implementations should handle exact duplicates separately from high-similarity loops.

## Output

The Self-Perception module produces the following XML fragment:

```xml
<self mirror="false" loop="false" style_cluster="unchanged" />
```

With detected issues:

```xml
<self mirror="true" mirror_score="0.52" loop="false" loop_score="0.12" style_cluster="unchanged" />
```

The `mirror_score` and `loop_score` attributes are optional — include them when the agent platform supports numeric output.
