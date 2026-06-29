#!/usr/bin/env python3
"""
Sentiment model trainer for Cogito Engine.
Generates a character-bigram → polarity mapping from labeled text files.
Zero dependencies — Python 3.9+ standard library only.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def _bigrams(text: str) -> list[str]:
    """Extract character-level bigrams from text. Language-agnostic."""
    text = text.strip()
    if len(text) < 2:
        return []
    return [text[i:i+2] for i in range(len(text) - 1)]


def _detect_language(pos_lines: list[str], neg_lines: list[str]) -> str:
    """Heuristic: count CJK characters vs Latin characters."""
    cjk = 0
    latin = 0
    for line in pos_lines + neg_lines:
        for ch in line:
            if '\u4e00' <= ch <= '\u9fff' or '\u3000' <= ch <= '\u303f':
                cjk += 1
            elif ch.isascii() and ch.isalpha():
                latin += 1
    return "zh" if cjk > latin else "en"


def _score_word(word: str) -> float:
    """Simple lexicon-based polarity for English words. Used as a fallback
    when no training data is provided and a quick sanity check is needed."""
    positive = {
        "good", "great", "excellent", "awesome", "love", "amazing", "fantastic",
        "wonderful", "best", "happy", "beautiful", "perfect", "nice", "thank",
        "thanks", "helpful", "brilliant", "outstanding", "superb", "delightful",
        "impressive", "recommend", "enjoy", "pleased", "satisfied",
    }
    negative = {
        "bad", "terrible", "awful", "hate", "worst", "horrible", "poor",
        "ugly", "boring", "waste", "broken", "fail", "failed", "error",
        "bug", "crash", "slow", "useless", "disappointed", "frustrating",
        "annoying", "stupid", "wrong", "missing",
    }
    word_lower = word.lower()
    if word_lower in positive:
        return 0.85
    if word_lower in negative:
        return 0.15
    return 0.5


def train(pos_file: str, neg_file: str, output: str, language: str,
          min_count: int, smooth: float):
    """Train a Bayesian sentiment model from positive and negative text files."""

    pos_lines = [line.strip() for line in Path(pos_file).read_text(encoding='utf-8').splitlines() if line.strip()]
    neg_lines = [line.strip() for line in Path(neg_file).read_text(encoding='utf-8').splitlines() if line.strip()]

    if not pos_lines:
        print(f"ERROR: {pos_file} is empty or has no valid lines")
        sys.exit(1)
    if not neg_lines:
        print(f"ERROR: {neg_file} is empty or has no valid lines")
        sys.exit(1)

    if language == "auto":
        language = _detect_language(pos_lines, neg_lines)

    pos_bigram_counts: Counter = Counter()
    neg_bigram_counts: Counter = Counter()

    for line in pos_lines:
        for bg in _bigrams(line):
            pos_bigram_counts[bg] += 1

    for line in neg_lines:
        for bg in _bigrams(line):
            neg_bigram_counts[bg] += 1

    # Compute priors
    pos_total = len(pos_lines)
    neg_total = len(neg_lines)
    all_total = pos_total + neg_total
    prior_positive = pos_total / all_total

    # Build bigram → polarity map
    all_bigrams = set(pos_bigram_counts.keys()) | set(neg_bigram_counts.keys())
    bigrams_out = {}

    for bg in all_bigrams:
        pos_count = pos_bigram_counts.get(bg, 0) + smooth
        neg_count = neg_bigram_counts.get(bg, 0) + smooth
        total = pos_count + neg_count
        if pos_count + neg_count < min_count:
            continue
        polarity = pos_count / total
        bigrams_out[bg] = {
            "positive": int(pos_count),
            "negative": int(neg_count),
            "polarity": round(polarity, 4),
        }

    model = {
        "language": language,
        "prior_positive": round(prior_positive, 4),
        "total_bigrams": len(bigrams_out),
        "smooth": smooth,
        "min_count": min_count,
        "training_samples": {"positive": pos_total, "negative": neg_total},
        "bigrams": bigrams_out,
    }

    with open(output, 'w', encoding='utf-8') as f:
        json.dump(model, f, ensure_ascii=False, indent=2)

    print(f"Trained {len(bigrams_out)} bigrams from {pos_total}+{neg_total} samples")
    print(f"Language: {language}  Prior(positive): {prior_positive:.2f}")
    print(f"Model saved to {output}")


def validate(model_file: str, validation_file: str):
    """Validate a trained model against labeled test data."""
    import math

    model = json.loads(Path(model_file).read_text(encoding='utf-8'))
    bigrams_map = model["bigrams"]

    lines = [line.strip() for line in Path(validation_file).read_text(encoding='utf-8').splitlines() if line.strip()]
    if not lines:
        print("ERROR: validation file is empty")
        sys.exit(1)

    correct = 0
    total = 0
    tp = fp = tn = fn = 0

    for line in lines:
        if len(line) < 3 or line[0] not in ('0', '1') or line[1] != ' ':
            continue
        expected = int(line[0])
        text = line[2:].strip()
        if not text:
            continue

        bgs = _bigrams(text)
        if not bgs:
            continue

        # Naive Bayes classification
        pos_score = math.log(model["prior_positive"]) if model["prior_positive"] > 0 else -999
        neg_score = math.log(1 - model["prior_positive"]) if model["prior_positive"] < 1 else -999

        for bg in bgs:
            info = bigrams_map.get(bg, {"polarity": 0.5, "positive": 1, "negative": 1})
            p_pos = max(info.get("polarity", 0.5), 0.001)
            p_neg = max(1 - p_pos, 0.001)
            pos_score += math.log(p_pos)
            neg_score += math.log(p_neg)

        predicted = 1 if pos_score > neg_score else 0

        if predicted == expected:
            correct += 1
        total += 1

        if expected == 1 and predicted == 1:
            tp += 1
        elif expected == 1 and predicted == 0:
            fn += 1
        elif expected == 0 and predicted == 1:
            fp += 1
        elif expected == 0 and predicted == 0:
            tn += 1

    if total == 0:
        print("No valid validation samples found")
        sys.exit(1)

    accuracy = correct / total
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    print(f"Samples: {total}")
    print(f"Accuracy:  {accuracy:.3f}")
    print(f"Precision: {precision:.3f}")
    print(f"Recall:    {recall:.3f}")
    print(f"F1:        {f1:.3f}")

    if accuracy < 0.65:
        print("\n⚠  Accuracy below 0.65 — consider adding more training data")
    elif accuracy < 0.75:
        print("\n⚡ Accuracy between 0.65-0.75 — usable but could be better")
    else:
        print("\n✓  Accuracy above 0.75 — ready for production")


def main():
    parser = argparse.ArgumentParser(
        description="Train a Bayesian sentiment model for Cogito Engine"
    )
    parser.add_argument("--pos", help="Path to positive samples file (one per line)")
    parser.add_argument("--neg", help="Path to negative samples file (one per line)")
    parser.add_argument("--output", default="sentiment_model.json", help="Output model file path")
    parser.add_argument("--language", default="auto", choices=["zh", "en", "auto"],
                        help="Language: zh, en, or auto-detect")
    parser.add_argument("--min-count", type=int, default=2,
                        help="Minimum bigram occurrence to include in model")
    parser.add_argument("--smooth", type=float, default=0.1,
                        help="Laplace smoothing factor")
    parser.add_argument("--model", help="Model file to validate")
    parser.add_argument("--validate", help="Validation file path (format: '1 text' or '0 text')")

    args = parser.parse_args()

    if args.model and args.validate:
        validate(args.model, args.validate)
        return

    if not args.pos or not args.neg:
        parser.error("--pos and --neg are required for training, or use --model + --validate")

    train(args.pos, args.neg, args.output, args.language, args.min_count, args.smooth)


if __name__ == "__main__":
    main()
