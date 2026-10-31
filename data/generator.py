"""Reproducible synthetic e-commerce data with deliberate profit-leak scenarios."""
from __future__ import annotations
import numpy as np, pandas as pd

CATS = {"Electronics": (30, 150, 6, ["Wireless Earbuds", "Smart Watch", "Phone Charger", "Bluetooth Speaker", "Webcam", "Power Bank"]),
        "Home & Kitchen": (15, 90, 8, ["Air Fryer", "Blender", "Coffee Grinder", "Knife Set", "Storage Bins", "Desk Lamp"]),
        "Fashion": (20, 80, 4, ["Running Jacket", "Denim Jeans", "Canvas Sneakers", "Wool Scarf", "Leather Belt", "Backpack"]),
        "Beauty": (10, 50, 3, ["Face Serum", "Hair Dryer", "Perfume", "Makeup Kit", "Beard Trimmer"]),
        "Sports": (15, 120, 7, ["Yoga Mat", "Dumbbell Set", "Water Bottle", "Resistance Bands", "Cycling Helmet"])}
SEASON = [1.0, .8, .8, .9, .9, 1.0, 1.0, 1.1, 1.0, 1.2, 1.7, 1.9]  # Jan..Dec


def generate(seed: int = 42, n_orders: int = 1800) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (orders, stock). Overrides by product index create the demo scenarios."""
    rng = np.random.default_rng(seed)
    prods, i = [], 0
    for cat, (lo, hi, ship, names) in CATS.items():
        for n in names:
            price = round(rng.uniform(lo, hi), 2)
            p = dict(pid=f"P{i+1:03d}", name=n, cat=cat, price=price, cost=price * rng.uniform(.45, .62), ship=ship * rng.uniform(.8, 1.2),
                     ret=.04, disc=None, pop=rng.lognormal(0, .5), days=rng.uniform(25, 110))
            if i == 0: p.update(cost=price * .88, pop=p["pop"] * 3)
            if i == 3: p.update(ret=.32)
            if i == 6: p.update(disc=.30)
            if i == 9: p.update(ship=price * .30)
            if i == 12: p.update(cost=price * 1.12)
            if i == 15: p.update(days=900)
            if i == 18: p.update(days=4, pop=p["pop"] * 2)
            if i == 21: p.update(ret=.22, disc=.20)
            prods.append(p); i += 1
    w = np.array([p["pop"] for p in prods]); w /= w.sum()
    days = pd.date_range("2025-11-01", "2026-10-31")
    dw = np.array([SEASON[d.month - 1] for d in days]); dw /= dw.sum()
    rows = []
    for k in range(n_orders):
        p = prods[rng.choice(len(prods), p=w)]
        d = days[rng.choice(len(days), p=dw)]
        disc = float(np.clip(rng.normal(p["disc"], .04), 0, .6)) if p["disc"] else float(rng.choice([0, 0, .05, .10]))
        r = p["ret"] * (1.5 if d.month == 1 else 1)
        rows.append(dict(order_id=f"ORD-{k+1:05d}", date=d.strftime("%Y-%m-%d"), product_id=p["pid"], product_name=p["name"],
                         category=p["cat"], quantity=1 + min(int(rng.poisson(.4)), 3), unit_price=p["price"], discount_pct=round(disc, 3),
                         unit_cost=round(p["cost"], 2), shipping_cost=round(max(p["ship"] * (1 + .25 * rng.standard_normal()), .5), 2),
                         platform_fee_pct=float(rng.choice([.03, .03, .05, .12])), returned=int(rng.random() < r)))
    o = pd.DataFrame(rows)
    u = o.groupby("product_id").quantity.sum()
    stock = pd.DataFrame([dict(product_id=p["pid"], stock=int(u.get(p["pid"], 0) / 365 * p["days"])) for p in prods])
    return o, stock
