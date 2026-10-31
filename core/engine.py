"""Deterministic profit, leakage, inventory and simulation engine. No LLM involved."""
from __future__ import annotations
import pandas as pd

REQ = ["order_id", "date", "product_id", "product_name", "category", "quantity", "unit_price",
       "discount_pct", "unit_cost", "shipping_cost", "platform_fee_pct", "returned"]
CFG = dict(margin_low=0.15, discount_max=0.12, return_max=0.10, ship_max=0.10, fee_max=0.05,
           holding_rate=0.20, overstock_days=150, stockout_days=14, high_profit=25, healthy=15, low=5)


def sdiv(a: float, b: float) -> float:
    """Safe division: returns 0.0 for zero/invalid denominators."""
    try:
        return float(a) / float(b) if b else 0.0
    except (TypeError, ValueError):
        return 0.0


def enrich(df: pd.DataFrame, price=1.0, disc=1.0, ret=1.0, ship=1.0, fee=1.0) -> pd.DataFrame:
    """Row-level financials. Multipliers are RELATIVE factors used by the simulator.
    gross=qty*price; discount=gross*disc_pct; refund=(gross-discount) if returned (full refund);
    net=gross-discount-refund; COGS is NOT recovered on returns (conservative);
    fees=(gross-discount)*fee_pct (not refunded); profit(contribution)=net-COGS-shipping-fees."""
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"])
    for c in ["quantity", "unit_price", "discount_pct", "unit_cost", "shipping_cost", "platform_fee_pct", "returned"]:
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
    q = d["quantity"].clip(lower=0)
    d["qty"] = q
    d["gross"] = q * d.unit_price * price
    d["discount"] = d.gross * (d.discount_pct * disc).clip(0, 1)
    d["refund"] = (d.gross - d.discount) * d.returned.clip(0, 1) * ret
    d["net"] = d.gross - d.discount - d.refund
    d["cogs"] = q * d.unit_cost
    d["shipping"] = d.shipping_cost * ship
    d["fees"] = (d.gross - d.discount) * d.platform_fee_pct * fee
    d["profit"] = d.net - d.cogs - d.shipping - d.fees
    d["ret_qty"] = q * d.returned.clip(0, 1) * ret
    return d


def metrics(e: pd.DataFrame) -> dict:
    s = e[["gross", "discount", "refund", "net", "cogs", "shipping", "fees", "profit", "qty", "ret_qty"]].sum()
    return dict(gross=s.gross, net=s.net, discount=s.discount, refund=s.refund, cogs=s.cogs, shipping=s.shipping,
                fees=s.fees, profit=s.profit, margin=sdiv(s.profit, s.net) * 100, units=s.qty,
                return_rate=sdiv(s.ret_qty, s.qty) * 100, orders=len(e), aov=sdiv(s.net, len(e)))


def by_product(e: pd.DataFrame, cfg: dict = CFG) -> pd.DataFrame:
    if e.empty:
        return pd.DataFrame()
    p = e.groupby(["product_id", "product_name", "category"], as_index=False).agg(
        units=("qty", "sum"), gross=("gross", "sum"), discount=("discount", "sum"), refund=("refund", "sum"),
        net=("net", "sum"), cogs=("cogs", "sum"), shipping=("shipping", "sum"), fees=("fees", "sum"),
        profit=("profit", "sum"), ret_qty=("ret_qty", "sum"))
    p["margin"] = [sdiv(a, b) * 100 for a, b in zip(p.profit, p.net)]
    p["return_rate"] = [sdiv(a, b) * 100 for a, b in zip(p.ret_qty, p.units)]
    p["discount_rate"] = [sdiv(a, b) for a, b in zip(p.discount, p.gross)]
    p["ship_rate"] = [sdiv(a, b) for a, b in zip(p.shipping, p.gross)]
    p["fee_rate"] = [sdiv(a, b) for a, b in zip(p.fees, p.gross)]

    def cls(m, prof):
        if prof < 0: return "Loss Making"
        if m >= cfg["high_profit"]: return "High Profit"
        if m >= cfg["healthy"]: return "Healthy"
        if m >= cfg["low"]: return "Low Margin"
        return "At Risk"
    p["class"] = [cls(m, pr) for m, pr in zip(p.margin, p.profit)]
    return p


def leakage(p: pd.DataFrame, total_net: float, cfg: dict = CFG) -> pd.DataFrame:
    """Rule-based leakage. Impact = money above the configured threshold (deterministic)."""
    out = []
    if p.empty:
        return pd.DataFrame(columns=["category", "product", "product_category", "impact", "severity", "evidence", "action"])
    med = p.net.median()

    def add(cat, r, impact, ev, act):
        if impact <= 0: return
        sh = sdiv(impact, total_net)
        out.append(dict(category=cat, product=r.product_name, product_category=r.category, impact=round(impact, 2),
                        severity="High" if sh > .02 else "Medium" if sh > .007 else "Low", evidence=ev, action=act))
    for r in p.itertuples():
        add("Negative Profit", r, -r.profit if r.profit < 0 else 0,
            f"Contribution profit {r.profit:,.0f} on net revenue {r.net:,.0f}", "Raise price, renegotiate cost, or delist")
        if r.profit >= 0 and r.margin < cfg["margin_low"] * 100 and r.net >= med:
            add("Margin Leakage", r, cfg["margin_low"] * r.net - r.profit,
                f"Margin {r.margin:.1f}% < {cfg['margin_low']:.0%} threshold with above-median revenue", "Review pricing and supplier cost")
        add("Discount Leakage", r, r.discount - cfg["discount_max"] * r.gross,
            f"Discounts {r.discount_rate:.1%} of gross vs {cfg['discount_max']:.0%} limit", "Cap discount depth/frequency")
        add("Return Leakage", r, r.refund * (1 - sdiv(cfg["return_max"] * 100, r.return_rate)) if r.return_rate > cfg["return_max"] * 100 else 0,
            f"Return rate {r.return_rate:.1f}% vs {cfg['return_max']:.0%} limit", "Investigate quality/description; improve QA")
        add("Shipping Leakage", r, r.shipping - cfg["ship_max"] * r.gross,
            f"Shipping {r.ship_rate:.1%} of gross vs {cfg['ship_max']:.0%} limit", "Renegotiate carrier, set min order/shipping fee")
        add("Platform Fee Leakage", r, r.fees - cfg["fee_max"] * r.gross,
            f"Fees {r.fee_rate:.1%} of gross vs {cfg['fee_max']:.0%} limit", "Shift volume to lower-fee channels")
    df = pd.DataFrame(out)
    return df.sort_values("impact", ascending=False).reset_index(drop=True) if len(df) else df


def inventory(e: pd.DataFrame, stock: pd.DataFrame, cfg: dict = CFG) -> pd.DataFrame:
    """days_left = stock / avg daily units over the selected window. Lead times are NOT assumed."""
    if e.empty:
        return pd.DataFrame()
    days = max((e.date.max() - e.date.min()).days + 1, 1)
    u = e.groupby(["product_id", "product_name"], as_index=False).agg(units=("qty", "sum"), cost=("unit_cost", "mean"))
    u = u.merge(stock, on="product_id", how="inner")
    u["velocity"] = u.units / days
    u["days_left"] = [sdiv(s, v) if v else float("inf") for s, v in zip(u.stock, u.velocity)]
    u["holding_cost_annual"] = u.stock * u.cost * cfg["holding_rate"]

    def act(r):
        if r.days_left > cfg["overstock_days"]: return "Overstock: reduce purchasing / consider promotion"
        if r.days_left < cfg["stockout_days"]: return "Stockout risk: reorder (verify supplier lead time)"
        return "OK"
    u["action"] = u.apply(act, axis=1)
    return u


def simulate(df: pd.DataFrame, price=0.0, disc=0.0, ret=0.0, ship=0.0, fee=0.0) -> dict:
    """price is a relative change; disc/ret/ship/fee are relative REDUCTIONS (0.10 = 10% of current value).
    Hypothetical, not a forecast; no demand response modelled."""
    base, sim = enrich(df), enrich(df, 1 + price, 1 - disc, 1 - ret, 1 - ship, 1 - fee)
    mb, ms = metrics(base), metrics(sim)
    pb, ps = by_product(base), by_product(sim)
    pp = pb[["product_name", "profit"]].merge(ps[["product_name", "profit"]], on="product_name", suffixes=("_current", "_simulated"))
    pp["delta"] = pp.profit_simulated - pp.profit_current
    return dict(current=mb, simulated=ms, delta=ms["profit"] - mb["profit"],
                pct=sdiv(ms["profit"] - mb["profit"], abs(mb["profit"])) * 100, products=pp.sort_values("delta", ascending=False))


def advice(q: str, m: dict, leaks: pd.DataFrame, prods: pd.DataFrame, df: pd.DataFrame) -> str:
    """Rule-based (NOT AI-generated) answers built from calculated metrics."""
    if leaks.empty or prods.empty:
        return "No data or no leakage detected for the current filters."
    top = leaks.iloc[0]
    worst = prods.sort_values("margin").head(3)
    if q.startswith("Summarize"):
        return (f"Net revenue {m['net']:,.0f}, contribution profit {m['profit']:,.0f} ({m['margin']:.1f}% margin), return rate "
                f"{m['return_rate']:.1f}%. Estimated leakage across {len(leaks)} issues totals {leaks.impact.sum():,.0f}.")
    if q.startswith("What happens"):
        s = simulate(df, disc=0.05)
        return (f"If discounts fall 5% (relative) and demand is unchanged, contribution profit changes by {s['delta']:,.0f} "
                f"({s['pct']:+.1f}%). Hypothetical only; customers may buy less.")
    if q.startswith("Which products"):
        return "Lowest-margin products: " + "; ".join(f"{r.product_name} ({r.margin:.1f}%)" for r in worst.itertuples())
    by_cat = leaks.groupby("category").impact.sum().sort_values(ascending=False)
    return (f"Biggest single issue: {top.category} on {top['product']} (impact {top.impact:,.0f}). {top.evidence}. "
            f"Suggested action: {top.action}. By category, most leakage is {by_cat.index[0]} ({by_cat.iloc[0]:,.0f}).")
