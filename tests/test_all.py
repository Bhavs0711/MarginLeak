import os, sys, tempfile
import pandas as pd, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import engine as E
from data import repo
from data.generator import generate

def row(**k):
    b = dict(order_id="1", date="2026-01-01", product_id="P1", product_name="A", category="C", quantity=2, unit_price=10.0,
             discount_pct=0.1, unit_cost=4.0, shipping_cost=2.0, platform_fee_pct=0.05, returned=0)
    b.update(k); return pd.DataFrame([b])

def test_formulas():
    m = E.metrics(E.enrich(row()))
    assert m["gross"] == 20 and m["net"] == 18 and round(m["profit"], 2) == 7.1
    assert round(m["margin"], 2) == round(7.1 / 18 * 100, 2)

def test_refund_and_negative_margin():
    m = E.metrics(E.enrich(row(returned=1)))
    assert m["net"] == 0 and round(m["profit"], 2) == -10.9 and m["margin"] == 0 and m["return_rate"] == 100

def test_zero_and_missing():
    assert E.sdiv(1, 0) == 0
    m = E.metrics(E.enrich(row(quantity=0, unit_price=None)))
    assert m["aov"] == 0 and m["return_rate"] == 0

def test_simulator_relative():
    df = row(returned=1)
    assert E.simulate(df)["delta"] == 0
    s = E.simulate(row(), disc=0.5)  # discounts 2 -> 1 (relative 50%)
    assert round(s["simulated"]["discount"], 2) == 1.0 and s["delta"] > 0
    r = E.simulate(row(returned=1), ret=0.1)  # 10% relative, refund 18 -> 16.2
    assert round(r["simulated"]["refund"], 2) == 16.2

def test_generator_and_leakage():
    o, s = generate(); o2, _ = generate()
    assert len(o) >= 1500 and o.equals(o2) and o.product_id.nunique() >= 20 and o.category.nunique() == 5
    e = E.enrich(o); p = E.by_product(e); l = E.leakage(p, E.metrics(e)["net"])
    assert {"Negative Profit", "Discount Leakage", "Return Leakage", "Shipping Leakage"} <= set(l.category)
    assert "Loss Making" in set(p["class"]) and set(["category", "impact", "severity", "evidence", "action"]) <= set(l.columns)
    inv = E.inventory(e, s)
    assert any(inv.action.str.startswith("Overstock")) and any(inv.action.str.startswith("Stockout"))
    assert "Biggest" in E.advice("Where", E.metrics(e), l, p, o)

def test_validation():
    df = pd.concat([row(order_id="1"), row(order_id="1"), row(order_id="2", quantity=-1), row(order_id="3", date="bad"), row(order_id="4")])
    ok, bad = repo.validate(df, existing_ids=["4"])
    assert list(ok.order_id) == ["1"] and len(bad) == 4 and "duplicate" in bad._reason.iloc[0]
    with pytest.raises(ValueError): repo.validate(df.drop(columns=["unit_cost"]))

def test_db_persistence_and_rollback():
    p = os.path.join(tempfile.mkdtemp(), "t.db")
    repo.init(p, seed=False); assert len(repo.load_orders(p)) == 0
    repo.insert_orders(row(order_id="A"), path=p); assert len(repo.load_orders(p)) == 1
    with pytest.raises(Exception): repo.insert_orders(pd.concat([row(order_id="B"), row(order_id="A")]), path=p)
    assert len(repo.load_orders(p)) == 1  # rolled back, B absent
    repo.reset_demo(p); assert len(repo.load_orders(p)) >= 1500
    repo.delete_all(p); assert len(repo.load_orders(p)) == 0

def test_upload_changes_metrics():
    p = os.path.join(tempfile.mkdtemp(), "t.db"); repo.init(p, seed=False)
    before = E.metrics(E.enrich(repo.load_orders(p).assign(date="2026-01-01")))["net"] if len(repo.load_orders(p)) else 0
    repo.insert_orders(row(order_id="Z"), path=p)
    assert E.metrics(E.enrich(repo.load_orders(p)))["net"] > before
