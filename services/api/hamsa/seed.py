"""Create a demo kirana store with a catalog, owned by +91 98000 00001.

    python -m hamsa.seed
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from .config import settings
from .db import Database
from .models import Business, CatalogItem, User

DEMO_OWNER_PHONE = "+919800000001"

ITEMS = [
    ("SUGAR1", "Sugar", ["चीनी", "cheeni", "shakkar"], 4800, "kg", 50),
    ("RICE-BAS", "Basmati Rice", ["basmati", "बासमती"], 12000, "kg", 40),
    ("RICE-SM", "Sona Masoori Rice", ["sona masoori", "masoori"], 6500, "kg", 60),
    ("ATTA5", "Aashirvaad Atta 5kg", ["atta", "आटा"], 26500, "pkt", 20),
    ("MILK", "Toned Milk 500ml", ["milk", "दूध", "doodh", "பால்"], 2800, "pkt", 100),
    ("OIL1", "Sunflower Oil 1L", ["oil", "तेल", "tel"], 15500, "pc", 30),
    ("DAL-TUR", "Toor Dal", ["toor", "arhar", "तुअर दाल", "अरहर"], 16000, "kg", 25),
    ("EGG6", "Eggs (6)", ["anda", "ande", "अंडे"], 4200, "pc", 40),
    ("TEA250", "Tata Tea Gold 250g", ["chai patti", "चायपत्ती"], 14500, "pkt", 15),
    ("SALT1", "Tata Salt 1kg", ["namak", "नमक"], 2800, "pkt", 50),
    ("ONION", "Onion", ["pyaz", "प्याज", "kanda"], 3500, "kg", 80),
    ("TOMATO", "Tomato", ["tamatar", "टमाटर"], 3000, "kg", 60),
    ("BREAD", "Bread", ["pav", "ब्रेड"], 4500, "pkt", 20),
    ("SOAP", "Lifebuoy Soap", ["sabun", "साबुन"], 3500, "pc", 40),
]


async def seed(db: Database) -> Business:
    await db.create_all()
    async with db.sessionmaker() as s:
        owner = await s.scalar(select(User).where(User.phone == DEMO_OWNER_PHONE))
        if owner is None:
            owner = User(phone=DEMO_OWNER_PHONE, display_name="Ramesh Sharma")
            s.add(owner)
            await s.flush()
        biz = await s.scalar(select(Business).where(Business.handle == "sharma-kirana"))
        if biz is None:
            biz = Business(
                owner_user_id=owner.id, handle="sharma-kirana", name="Sharma Kirana Store", category="kirana",
                vpa="sharmakirana@okaxis", address="Shop 4, Gandhi Market, Indiranagar, Bengaluru 560038",
                hours="7am–10pm, all days", delivery_note="Free home delivery within 2 km for orders above ₹199",
                faq=[{"q": "Do you deliver?", "a": "Yes! Free home delivery within 2 km for orders above ₹199."},
                     {"q": "Do you accept UPI?", "a": "Yes, all UPI apps. We also accept cash on delivery."}],
            )
            s.add(biz)
            await s.flush()
            s.add_all([CatalogItem(business_id=biz.id, sku=sku, name=n, aliases=a, price_paise=p, unit=u, stock=st)
                       for sku, n, a, p, u, st in ITEMS])
        await s.commit()
        return biz


if __name__ == "__main__":
    biz = asyncio.run(seed(Database(settings.database_url)))
    print(f"Seeded business '{biz.handle}' (owner {DEMO_OWNER_PHONE})")
