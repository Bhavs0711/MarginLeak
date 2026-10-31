# MarginLeak — Find the profit you're leaving behind.
Profit-leakage detection for small e-commerce businesses: it explains **why** margins erode and **what** to fix.

## Problem
High revenue can hide losses from discounts, returns, shipping, platform fees and idle stock. Owners track revenue, not contribution profit.

## Features (implemented)
Overview dashboard with filters · Rule-based leakage detection (margin, discount, return, shipping, platform fee, negative profit) with severity, evidence and actions · Product classification · Inventory risk · What-if simulator (price, discount, returns, shipping, fees; CSV export) · Rule-based advisor · CSV upload with validation, column mapping, rejected-record download, confirmed import/replace (SQLite transactions), demo reset, delete-all.

## Quick start (macOS)
```bash
cd MarginLeak && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
python -m pytest -q
```

## Architecture
`core/engine.py` (all math) · `data/generator.py` (seeded synthetic data) · `data/repo.py` (SQLite + validation) · `app.py` (UI) · `tests/`.

## Methodology
Gross = qty×price. Discount = gross×discount%. Refund = (gross−discount) on returned orders (full refund assumed). Net = gross−discount−refund. COGS = qty×unit cost (not recovered on returns). Fees = (gross−discount)×fee% (not refunded). **Contribution profit** = net − COGS − shipping − fees (not accounting profit: no overheads/tax). Margin = profit/net. Return rate = returned units/units sold. Zero denominators return 0.
Leakage impact = amount above a configurable threshold (see `CFG`); overlapping issues are not additive savings.
Simulator: all changes are **relative** (10% return reduction turns 20% into 18%). No demand elasticity; results are hypothetical, not forecasts.
Inventory: days remaining = stock / avg daily units; holding cost = stock × avg cost × 20% annual (assumption); lead times are not assumed.

## Data & privacy
Local SQLite file (`marginleak.db`, git-ignored). CSVs are parsed as data only, size-limited, formula-prefix neutralised. "Delete ALL data" wipes the DB.

## Known limitations
No PDF report; no LLM advisor (rule-based only); no inventory-quantity simulation; thresholds are code-configured, not UI-editable; single full-refund assumption.

## Future work
PDF executive summary, OpenAI-compatible advisor (verified metrics as context), editable thresholds, channel-level fees.
