# Benchmarking Methodology

Reference guide for crafting statistically sound performance scenarios in this project. The setup is a single bare-metal Esprimo P956 (DVFS ON, Turbo Boost ON, HT ON) running XWiki in Docker containers, measured by the Green Metrics Tool. All guidance is calibrated to that context.

---

## 1. How Many Iterations Are Needed?

The goal is a phase duration and repetition count long enough that measurement noise is small relative to the signal.

### The practical threshold

Compute the **coefficient of variation** (CV = σ/μ) across repeated runs of the same scenario on the same version:

| CV | Interpretation |
|---|---|
| < 5% | Acceptable for most comparisons |
| 5–10% | Marginal; differences < 10% are unreliable |
| > 10% | Environment is too noisy; diagnose before drawing conclusions |

Research on serverless workloads found 125/132 experiments had CV < 5%, and 160/180 had CV < 10%. For detecting differences > 5% (the typical threshold in industry), the study "When Should I Run My Application Benchmark?" found that precise timing and run counts are "far less critical" — but for smaller differences, stricter protocols are necessary. [[source]](https://arxiv.org/html/2504.11826v1)

### Minimum run count

- **5 independent runs** per (version, scenario) is the practical floor for computing variance at all.
- **10+ runs** is the defensible threshold for release-gating decisions where sub-5% CV is required.
- Within a single run, **30+ iterations** allows the Central Limit Theorem to begin averaging out per-request noise.

### Minimum phase duration

Short phases are dominated by DVFS ramp-up transients (see §3). Targets:

| Phase type | Minimum | Comfortable |
|---|---|---|
| Active HTTP load (fast ops <50 ms) | 30 s | 60–120 s |
| Active HTTP load (slow ops >200 ms) | 30 s | 30–60 s |
| Idle / background | 120 s | 300 s |

The idle scenario in this project was extended from 60 s to 300 s for exactly this reason.

### Translating to iteration counts

`REPS = target_duration_s / expected_latency_s`

Examples for this project's machine (XWiki response times are estimates from the XWiki 16.10→17.10 perf report):

| Operation | Latency | REPS for ~30 s | REPS for ~60 s |
|---|---|---|---|
| `bin/get` Main.WebHome | ~24 ms | 1250 | 2500 |
| `bin/get` empty page | ~17 ms | 1750 | 3500 |
| `bin/get` {{id}} macros | ~26 ms | 1150 | 2300 |
| `bin/get` {{html}} macros | ~460 ms | 65 | 130 |
| `bin/get` non-existing page | ~200 ms | 150 | 300 |
| `bin/view` Search `text=*` | ~350 ms | 85 | 170 |
| Browser navigation (UI) | ~1–2 s | 15–30 | 30–60 |

The current scenario scripts use conservative lower counts (100–1000); pilot runs should be used to calibrate against actual cluster latencies before committing to final counts.

**Dumbbench** (used by XWiki's own test suite) takes a more principled approach: it starts with 20 iterations, uses **median absolute deviation** (MAD) rather than standard deviation to handle outliers robustly, and continues iterating until the relative uncertainty drops below a target (default 5%). It caps at 10,000 iterations. [[source]](https://metacpan.org/release/BDFOY/Dumbbench-0.505) The same adaptive logic could be implemented in Python if fixed REPS prove insufficient.

---

## 2. JVM Warm-Up

XWiki runs on a JVM. The first N requests after startup are structurally unrepresentative because:

1. **Bytecode interpretation**: the JVM initially interprets bytecode, which is ~10–100× slower than compiled native code.
2. **Tiered JIT compilation**: HotSpot compiles code in tiers. C1 (client) kicks in at ~1 500 invocations of a method; C2 (server) at ~10 000. Code paths exercised only infrequently may never be C2-compiled.
3. **Class loading**: classes are loaded lazily; first requests pay one-time loading costs.
4. **Caches**: XWiki's template cache, Velocity cache, Hibernate second-level cache, and Solr field cache are cold until the first access to each document.

**Consequence**: the first 10–100 requests to any page will be slower than steady-state. In a 50-iteration benchmark the first few dominate the average. In a 1000-iteration benchmark they contribute < 1%.

**JMH defaults for reference**: 5–10 warmup iterations (discarded) + 5–10 measurement iterations, run in 5 separate JVM forks. [[source]](https://howtodoinjava.com/java/library/jmh-java-microbenchmark-harness/)

**Mitigation in this project**: `wait_for_xwiki.sh` already makes HTTP requests before the `[RUNTIME]` phase starts (to verify readiness and wait for the Solr indexer), which partially warms JIT-compiled paths. For a more rigorous warm-up, add a dedicated hidden flow step that makes ~100 requests to the target URL before measurement begins. This is not yet implemented — it's a gap worth closing if JVM warm-up effects are suspected in cross-version comparisons.

Research by Kalibera & Jones ("Virtual Machine Warmup Blows Hot and Cold") shows that warmup behaviour is non-monotone and sometimes never stabilises — see [[paper]](https://arxiv.org/pdf/1602.00602) for the full picture. The practical takeaway: a larger repetition count (1000+) is more robust than trying to determine the "right" warmup cutoff.

---

## 3. DVFS and Turbo Boost Effects

The Esprimo P956 runs with **DVFS ON** and **Turbo Boost ON** — both are set by the cluster operator and cannot be changed per-measurement.

### What this means for energy readings

DVFS allows the CPU to change frequency (and voltage) dynamically based on load. Turbo Boost allows momentary bursts above the rated TDP clock. Both cause:

- **Ramp-up transients**: on the first 0.1–1 s of a new workload, the CPU escalates from a lower P-state to a higher one. The transient contributes disproportionately high energy to a short measurement window.
- **Thermal variation**: sustained Turbo depends on thermal headroom; back-to-back hot runs clock lower than cold runs.
- **Cross-run variance**: the Esprimo P956 with TB ON shows standard deviation of 0.04–0.77% for energy in green-coding.io's own tests — low in absolute terms but relevant when comparing differences of a few percent. [[source]](https://www.green-coding.io/case-studies/turbo-boost-and-energy/)

Green-coding.io found that TB ON can increase energy by 106–136% while reducing time by only 14–28%, depending on machine. Total system energy can be *higher* with TB ON due to auxiliary components continuing to run. For energy-efficiency comparisons, disabling TB would give more stable results — but since we cannot, we must compensate with measurement design.

### Mitigations (given we cannot disable DVFS/TB)

1. **Longer phases**: a 60 s active-load phase averages over ~60 DVFS transitions; a 1 s phase is almost entirely transient. Targeting 30–120 s active phases (see §1) is the primary mitigation.
2. **Multiple independent runs**: the GMT cluster already queues separate runs; running each (version, scenario) pair 5× and looking at the spread reveals DVFS-induced variance directly.
3. **Never compare single runs**: a single run difference of < 5–10% on DVFS hardware is within noise. Only consistent cross-run differences are meaningful.
4. **Baseline correction**: GMT measures `[BASELINE]` (idle machine) before `[RUNTIME]` in each run. The report subtracts the baseline extrapolated over runtime duration. This corrects for different idle power states but not for Turbo-induced variance during the load phase.

---

## 4. Micro-Benchmarks vs Macro-Benchmarks

This project uses both, and they answer different questions.

### Definitions

| Type | Definition | Examples in this project |
|---|---|---|
| **Micro-benchmark** | Isolated operation, fixed input, no think time | `render_home`, `render_id`, `reload_nopage`, `search_perf` |
| **Macro-benchmark** | End-to-end user journey, realistic pacing | `browse`, `edit`, `search`, `idle` |

### What each is good for

**Micro-benchmarks** are effective at detecting specific regressions in a single operation — "the XWiki rendering engine got 20% heavier in 12.x" is a micro-benchmark finding. They have low per-run variation and are cheap to run at high repetition counts. They are poor at detecting systemic effects (GC pressure, thread-pool starvation, cache eviction under realistic load) because those emerge from workload mix. [[source]](https://arxiv.org/pdf/2311.04108)

**Macro-benchmarks** capture the production impact of a change — including second-order effects invisible to micro-benchmarks. They have higher run-to-run variance because user-journey timing, tour dismissal, and browser rendering all vary. They're the right tool for answering "is XWiki 12.x heavier to *use* than 11.x?"

**Pitfall**: micro-benchmark results can mislead. AppFolio's engineering blog notes that microbenchmarks show "chaotic results across versions — leaping forward when optimizations hit, then stalling" — making them poor for communicating trends without statistical aggregation. [[source]](https://engineering.appfolio.com/appfolio-engineering/2019/1/7/microbenchmarks-vs-macrobenchmarks-ie-whats-a-microbenchmark)

**Best practice**: use micro-benchmarks to confirm a hypothesis identified in macro-benchmarks, not as the primary signal.

---

## 5. Common Pitfalls in Containerised Environments

### OS noise

The OS scheduler, IRQ handling, and background daemons introduce jitter of 1–5% for typical server workloads. Mitigations: CPU pinning (not available in Docker without privileged mode), disabling unnecessary services, and — most practically — running enough iterations that jitter averages out.

### Container network overhead

Docker bridge networking (used in this project's container stack) adds 5–15% latency overhead vs. host networking. This is constant across versions and cancels out in cross-version comparisons, but it means that absolute latency figures from `debug_stack.sh` runs are lower than cluster measurements where the same bridge network is used consistently.

### Thermal bias

Back-to-back runs of the same version will run at lower Turbo clocks than the first run, because the CPU is thermally saturated. The GMT cluster queues jobs with some idle time between runs, mitigating this. For local `debug_stack.sh` runs back-to-back, add a 60 s cool-down between runs.

### Background processes during measurement

Solr indexing after seed restore is the primary known source of background noise in this project. `wait_for_xwiki.sh` gates the start of `[RUNTIME]` on a zero Solr queue size, eliminating this. The `--repair` flow exists to fix seeds where the seed Solr index is stale.

Other background tasks that can fire during measurement: Tomcat session expiration (every 30 min by default), XWiki scheduled jobs (daily maintenance, notification aggregation). These are unlikely to fire during a typical 30–120 s scenario but are a confound for idle scenarios. XWiki's Activity Stream job fires on a configurable schedule; seeds generated by `provision_version.sh` should be checked to confirm no scheduled job fires within the measurement window.

### Single-run conclusions

The single most common pitfall: reporting a result from N=1 as if it were established. On DVFS hardware, N=1 differences below 10% are not credible. See §1 for run count recommendations.

---

## 6. Tool Reference

| Tool | Language | Primary use | Key parameter |
|---|---|---|---|
| **Green Metrics Tool** | Python/Docker | Energy/carbon of containerised workflows | `[BASELINE]` + `[RUNTIME]` phases, RAPL + PSU meter |
| **JMH** | Java | JVM micro-benchmarks | `@Warmup(iterations=10)`, `@Measurement(iterations=10)`, `@Fork(5)` |
| **Dumbbench** | Perl | Statistical CLI benchmarking | `target_relative_precision=0.05`, MAD-based stopping |
| **wrk / wrk2** | C | HTTP throughput load testing | `wrk2` uses HDR histogram for latency percentiles |
| **Gatling** | Scala/DSL | Load scenario scripting with reports | Suitable for multi-user macro-benchmarks |
| **Playwright** | Python/JS | Browser automation for UI scenarios | Used in this project for macro-benchmarks |

### Academic references

- Kalibera & Jones, **"Virtual Machine Warmup Blows Hot and Cold"** (2017) — definitive study on JVM warmup non-monotonicity. [[arxiv]](https://arxiv.org/pdf/1602.00602)
- Hoffmann & Majuntke, **"Green Metrics Tool: Measuring for fun and profit"** (2025) — GMT's own methodology paper. [[arxiv]](https://arxiv.org/pdf/2506.23967)
- **"When Should I Run My Application Benchmark?"** (2025) — time-of-day and periodicity effects on web benchmarks. [[arxiv]](https://arxiv.org/html/2504.11826v1)
- **"The Early Microbenchmark Catches the Bug"** (2023) — micro vs macro benchmark effectiveness for detecting regressions. [[arxiv]](https://arxiv.org/pdf/2311.04108)
- green-coding.io, **"Turbo Boost and energy"** — quantitative DVFS/TB effects on energy measurements. [[case study]](https://www.green-coding.io/case-studies/turbo-boost-and-energy/)
- XWiki performance test template — the methodology this project's benchmark scenarios mirror: [[test.xwiki.org]](https://test.xwiki.org/xwiki/bin/view/Performances/Template)
