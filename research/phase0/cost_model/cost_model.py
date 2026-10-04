"""Hamsa unit-economics model (Phase 0).

Every number is either a verified price (source in ASSUMPTIONS_SOURCES) or an
explicit hypothesis to be measured in Phases 2-5. Change a value here and
re-run; RESULTS.md is regenerated.

Usage:
  python cost_model.py            # writes RESULTS.md next to this file
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path

HERE = Path(__file__).resolve().parent

INR_PER_USD = 88.0  # hypothesis; update at budgeting time


@dataclass
class GPU:
    name: str
    inr_per_hour: float
    source: str


GPUS = {
    "L40S_indiaai": GPU("L40S (IndiaAI on-demand)", 67.5, "compute.indiaai.gov.in price calculator, Mar 2026"),
    "L40S_indiaai_12m": GPU("L40S (IndiaAI 12-month reserved)", 45.0, "compute.indiaai.gov.in price calculator, Mar 2026"),
    "L40S_e2e": GPU("L40S (E2E Networks on-demand)", 102.0, "e2enetworks.com/gpus/nvidia-l40s, Oct 2026"),
    "H100_commercial_low": GPU("H100 (cheapest Indian on-demand)", 192.48, "maapan.ai/prices/h100, 6 Sep 2026"),
}


@dataclass
class TextAssumptions:
    """Per customer message. 'Conversation' = one customer session with the business."""

    msgs_per_conversation: float = 6.0
    # Cascade share of customer messages resolved at each tier (targets, to be measured).
    share_edge: float = 0.20          # on-device: greetings, FAQ match, order-status lookups
    share_intent_template: float = 0.20  # server-side small classifier + deterministic template
    share_semantic_cache: float = 0.10
    share_small_llm: float = 0.47     # Hamsa-LM
    share_large_llm: float = 0.03     # fallback
    # Hamsa-LM call shape (tokens). System prompt + catalog snippet are prefix-cached per tenant.
    prompt_tokens: int = 2600
    prefix_cache_hit_tokens: int = 1600
    output_tokens: int = 120          # reply + tool-call JSON
    # Serving throughput for a ~4B dense / ~2.4B-active MoE at FP8 on one L40S with vLLM
    # continuous batching. HYPOTHESIS: to be benchmarked in Phase 3.
    prefill_tok_per_s: float = 20000.0
    decode_tok_per_s_aggregate: float = 2500.0
    gpu_utilization: float = 0.40     # average over the day; India traffic is peaky
    gpu_key: str = "L40S_e2e"
    # Large-model fallback, priced as an API call (or self-hosted Sarvam-105B equivalent).
    large_in_tokens: int = 4000
    large_out_tokens: int = 250
    large_usd_per_m_in: float = 0.30  # hypothesis for an open-weight MoE served by a 3rd party
    large_usd_per_m_out: float = 1.20
    # Embeddings + rerank per message that reaches retrieval (semantic cache or LLM tiers)
    retrieval_inr_per_msg: float = 0.0008
    # Non-AI platform cost per conversation (gateway, Postgres, Cassandra, Redis/Valkey,
    # object storage, egress, observability), amortised. HYPOTHESIS.
    platform_inr_per_conversation: float = 0.015


@dataclass
class VoiceAssumptions:
    """Per minute of cascaded voice (ASR -> Hamsa-LM -> TTS), self-hosted."""

    asr_streams_per_gpu: float = 60.0     # streaming FastConformer/Conformer CTC; HYPOTHESIS
    tts_realtime_streams_per_gpu: float = 16.0  # IndicF5/Parler-class; HYPOTHESIS
    agent_talk_ratio: float = 0.45        # fraction of call time the agent speaks
    llm_turns_per_minute: float = 5.0
    gpu_utilization: float = 0.40
    gpu_key: str = "L40S_e2e"
    # PSTN/SIP inbound termination for the telephony bridge. HYPOTHESIS: needs operator quotes.
    pstn_inr_per_min: float = 0.40


@dataclass
class Plan:
    name: str
    price_inr: float          # per month, exclusive of GST
    ai_conversations: int     # included AI-handled conversations per month
    web_voice_minutes: int    # browser/WebRTC voice minutes
    pstn_minutes: int         # phone-number minutes
    support_inr: float        # amortised human support + onboarding per tenant-month
    fixed_infra_inr: float    # per-tenant fixed: storage, backups, catalog, monitoring
    typical_utilisation: float = 0.4  # fraction of allowance a median tenant uses


PLANS = [
    Plan("Kirana (₹99)", 99, ai_conversations=300, web_voice_minutes=30, pstn_minutes=0,
         support_inr=8, fixed_infra_inr=6),
    Plan("Dukaan (₹299)", 299, ai_conversations=1500, web_voice_minutes=150, pstn_minutes=0,
         support_inr=20, fixed_infra_inr=10),
    Plan("Vyapaar (₹999)", 999, ai_conversations=6000, web_voice_minutes=600, pstn_minutes=200,
         support_inr=60, fixed_infra_inr=25),
    Plan("Pro (₹2,999)", 2999, ai_conversations=20000, web_voice_minutes=2000, pstn_minutes=1000,
         support_inr=150, fixed_infra_inr=60),
]

PAYMENT_GATEWAY_FEE = 0.02 * 1.18  # subscription collection; Razorpay 2% + GST on fee

# WhatsApp Cloud API, India, effective 1 Oct 2026 (ex-GST), for the channel-cost comparison.
WA_SERVICE_INR = 0.1150
WA_FREE_SERVICE_PER_NUMBER = 1000
WA_MARKETING_INR = 0.8631

ASSUMPTIONS_SOURCES = {
    "GPU prices": {k: f"{g.name}: ₹{g.inr_per_hour}/h — {g.source}" for k, g in GPUS.items()},
    "WhatsApp India rates": "Meta rate card effective 1 Oct 2026: marketing ₹0.8631, utility/auth/service ₹0.1150, "
                            "first 1,000 service messages per number per month free",
    "UPI MDR": "Zero MDR for P2M <= ₹2,000 and for P2PM small merchants <= ₹1 lakh/month via QR; 0.4% above ₹2,000 "
               "from 15 Oct 2026 (PIB)",
}


def gpu_inr_per_second(key: str) -> float:
    return GPUS[key].inr_per_hour / 3600.0


def text_cost_per_conversation(t: TextAssumptions) -> dict[str, float]:
    gpu_s = gpu_inr_per_second(t.gpu_key) / t.gpu_utilization
    uncached = t.prompt_tokens - t.prefix_cache_hit_tokens
    small_call_gpu_seconds = uncached / t.prefill_tok_per_s + t.output_tokens / t.decode_tok_per_s_aggregate
    small_call_inr = small_call_gpu_seconds * gpu_s
    large_call_inr = (t.large_in_tokens * t.large_usd_per_m_in + t.large_out_tokens * t.large_usd_per_m_out) / 1e6 * INR_PER_USD
    m = t.msgs_per_conversation
    retrieval_msgs = m * (t.share_semantic_cache + t.share_small_llm + t.share_large_llm)
    parts = {
        "small_llm": m * t.share_small_llm * small_call_inr,
        "large_llm": m * t.share_large_llm * large_call_inr,
        "retrieval": retrieval_msgs * t.retrieval_inr_per_msg,
        "platform": t.platform_inr_per_conversation,
    }
    parts["total"] = sum(parts.values())
    parts["small_call_inr"] = small_call_inr
    parts["large_call_inr"] = large_call_inr
    parts["llm_free_share"] = t.share_edge + t.share_intent_template + t.share_semantic_cache
    return parts


def voice_cost_per_minute(v: VoiceAssumptions, t: TextAssumptions, pstn: bool) -> dict[str, float]:
    gpu_min = GPUS[v.gpu_key].inr_per_hour / 60.0 / v.gpu_utilization
    parts = {
        "asr": gpu_min / v.asr_streams_per_gpu,
        "tts": gpu_min * v.agent_talk_ratio / v.tts_realtime_streams_per_gpu,
        "llm": v.llm_turns_per_minute * text_cost_per_conversation(t)["small_call_inr"],
        "pstn": v.pstn_inr_per_min if pstn else 0.0,
    }
    parts["total"] = sum(parts.values())
    return parts


def plan_economics(p: Plan, t: TextAssumptions, v: VoiceAssumptions, utilisation: float) -> dict[str, float]:
    conv = text_cost_per_conversation(t)["total"]
    web = voice_cost_per_minute(v, t, pstn=False)["total"]
    phone = voice_cost_per_minute(v, t, pstn=True)["total"]
    variable = utilisation * (p.ai_conversations * conv + p.web_voice_minutes * web + p.pstn_minutes * phone)
    fixed = p.support_inr + p.fixed_infra_inr + p.price_inr * PAYMENT_GATEWAY_FEE
    cost = variable + fixed
    return {
        "variable_cost": variable,
        "fixed_cost": fixed,
        "total_cost": cost,
        "gross_margin_pct": 100.0 * (p.price_inr - cost) / p.price_inr,
    }


def whatsapp_channel_cost(p: Plan, t: TextAssumptions, utilisation: float) -> float:
    replies = utilisation * p.ai_conversations * t.msgs_per_conversation
    return max(0.0, replies - WA_FREE_SERVICE_PER_NUMBER) * WA_SERVICE_INR


def sensitivity(t: TextAssumptions, v: VoiceAssumptions) -> list[tuple[str, float, float]]:
    """Gross margin of the ₹99 plan at full allowance under pessimistic single-variable changes."""
    base_plan = PLANS[0]
    rows = []
    cases = {
        "baseline": {},
        "cascade fails: 80% of msgs hit Hamsa-LM": dict(share_edge=0.05, share_intent_template=0.05, share_semantic_cache=0.05, share_small_llm=0.80, share_large_llm=0.05),
        "large fallback 10% instead of 3%": dict(share_small_llm=0.40, share_large_llm=0.10),
        "throughput 3x worse than hypothesis": dict(prefill_tok_per_s=6667.0, decode_tok_per_s_aggregate=833.0),
        "GPU utilisation 15%": dict(gpu_utilization=0.15),
        "no prefix caching": dict(prefix_cache_hit_tokens=0),
        "IndiaAI reserved L40S": dict(gpu_key="L40S_indiaai_12m"),
    }
    for name, overrides in cases.items():
        tt = TextAssumptions(**{**asdict(t), **overrides})
        full = plan_economics(base_plan, tt, v, 1.0)
        rows.append((name, text_cost_per_conversation(tt)["total"], full["gross_margin_pct"]))
    return rows


def main() -> None:
    t, v = TextAssumptions(), VoiceAssumptions()
    conv = text_cost_per_conversation(t)
    web = voice_cost_per_minute(v, t, pstn=False)
    phone = voice_cost_per_minute(v, t, pstn=True)

    L = ["# Hamsa unit economics (generated by cost_model.py)", "",
         "All ₹ figures exclude GST. Values marked HYPOTHESIS in `cost_model.py` must be replaced by measurements "
         "from the Phase 3 serving benchmark and Phase 7 voice benchmark.", "",
         "## Cost per AI-handled text conversation", "",
         f"- Conversation = {t.msgs_per_conversation:g} customer messages; LLM-free share target = {conv['llm_free_share']:.0%} "
         f"(edge {t.share_edge:.0%}, intent/template {t.share_intent_template:.0%}, semantic cache {t.share_semantic_cache:.0%}); "
         f"Hamsa-LM {t.share_small_llm:.0%}; large fallback {t.share_large_llm:.0%}.",
         f"- One Hamsa-LM call: ₹{conv['small_call_inr']:.4f} on {GPUS[t.gpu_key].name} at {t.gpu_utilization:.0%} utilisation.",
         f"- One large-model fallback call: ₹{conv['large_call_inr']:.4f}.", "",
         "| component | ₹ per conversation |", "|---|---:|"]
    for k in ("small_llm", "large_llm", "retrieval", "platform", "total"):
        L.append(f"| {k} | {conv[k]:.4f} |")
    L += ["", "## Cost per voice minute (cascaded, self-hosted)", "", "| component | web voice ₹/min | phone (SIP/PSTN) ₹/min |", "|---|---:|---:|"]
    for k in ("asr", "tts", "llm", "pstn", "total"):
        L.append(f"| {k} | {web[k]:.4f} | {phone[k]:.4f} |")

    L += ["", "## Plans", "",
          "| plan | price | AI convs | web voice min | phone min | cost @ typical use | margin @ typical | cost @ 100% use | margin @ 100% | WhatsApp channel cost @ typical (pass-through) |",
          "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for p in PLANS:
        typ = plan_economics(p, t, v, p.typical_utilisation)
        full = plan_economics(p, t, v, 1.0)
        wa = whatsapp_channel_cost(p, t, p.typical_utilisation)
        L.append(f"| {p.name} | ₹{p.price_inr:,.0f} | {p.ai_conversations:,} | {p.web_voice_minutes:,} | {p.pstn_minutes:,} | "
                 f"₹{typ['total_cost']:.2f} | {typ['gross_margin_pct']:.0f}% | ₹{full['total_cost']:.2f} | {full['gross_margin_pct']:.0f}% | ₹{wa:,.0f} |")

    L += ["", "## Sensitivity: ₹99 plan at 100% of allowance", "", "| scenario | ₹ per conversation | gross margin |", "|---|---:|---:|"]
    for name, c, gm in sensitivity(t, v):
        L.append(f"| {name} | {c:.4f} | {gm:.0f}% |")

    L += ["", "## Verified price inputs", ""]
    for k, val in ASSUMPTIONS_SOURCES.items():
        if isinstance(val, dict):
            for vv in val.values():
                L.append(f"- {k}: {vv}")
        else:
            L.append(f"- {k}: {val}")
    (HERE / "RESULTS.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
