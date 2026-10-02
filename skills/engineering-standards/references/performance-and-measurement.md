# Performance and measurement

## Principle
Optimize what the profile shows, on real data, and prove the result did not cost quality or reliability. In the reference project the biggest win (2 videos at once, picture copy instead of re-encode) came from reading a timing breakdown; several plausible ideas were measured and *dropped* (filter graph variants, extra threads, a fancy loudness gate), and one "speedup" (adaptive waits on a flaky site) was withdrawn because it could not be shown safe.

## Procedure
1. **Break the end-to-end time into stages** with a small harness that times each stage on real inputs (here: probe, hash, fingerprint, proxy encode, remote model call, render, QC). Keep the harness in scratch or `tools/`.
2. **Find what dominates and what waits.** If most of a unit's time is waiting on a remote call, run units concurrently (bounded: 2 by default, env-configurable, 1 restores old behaviour) rather than micro-optimizing the CPU part.
3. **Skip work that adds nothing.** If an input already is the output (a portrait H.264 clip that would be re-encoded to the same format), copy it: faster and lossless. Guard the shortcut with a strict predicate (codec, size, rotation/flip/display matrix, frame rate, bitrate) and an integrity test (checksum of decoded frames equal).
4. **Match inputs to what the consumer uses.** A model that samples 1 frame/second gains nothing from a 2 fps upload; cut it.
5. **Quality knobs need a reference.** Compare encodes against a very-high-quality reference using objective metrics (SSIM/PSNR) and size/time; pick the knee (veryfast/crf 24: SSIM 0.992 vs reference, ~40% smaller and faster). Check by eye on a real frame too.
6. **Replace fixed sleeps with adaptive waits only where measured counts are unchanged**, never where the third party is flaky. Put per-step timing in the log so the effect is visible later.
7. **Concurrency changes need a race review.** Anything that checks-then-writes across concurrent workers (duplicate detection, quotas, claims) must be one transaction. Add a test that fails when the window reopens.
8. **Record before/after in a table** in the roadmap with the conditions (machine, load, input), plus the experiments that did not help.

## Measuring honestly
- Take the "before" numbers first; same input, same machine state. Note load average.
- One run is an anecdote: repeat, report the range, and say when variance exceeds the effect.
- Do not benchmark against a rate-limiting third party repeatedly; interleave A/B and stop when results turn erratic (0 to 98 items on identical code is the site, not the code).
- Do not tune unverifiable things (provider options you cannot test because the API is down). A wrong option can break every call. Say "not measured" and leave it.
- Distinguish facts you measured, facts you inferred, and facts you assume, in code comments and docs ("measured on 520 live videos on 2026-10-01; raw data not kept").

## Typical wins (check each against your own profile; do not apply blindly)
bounded parallelism over remote waits; copy instead of re-encode when output == input; smaller/cheaper inputs for model calls; skip redundant passes (do integrity check and loudness measurement in the same decode); cache per-request settings reads; avoid N+1 queries; batch writes in one transaction; make timeouts proportional to the work (a per-account browser launch needs a timeout that scales with the number of accounts).
