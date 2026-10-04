# Hamsa

An Indian messaging app in the WhatsApp mould: end-to-end encrypted personal chats, groups and calls, free for everyone, with businesses inside the same app running sales, support and payments through an Indic AI agent on plans from ₹99/month.

## Status

| Phase | Deliverable | Status |
|---|---|---|
| 0 | Research memo: product shape, model selection, serving, cost model, risks | **In review** — [`docs/phase-0/research-memo.md`](docs/phase-0/research-memo.md) |
| 1 | Architecture, data model, API/event schemas, agent graph, security model, monorepo | Not started |
| 2–10 | Platform MVP → RAG/vision → agents → Hamsa-LM → Edge → Speech → Predictive ML → Flywheel → Security/scale | Not started |

## Layout

```
docs/phase-0/research-memo.md        Phase 0 memo (start here)
research/phase0/tokenizer_fertility/ Fertility harness, code-mixed business probe set, results
research/phase0/cost_model/          Unit-economics model per plan, results
```

## Reproduce Phase 0 measurements

```bash
cd research/phase0
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python tokenizer_fertility/fertility.py --max-per-lang 400
python cost_model/cost_model.py
```
