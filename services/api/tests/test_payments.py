import pytest

from hamsa.payments import format_inr, upi_intent, valid_vpa


def test_format_inr_indian_grouping():
    assert format_inr(4800) == "₹48"
    assert format_inr(4850) == "₹48.50"
    assert format_inr(123456700) == "₹12,34,567"
    assert format_inr(100000) == "₹1,000"


def test_upi_intent_pays_merchant_directly():
    link = upi_intent("sharmakirana@okaxis", "Sharma Kirana Store", 12350, ref="HABC12", note="Hamsa order HABC12")
    assert link.startswith("upi://pay?pa=sharmakirana@okaxis&pn=Sharma%20Kirana%20Store&am=123.50&cu=INR&tr=HABC12")


@pytest.mark.parametrize("vpa,ok", [("a.b@okhdfc", True), ("9876543210@ybl", True), ("bad", False), ("x@1bank", False)])
def test_vpa_validation(vpa, ok):
    assert valid_vpa(vpa) is ok
    if not ok:
        with pytest.raises(ValueError):
            upi_intent(vpa, "x", 100, "r", "n")
