import pytest

from hamsa.agent.lang import detect, normalize_digits
from hamsa.agent.nlu import CatalogEntry, convert_qty, detect_intents, find_mentions, group_overlaps

CATALOG = [
    CatalogEntry("SUGAR1", "Sugar", "kg", 4800, ["cheeni"]),
    CatalogEntry("RICE-BAS", "Basmati Rice", "kg", 12000, ["basmati"]),
    CatalogEntry("RICE-SM", "Sona Masoori Rice", "kg", 6500, ["sona masoori"]),
    CatalogEntry("MILK", "Toned Milk 500ml", "pkt", 2800, []),
    CatalogEntry("EGG6", "Eggs (6)", "pc", 4200, []),
]


@pytest.mark.parametrize("text,lang", [
    ("2 kg cheeni bhejo", "hi_latn"),
    ("मुझे दो किलो चीनी चाहिए", "hi"),
    ("मला दोन किलो साखर पाहिजे", "mr"),
    ("எனக்கு 2 கிலோ சர்க்கரை வேணும்", "ta"),
    ("sakkarai evlo", "ta_latn"),
    ("నాకు 2 కిలో చక్కెర కావాలి", "te"),
    ("2 কেজি চিনি লাগবে", "bn"),
    ("I need 2 kg sugar", "en"),
])
def test_language(text, lang):
    assert detect(text) == lang


def test_indic_digits_normalised():
    assert normalize_digits("२ किलो") == "2 किलो"
    assert normalize_digits("௨") == "2"


@pytest.mark.parametrize("text,sku,qty", [
    ("2 kg cheeni bhejo", "SUGAR1", 2),
    ("cheeni 3 kilo", "SUGAR1", 3),
    ("दो किलो चीनी चाहिए", "SUGAR1", 2),
    ("चीनी दे दो", "SUGAR1", 1),
    ("எனக்கு 2 கிலோ சர்க்கரை வேணும்", "SUGAR1", 2),
    ("2 కిలో చక్కెర కావాలి", "SUGAR1", 2),
    ("2 কেজি চিনি", "SUGAR1", 2),
    ("2 doodh packet", "MILK", 2),
    ("ande x2", "EGG6", 2),
    ("suger 2kg", "SUGAR1", 2),
])
def test_mentions_and_quantities(text, sku, qty):
    groups = group_overlaps(find_mentions(text, CATALOG))
    assert [g[0].sku for g in groups] == [sku]
    assert groups[0][0].qty == qty


def test_generic_word_is_ambiguous_specific_word_is_not():
    groups = group_overlaps(find_mentions("1 kg rice", CATALOG))
    assert sorted(m.sku for m in groups[0]) == ["RICE-BAS", "RICE-SM"]
    groups = group_overlaps(find_mentions("1 kg basmati", CATALOG))
    assert [m.sku for m in groups[0]] == ["RICE-BAS"]


def test_typo_tolerance_does_not_invent_items():
    onion = [CatalogEntry("ONION", "Onion", "kg", 3500, ["kanda"])]
    assert find_mentions("khana banana hai", onion) == []
    assert [m.sku for m in find_mentions("onoin 1kg", onion)] == ["ONION"]


def test_multiple_items():
    groups = group_overlaps(find_mentions("2 kg cheeni aur 1 doodh bhejo", CATALOG))
    assert [(g[0].sku, g[0].qty) for g in groups] == [("SUGAR1", 2), ("MILK", 1)]


def test_basmati_does_not_trigger_bas_checkout():
    assert "checkout" not in detect_intents("1 kg basmati")
    assert "checkout" in detect_intents("bas itna hi")


@pytest.mark.parametrize("text,intent", [
    ("menu dikhao", "browse"), ("मेनू", "browse"), ("confirm", "checkout"), ("போதும்", "checkout"),
    ("payment done", "paid"), ("pay kar diya", "paid"), ("order kab aayega", "status"), ("owner se baat karni hai", "human"),
    ("cancel karo", "cancel"), ("நன்றி", "thanks"), ("dukaan kab khulta hai", "hours"),
])
def test_intents(text, intent):
    assert intent in detect_intents(text)


def test_unit_conversion():
    assert convert_qty(500, "g", "kg") == 0.5
    assert convert_qty(2, "kg", "kg") == 2
