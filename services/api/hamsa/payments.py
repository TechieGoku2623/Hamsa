from __future__ import annotations

import re
from urllib.parse import quote

_VPA_RE = re.compile(r"^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z][a-zA-Z0-9.\-]{1,64}$")


def valid_vpa(vpa: str) -> bool:
    return bool(_VPA_RE.match(vpa or ""))


def format_inr(paise: int) -> str:
    rupees, p = divmod(paise, 100)
    s = str(rupees)
    # Indian digit grouping: 12,34,567
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups + [tail])
    return f"₹{s}" if p == 0 else f"₹{s}.{p:02d}"


def upi_intent(vpa: str, payee_name: str, amount_paise: int, ref: str, note: str) -> str:
    """UPI deep link (NPCI linking spec). Money goes straight to the merchant's VPA; Hamsa never holds funds."""
    if not valid_vpa(vpa):
        raise ValueError("invalid VPA")
    params = {
        "pa": vpa,
        "pn": payee_name[:50],
        "am": f"{amount_paise / 100:.2f}",
        "cu": "INR",
        "tr": ref,
        "tn": note[:50],
    }
    return "upi://pay?" + "&".join(f"{k}={quote(v, safe='@.')}" for k, v in params.items())
