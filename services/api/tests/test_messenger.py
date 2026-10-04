from conftest import JWK, auth, login


def _device(client, token, name="phone"):
    r = client.post("/api/devices", json={"name": name, "public_key": JWK}, headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_phone_normalisation_and_otp_errors(client):
    r = client.post("/api/auth/otp/request", json={"phone": "098765 43210"})
    assert r.json()["phone"] == "+919876543210"
    assert client.post("/api/auth/otp/request", json={"phone": "12"}).status_code == 422
    r = client.post("/api/auth/otp/verify", json={"phone": "9876543210", "code": "000000"})
    assert r.status_code in (400,)  # wrong code (dev code is random)


def test_otp_attempt_limit(client):
    client.post("/api/auth/otp/request", json={"phone": "9876543210"})
    for _ in range(5):
        client.post("/api/auth/otp/verify", json={"phone": "9876543210", "code": "999999"})
    r = client.post("/api/auth/otp/verify", json={"phone": "9876543210", "code": "999999"})
    assert r.status_code == 429


def test_under_18_blocked_without_parental_consent(client):
    code = client.post("/api/auth/otp/request", json={"phone": "9876500000"}).json()["dev_code"]
    r = client.post("/api/auth/otp/verify", json={"phone": "9876500000", "code": code, "birth_year": 2015})
    assert r.status_code == 403


def test_public_key_must_not_contain_private_part(client):
    a = login(client, "9876543210", "Asha")
    r = client.post("/api/devices", json={"public_key": {**JWK, "d": "secret"}}, headers=auth(a["token"]))
    assert r.status_code == 422


def test_direct_chat_e2ee_relay_and_ack(client):
    a = login(client, "9876543210", "Asha")
    b = login(client, "9123456789", "Bala")
    a_dev, b_dev = _device(client, a["token"]), _device(client, b["token"])
    a_web = _device(client, a["token"], "web")

    found = client.post("/api/contacts/lookup", json={"phones": ["+91 91234 56789", "999"]}, headers=auth(a["token"])).json()
    assert [u["display_name"] for u in found] == ["Bala"]

    conv = client.post("/api/conversations", json={"kind": "direct", "peer_user_id": b["user"]["id"]}, headers=auth(a["token"])).json()
    again = client.post("/api/conversations", json={"kind": "direct", "peer_user_id": a["user"]["id"]}, headers=auth(b["token"])).json()
    assert conv["id"] == again["id"]

    devices = client.get(f"/api/conversations/{conv['id']}/devices", headers=auth(a["token"])).json()
    assert {d["id"] for d in devices} == {a_dev, b_dev, a_web}

    with client.websocket_connect(f"/api/ws?token={b['token']}&device_id={b_dev}") as ws:
        # Missing a_web (sender's other device) -> server refuses so no device silently misses a message.
        bad = {"message_id": "m-00000001", "sender_device_id": a_dev,
               "envelopes": [{"recipient_device_id": b_dev, "payload": {"ct": "x"}}]}
        r = client.post(f"/api/conversations/{conv['id']}/envelopes", json=bad, headers=auth(a["token"]))
        assert r.status_code == 409 and r.json()["detail"]["error"] == "device_mismatch"

        good = {**bad, "envelopes": [{"recipient_device_id": b_dev, "payload": {"ct": "opaque-1"}},
                                     {"recipient_device_id": a_web, "payload": {"ct": "opaque-2"}}]}
        r = client.post(f"/api/conversations/{conv['id']}/envelopes", json=good, headers=auth(a["token"]))
        assert r.status_code == 200 and r.json()["delivered_to"] == 2
        event = ws.receive_json()
        assert event["type"] == "envelope" and event["envelope"]["payload"] == {"ct": "opaque-1"}

    pending = client.get(f"/api/devices/{b_dev}/envelopes", headers=auth(b["token"])).json()
    assert len(pending) == 1
    assert client.get(f"/api/devices/{b_dev}/envelopes", headers=auth(a["token"])).status_code == 404
    r = client.post("/api/envelopes/ack", json={"device_id": b_dev, "ids": [pending[0]["id"]]}, headers=auth(b["token"]))
    assert r.json()["deleted"] == 1
    assert client.get(f"/api/devices/{b_dev}/envelopes", headers=auth(b["token"])).json() == []
    # The server keeps no plaintext history for personal chats.
    assert client.get(f"/api/conversations/{conv['id']}/messages", headers=auth(a["token"])).status_code == 400


def test_sender_must_own_device_and_be_member(client):
    a = login(client, "9876543210", "Asha")
    b = login(client, "9123456789", "Bala")
    c = login(client, "9000000002", "Chitra")
    a_dev, b_dev, c_dev = (_device(client, x["token"]) for x in (a, b, c))
    conv = client.post("/api/conversations", json={"kind": "direct", "peer_user_id": b["user"]["id"]}, headers=auth(a["token"])).json()
    body = {"message_id": "m-00000002", "sender_device_id": c_dev, "envelopes": [{"recipient_device_id": b_dev, "payload": {}}]}
    assert client.post(f"/api/conversations/{conv['id']}/envelopes", json=body, headers=auth(c["token"])).status_code == 404
    body["sender_device_id"] = b_dev
    assert client.post(f"/api/conversations/{conv['id']}/envelopes", json=body, headers=auth(a["token"])).status_code == 403


def test_group_chat(client):
    a, b, c = (login(client, p, n) for p, n in (("9876543210", "Asha"), ("9123456789", "Bala"), ("9000000002", "Chitra")))
    devs = {x["user"]["id"]: _device(client, x["token"]) for x in (a, b, c)}
    r = client.post("/api/conversations", json={"kind": "group", "title": "Family", "member_user_ids": [b["user"]["id"]]},
                    headers=auth(a["token"]))
    g = r.json()
    assert g["kind"] == "group" and len(g["members"]) == 2
    assert client.post(f"/api/conversations/{g['id']}/members", json={"user_ids": [c["user"]["id"]]},
                       headers=auth(b["token"])).status_code == 403
    g = client.post(f"/api/conversations/{g['id']}/members", json={"user_ids": [c["user"]["id"]]}, headers=auth(a["token"])).json()
    assert len(g["members"]) == 3
    env = [{"recipient_device_id": devs[u], "payload": {"ct": u}} for u in (b["user"]["id"], c["user"]["id"])]
    r = client.post(f"/api/conversations/{g['id']}/envelopes",
                    json={"message_id": "g-00000001", "sender_device_id": devs[a["user"]["id"]], "envelopes": env}, headers=auth(a["token"]))
    assert r.json()["delivered_to"] == 2
    assert client.post(f"/api/conversations/{g['id']}/leave", headers=auth(c["token"])).json() == {"ok": True}


def test_guests_cannot_start_personal_chats(client):
    g = client.post("/api/auth/guest", json={"display_name": "Visitor"}).json()
    b = login(client, "9123456789", "Bala")
    r = client.post("/api/conversations", json={"kind": "direct", "peer_user_id": b["user"]["id"]}, headers=auth(g["token"]))
    assert r.status_code == 403


def test_call_signalling_relay(client):
    a = login(client, "9876543210", "Asha")
    b = login(client, "9123456789", "Bala")
    conv = client.post("/api/conversations", json={"kind": "direct", "peer_user_id": b["user"]["id"]}, headers=auth(a["token"])).json()
    with client.websocket_connect(f"/api/ws?token={b['token']}") as wb, client.websocket_connect(f"/api/ws?token={a['token']}") as wa:
        wa.send_json({"type": "ping"})
        assert wa.receive_json() == {"type": "pong"}
        wa.send_json({"type": "signal", "conversation_id": conv["id"], "to_user": b["user"]["id"], "data": {"sdp": "offer"}})
        ev = wb.receive_json()
        assert ev == {"type": "signal", "conversation_id": conv["id"], "from_user": a["user"]["id"], "data": {"sdp": "offer"}}


def test_ws_rejects_bad_token(client):
    import pytest
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/ws?token=nope") as ws:
            ws.receive_json()
