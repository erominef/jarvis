# Hardware Benchmarks

## The Fundamental Constraint

Token generation speed for CPU inference is determined by:

```
tok/s ≈ DRAM_bandwidth / model_size_in_VRAM
```

This is physics. The GPU runs a weight through compute once per forward pass — the bottleneck is how fast you can move those weights from memory into the compute units. Software optimizations (flash attention, thread tuning, quantization) help at the margins, but the ceiling is set by your memory bus.

---

## Ubuntu PC (i7-6700, Skylake)

- **Memory:** DDR4-2133, dual channel ~25 GB/s bandwidth
- **CPU:** 4 cores / 8 threads, AVX2 + FMA instructions
- **RAM:** 16 GB total, ~15 GB available for models

| Model | Size (Q4) | tok/s | Notes |
|-------|-----------|-------|-------|
| qwen3:0.6b | ~0.5 GB | 26–30 | Fastest useful model |
| qwen3:4b | ~2.3 GB | 12–14 | Best quality/speed tradeoff |
| qwen2.5:7b | ~4.1 GB | 5–6 | Best tool use |
| llama3.2 (3B) | 2.02 GB | 12–14 | Legacy, replaced by qwen3 |
| llama3.1:8b | 4.92 GB | 5–5.5 | Legacy, replaced by qwen2.5:7b |

AVX2 + FMA gives meaningful speedup over SSE4.2-only CPUs for matrix multiply operations.

---

## Xeon (2× X5670, Westmere)

- **Memory:** DDR3-1333, 6-channel per socket ~38 GB/s theoretical, ~30 GB/s effective
- **CPU:** 24 threads (2×6 cores + HT), SSE4.2 only (no AVX)
- **RAM:** 64 GB — can run 32B+ models

| Model | Size (Q4) | tok/s | Notes |
|-------|-----------|-------|-------|
| qwen3:14b | ~8.2 GB | 2.4–2.6 | Primary reasoning model |
| deepseek-r1:7b | ~4.4 GB | 2.8–3.0 | Chain-of-thought, thinking tokens add latency |
| deepseek-r1:14b | ~8.2 GB | 1.4–1.6 | Max reasoning |
| qwen3:4b | ~2.3 GB | ~5 | Fallback for PC-down |

**No AVX** means the Xeon is slower per-thread than the PC despite more threads and faster memory bus. The 64 GB RAM is the Xeon's actual advantage — it can run models that don't fit on the PC.

**NUMA interleaving:** `numactl --interleave=all` is set in Ollama's systemd unit. On a dual-socket Xeon, memory is split across two NUMA nodes. Without interleaving, models that span both nodes get inconsistent latency.

---

## Why the Old System Felt Faster

The previous system used phi3:mini (15.4 tok/s on Xeon due to GQA architecture) and tinydolphin (1B, ~20 tok/s) as defaults. Raw token throughput was higher, but response quality was lower.

The qwen3 models traded ~2–3 tok/s for significantly better instruction following and tool call accuracy. For an agent that's executing actions and calling tools, correctness matters more than raw speed.

---

## Optimization History

| Optimization | Effect |
|-------------|--------|
| `OLLAMA_MAX_LOADED_MODELS=3` | Eliminated model swap penalty between messages |
| `OLLAMA_FLASH_ATTENTION=1` | ~5–10% throughput improvement on longer contexts |
| `OLLAMA_NUM_THREADS=8` (PC) | Matches physical core count (4C/8T) — diminishing returns above this |
| CPU governor `performance` | Eliminated frequency scaling latency on first token |
| `numactl --interleave=all` (Xeon) | Consistent latency vs. sporadic slowdowns |
| Keep-warm heartbeat cron | First token in ~1s vs. 3–5s cold load |

What was tried and didn't help:
- **Intel HD 530 Vulkan (PC GPU):** Loads correctly, crashes mid-inference with `vk::DeviceLostError`. Disabled permanently.
- **Increasing threads above 8 on PC:** Hyperthreading cores contend on shared L1/L2 cache — no speedup.
- **Model quantization below Q4:** Quality degradation not worth the ~10% speed gain at this scale.
