"""MarginLeak - Streamlit UI. All numbers come from core.engine (deterministic)."""
import pandas as pd, plotly.express as px, plotly.graph_objects as go, streamlit as st
from core import engine as E
from data import repo
from data.generator import generate

st.set_page_config("MarginLeak", "💧", layout="wide")
st.markdown("""<style>
.block-container{padding-top:1.5rem;max-width:1400px}
[data-testid=stSidebar]{background:linear-gradient(180deg,#0f1730,#0b1120);border-right:1px solid #1f2a44}
.kpi{background:linear-gradient(135deg,#16203a,#1a1740);border:1px solid #2a3558;border-radius:14px;padding:16px}
.kpi b{font-size:1.5rem}.kpi span{color:#9aa7c7;font-size:.8rem;text-transform:uppercase;letter-spacing:.06em}
.logo{font-size:1.6rem;font-weight:800;background:linear-gradient(90deg,#7c8cff,#b983ff);-webkit-background-clip:text;color:transparent}
</style>""", unsafe_allow_html=True)
CUR = "$"; money = lambda v: f"{'-' if v < 0 else ''}{CUR}{abs(v):,.0f}"
T = dict(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=10, r=10, t=40, b=10))
def kpi(col, label, val): col.markdown(f"<div class='kpi'><span>{label}</span><br><b>{val}</b></div>", unsafe_allow_html=True)

repo.init()
raw, stock = repo.load_orders(), repo.load_stock()
st.sidebar.markdown("<div class='logo'>💧 MarginLeak</div><small>Find the profit you're leaving behind.</small>", unsafe_allow_html=True)
page = st.sidebar.radio("Navigate", ["Overview", "Leakage Detection", "Product Intelligence", "Inventory Intelligence",
                                     "What-if Simulator", "Advisor (rule-based)", "Data Management"], label_visibility="collapsed")
st.sidebar.caption(f"Dataset: {len(raw):,} orders · Currency: {CUR} (USD)")

df = raw
if not raw.empty:
    d = pd.to_datetime(raw.date)
    rng = st.sidebar.date_input("Date range", (d.min().date(), d.max().date()))
    cats = st.sidebar.multiselect("Category", sorted(raw.category.unique()), default=sorted(raw.category.unique()))
    if len(rng) == 2:
        df = raw[(d.dt.date >= rng[0]) & (d.dt.date <= rng[1]) & raw.category.isin(cats)]
    prods_sel = st.sidebar.multiselect("Products (optional)", sorted(df.product_name.unique()))
    if prods_sel: df = df[df.product_name.isin(prods_sel)]

if page != "Data Management" and df.empty:
    st.info("No data for the current filters. Load demo data or upload a CSV in **Data Management**."); st.stop()
if page != "Data Management":
    e = E.enrich(df); m = E.metrics(e); p = E.by_product(e); lk = E.leakage(p, m["net"])
    st.title(page)

if page == "Overview":
    st.caption("Contribution profit = net revenue − COGS − shipping − platform fees. It is NOT accounting profit (no overheads, tax, salaries).")
    c = st.columns(6)
    for col, (l, v) in zip(c, [("Gross revenue", money(m["gross"])), ("Net revenue", money(m["net"])), ("Contribution profit", money(m["profit"])),
                               ("Contribution margin", f"{m['margin']:.1f}%"), ("Est. leakage", money(lk.impact.sum() if len(lk) else 0)),
                               ("Return rate", f"{m['return_rate']:.1f}%")]): kpi(col, l, v)
    e["month"] = e.date.dt.to_period("M").dt.to_timestamp()
    mo = e.groupby("month").agg(net=("net", "sum"), profit=("profit", "sum"), q=("qty", "sum"), r=("ret_qty", "sum")).reset_index()
    a, b = st.columns(2)
    a.plotly_chart(px.line(mo, x="month", y=["net", "profit"], title="Net revenue vs contribution profit").update_layout(**T), width="stretch")
    mo["return_rate"] = mo.r / mo.q * 100
    b.plotly_chart(px.line(mo, x="month", y="return_rate", title="Return rate % by month").update_layout(**T), width="stretch")
    a, b = st.columns(2)
    a.plotly_chart(px.bar(p.groupby("category").profit.sum().reset_index(), x="category", y="profit", title="Profit by category").update_layout(**T), width="stretch")
    if len(lk): b.plotly_chart(px.pie(lk.groupby("category").impact.sum().reset_index(), names="category", values="impact", hole=.55, title="Leakage distribution").update_layout(**T), width="stretch")
    a, b = st.columns(2)
    a.plotly_chart(px.bar(p.nlargest(8, "profit"), x="profit", y="product_name", orientation="h", title="Top profitable").update_layout(**T), width="stretch")
    b.plotly_chart(px.bar(p.nsmallest(8, "profit"), x="profit", y="product_name", orientation="h", title="Worst performing").update_layout(**T), width="stretch")
    st.plotly_chart(px.scatter(p, x="discount_rate", y="margin", size="gross", color="category", hover_name="product_name", title="Discount rate vs margin").update_layout(**T), width="stretch")
    st.download_button("Download business report (CSV)", pd.DataFrame([m]).to_csv(index=False), "business_report.csv")

elif page == "Leakage Detection":
    st.caption("Impact = money above the configured threshold. Thresholds are in the engine config (core/engine.py CFG).")
    if lk.empty: st.success("No leakage detected with current thresholds.")
    else:
        st.metric("Total estimated leakage", money(lk.impact.sum()))
        st.caption("Issues can overlap (e.g. a loss-making product also has discount leakage), so the total is an upper-bound indicator, not an additive saving.")
        st.dataframe(lk, width="stretch", hide_index=True)
        st.download_button("Download leakage report (CSV)", lk.to_csv(index=False), "leakage_report.csv")

elif page == "Product Intelligence":
    q = st.text_input("Search product"); sel = p[p.product_name.str.contains(q, case=False)] if q else p
    cols = ["product_name", "category", "units", "gross", "net", "cogs", "shipping", "discount", "refund", "profit", "margin", "return_rate", "class"]
    st.dataframe(sel[cols].sort_values("profit"), width="stretch", hide_index=True)
    one = st.selectbox("Product detail", p.product_name)
    r = p[p.product_name == one].iloc[0]
    st.write(f"**{one}** is classified **{r['class']}** because contribution margin is {r.margin:.1f}% (High ≥ {E.CFG['high_profit']}%, Healthy ≥ {E.CFG['healthy']}%, Low ≥ {E.CFG['low']}%, below that At Risk; negative profit = Loss Making).")
    st.dataframe(lk[lk["product"] == one], width="stretch", hide_index=True)
    st.download_button("Download product report (CSV)", p.to_csv(index=False), "product_report.csv")

elif page == "Inventory Intelligence":
    inv = E.inventory(e, stock)
    st.caption(f"Days remaining = stock ÷ average daily units. Holding cost = stock × avg unit cost × {E.CFG['holding_rate']:.0%} annual rate (assumption). Supplier lead times are not in the data.")
    if inv.empty: st.info("No stock data for these products.")
    else:
        st.metric("Estimated annual holding cost", money(inv.holding_cost_annual.sum()))
        st.dataframe(inv[inv.action != "OK"].sort_values("days_left"), width="stretch", hide_index=True)
        st.download_button("Download inventory report (CSV)", inv.to_csv(index=False), "inventory_report.csv")

elif page == "What-if Simulator":
    st.caption("All changes are RELATIVE (e.g. 10% return reduction: 20% → 18%, not 10%). Hypothetical; demand response is not modelled; not a forecast.")
    PRE = {"A: Reduce discounting 5%": (0, 5, 0, 0, 0), "B: Reduce return rate 10% (relative)": (0, 0, 10, 0, 0),
           "C: Reduce shipping 8%": (0, 0, 0, 8, 0), "E: Custom": (0, 0, 0, 0, 0)}
    sc = st.selectbox("Scenario", list(PRE)); v = PRE[sc]; k = sc[:1]
    c = st.columns(5)
    pr = c[0].slider("Price change %", -20, 20, v[0], key=f"p{k}"); di = c[1].slider("Discount reduction % (rel.)", 0, 50, v[1], key=f"d{k}")
    re = c[2].slider("Return reduction % (rel.)", 0, 50, v[2], key=f"r{k}"); sh = c[3].slider("Shipping reduction %", 0, 50, v[3], key=f"s{k}")
    fe = c[4].slider("Platform fee reduction %", 0, 50, v[4], key=f"f{k}")
    s = E.simulate(df, pr / 100, di / 100, re / 100, sh / 100, fe / 100)
    c = st.columns(5)
    kpi(c[0], "Current profit", money(s["current"]["profit"])); kpi(c[1], "Simulated profit", money(s["simulated"]["profit"]))
    kpi(c[2], "Difference", money(s["delta"])); kpi(c[3], "Change", f"{s['pct']:+.1f}%")
    kpi(c[4], "Margin", f"{s['current']['margin']:.1f}% → {s['simulated']['margin']:.1f}%")
    f = go.Figure([go.Bar(name="Current", x=["Contribution profit"], y=[s["current"]["profit"]]), go.Bar(name="Simulated", x=["Contribution profit"], y=[s["simulated"]["profit"]])])
    st.plotly_chart(f.update_layout(**T, barmode="group"), width="stretch")
    st.dataframe(s["products"], width="stretch", hide_index=True)
    st.download_button("Export scenario (CSV)", s["products"].to_csv(index=False), "scenario.csv")

elif page == "Advisor (rule-based)":
    st.caption("Rule-based insights built from verified calculated metrics. No LLM is used in this build, so nothing here is AI-generated.")
    q = st.selectbox("Ask", ["Summarize my business performance", "Where am I losing the most money?", "What should I fix first?",
                             "Which products should I investigate?", "What happens if I reduce discounts?"])
    st.info(E.advice(q, m, lk, p, df))

else:
    st.markdown("**Schema (CSV columns):** " + ", ".join(E.REQ))
    st.caption("Local SQLite only (marginleak.db). Uploads are validated, never executed, and you can delete everything below.")
    o, _ = generate(n_orders=10)
    st.download_button("Download CSV template", o.head(3).to_csv(index=False), "template.csv")
    st.download_button("Download full sample dataset", generate()[0].to_csv(index=False), "sample_orders.csv")
    up = st.file_uploader("Upload orders CSV", type=["csv"])
    if up is not None:
        if up.size > 5_000_000: st.error("File too large (max 5 MB)")
        else:
            try:
                raw_up = pd.read_csv(up)
                st.dataframe(raw_up.head(10))
                miss = [c for c in E.REQ if c not in raw_up.columns]
                mapping = {}
                if miss:
                    st.warning("Map your columns to the required fields:")
                    for c in miss: mapping[c] = st.selectbox(c, ["-"] + list(raw_up.columns), key="m" + c)
                    if any(v == "-" for v in mapping.values()): st.stop()
                    raw_up = raw_up.rename(columns={v: k for k, v in mapping.items()})
                mode = st.radio("Import mode", ["Append (skip nothing; duplicates are rejected)", "Replace all existing data"])
                ok, bad = repo.validate(raw_up, [] if mode.startswith("Replace") else raw.order_id)
                st.write(f"Valid: **{len(ok)}** · Rejected: **{len(bad)}**")
                if len(bad):
                    st.dataframe(bad); st.download_button("Download rejected records", bad.to_csv(index=False), "rejected.csv")
                if len(ok) and st.checkbox("I confirm this import") and st.button("Import valid records"):
                    repo.insert_orders(ok, replace=mode.startswith("Replace")); st.success(f"Imported {len(ok)} records"); st.rerun()
            except Exception as ex:
                st.error(f"Could not process file: {ex}")
    c = st.columns(2)
    if c[0].button("Reset demo data") : repo.reset_demo(); st.rerun()
    if c[1].button("Delete ALL data"): repo.delete_all(); st.rerun()
