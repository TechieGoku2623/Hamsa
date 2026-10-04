# Hamsa — Phase 0 Research Memo

Status: **for approval** · Date: 4 Oct 2026 · Scope: model selection, serving, speech/vision/retrieval components, platform components, cost model, compliance, risks.

Every version, licence and price below was checked against a primary source (model card, release page, gazette, or rate card) on or shortly before the date above. Two pieces of evidence were **measured by us** rather than quoted:

- Tokenizer fertility on all 22 scheduled languages, native and romanized script, plus a parallel code-mixed business-chat probe — `research/phase0/tokenizer_fertility/` (reproducible script + raw JSON).
- A parametric unit-economics model per plan — `research/phase0/cost_model/` (every hypothesis is a named field, re-runnable).

---

## 1. Executive summary

1. **₹99/month is economically viable** if (a) we own the chat channel instead of reselling WhatsApp, (b) ~50% of customer messages are resolved without an LLM, and (c) the large-model fallback stays at ≤3% of messages. Modelled gross margin on the ₹99 plan is 73% at typical usage and 58% at full allowance; all-in variable cost is ~₹0.06 per AI-handled conversation. At the ₹99 tier the real cost drivers are support/onboarding and payment collection, not GPUs.
2. **WhatsApp cannot be the default channel at these prices.** From 1 Oct 2026 Meta charges ₹0.115 per service reply in India after 1,000 free per number per month. A ₹299 tenant at typical usage would incur ≈₹299/month in WhatsApp fees alone. Hamsa's default channel must be its own zero-install chat link/PWA; WhatsApp is an optional pass-through add-on billed at cost.
3. **Tokenizer choice is a 2× cost lever on native-script Indic text and almost irrelevant for romanized text.** Measured mean native-script fertility: Sarvam 2.34, Gemma 4 3.18, gpt-oss 4.05, Qwen3.5 4.80 tokens/word. Romanized fertility is ≈2.6–2.9 for every modern tokenizer.
4. **Sarvam's tokenizer is a Gemma-family vocabulary with ~23k slots reassigned to Indic scripts** (we measured 91% vocabulary overlap with Gemma 4, 233k tokens at identical IDs). This makes "Gemma 4 base + Sarvam-style Indic vocab surgery" a cheap, low-risk path for Hamsa-LM.
5. **Recommended model plan (two tracks):**
   - *Hamsa-LM v0 (Phases 3–4):* serve **Sarvam-30B** (Apache-2.0, MoE 30B total / 2.4B active, native Indic + romanized + code-mixed, tool calling) on FP8 as the production model. It breaks the 3–8B guideline on *total* parameters, but its compute per token is that of a 2.4B model and it has the best Indic tokenizer we measured.
   - *Hamsa-LM v1 (Phase 5 student):* distil into a **Gemma 4 E4B** student with Indic vocabulary extension (primary) and **Qwen3.5-4B** (control; stronger agentic scores, 2× worse native-script tokenizer). Pick by quality-per-₹ on Hamsa-Bench.
6. **Licence traps found** (these change the stack the brief proposed): ScyllaDB is no longer open source (use Apache Cassandra 5); MinIO Community is archived (use SeaweedFS); Redis 8 is AGPL/RSAL/SSPL (use Valkey 9, BSD); Redpanda is BSL (use NATS JetStream for the backbone, Kafka-API only if needed); Surya OCR weights are revenue-capped and forbid competing use (exclude); Sarvam-1 is non-commercial (exclude); Kimi K3 has attribution clauses (avoid as a teacher).
7. **Compliance dates that shape the roadmap:** DPDP Rules notified 13 Nov 2025 — Consent Manager rules live 13 Nov 2026, bulk of obligations live **13 May 2027**. UPI MDR stays zero for P2M ≤ ₹2,000 and for small P2PM merchants; 0.4% above ₹2,000 from 15 Oct 2026. TRAI's Sept 2026 TCCCPR amendment hits our SMS/PSTN legs. Hamsa must not hold merchant funds (avoid needing an RBI Payment Aggregator licence).

**Decisions requested** are listed in §12.

---

## 2. Hamsa-LM: base model selection

### 2.1 Candidates (verified Oct 2026)

| Model | Released | Params | Licence | Indic support (vendor claim) | Notes |
|---|---|---|---|---|---|
| **Sarvam-30B** (`sarvamai/sarvam-30b`, also published as `sarvam2-30b`) | Mar 2026 | 30B MoE, 2.4B active, 128 experts, GQA, 64K ctx | Apache-2.0 | 22 scheduled langs in card; vendor says best in 10 + EN, native/romanized/code-mixed | Built for voice agents & tool calls (powers Samvaad). vLLM support landed (Transformers v5 compat in vLLM changelog); SGLang day-0. |
| **Sarvam-105B** | Mar 2026 | 105B MoE, 10.3B active, MLA | Apache-2.0 | 22 langs | Teacher / large fallback candidate. Vendor: Tau2 avg 68.3. |
| **Gemma 4 E4B / E2B** | Apr 2026 | 4.5B eff. (8B w/ embeddings) / 2.3B eff. | Apache-2.0 (first Gemma under Apache) | 140+ languages | Text+image+audio input; 128K ctx; ships MTP/assistant drafts for speculative decoding; QAT checkpoints. |
| **Gemma 4 12B / 26B-A4B / 31B** | Apr 2026 | | Apache-2.0 | | 26B-A4B is a strong cheap MoE alternative to Sarvam-30B. |
| **Qwen3.5-4B / 9B / 2B / 0.8B** | Mar 2026 | dense, Gated DeltaNet hybrid (3:1 linear:full attention), MTP | Apache-2.0 | 201 languages | Best agentic scores in class (Qwen3.5-4B TAU2 79.9 vs Gemma 4 E4B 42.2). Natively multimodal. Hybrid attention = LoRA edge cases in vLLM (partial LoRA fixes in v0.29). |
| Qwen3.6 / 3.8 (27B, 35B-A3B …) | Apr–Aug 2026 | | Apache-2.0 | | Larger; teacher/fallback candidates. Qwen4 announced as "in training" (22 Sep 2026), no date. |
| DeepSeek V4 Flash / Pro | Apr 2026 | 284B-A13B / 1.6T-A49B | MIT | general multilingual | Teacher candidate; 1M ctx. |
| GLM-5.2 | 2026 | | MIT (weights) | | Teacher candidate. |
| Kimi K3 | Jul 2026 | 2.8T | Custom: attribution required above 100M MAU or $20M monthly revenue | | Avoid as teacher (derivative-work attribution). |
| Krutrim-2 | 2025 | 12B (Mistral-NeMo) | Krutrim Community Licence | 10 Indic | Custom licence; tokenizer = Mistral Tekken (poor Odia). |
| Sarvam-1 | 2024 | 2B | **Non-commercial** | 10 Indic | Excluded. |
| BharatGen Param-1 | 2025 | 2.9B, EN+HI | card metadata Apache-2.0, README says MIT | Hindi only | Too narrow. |
| Llama 3.x / 4 | | | Llama community licence, gated | | Excluded: gated, custom licence, worst Indic tokenizers in published comparisons. |

### 2.2 Tokenizer fertility — measured

Method: tokens per whitespace word, special tokens excluded, up to 400 sentences per language/script/form from AI4Bharat *Bhasha-Abhijnaanam* (all 22 scheduled languages, native script; romanized where available). Separately, a 12-intent × 11-variant parallel business-chat probe (orders, bookings, complaints, discounts, UPI confirmation, refunds) in English, Hindi (Devanagari, romanized Hinglish, mixed-script), Tamil/Tanglish, Bengali/Benglish, Telugu/Tenglish, Marathi, Kannada. Full tables: `research/phase0/tokenizer_fertility/results/RESULTS.md`.

| tokenizer | vocab | native fertility (mean of 24 lang/script pairs) | worst | romanized fertility | probe: Indic tokens/msg (EN ≈ 15) |
|---|---:|---:|---|---:|---:|
| indictok-256k (reference, no model) | 256,000 | 2.01 | 3.03 Santali | 3.08 | 15.7 |
| **Sarvam-30B / 105B** (identical) | 262,144 | **2.34** | 3.53 Manipuri-Bengali | 2.62 | **16.4** |
| **Gemma 4** | 262,144 | 3.18 | 12.36 Meetei Mayek | 2.62 | 17.2 |
| gpt-oss / Phi-4-mini (o200k) | 200k | 4.05 | 16.39 Meetei Mayek | 2.62 | 18.9 |
| Sarvam-1 | 68,096 | 4.54 | 17.36 | 3.55 | 19.4 |
| **Qwen3.5** | 248,070 | 4.80 | 16.39 | 2.80 | 24.1 |
| DeepSeek V4 | 129,280 | 4.96 | 11.88 | 2.86 | 27.1 |
| Ministral 3 / Krutrim-2 (Tekken) | 131,072 | 5.03 | 18.24 Odia | 2.86 | 22.7 |
| LFM2 | 64,400 | 12.19 | 27.53 Malayalam | 3.02 | 65.3 |

What this means for Hamsa:

- **Native-script cost.** On Tamil, Telugu and Kannada business messages Qwen3.5 uses 2.1–2.4× the English token count; Sarvam uses 1.2–1.3×; Gemma 4 sits between (1.3–1.6×). Since output tokens dominate latency, this is also a latency lever.
- **Romanized and mixed-script text is cheap everywhere.** Hinglish/Tanglish/Benglish/Tenglish cost 1.0–1.25× English on all modern tokenizers. A large share of Indian chat is romanized, so the tokenizer gap in production will be smaller than the native-script numbers suggest — we will measure the real script mix in Phase 2 traffic.
- **Long-tail scripts.** Only Sarvam handles Meetei Mayek (Manipuri) and Ol Chiki (Santali) well; Gemma 4 is 5–12 tokens/word there. Gemma 4 also lags Sarvam on Odia, Gujarati, Punjabi, Kannada, Telugu and Malayalam.
- **Lineage finding.** Sarvam's vocabulary shares 239,301 of 262,144 entries with Gemma 4, 233,116 at the same ID. The ~23k Sarvam-only tokens are almost all Odia, Kannada, Gurmukhi, Malayalam, Telugu, Meetei, Gujarati, Ol Chiki and Tibetan; the Gemma-only tokens are Hangul, Kana, Thai, CJK, Cuneiform, Khmer, Ethiopic. So Indic vocab extension of a Gemma 4 student is a *replacement of ~9% of rows*, not a new tokenizer: reinitialise those embeddings (mean of sub-token embeddings), then continue pre-training on Indic text. This is the main technical reason Gemma 4 is the primary student.
- **Caveat.** Fertility does not predict downstream quality (Ali et al. 2023; also noted by the indictok authors). It predicts cost. Quality comes from §2.3.

### 2.3 Indic quality evidence and its gaps

- Published Indic benchmarks (MILU, IndicGenBench, IN22) **have no results for the 2026 small models** (Gemma 4 E4B, Qwen3.5-4B). Vendor cards report only generic multilingual suites (MMMLU: Gemma 4 E4B 76.6 vs Qwen3.5-4B 76.1).
- Sarvam reports a pairwise LLM-as-judge Indic benchmark (110 prompts × 22 languages × native/romanized), win rates ~89–90% for 30B/105B — vendor-run, judge-based, not independent.
- No public benchmark covers *business-dialogue, code-mixed, tool-calling* behaviour, which is what Hamsa needs.

Therefore **Phase 0.5 deliverable (before Phase 3 model lock): Hamsa-Bench v0** — ~2,000 human-verified items across 7 verticals × 10 language/script variants, scoring tool-call exactness, JSON-schema validity, price arithmetic, reply language/script match, faithfulness to catalog, and escalation correctness. Run zero-shot on Sarvam-30B, Gemma 4 E4B/26B-A4B, Qwen3.5-4B/9B, plus one frontier model as a ceiling. Budget: a few GPU-days on L40S plus annotator time.

### 2.4 Recommendation

| Role | Choice | Why | Alternatives kept warm |
|---|---|---|---|
| Production LLM, Phases 3–4 (Hamsa-LM v0) | **Sarvam-30B, FP8**, per-tenant prefix caching, per-vertical LoRA | Best Indic tokenizer + strong Indic chat + tool calling, Apache-2.0, 2.4B active params → small-model compute | Gemma 4 26B-A4B; Qwen3.5-9B |
| Distilled student, Phase 5 (Hamsa-LM v1) | **Gemma 4 E4B + Indic vocab surgery** | Apache-2.0, multimodal incl. audio, MTP drafts, tokenizer lineage shared with Sarvam, small enough for single-L4/L40S serving and owner-device experiments | **Qwen3.5-4B** as control arm (better agentic, worse tokenizer) |
| Teachers for synthetic data | **Sarvam-105B** (Indic), **DeepSeek V4** (MIT), **Qwen3.5-397B / Qwen3.8** (Apache), **GLM-5.2** (MIT) | Permissive licences explicitly allow derivative training | — |
| Large fallback at runtime | Self-hosted Sarvam-105B, or a hosted open MoE | See §9: the 3% fallback is about half of model cost; self-hosting it matters | Frontier API (judge/eval only) |

**Do not train on closed frontier API outputs** without legal review: most closed providers' terms prohibit using outputs to develop competing models. Use them only as evaluation judges (calibrated against human labels), and keep the training corpus traceable to permissively licensed teachers.

### 2.5 Post-training stack

- **TRL v1.0** (stable SFT, DPO, GRPO incl. Dr. GRPO/DAPO/GSPO variants, custom and async reward functions) as the default trainer; **Unsloth** for single-GPU LoRA/GRPO iteration; **verl** for multi-node or multi-turn agentic RL. vLLM is the rollout engine for all three.
- Verifiable rewards map directly to Hamsa's domain: JSON-schema validity, tool name + argument exact match, catalog price/stock lookup, total = Σ(qty × price) − discount ≤ cap, reply-script detector (Unicode block + IndicLID), language match. These are cheap deterministic checks, which is why RLVR fits better here than learned reward models.
- Sarvam's own report (async GRPO, no KL term, CISPO-style objective) is a useful reference recipe at scale; for a 4B student we start conservative (KL-regularised GRPO, small group sizes).

---

## 3. Hamsa-Edge (on-device)

- **Runtime:** Transformers.js **4.3.0** (v4 released Feb 2026, C++ WebGPU runtime shared with ONNX Runtime) depending on `onnxruntime-web 1.31.0-dev`; pin the exact ORT version Transformers.js expects, otherwise the WebGPU backend fails to load. WASM fallback for devices without WebGPU.
- **Budget reality:** target customers include low-end Android phones on prepaid data. Initial edge bundle ≤ 15 MB, lazily loaded after first message, cached in the Cache Storage API. That rules out generative LLMs on the customer side; Qwen3.5-0.8B (~1.6 GB BF16, ~0.5 GB INT4) and Gemma 4 E2B are owner-app-only experiments on capable devices.
- **Customer-side models (encoders, INT8):** language/script ID (IndicLID-style, fastText or small transformer), transliteration normalisation (IndicXlit-style seq2seq, or rule-based for the top 5 scripts), intent + FAQ matcher (a distilled 20–60M multilingual encoder, starting from MuRIL (Apache-2.0) or IndicBERT v2 (MIT)), PII masking (regex for phone/Aadhaar/PAN/card + a tiny NER).
- **Metric:** `% messages resolved on-device` and `% messages pre-processed on-device` are first-class product metrics from Phase 6; the cost model assumes 20% resolved on-device.
- **Federated learning:** deferred. The gain over server-side training on consented, PII-scrubbed data is small at our scale, and secure aggregation + DP add real complexity. Revisit after Phase 9 with an explicit privacy case.

---

## 4. Serving and inference efficiency

| Concern | Choice (verified version) | Rationale |
|---|---|---|
| Engine | **vLLM v0.29.0** (9 Sep 2026), primary | Mature multi-LoRA incl. MoE LoRA and mixed 2D/3D adapters; FP8 weights + KV; speculative decoding (EAGLE-3, MTP, draft model, n-gram/suffix, DFlash); structured outputs; Gemma 4 MTP under CUDA graphs; Sarvam support. |
| Contender | **SGLang v0.5.18** (22 Aug 2026) | RadixAttention prefix sharing suits thousands of tenants with shared vertical prompts; had day-0 Sarvam support. Bake-off in Phase 3 on our traces. |
| Quantisation | FP8 (W8A8) on L40S/H100 as default; AWQ/GPTQ INT4 for memory-bound multi-LoRA hosts; NVFP4 when Blackwell capacity is affordable in India | L40S (Ada) supports FP8 natively and is the cheapest Indian inference GPU (₹45–102/h). |
| Speculative decoding | MTP heads (Qwen3.5 native; Gemma 4 ships assistant/MTP drafts); EAGLE-3 trained on our dialogues for Sarvam-30B; suffix decoding for templated replies | Validate LoRA + spec-decode composition per model: vLLM fixed LoRA+spec for V1 but has had TP/CUDA-graph edge cases. |
| Prefix caching | Per-tenant system prompt + catalog digest as a stable prefix; vertical prompt as a shared outer prefix | Cost model assumes 1,600 of 2,600 prompt tokens cached; turning caching off costs ~6 margin points on the ₹99 plan. |
| Constrained decoding | JSON-schema / grammar for every tool call and order object | Also a reward signal in RLVR. |
| Cascade router | Edge → intent + template → semantic cache (Valkey) → Hamsa-LM → large fallback | v0: rules + logistic regression on (intent confidence, retrieval score, tool needed, language, tenant tier). v1: classifier trained on cost-vs-quality labels from shadow runs where both tiers answer. |
| Pools | Latency pool (on-demand L40S/H100, India regions) and batch pool (spot/preemptible for synthetic data, evals, embeddings) | KEDA scaling on queue depth and vLLM waiting-requests metric. |

Targets to report from Phase 3 onwards: p50/p95 time-to-first-token and full-reply latency per tier, ₹ per conversation, % LLM-free resolutions, fallback rate.

---

## 5. Speech

| Component | Candidates (licence) | Recommendation |
|---|---|---|
| Streaming ASR | **SraVaani-0.5-live** (ARTPARK-IISc, MIT, gated): cache-aware FastConformer-CTC, 63 Indian languages/dialects incl. 19+ scheduled, code-switch BPE, real-time on CPU; **IndicConformer-600M** (AI4Bharat, MIT, gated): 22 languages, CTC/RNNT, not natively streaming; Sarvam Saaras v4 (API only; codemix/translit modes; 8 kHz telephony) | Start with SraVaani-live for streaming + IndicConformer for offline voice notes; fine-tune on noisy shop/telephony audio. Saaras v4 as quality benchmark and burst fallback. |
| TTS | **IndicF5** (MIT, 11 languages, reference-audio prompting, explicit "consented cloning only" term); **Indic Parler-TTS** (Apache-2.0, gated, ~0.9B, 18 languages incl. English, description-controlled voices); Sarvam Bulbul v3 (API only) | Parler for default voices (controllable, no cloning); IndicF5 only for the *consented* owner-voice feature with watermarking. Both need streaming adaptation and latency work. |
| Speech-to-speech | **Human-1** (JoshTalks, CC-BY-4.0, Moshi 7B adapted to Hindi, 26k h of real conversations; research quality); Roxi-Duplex (Moshi LoRA, Indian English, proof of concept) | Research track only (Hindi premium tier). Cascaded for all tiers in Phase 7. |
| Turn detection / VAD | Silero VAD; LiveKit Turn Detector v1-mini (open weights, LiveKit model licence, 14 languages — Indic coverage to verify); Pipecat smart-turn (BSD, English only) | Train our own Indic end-of-utterance model on Phase 7 data; it is a known gap. |
| Real-time transport + SIP | LiveKit server + Agents 1.6.1 + LiveKit SIP | Open-source, WebRTC SFU, built-in SIP; aligns with Rust/Python split. |

Latency budget for < 800 ms turn latency (cascaded): end-of-utterance 150–250 ms, ASR finalisation ≤ 100 ms, LLM time-to-first-token ≤ 200 ms (cached prefix, FP8), TTS first audio chunk ≤ 150 ms, network/jitter ≤ 100 ms. A public self-hosted cascade measured 0.7–1.2 s using hosted APIs; hitting < 800 ms requires co-locating all three models in one Indian zone and streaming at every stage. Sub-500 ms requires speech-to-speech.

Low bandwidth: Opus at 12–16 kbps wideband with in-band FEC and DTX; fall back to push-to-talk voice notes (Opus in Ogg) when RTT or loss exceeds a threshold.

Telephony regulation: Indian rules restrict interconnecting internet telephony with the PSTN without the right licence. Use a licensed Indian CPaaS/DID provider for PSTN legs; outbound commercial calls fall under TRAI TCCCPR (DLT registration, 140/160-series rules, Sept 2026 amendment). Get operator quotes; the cost model's ₹0.40/min PSTN figure is a placeholder.

---

## 6. Knowledge and vision

**Embeddings and retrieval**

- Online: **Qwen3-Embedding-0.6B** (Apache-2.0, 1024-d, Matryoshka, instruction-aware) for cost; offline/quality: **Qwen3-Embedding-8B** or **LingoIITGN/qwen-indic-v1** (Apache-2.0, LoRA-tuned 8B for 22 Indic languages, 73.8 on MTEB-Indic). **BGE-M3** (MIT) as an alternative that also gives sparse vectors.
- Reranker: **Qwen3-Reranker-0.6B** (Apache-2.0), which outperforms BGE-reranker-v2-m3 on multilingual retrieval in Qwen's tables.
- Store: PostgreSQL 18 + **pgvector 0.8.4** (30 Jun 2026). BM25: ParadeDB **pg_search 0.26.0** (AGPL-3.0 — fine for unmodified internal use; legal sign-off needed) or Postgres FTS with custom Indic dictionaries. Indic BM25 quality depends on tokenisation and transliteration normalisation; romanized queries must be matched to native-script catalog entries (store both forms).
- Code-mixed query rewriting: a small Hamsa-LM call producing `{native_script, romanized, english}` variants, cached per query string.

**Vision (photo → catalog)**

- Evidence: on real Devanagari scans, open Qwen3-VL-8B scored chrF++ 75.2 versus 58.5 for GPT-5.5, and olmOCR-7B fell to 40.5 (arXiv 2606.29213). English OCR benchmarks don't predict Indic OCR.
- Sarvam's Indic OCR bench (6,909 samples, 22 languages) puts Sarvam Vision 2.1 first (87.39); open Gemma 4 and Surya 2 trail.
- **Excluded:** Surya OCR 2 weights (modified OpenRAIL-M: no free commercial use above $2M revenue/funding — some pages say $5M — and no competing products). Chitrapathak-1 uses the Krutrim licence (review needed).
- **Recommendation:** Qwen3.5-4B/9B or Gemma 4 (both Apache-2.0, natively multimodal) fine-tuned for *menu / shelf / price board / handwritten bill → JSON catalog rows* with per-field confidence. Low-confidence fields go to the owner's review queue; corrections become training data. Handwriting baseline: SemiHastakshar (IIIT-H) research results (Tamil CER 1.43%) indicate what's achievable with semi-supervised training.

---

## 7. Platform components (licence-checked)

| Brief proposed | Recommendation | Reason |
|---|---|---|
| ScyllaDB or Cassandra | **Apache Cassandra 5.0** (Apache-2.0) for message history | ScyllaDB moved to a source-available licence from 2025.1; the last AGPL release is 6.2.x; the free tier is capped by cluster size. |
| Redis | **Valkey 9** (BSD-3) | Redis 8 is RSALv2/SSPLv1/AGPLv3; Valkey is the permissive default and what major clouds now ship. |
| MinIO / S3 | **SeaweedFS** (Apache-2.0); S3 on a sovereign Indian cloud where managed | MinIO Community entered maintenance mode Dec 2025 and was archived Apr 2026. |
| NATS JetStream or Redpanda | **NATS JetStream** (Apache-2.0) for the real-time backbone; Kafka-API (Apache Kafka) only for the analytics firehose if needed | Redpanda Community is BSL 1.1 and restricts offering it as a service; NATS also handles request/reply and presence fan-out well. |
| ClickHouse | ClickHouse (Apache-2.0) | — |
| Temporal | **Temporal** (MIT); Python SDK ≥ 1.27 with the **LangGraph plugin** (public preview, Jul 2026; Python 3.11+) | Lets LangGraph graphs run as durable workflows (cart recovery, payment reminders). |
| LangGraph | **LangGraph v1.2.0** (node timeouts, error recovery, graceful shutdown) | — |
| MCP | **MCP spec 2026-07-28** | Stateless request/response core (no `initialize` handshake or session header) → any request can hit any server replica; this simplifies multi-tenant MCP gateways. Tier-1 SDKs: TS, Python, Go, C#; Rust SDK supports it. Avoid deprecated HTTP+SSE transport and Dynamic Client Registration. |
| OpenMLS | **OpenMLS 0.9.0** (25 Aug 2026), RFC 9420 | Pin ≥ 0.8.1/0.7.4 for the Feb 2026 dependency security fixes. |
| Postgres + pgvector | PostgreSQL 18, pgvector 0.8.4 | — |

The Rust real-time gateway, FastAPI services, Kubernetes/GitOps, OpenTelemetry, Prometheus/Grafana and Langfuse choices from the brief stand; their versions are pinned in Phase 1.

---

## 8. Security, privacy, compliance

**DPDP Act 2023 + DPDP Rules 2025** (notified 13 Nov 2025):

| Date | What becomes binding |
|---|---|
| 13 Nov 2025 | Rules 1, 2, 17–21 (definitions, Data Protection Board) |
| 13 Nov 2026 | Rule 4 — Consent Manager registration and obligations (India-incorporated companies; 7-year consent records) |
| 13 May 2027 | Rules 3, 5–16, 22, 23 — notice, security safeguards, breach intimation (without delay + detailed report within 72 h), retention/erasure, children's data, Significant Data Fiduciary duties, data principal rights, cross-border transfers |

Role mapping: for end-customer chats the **business is the Data Fiduciary and Hamsa is its Data Processor**; for owner accounts and cross-tenant analytics Hamsa is a Fiduciary. Product consequences: per-business consent notices generated in the customer's language, purpose tags on every stored datum, retention policies enforced by TTL in Cassandra/ClickHouse, data-principal export/delete APIs, India-only data residency. Becoming a registered Consent Manager is optional and a separate business; integrating with registered Consent Managers is enough.

**Other regulation**

- **UPI (NPCI framework, 15 Oct 2026):** zero MDR for P2M ≤ ₹2,000 and for P2PM small merchants receiving ≤ ₹1 lakh/month via QR; 0.4% (cap ₹300) above ₹2,000 for standard P2M. Design: for kirana tenants, generate UPI intent/dynamic QR payable **directly to the merchant's VPA** so funds never touch Hamsa; for larger tenants, integrate licensed payment aggregators (Razorpay, Cashfree; both support intent, dynamic QR, payment links, AutoPay). Holding funds would require an RBI Payment Aggregator licence.
- **TRAI TCCCPR (Third Amendment, 18 Sep 2026)** applies to SMS and voice legs: DLT registration of entity, headers, templates and consent; AI-based UCC detection by operators. A separate Consumer Affairs draft (2026) proposes extending anti-spam duties to OTT/messaging and **requiring AI-generated commercial voice/text to be disclosed at the start of the interaction** — we build that disclosure in now.
- Synthetic voice: label AI voice and watermark owner voice clones; consent records per voice.

**AI-specific controls:** PII detection/redaction before any model call (regex for phone, Aadhaar with Verhoeff checksum, PAN, card numbers with Luhn, UPI IDs, plus NER), reversible tokenisation vault; prompt-injection classifier on retrieved and user content; per-tenant tool allowlists; discount and spend caps enforced in the Verifier, not the prompt; refunds always human-approved.

**Confidential computing:** H100/H200 (single-GPU; PPCIe for multi-GPU), B200/B300 (multi-GPU) support GPU TEEs with NVIDIA attestation (NRAS or local verifier). NVIDIA's confidential-containers stack needs AMD SEV-SNP or Intel TDX hosts on Ubuntu 25.10/26.04, Kata 4.0, GPU Operator ≥ 26.3.1, Trustee for key release. Indian availability is thin (NTT DATA + Fortanix announced a managed service in Feb 2026; others "support" CC but need confirmation). Recommendation: **enterprise tier only**, with attestation shown in the owner dashboard; the throughput overhead must be measured before pricing it.

---

## 9. Cost model

Source: `research/phase0/cost_model/cost_model.py` → `RESULTS.md`. Prices exclude GST. Verified inputs: L40S ₹102/h (E2E on-demand), ₹67.5/h (IndiaAI on-demand), ₹45/h (IndiaAI 12-month reserved); cheapest Indian H100 on-demand ₹192/h; WhatsApp India rates from 1 Oct 2026. Hypotheses (to be replaced by Phase 3/7 measurements): throughput 20k prefill / 2.5k aggregate decode tok/s per L40S for a ~4B-class model at FP8, 40% average GPU utilisation, cascade shares, voice concurrency per GPU, PSTN ₹0.40/min.

**Per unit**

- Hamsa-LM call: ₹0.0069. Large-fallback call: ₹0.13 (~19× more).
- AI text conversation (6 customer messages): **₹0.061** = small LLM 0.020 + large fallback 0.024 + retrieval 0.003 + platform 0.015.
- Voice: **₹0.23/min** web (TTS is the largest part), **₹0.63/min** phone (PSTN dominates).

**Plans (proposal)**

| plan | price/mo | included AI conversations | web voice min | phone min | margin @ typical use (40%) | margin @ 100% use | WhatsApp fees if used as channel @ typical |
|---|---:|---:|---:|---:|---:|---:|---:|
| Kirana | ₹99 | 300 | 30 | 0 | 73% | 58% | ₹0 (under free 1,000) |
| Dukaan | ₹299 | 1,500 | 150 | 0 | 71% | 46% | ₹299 |
| Vyapaar | ₹999 | 6,000 | 600 | 200 | 64% | 26% | ₹1,541 |
| Pro | ₹2,999 | 20,000 | 2,000 | 1,000 | 60% | 14% | ₹5,405 |
| Enterprise | custom | | | | per-tenant LoRA, TEE inference, SLA | | |

**Sensitivity (₹99 plan at 100% allowance):** baseline 58%; cascade failure (80% of messages hit the LLM) 49%; fallback at 10% instead of 3% 42%; throughput 3× worse 44%; utilisation 15% 46%; no prefix caching 52%; IndiaAI reserved L40S 62%. No single failure breaks the ₹99 plan.

**What the model tells us to do**

1. **Drive fallback rate down before anything else.** At 3% of messages it is already about half of model cost (39% of the all-in per-conversation cost). Self-host the fallback (Sarvam-105B on reserved H100s) and train the router to prefer clarifying questions over escalation.
2. **Voice needs metered pricing above the included minutes**, and web voice should be pushed over PSTN; PSTN is 64% of phone-minute cost.
3. **At ₹99, fixed per-tenant cost dominates at typical usage**: ₹16 (support ₹8, infra ₹6, subscription collection ₹2) versus ₹10 of AI + voice; even at full allowance variable cost is only ₹25. Self-serve onboarding (catalog from photos, auto-generated FAQ) is an economic requirement, not polish.
4. **Reserve IndiaAI capacity** for the steady-state latency pool; keep on-demand/spot for peaks and batch.
5. **Avoid OTP SMS/WhatsApp authentication costs:** customers chat anonymously via link; identity is established at payment (UPI VPA) or by optional phone verification only when the business needs it.

---

## 10. Risk register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Small model can't reach required tool-call / arithmetic reliability in code-mixed dialogues | Medium | High | Verifier node blocks wrong prices/SKUs; constrained decoding; RLVR on deterministic rewards; Sarvam-30B as v0 so product isn't blocked on distillation |
| R2 | Cascade resolves far less than 50% without an LLM | Medium | Medium | Sensitivity shows margin survives (49%); measure from Phase 3 shadow traffic; tune templates per vertical |
| R3 | Teacher/data licence contamination | Medium | High | Only Apache/MIT teachers for training data; provenance tags on every synthetic sample; legal review of each teacher's terms |
| R4 | Sarvam-30B serving immaturity in vLLM (custom MoE kernels, LoRA on MoE) | Medium | Medium | Phase 3 bake-off vLLM vs SGLang; fallback to Gemma 4 26B-A4B which has first-class engine support |
| R5 | Indic ASR/TTS quality on noisy, code-mixed, 8 kHz audio | High | High | Collect consented shop/telephony audio early (Phase 2 voice notes), fine-tune; Saaras/Bulbul APIs as interim fallback for premium tiers |
| R6 | WebGPU unavailable or slow on low-end Android | High | Low | WASM fallback; edge is an optimisation, not a dependency; cost model survives edge share 5% |
| R7 | Regulatory: TRAI/Consumer Affairs extend anti-spam + AI disclosure to OTT; DPDP enforcement from May 2027 | High | Medium | Build consent, opt-out, sender identity, AI disclosure, audit logs into Phase 2 data model |
| R8 | Payments regulation (PA licence) if we touch funds | Low (by design) | High | Direct-to-merchant UPI intent; licensed PAs only |
| R9 | Confidential-computing GPU capacity in India is scarce/expensive | High | Low | Enterprise-only; partner route (NTT DATA/Fortanix or a CC-enabled Indian cloud); price after measurement |
| R10 | Infra licence drift (as happened with Scylla, MinIO, Redis, Redpanda) | Medium | Medium | Prefer foundation-governed projects (Apache, Linux Foundation, CNCF); quarterly licence audit in CI (SBOM + licence scanner) |
| R11 | Fertility advantage doesn't hold in real traffic (mostly romanized) | Medium | Low | Measure script mix in Phase 2; romanized cost is already ≈ parity across tokenizers |
| R12 | Spam/abuse of free-ish broadcast channel harms deliverability and trust | Medium | High | Opt-in only broadcasts; uplift targeting (Phase 8); per-tenant rate limits; graph-based abuse detection |

---

## 11. Open experiments before or during Phase 1

1. **Hamsa-Bench v0** (§2.3) — required before locking the Phase 3 model.
2. **Serving bake-off** on synthetic traces: Sarvam-30B FP8 and Gemma 4 E4B / Qwen3.5-4B on L40S and H100; vLLM vs SGLang; with prefix caching, multi-LoRA (8–32 adapters) and speculative decoding. Output: measured tok/s and p95 latency to replace the cost-model hypotheses.
3. **IN22-Gen / FLORES+ fertility rerun** (gated datasets; needs a Hugging Face token) to get English-parallel parity numbers on a standard benchmark.
4. **Gemma 4 vocab-surgery pilot:** swap the ~23k non-Indic rows for Sarvam-style Indic tokens, 1–2B tokens of continued pre-training on a single 8×GPU node, measure perplexity and Hamsa-Bench delta.
5. **ASR/TTS spot-check** on 2 hours of real shop audio: SraVaani-live, IndicConformer, Saaras v4; Parler vs IndicF5 vs Bulbul v3 MOS on 5 languages.
6. **PSTN/SIP quotes** from 2–3 licensed Indian providers; confidential-computing GPU availability quotes.

---

## 12. Decisions requested

1. **Model plan:** approve Sarvam-30B as Hamsa-LM v0 and Gemma 4 E4B (+ vocab surgery) vs Qwen3.5-4B as the Phase 5 student bake-off — noting Sarvam-30B exceeds the 3–8B total-parameter guideline (2.4B active).
2. **Channel strategy:** own zero-install chat link/PWA as default; WhatsApp as a pass-through paid add-on.
3. **Stack substitutions:** Cassandra 5 (not ScyllaDB), Valkey 9 (not Redis), SeaweedFS (not MinIO), NATS JetStream as backbone (not Redpanda).
4. **Payments posture:** never hold merchant funds; direct UPI intent for small merchants, licensed PAs for others.
5. **Plan ladder:** ₹99 / ₹299 / ₹999 / ₹2,999 / Enterprise with the allowances above and metered voice overage.
6. **Phase 0.5:** fund Hamsa-Bench v0 and the serving bake-off (§11 items 1–2) before Phase 3 model lock; they can run in parallel with Phase 1–2 platform work.

On approval, Phase 1 will deliver architecture diagrams, data model, API and event schemas, the agent graph, the security model and the monorepo layout.

---

## Appendix A — Reproducing the measurements

```bash
cd research/phase0
python3 -m venv .venv && . .venv/bin/activate   # or: uv venv
pip install -r requirements.txt
python tokenizer_fertility/fertility.py --max-per-lang 400   # ~1 min, downloads only tokenizer.json files
python cost_model/cost_model.py                               # stdlib only
```

## Appendix B — Primary sources

- Sarvam 30B/105B release blog (6 Mar 2026) and Hugging Face cards; Sarvam Saaras v4, Bulbul v3 docs; Sarvam Vision 2.1 blog.
- Qwen3.5 GitHub/HF cards (small series 2 Mar 2026); Qwen timeline (Qwen4 in training, 22 Sep 2026).
- Gemma 4 model card (last updated 30 Jul 2026), Google blog and Open Source blog (Apache-2.0, 2 Apr 2026), HF blog.
- vLLM v0.29.0 release notes (9 Sep 2026); SGLang v0.5.18 (22 Aug 2026); TRL v1.0 release; Unsloth RL guide.
- MCP specification 2026-07-28 and changelog; LangChain/LangGraph changelog (v1.2.0); Temporal LangGraph plugin docs/blog (16 Jul 2026).
- OpenMLS crates.io (0.9.0, 25 Aug 2026) and changelog.
- Transformers.js v4 blog (9 Feb 2026), npm @huggingface/transformers 4.3.0.
- Qwen3-Embedding/Reranker repo; LingoIITGN/qwen-indic-v1 card; pgvector 0.8.4 (ParadeDB PR #5475); pg_search 0.26.0 (PGXN).
- AI4Bharat IndicConformer, IndicF5, Indic Parler-TTS cards; ARTPARK-IISc SraVaani-0.5-live card; JoshTalks Human-1 paper (arXiv 2604.23295) and card; LiveKit Agents 1.6.1 / Turn Detector v1.
- Surya OCR 2 release and weight licence; "Can OCR-VLMs Read Devanagari?" (arXiv 2606.29213); Chitrapathak repo; SemiHastakshar (IIIT-H).
- ScyllaDB source-available FAQ; MinIO archival timeline; Redis licences page; Valkey 9 coverage; Redpanda licence summary.
- NVIDIA confidential containers supported platforms; Intel Trust Authority GPU attestation; Fortanix/NTT DATA India announcement (17 Feb 2026).
- DPDP Rules 2025 gazette (G.S.R. 846(E), 13 Nov 2025), PIB, KPMG/EY summaries.
- TRAI TCCCPR Third Amendment (18 Sep 2026), TRAI direction (27 Feb 2026), Consumer Affairs draft coverage.
- PIB UPI MDR framework; Cashfree and Razorpay pricing pages.
- Meta WhatsApp Business Platform INR rate card effective 1 Oct 2026.
- IndiaAI compute portal price calculator and Ready Reckoner (13 Mar 2026); E2E Networks L40S page; Maapan Bazaar H100 price tracker (6 Sep 2026).
- Tokenizer studies: IndicSuperTokenizer/MUTANT (ACL 2026), "Evaluating Tokenizer Performance … Official Indian Languages" (arXiv 2411.12240), indictok-256k card.
