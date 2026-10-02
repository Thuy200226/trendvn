# Performance budget and results

## Targets (SLIs/SLOs)
| Operation / page | Metric | Budget | Measured (date, conditions) |
|---|---|---|---|
| <API endpoint> | latency p95 / p99 | <300 ms / 800 ms> | |
| <batch job> | wall time per unit | <seconds> | |
| <web page> | LCP / INP / CLS at p75 | <= 2.5 s / <= 200 ms / <= 0.1 | |
| <service> | memory / startup | <MB> / <s> | |
| <CI fast gate> | duration | < 10 min | |

(Web Vitals thresholds: re-check at web.dev before using them as contract numbers.)

## Baseline
Date, commit, machine, load average, data size, tool and command used to measure, number of runs, range:

## Stage breakdown (where the time goes)
| Stage | Time | Share | Waiting or CPU? |
|---|---|---|---|

## Changes and results
| Change | Before | After | Quality/correctness check | Decision |
|---|---|---|---|---|

## Experiments that did not help (so nobody repeats them)
- <idea> - <measurement> - <why dropped>

## Guard
Benchmark/test name and threshold in CI; dashboard/alert; tunables (env var, default, limits):
