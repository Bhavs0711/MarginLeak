"""SQLite persistence (transactional) and CSV validation."""
from __future__ import annotations
import logging, os, sqlite3
import pandas as pd
from core.engine import REQ
from data.generator import generate

log = logging.getLogger("marginleak")
DB = os.environ.get("MARGINLEAK_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "marginleak.db"))
NUM = ["quantity", "unit_price", "discount_pct", "unit_cost", "shipping_cost", "platform_fee_pct", "returned"]


def _c(path=None):
    return sqlite3.connect(path or DB)


def init(path=None, seed=True):
    c = _c(path)
    with c:
        c.execute("CREATE TABLE IF NOT EXISTS orders(order_id TEXT PRIMARY KEY,date TEXT,product_id TEXT,product_name TEXT,category TEXT,quantity INTEGER,unit_price REAL,discount_pct REAL,unit_cost REAL,shipping_cost REAL,platform_fee_pct REAL,returned INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS stock(product_id TEXT PRIMARY KEY,stock INTEGER)")
        n = c.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    c.close()
    if seed and n == 0:
        reset_demo(path)


def load_orders(path=None) -> pd.DataFrame:
    c = _c(path); df = pd.read_sql("SELECT * FROM orders", c); c.close(); return df


def load_stock(path=None) -> pd.DataFrame:
    c = _c(path); df = pd.read_sql("SELECT * FROM stock", c); c.close(); return df


def insert_orders(df: pd.DataFrame, replace=False, path=None):
    """Atomic: any failure (e.g. duplicate key) rolls back the whole import."""
    c = _c(path)
    try:
        with c:
            if replace: c.execute("DELETE FROM orders")
            c.executemany(f"INSERT INTO orders VALUES({','.join('?'*len(REQ))})", df[REQ].astype(object).values.tolist())
    finally:
        c.close()


def reset_demo(path=None):
    o, s = generate()
    insert_orders(o, replace=True, path=path)
    c = _c(path)
    with c:
        c.execute("DELETE FROM stock"); c.executemany("INSERT INTO stock VALUES(?,?)", s.values.tolist())
    c.close()
    log.info("demo data reset")


def delete_all(path=None):
    c = _c(path)
    with c:
        c.execute("DELETE FROM orders"); c.execute("DELETE FROM stock")
    c.close()


def _safe(s: pd.Series) -> pd.Series:
    """Neutralise spreadsheet-formula injection in text fields."""
    s = s.astype(str).str.strip()
    return s.where(~s.str[:1].isin(list("=+-@")), "'" + s)


def validate(df: pd.DataFrame, existing_ids=()) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (valid, rejected_with_reason). Raises ValueError on missing columns. Nothing is silently dropped."""
    miss = [c for c in REQ if c not in df.columns]
    if miss:
        raise ValueError(f"Missing required columns: {', '.join(miss)}")
    d = df[REQ].copy(); d["_reason"] = ""

    def flag(m, msg): d.loc[m, "_reason"] += msg + "; "
    for c in ["order_id", "product_id", "product_name", "category"]:
        d[c] = _safe(d[c]); flag(d[c].isin(["", "nan"]), f"{c} missing")
    for c in NUM:
        d[c] = pd.to_numeric(d[c], errors="coerce"); flag(d[c].isna(), f"{c} missing/non-numeric")
    dt = pd.to_datetime(d["date"], errors="coerce"); flag(dt.isna(), "invalid date")
    flag(d.quantity <= 0, "quantity must be > 0"); flag(d.unit_price < 0, "negative price")
    flag(d.unit_cost < 0, "negative cost"); flag(d.shipping_cost < 0, "negative shipping")
    flag(~d.discount_pct.between(0, 1) & d.discount_pct.notna(), "discount_pct must be 0-1")
    flag(~d.platform_fee_pct.between(0, 1) & d.platform_fee_pct.notna(), "platform_fee_pct must be 0-1")
    flag(d.duplicated("order_id", keep="first"), "duplicate order_id in file")
    flag(d.order_id.isin(set(existing_ids)), "order_id already in database")
    bad = d._reason != ""
    ok = d[~bad].drop(columns="_reason").copy()
    ok["date"] = dt[~bad].dt.strftime("%Y-%m-%d")
    ok["quantity"] = ok.quantity.astype(int); ok["returned"] = ok.returned.clip(0, 1).round().astype(int)
    return ok, d[bad]
