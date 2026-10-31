# Evaluation summary (2026-10-31T17:40:28+00:00)

## Retrieval (section level, in-scope questions)

| Mode @ chunk tokens | split | n | hit@1 | hit@3 | hit@5 | MRR |
|---|---|---|---|---|---|---|
| bm25@200 | dev | 20 | 0.800 | 0.950 | 0.950 | 0.870 |
| bm25@200 | test | 20 | 0.750 | 1.000 | 1.000 | 0.867 |
| bm25@200 | all | 40 | 0.775 | 0.975 | 0.975 | 0.868 |
| vector@200 | dev | 20 | 0.900 | 0.900 | 1.000 | 0.922 |
| vector@200 | test | 20 | 1.000 | 1.000 | 1.000 | 1.000 |
| vector@200 | all | 40 | 0.950 | 0.950 | 1.000 | 0.961 |
| hybrid@200 | dev | 20 | 1.000 | 1.000 | 1.000 | 1.000 |
| hybrid@200 | test | 20 | 1.000 | 1.000 | 1.000 | 1.000 |
| hybrid@200 | all | 40 | 1.000 | 1.000 | 1.000 | 1.000 |
| bm25@300 | dev | 20 | 0.850 | 0.950 | 0.950 | 0.896 |
| bm25@300 | test | 20 | 0.700 | 1.000 | 1.000 | 0.842 |
| bm25@300 | all | 40 | 0.775 | 0.975 | 0.975 | 0.869 |
| vector@300 | dev | 20 | 0.850 | 0.950 | 1.000 | 0.904 |
| vector@300 | test | 20 | 0.900 | 1.000 | 1.000 | 0.950 |
| vector@300 | all | 40 | 0.875 | 0.975 | 1.000 | 0.927 |
| hybrid@300 | dev | 20 | 0.950 | 1.000 | 1.000 | 0.975 |
| hybrid@300 | test | 20 | 0.950 | 1.000 | 1.000 | 0.975 |
| hybrid@300 | all | 40 | 0.950 | 1.000 | 1.000 | 0.975 |
| bm25@400 | dev | 20 | 0.750 | 0.950 | 0.950 | 0.838 |
| bm25@400 | test | 20 | 0.750 | 1.000 | 1.000 | 0.858 |
| bm25@400 | all | 40 | 0.750 | 0.975 | 0.975 | 0.848 |
| vector@400 | dev | 20 | 0.800 | 0.950 | 1.000 | 0.887 |
| vector@400 | test | 20 | 0.950 | 1.000 | 1.000 | 0.975 |
| vector@400 | all | 40 | 0.875 | 0.975 | 1.000 | 0.931 |
| hybrid@400 | dev | 20 | 0.900 | 1.000 | 1.000 | 0.942 |
| hybrid@400 | test | 20 | 1.000 | 1.000 | 1.000 | 1.000 |
| hybrid@400 | all | 40 | 0.950 | 1.000 | 1.000 | 0.971 |

## Refusal gate

Threshold tuned on dev: 0.8313

| split | accuracy | in-scope answered | out-of-scope refused |
|---|---|---|---|
| dev | 1.000 | 1.000 | 1.000 |
| test | 1.000 | 1.000 | 1.000 |

## Classification

```json
{
  "model": "openai/gpt-oss-120b",
  "prompt_version": "v1",
  "n": 37,
  "label_status": [
    "draft"
  ],
  "provisional": true,
  "topics": {
    "micro_precision": 0.5666666666666667,
    "micro_recall": 0.6938775510204082,
    "micro_f1": 0.6238532110091742,
    "macro_f1": 0.6455627705627706,
    "per_label_f1": {
      "data_protection": 0.9333333333333333,
      "cybersecurity": 0.8571428571428571,
      "platform_liability": 0.2857142857142857,
      "competition": 0.6666666666666666,
      "transparency": 0.6,
      "enforcement_penalties": 0.8,
      "scope_definitions": 0.5454545454545454,
      "other": 0.47619047619047616
    }
  },
  "sectors": {
    "micro_precision": 0.2631578947368421,
    "micro_recall": 0.24390243902439024,
    "micro_f1": 0.25316455696202533,
    "macro_f1": 0.277037037037037,
    "per_label_f1": {
      "all": 0.2222222222222222,
      "public_sector": 0.0,
      "online_platforms": 0.6666666666666666,
      "telecom": 0.29629629629629634,
      "other": 0.19999999999999998
    }
  },
  "impact": {
    "n": 37,
    "accuracy": 0.5675675675675675,
    "within_one": 0.972972972972973,
    "confusion": {
      "low": {
        "low": 7,
        "medium": 8,
        "high": 1
      },
      "medium": {
        "low": 1,
        "medium": 9,
        "high": 0
      },
      "high": {
        "low": 0,
        "medium": 6,
        "high": 5
      }
    }
  },
  "primary_topic_accuracy": 0.5945945945945946
}
```

## System

```json
{
  "changes_total": 107,
  "enrichment": [
    {
      "model": "openai/gpt-oss-120b",
      "prompt_version": "v1",
      "succeeded": 82,
      "failed": 0,
      "tokens_per_change": 1810.2073170731708,
      "median_latency_ms": 717.0,
      "shadow_cost_per_1000_changes_usd": 0.36639329268292664,
      "shadow_cost_total_usd": 0.030044249999999984
    }
  ]
}
```
