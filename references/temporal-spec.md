---
title: "Temporal Parser Specification"
description: "Specification for the Temporal module: natural-language time expression vocabulary, longest-match-first resolution, timezone handling, and word stripping."
tags: [cogito-engine, temporal, time-parsing, specification]
---

# Temporal Parser Specification

## Purpose

The Temporal module parses natural-language time expressions from user messages and resolves them to precise local ISO 8601 timestamps. It also strips temporal words from the message text so they do not pollute keyword extraction and focus tracking.

## Time Expression Vocabulary

The module recognizes the following categories of temporal expressions, checked in priority order (longest match first):

### Absolute date references

| Expression | Resolution |
|-----------|------------|
| `YYYY-MM-DD` | Exact date (e.g., `2026-06-29`) |
| `YYYY/MM/DD` | Exact date |
| `YYYY年M月D日` | Exact date |
| `M月D日` | Current year |

### Relative day offsets

| Expression | Resolution |
|-----------|------------|
| `今天` / `today` | Current local date |
| `昨天` / `yesterday` | Current date minus 1 day |
| `前天` / `day before yesterday` | Current date minus 2 days |
| `明天` / `tomorrow` | Current date plus 1 day |
| `后天` / `day after tomorrow` | Current date plus 2 days |
| `N天前` / `N days ago` | Current date minus N days |
| `N天后` / `N days later` | Current date plus N days |

### Day names

| Expression | Resolution |
|-----------|------------|
| `星期一`–`星期日` | Most recent occurrence of that weekday |
| `Monday`–`Sunday` | Most recent occurrence |
| `上周一` / `last Monday` | Previous week, that weekday |
| `下周三` / `next Wednesday` | Next week, that weekday |

### Period markers

| Expression | Resolution |
|-----------|------------|
| `早上` / `morning` | 06:00–11:59 local |
| `上午` / `late morning` | 09:00–11:59 local |
| `中午` / `noon` | 12:00–12:59 local |
| `下午` / `afternoon` | 13:00–17:59 local |
| `晚上` / `evening` | 18:00–23:59 local |
| `凌晨` / `late night` | 00:00–05:59 local |

### Week/month/year references

| Expression | Resolution |
|-----------|------------|
| `这周` / `this week` | Monday–Sunday of current week |
| `上周` / `last week` | Monday–Sunday of previous week |
| `下周` / `next week` | Monday–Sunday of next week |
| `这个月` / `this month` | 1st to last day of current month |
| `上个月` / `last month` | 1st to last day of previous month |
| `今年` / `this year` | Jan 1 to Dec 31 of current year |
| `去年` / `last year` | Jan 1 to Dec 31 of previous year |

## Longest-Match-First Algorithm

The module scans the message text for matches in the vocabulary. When multiple expressions overlap, the longest match wins. For example, in "上周三下午":

1. "上周三" (last Wednesday) is one candidate — 3 characters
2. "周三" (Wednesday) is another — 2 characters, but "上周三" is longer
3. "下午" (afternoon) is a separate match — 2 characters

Resolution: "上周三" → previous week's Wednesday, "下午" → afternoon period.

### Consumptive scanning

After a match is found, the matched characters are removed from the scan window. This prevents double-counting tokens. The scan continues from the character after the match.

### Implicit disambiguation

When a relative expression could point to multiple dates, the module uses "most recent" as the default: "星期五" on a Tuesday refers to last Friday, not next Friday, unless context suggests future intent.

## Timezone Handling

**Output is always in the agent's local timezone with offset.** Never output UTC.

```
✅ 2026-06-29T15:41:00+08:00
❌ 2026-06-29T07:41:00Z
❌ 2026-06-29T07:41:00+00:00
```

The agent must call its platform's local time API. No hardcoded offsets. No assumptions about UTC.

## Word Stripping

After parsing, all matched temporal expressions are removed from the message text. The stripped text is what feeds into keyword extraction and self-perception. This prevents "yesterday" from becoming a focus keyword.

Stripping preserves surrounding punctuation and whitespace. The stripped text should read naturally.

## Output

The Temporal module produces the following XML fragment:

```xml
<temporal iso="2026-06-29T15:41:00+08:00" weekday="Monday" period="afternoon" local="2026-06-29 15:41" timezone="CST" />
```

When no temporal expression is detected (but time metadata is still needed):

```xml
<temporal iso="2026-06-29T15:41:00+08:00" weekday="Monday" period="afternoon" />
```

The `local` and `timezone` fields are optional. The `iso`, `weekday`, and `period` fields are required.
