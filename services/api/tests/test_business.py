from conftest import auth, login, owner


def _open_chat(client, token):
    r = client.post("/api/public/b/sharma-kirana/chat", headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


def _say(client, token, conv_id, text):
    r = client.post(f"/api/conversations/{conv_id}/messages", json={"text": text}, headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()["reply"]


def test_public_profile(client):
    r = client.get("/api/public/b/sharma-kirana").json()
    assert r["business"]["name"] == "Sharma Kirana Store" and len(r["items"]) == 14
    assert client.get("/api/public/b/nope").status_code == 404


def test_hinglish_order_to_upi_and_owner_confirmation(client):
    guest = client.post("/api/auth/guest", json={"display_name": "Priya"}).json()
    conv = _open_chat(client, guest["token"])
    assert conv["business"]["handle"] == "sharma-kirana"

    r = _say(client, guest["token"], conv["id"], "Namaste")
    assert "Sharma Kirana Store" in r["text"] and r["meta"]["tier"] == "rules"

    r = _say(client, guest["token"], conv["id"], "2 kg cheeni aur 1 doodh bhejo")
    assert r["meta"]["lang"] == "hi_latn"
    assert "add kar diya" in r["text"] and "₹124" in r["text"]  # 2×48 + 28

    r = _say(client, guest["token"], conv["id"], "1 kg rice")
    assert "Basmati" in r["text"] and "Sona Masoori" in r["text"]  # ambiguous -> clarify

    r = _say(client, guest["token"], conv["id"], "1 kg basmati")
    assert "₹244" in r["text"] and r["meta"]["lang"] == "hi_latn"  # no language evidence -> stays Hinglish

    r = _say(client, guest["token"], conv["id"], "confirm")
    assert r["meta"]["lang"] == "hi_latn" and "ho gaya" in r["text"]
    code = r["meta"]["order_code"]
    action = r["meta"]["actions"][0]
    assert action["type"] == "upi_pay" and action["amount_paise"] == 24400
    assert action["link"].startswith("upi://pay?pa=sharmakirana@okaxis") and f"tr={code}" in action["link"]

    o = owner(client)
    biz = client.get("/api/businesses/mine", headers=auth(o["token"])).json()[0]
    orders = client.get(f"/api/businesses/{biz['id']}/orders", headers=auth(o["token"])).json()
    assert orders[0]["code"] == code and orders[0]["total_paise"] == 24400 and orders[0]["status"] == "pending_payment"

    r = _say(client, guest["token"], conv["id"], "payment kar diya")
    assert code in r["text"]
    orders = client.get(f"/api/businesses/{biz['id']}/orders", headers=auth(o["token"])).json()
    assert orders[0]["status"] == "payment_claimed"

    r = client.patch(f"/api/orders/{orders[0]['id']}", json={"status": "paid"}, headers=auth(o["token"]))
    assert r.json()["status"] == "paid"
    assert client.patch(f"/api/orders/{orders[0]['id']}", json={"status": "paid"}, headers=auth(o["token"])).status_code == 409
    history = client.get(f"/api/conversations/{conv['id']}/messages", headers=auth(guest["token"])).json()
    assert history[-1]["sender_type"] == "system" and "payment mil gaya" in history[-1]["text"]

    # Stock was reserved: 50 - 2 sugar.
    items = {i["sku"]: i for i in client.get(f"/api/businesses/{biz['id']}/items", headers=auth(o["token"])).json()}
    assert items["SUGAR1"]["stock"] == 48


def test_tamil_and_hindi_replies_use_native_script(client):
    g = client.post("/api/auth/guest", json={}).json()
    conv = _open_chat(client, g["token"])
    r = _say(client, g["token"], conv["id"], "எனக்கு 2 கிலோ சர்க்கரை வேணும்")
    assert r["meta"]["lang"] == "ta" and "சேர்க்கப்பட்டது" in r["text"] and "சர்க்கரை" in r["text"]
    r = _say(client, g["token"], conv["id"], "चीनी कितने की है?")
    assert r["meta"]["lang"] == "hi" and "चीनी का दाम ₹48 प्रति किलो है" in r["text"]


def test_menu_hours_faq_and_status(client):
    g = client.post("/api/auth/guest", json={}).json()
    conv = _open_chat(client, g["token"])
    assert "Toor Dal" in _say(client, g["token"], conv["id"], "menu")["text"]
    assert "7am" in _say(client, g["token"], conv["id"], "shop timing?")["text"]
    r = _say(client, g["token"], conv["id"], "Do you deliver?")
    assert r["meta"]["tier"] == "faq" and "2 km" in r["text"]
    assert "don't have any orders" in _say(client, g["token"], conv["id"], "where is my order")["text"]


def test_cancel_before_payment_restores_stock(client):
    g = client.post("/api/auth/guest", json={}).json()
    conv = _open_chat(client, g["token"])
    _say(client, g["token"], conv["id"], "3 kg onion")
    r = _say(client, g["token"], conv["id"], "confirm")
    assert r["meta"]["order_code"]
    r = _say(client, g["token"], conv["id"], "cancel karo")
    assert "cancel" in r["text"]
    o = owner(client)
    biz = client.get("/api/businesses/mine", headers=auth(o["token"])).json()[0]
    items = {i["sku"]: i for i in client.get(f"/api/businesses/{biz['id']}/items", headers=auth(o["token"])).json()}
    assert items["ONION"]["stock"] == 80


def test_out_of_stock_and_verifier_limits(client):
    o = owner(client)
    biz = client.get("/api/businesses/mine", headers=auth(o["token"])).json()[0]
    items = {i["sku"]: i for i in client.get(f"/api/businesses/{biz['id']}/items", headers=auth(o["token"])).json()}
    client.patch(f"/api/items/{items['BREAD']['id']}", json={"stock": 0}, headers=auth(o["token"]))
    g = client.post("/api/auth/guest", json={}).json()
    conv = _open_chat(client, g["token"])
    assert "out of stock" in _say(client, g["token"], conv["id"], "1 bread please")["text"]


def test_handoff_pauses_ai_and_owner_takes_over(client):
    g = client.post("/api/auth/guest", json={}).json()
    conv = _open_chat(client, g["token"])
    o = owner(client)
    with client.websocket_connect(f"/api/ws?token={o['token']}") as ws:
        r = _say(client, g["token"], conv["id"], "owner se baat karni hai")
        assert "owner" in r["text"]
        kinds = [ws.receive_json()["type"] for _ in range(3)]
        assert "needs_human" in kinds
    assert _say(client, g["token"], conv["id"], "hello?") is None  # AI paused
    biz = client.get("/api/businesses/mine", headers=auth(o["token"])).json()[0]
    inbox = client.get(f"/api/businesses/{biz['id']}/conversations", headers=auth(o["token"])).json()
    assert inbox[0]["needs_human"] is True and inbox[0]["ai_enabled"] is False
    r = client.post(f"/api/conversations/{conv['id']}/messages", json={"text": "Haan ji, boliye"}, headers=auth(o["token"]))
    assert r.json()["message"]["sender_type"] == "owner"
    r = client.post(f"/api/conversations/{conv['id']}/ai", json={"enabled": True}, headers=auth(o["token"]))
    assert r.json()["ai_enabled"] is True and r.json()["needs_human"] is False


def test_guest_registration_keeps_chat_and_orders(client):
    g = client.post("/api/auth/guest", json={"display_name": "Priya"}).json()
    conv = _open_chat(client, g["token"])
    _say(client, g["token"], conv["id"], "1 kg sugar")
    _say(client, g["token"], conv["id"], "confirm")
    user = login(client, "9876543210", "Priya", token=g["token"])
    convs = client.get("/api/conversations", headers=auth(user["token"])).json()
    assert [c["id"] for c in convs] == [conv["id"]]
    assert len(client.get("/api/orders/mine", headers=auth(user["token"])).json()) == 1


def test_owner_onboarding_and_validation(client):
    u = login(client, "9000000009", "Meena")
    r = client.post("/api/businesses", json={"handle": "meena-tiffins", "name": "Meena Tiffins", "vpa": "not-a-vpa"}, headers=auth(u["token"]))
    assert r.status_code == 422
    r = client.post("/api/businesses", json={"handle": "meena-tiffins", "name": "Meena Tiffins", "category": "restaurant",
                                             "vpa": "meena@oksbi"}, headers=auth(u["token"]))
    biz = r.json()
    assert client.post("/api/businesses", json={"handle": "meena-tiffins", "name": "Another"}, headers=auth(u["token"])).status_code == 409
    r = client.post(f"/api/businesses/{biz['id']}/items", json={"sku": "IDLI", "name": "Idli (4)", "aliases": ["இட்லி"],
                                                                  "price_paise": 4000, "unit": "pc"}, headers=auth(u["token"]))
    assert r.status_code == 200
    other = login(client, "9000000010", "Other")
    assert client.get(f"/api/businesses/{biz['id']}/items", headers=auth(other["token"])).status_code == 404
    g = client.post("/api/auth/guest", json={}).json()
    conv = client.post("/api/public/b/meena-tiffins/chat", headers=auth(g["token"])).json()
    r = _say(client, g["token"], conv["id"], "2 இட்லி வேணும்")
    assert "₹80" in r["text"]
