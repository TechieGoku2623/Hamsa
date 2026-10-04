import json

import httpx

from conftest import auth
from hamsa.agent.llm import LLMClient


def _fake_llm(script):
    """OpenAI-compatible fake: returns scripted assistant messages in order, records requests."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        msg = script[min(len(calls) - 1, len(script) - 1)]
        return httpx.Response(200, json={"choices": [{"message": msg}]})

    client = LLMClient("http://llm.test/v1", "hamsa-lm", "k", 5, transport=httpx.MockTransport(handler))
    return client, calls


def _tool_call(name, args, i="c1"):
    return {"role": "assistant", "content": "", "tool_calls": [{"id": i, "type": "function",
                                                                 "function": {"name": name, "arguments": json.dumps(args)}}]}


def _chat(client):
    g = client.post("/api/auth/guest", json={}).json()
    conv = client.post("/api/public/b/sharma-kirana/chat", headers=auth(g["token"])).json()
    return g["token"], conv["id"]


def _say(client, token, cid, text):
    return client.post(f"/api/conversations/{cid}/messages", json={"text": text}, headers=auth(token)).json()["reply"]


def test_llm_handles_what_rules_cannot_and_tools_use_catalog_prices(make_client):
    llm, calls = _fake_llm([
        _tool_call("add_to_cart", {"items": [{"sku": "DAL-TUR", "qty": 2}]}),
        {"role": "assistant", "content": "Dal makhani ke liye 2 kg toor dal add kar di. Total ₹320."},
    ])
    client = make_client(llm=llm)
    token, cid = _chat(client)
    r = _say(client, token, cid, "aaj raat 4 logon ke liye khana banana hai, kuch suggest karo")
    assert r["meta"]["tier"] == "llm" and r["meta"]["trace"]["tool_calls"] == ["add_to_cart"]
    assert r["text"].endswith("₹320.")
    system = calls[0]["messages"][0]["content"]
    assert "DAL-TUR | Toor Dal" in system and "Hinglish" in system
    assert {t["function"]["name"] for t in calls[0]["tools"]} >= {"add_to_cart", "place_order", "handoff_to_owner"}


def test_verifier_replaces_reply_with_invented_price(make_client):
    llm, _ = _fake_llm([
        _tool_call("add_to_cart", {"items": [{"sku": "DAL-TUR", "qty": 1}]}),
        {"role": "assistant", "content": "Added toor dal, special price ₹99 today!"},
    ])
    client = make_client(llm=llm)
    token, cid = _chat(client)
    r = _say(client, token, cid, "something for sambar, whatever you suggest")
    assert r["meta"]["trace"]["verifier"] == "replaced"
    assert "₹99" not in r["text"] and "₹160" in r["text"]


def test_tool_errors_are_returned_to_model_not_applied(make_client):
    llm, calls = _fake_llm([
        _tool_call("add_to_cart", {"items": [{"sku": "CAVIAR", "qty": 1}, {"sku": "SUGAR1", "qty": 5000}]}),
        {"role": "assistant", "content": "Sorry, we don't have that."},
    ])
    client = make_client(llm=llm)
    token, cid = _chat(client)
    r = _say(client, token, cid, "something fancy for a party")
    tool_msg = next(m for m in calls[1]["messages"] if m["role"] == "tool")
    assert json.loads(tool_msg["content"]) == {"ok": False, "error": "unknown_item"}
    assert r["text"] == "Sorry, we don't have that."


def test_llm_outage_falls_back_to_template(make_client):
    def boom(request):
        return httpx.Response(503)

    llm = LLMClient("http://llm.test/v1", "m", "k", 5, transport=httpx.MockTransport(boom))
    client = make_client(llm=llm)
    token, cid = _chat(client)
    r = _say(client, token, cid, "kuch accha sa suggest karo")
    assert r["meta"]["tier"] == "fallback" and r["meta"]["trace"]["llm_error"] is True


def test_rules_tier_skips_llm(make_client):
    llm, calls = _fake_llm([{"role": "assistant", "content": "unused"}])
    client = make_client(llm=llm)
    token, cid = _chat(client)
    r = _say(client, token, cid, "2 kg cheeni")
    assert r["meta"]["tier"] == "rules" and calls == []
