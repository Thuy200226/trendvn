# Performance and speed standard (any stack)

Principle: performance is a requirement with a number, measured on realistic data, defended by a gate. The fastest code is the code you do not run: remove work first, then batch, cache and parallelize, and only then micro-optimize. Never optimize something you have not measured; never ship an optimization you could not show is safe.

## 1. Define the target
- Write **SLIs/SLOs and budgets** before work: user-facing latency percentiles (p50/p95/p99, not averages), throughput, error rate, memory, startup/cold-start time, cost per unit of work, build and CI time.
- Web UI budgets (**Core Web Vitals**, measured at the 75th percentile of real users): LCP <= 2.5 s, INP <= 200 ms, CLS <= 0.1. Add bundle-size and request-count budgets. (Thresholds are published by Google/web.dev; re-check them before using them as contract numbers: at least one source claims LCP's "good" bar was tightened to 2.0 s in 2026, which was not confirmed from the primary source.)
- Services: pick the **RED** (rate, errors, duration) view for requests and **USE** (utilization, saturation, errors) for resources.
- Put the budget in the repo (`assets/performance-budget-template.md`) and, where possible, in CI as a failing check.

## 2. Measure properly
1. **Baseline first**: same input, same machine state, same build; note load average and data size. Without a "before" there is no "after".
2. **Profile, don't guess**: CPU profiler / flame graph, query plans (`EXPLAIN ANALYZE`), tracing spans per stage, allocation profiles, browser performance panel. Break an end-to-end operation into stages with timings (probe, fetch, parse, compute, write, remote call) and look at what dominates and what merely **waits**.
3. **Realistic data and load**: production-shaped data volumes and distributions; load/soak tests with a tool (k6, Locust, wrk, JMeter); warm up; test at and beyond expected peak; watch saturation, not only latency.
4. **Statistics**: repeat runs, report ranges and percentiles; say when variance is larger than the effect.
5. **Beware confounders**: third parties that rate-limit or fail intermittently, shared or loaded machines, caches (cold vs warm), time-of-day effects. If an A/B cannot separate the variants, report "inconclusive" and keep the proven behaviour. Don't hammer a third party while benchmarking; interleave A/B.
6. **Record the result** as a before/after table with conditions, plus experiments that did not help.

## 3. Where speed usually comes from (check each against your profile)
**Do less work**: skip passes whose output is unused; if an input already is the desired output, copy it instead of re-processing (lossless and faster); send consumers only what they use (a model that samples 1 frame/s gains nothing from a 2 fps upload); lazy-load; paginate and cap unbounded queries; compute once and reuse.
**Algorithms and data structures**: remove accidental O(n^2), choose the right index/structure, avoid repeated parsing/serialization, stream instead of loading everything.
**Database**: fix N+1 (batch/join), add the right indexes (check the plan, mind write cost), select only needed columns, bound result sets, use connection pooling, batch writes in one transaction, keep transactions short, read replicas for heavy reads, avoid long locks; for SQLite use WAL and short writers.
**Caching** (with an invalidation story): HTTP caching (ETag, `Cache-Control`), CDN for static assets, application cache for expensive pure results, memoization; define TTL and what invalidates; never cache per-user data in shared caches; measure hit ratio.
**Concurrency**: parallelize *waiting-dominated* work (network, remote APIs) with **bounded** concurrency (a small default, configurable via env, 1 restores serial behaviour); use async I/O or worker pools; apply backpressure and timeouts; make check-then-write sequences atomic (one transaction) or concurrency will introduce races (duplicate detection, quotas, claims); add a stress test that fails when the window reopens.
**Network**: fewer round trips, HTTP/2 or 3, keep-alive, compression for text payloads, smaller payloads, retries with jittered backoff and idempotency, timeouts on every call.
**Frontend**: ship less JavaScript (code splitting, tree-shaking, defer non-critical), optimized images (AVIF/WebP, responsive sizes, explicit width/height to prevent layout shift), preload critical resources, avoid long main-thread tasks (INP), virtualize long lists, server-render or stream critical content.
**Runtime/infra**: right-size resources, avoid cold starts (warm pools, smaller images), tune GC/heap only with evidence, put work close to the data, autoscale on the saturating resource.
**Build and CI speed**: cache dependencies and build layers, split tests across runners, run the fast gate first, skip unaffected work, keep images small.

## 4. Quality knobs need a reference
When trading quality for speed or size (compression, encoding, sampling, ML thresholds), compare against a high-quality reference with an objective metric (SSIM/PSNR/VMAF for video, WER for speech, precision/recall for classifiers) and look at real samples. Pick the knee of the curve and write the numbers next to the setting in code ("veryfast/crf 24: SSIM 0.992 vs reference, ~40% smaller and faster").

## 5. Guard what you gained
- A performance test or benchmark with a threshold in CI for the critical path; compare against the stored baseline and fail on regressions beyond noise.
- Dashboards and alerts on SLO burn; per-stage timing logs so regressions are visible in production.
- Keep the fast path correct: a shortcut (copy, cache, skip) needs a strict predicate, an integrity test (e.g. checksum equality of output), and a fallback to the slow path on any doubt.
- Document tunables (env var names, defaults, limits) next to the code and in the ops docs; parse them defensively (a typo must not stop the service).

## 6. Do not
Optimize without a profile; trust averages; benchmark on toy data; tune provider/vendor options you cannot test (a wrong option can break every call - say "not measured" and leave it); trade correctness or security for speed; leave an optimization that you could not prove safe.
