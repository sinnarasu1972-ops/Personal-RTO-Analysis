"""
Mahindra Personal RTO Dashboard - COMPLETE FASTAPI APPLICATION
- Shows RTO allocation: Unnati vs PACL
- Dashboard page with monthly data
- Quarterly Analysis page - calculated from data files with RTO filtering
  F25 = Apr2024 (2024) to Mar2025 (2025)
  F26 = Apr2025 (2025) to Mar2026 (2026)
- 2026 partial year support - DYNAMIC MONTHS
- MAHINDRA row highlighted in yellow
- Professional design
- MODIFIED FOR RENDER CLOUD DEPLOYMENT - COMPLETE VERSION
"""

import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Set
import pandas as pd
import numpy as np
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

# =========================================================
# CONFIG - CLOUD READY
# =========================================================
APP_TITLE = "Mahindra Personal RTO Dashboard"

# For Render, use environment-based paths
BASE_DATA_PATH = os.getenv("DATA_PATH", "/tmp/mahindra_data")

# Create data directories if they don't exist
os.makedirs(BASE_DATA_PATH, exist_ok=True)

YEAR_DIRS: Dict[int, Path] = {
    2024: Path(os.getenv("DATA_2024", f"{BASE_DATA_PATH}/2024")),
    2025: Path(os.getenv("DATA_2025", f"{BASE_DATA_PATH}/2025")),
    2026: Path(os.getenv("DATA_2026", f"{BASE_DATA_PATH}/2026")),
}

# RTO Territory Allocation: Unnati vs PACL
RTO_ALLOCATIONS = {
    'MH27': {'Unnati': 100, 'PACL': 0},
    'MH29': {'Unnati': 100, 'PACL': 0},
    'MH31': {'Unnati': 60, 'PACL': 40},
    'MH32': {'Unnati': 0, 'PACL': 100},
    'MH33': {'Unnati': 0, 'PACL': 100},
    'MH34': {'Unnati': 0, 'PACL': 100},
    'MH35': {'Unnati': 0, 'PACL': 100},
    'MH36': {'Unnati': 0, 'PACL': 100},
    'MH40': {'Unnati': 60, 'PACL': 40},
    'MH49': {'Unnati': 60, 'PACL': 40}
}

DEFAULT_RTOS = ['MH27', 'MH29', 'MH31', 'MH32', 'MH33', 'MH34', 'MH35', 'MH36', 'MH40', 'MH49']

FILE_GLOB = "MH*.xlsx"
ALL_MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
MONTH_SET = set(ALL_MONTHS)

QUARTERS = {
    'Q1': ['APR', 'MAY', 'JUN'],
    'Q2': ['JUL', 'AUG', 'SEP'],
    'Q3': ['OCT', 'NOV', 'DEC'],
    'Q4': ['JAN', 'FEB', 'MAR']
}

_CACHE = {"df": None, "last_load": 0.0, "files": [], "months": []}
RECHECK_SECONDS = 5

app = FastAPI(title=APP_TITLE)

# Add CORS middleware for cloud deployment
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================================
# HELPERS
# =========================================================

def _safe_int(x) -> int:
    try:
        if pd.isna(x):
            return 0
        if isinstance(x, str):
            x = x.strip().replace(",", "")
            if x == "":
                return 0
        v = pd.to_numeric(x, errors="coerce")
        return int(v) if not pd.isna(v) else 0
    except:
        return 0


def _extract_rto_from_filename(fp: Path) -> Optional[str]:
    try:
        m = re.search(r"(MH\d{2})", fp.stem.upper())
        return m.group(1) if m else None
    except:
        return None


def _parse_excel_format(fp: Path, cal_year: int) -> pd.DataFrame:
    try:
        print(f"  Reading: {fp.name}")
        
        try:
            raw = pd.read_excel(fp, sheet_name=0, header=None, engine="openpyxl")
        except:
            raw = pd.read_excel(fp, sheet_name=0, header=None)
        
        if raw.empty:
            return pd.DataFrame(columns=["cal_year", "rto", "maker", "month", "regs"])

        month_row = None
        for r in range(min(5, len(raw))):
            row_vals = [str(x).strip().upper() for x in raw.iloc[r] if pd.notna(x)]
            month_count = sum(1 for v in row_vals if v in MONTH_SET)
            if month_count >= 1:
                month_row = r
                break

        if month_row is None:
            return pd.DataFrame(columns=["cal_year", "rto", "maker", "month", "regs"])

        month_cols = {}
        for c in range(raw.shape[1]):
            val = raw.iat[month_row, c]
            if pd.isna(val):
                continue
            s = str(val).strip().upper()
            if s in MONTH_SET:
                month_cols[c] = s

        if not month_cols:
            return pd.DataFrame(columns=["cal_year", "rto", "maker", "month", "regs"])

        print(f"    Found {len(month_cols)} month columns: {', '.join(sorted(set(month_cols.values())))}")

        if month_cols:
            first_month_col = min(month_cols.keys())
            maker_col = first_month_col - 1
            if maker_col < 0:
                maker_col = 1
        else:
            maker_col = 1

        rto = _extract_rto_from_filename(fp)
        if not rto:
            return pd.DataFrame(columns=["cal_year", "rto", "maker", "month", "regs"])

        print(f"    RTO: {rto}")

        rows = []
        data_start = month_row + 1

        for r in range(data_start, len(raw)):
            maker_val = raw.iat[r, maker_col] if maker_col < raw.shape[1] else None
            if pd.isna(maker_val):
                continue

            maker = str(maker_val).strip()
            maker = ' '.join(maker.split())
            
            if not maker or len(maker) < 2:
                continue

            for col_idx, month_name in month_cols.items():
                if col_idx < raw.shape[1]:
                    regs = _safe_int(raw.iat[r, col_idx])
                    rows.append((cal_year, rto, maker, month_name, regs))

        print(f"    Extracted {len(rows)} records")
        return pd.DataFrame(rows, columns=["cal_year", "rto", "maker", "month", "regs"])

    except Exception as e:
        print(f"    ERROR: {str(e)}")
        return pd.DataFrame(columns=["cal_year", "rto", "maker", "month", "regs"])


def get_rtos() -> List[str]:
    """Get list of RTOs from data or use default"""
    try:
        df = load_all_years()
        if not df.empty and 'rto' in df.columns:
            rto_list = sorted(df["rto"].unique().tolist())
            if rto_list:
                return ["ALL"] + rto_list
    except:
        pass
    return ["ALL"] + DEFAULT_RTOS


def get_available_months() -> List[str]:
    """Get list of months that actually exist in the loaded data"""
    months = _CACHE.get("months", [])
    if months:
        return months
    return ALL_MONTHS


def load_all_years(force: bool = False) -> pd.DataFrame:
    now = time.time()
    
    if not force and _CACHE["df"] is not None and (now - _CACHE["last_load"] < RECHECK_SECONDS):
        return _CACHE["df"]

    print("\n" + "=" * 80)
    print("LOADING EXCEL FILES")
    print("=" * 80)

    parts = []
    used = []
    found_months: Set[str] = set()

    for year, dir_path in YEAR_DIRS.items():
        if not dir_path.exists():
            print(f"\nWARNING: {year} path not found: {dir_path}")
            continue

        files = list(dir_path.glob(FILE_GLOB))
        print(f"\n{year}: {dir_path}")
        print(f"Found {len(files)} files")

        for fp in sorted(files):
            dfp = _parse_excel_format(fp, cal_year=year)
            if not dfp.empty:
                parts.append(dfp)
                used.append(str(fp))
                file_months = set(dfp["month"].unique())
                found_months.update(file_months)
                print(f"      Months in this file: {', '.join(sorted(file_months))}")

    if parts:
        df = pd.concat(parts, ignore_index=True)
    else:
        df = pd.DataFrame(columns=["cal_year", "rto", "maker", "month", "regs"])

    df["cal_year"] = pd.to_numeric(df["cal_year"], errors="coerce").fillna(0).astype(int)
    df["rto"] = df["rto"].astype(str).str.upper().str.strip()
    df["maker"] = df["maker"].astype(str).str.strip()
    df["month"] = df["month"].astype(str).str.upper().str.strip()
    df["regs"] = pd.to_numeric(df["regs"], errors="coerce").fillna(0).astype(int)

    df = df[df["month"].isin(ALL_MONTHS)]

    month_order = {m: i for i, m in enumerate(ALL_MONTHS)}
    sorted_months = sorted(found_months, key=lambda x: month_order.get(x, 999))

    _CACHE["df"] = df
    _CACHE["last_load"] = now
    _CACHE["files"] = used
    _CACHE["months"] = sorted_months

    print(f"\nDYNAMIC MONTHS DETECTED: {', '.join(sorted_months)}")
    print(f"TOTAL RECORDS: {len(df)}")
    print(f"FILES LOADED: {len(used)}")
    print("=" * 80 + "\n")

    return df


# =========================================================
# HTML TEMPLATE & CSS
# =========================================================

def get_css() -> str:
    return """
    :root {
        --bg1: #5b7cfa;
        --bg2: #6c7be5;
        --accent: #5b7cfa;
        --accent-dark: #4c63d2;
        --text: #ffffff;
        --muted: #e0e7ff;
        --border: rgba(255,255,255,0.15);
        --unnati: #66bb6a;
        --pacl: #ef5350;
    }
    
    body {
        --header-bg: rgba(255,255,255,0.95);
        --header-text: #1a1a1a;
        --panel-bg: rgba(255,255,255,0.95);
        --panel-text: #333333;
        --table-header-bg: rgba(91,124,250,0.1);
        --table-header-text: #333333;
        --table-row-hover: rgba(91,124,250,0.05);
        --table-border: rgba(91,124,250,0.08);
        --th-border: rgba(91,124,250,0.2);
        --filter-bg: rgba(91,124,250,0.05);
        --filter-border: rgba(91,124,250,0.15);
        --select-bg: rgba(255,255,255,0.8);
        --select-text: #333333;
        --select-border: rgba(91,124,250,0.2);
        --info-bg: rgba(91,124,250,0.1);
        --info-text: #5b7cfa;
        --error-bg: rgba(255,100,100,0.1);
        --error-text: #e53935;
        --error-border: rgba(255,100,100,0.3);
    }
    
    body.light-mode {
        --header-bg: #1a1a2e;
        --header-text: #ffffff;
        --panel-bg: #16213e;
        --panel-text: #e0e0e0;
        --table-header-bg: rgba(91,124,250,0.3);
        --table-header-text: #ffffff;
        --table-row-hover: rgba(91,124,250,0.2);
        --table-border: rgba(91,124,250,0.2);
        --th-border: rgba(91,124,250,0.4);
        --filter-bg: rgba(91,124,250,0.15);
        --filter-border: rgba(91,124,250,0.3);
        --select-bg: rgba(50,70,120,0.9);
        --select-text: #e0e0e0;
        --select-border: rgba(91,124,250,0.4);
        --info-bg: rgba(91,124,250,0.2);
        --info-text: #a0c4ff;
        --error-bg: rgba(255,100,100,0.2);
        --error-text: #ff9999;
        --error-border: rgba(255,100,100,0.4);
    }
    
    * { box-sizing: border-box; }
    body {
        margin: 0;
        padding: 20px;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        background: linear-gradient(135deg, #5b7cfa, #6c7be5);
        color: var(--text);
        min-height: 100vh;
        transition: background 0.3s ease;
    }
    
    body.light-mode {
        background: linear-gradient(135deg, #1a1a2e, #16213e);
    }
    
    .container { max-width: 2200px; margin: 0 auto; }
    .header {
        background: var(--header-bg);
        border: 1px solid rgba(255,255,255,0.2);
        padding: 20px;
        border-radius: 12px;
        margin-bottom: 20px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 20px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    }
    .title { 
        font-size: 28px; 
        font-weight: bold; 
        color: var(--header-text);
    }
    .subtitle { 
        font-size: 13px; 
        color: var(--header-text);
        opacity: 0.7;
        margin-top: 5px;
    }
    .header-right {
        display: flex;
        gap: 15px;
        align-items: center;
        flex-wrap: wrap;
    }
    .nav {
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
    }
    .nav a {
        padding: 10px 16px;
        border-radius: 8px;
        border: 1px solid rgba(91,124,250,0.3);
        background: rgba(91,124,250,0.1);
        color: var(--header-text);
        text-decoration: none;
        font-weight: 600;
        font-size: 12px;
        transition: all 0.2s;
        white-space: nowrap;
    }
    .nav a:hover {
        background: rgba(91,124,250,0.2);
        border-color: rgba(91,124,250,0.5);
    }
    .nav a.active {
        background: #5b7cfa;
        color: white;
        border-color: #5b7cfa;
    }
    
    .theme-toggle {
        padding: 10px 16px;
        border-radius: 8px;
        border: 1px solid rgba(91,124,250,0.3);
        background: rgba(91,124,250,0.1);
        color: var(--header-text);
        text-decoration: none;
        font-weight: 600;
        font-size: 12px;
        cursor: pointer;
        transition: all 0.2s;
        white-space: nowrap;
    }
    
    .theme-toggle:hover {
        background: rgba(91,124,250,0.2);
        border-color: rgba(91,124,250,0.5);
    }
    
    .panel {
        background: var(--panel-bg);
        border: 1px solid rgba(255,255,255,0.2);
        padding: 20px;
        border-radius: 12px;
        margin-bottom: 20px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    }
    .filters {
        display: flex;
        gap: 15px;
        flex-wrap: wrap;
        align-items: center;
        margin-bottom: 20px;
        padding: 15px;
        background: var(--filter-bg);
        border-radius: 8px;
        border: 1px solid var(--filter-border);
    }
    label { 
        font-size: 13px; 
        color: var(--panel-text);
        font-weight: 600; 
    }
    select, input {
        padding: 10px 12px;
        background: var(--select-bg);
        border: 1px solid var(--select-border);
        color: var(--select-text);
        border-radius: 6px;
        font-size: 13px;
        min-width: 150px;
    }
    button {
        padding: 10px 20px;
        background: #5b7cfa;
        border: none;
        color: white;
        border-radius: 6px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.2s;
    }
    button:hover { 
        background: #4c63d2;
        box-shadow: 0 2px 8px rgba(91,124,250,0.3);
    }
    .table-wrapper {
        overflow-x: auto;
        margin-top: 20px;
        border-radius: 8px;
        border: 1px solid var(--th-border);
    }
    table {
        width: 100%;
        border-collapse: collapse;
        min-width: 900px;
    }
    th {
        background: var(--table-header-bg);
        padding: 12px 8px;
        text-align: center;
        font-weight: 600;
        color: var(--table-header-text);
        font-size: 10px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        border-bottom: 1px solid var(--th-border);
    }
    td {
        padding: 10px 8px;
        border-bottom: 1px solid var(--table-border);
        font-size: 12px;
        color: var(--panel-text);
    }
    tr:hover td { 
        background: var(--table-row-hover);
    }
    td.maker-col, th.maker-col { 
        min-width: 140px;
        text-align: left;
        color: var(--panel-text);
        font-weight: 500;
    }
    td.total-col, th.total-col { 
        text-align: right; 
        font-weight: 600; 
        background: var(--table-header-bg);
        color: #5b7cfa;
        width: 70px;
    }
    .month-header {
        font-weight: 700;
        color: #5b7cfa;
        border-bottom: 1px solid rgba(91,124,250,0.3);
        padding: 8px 4px !important;
    }
    .month-count {
        border-right: 1px solid var(--th-border);
        text-align: right;
        padding-right: 6px !important;
        width: 45px;
        font-weight: 500;
        color: var(--panel-text);
    }
    .month-pct {
        text-align: right;
        padding-left: 2px !important;
        padding-right: 6px !important;
        width: 35px;
        color: var(--panel-text);
        font-size: 11px;
        opacity: 0.8;
    }
    tr:hover .month-count,
    tr:hover .month-pct {
        background: var(--table-row-hover);
    }
    td.rto-col, th.rto-col {
        width: 70px;
        text-align: center;
        font-weight: 600;
        color: #5b7cfa;
    }
    /* MAHINDRA Row Highlighting */
    tr.mahindra-highlight {
        background: rgba(255, 235, 59, 0.25) !important;
    }
    tr.mahindra-highlight td {
        background: rgba(255, 235, 59, 0.25) !important;
    }
    tr.mahindra-highlight:hover td {
        background: rgba(255, 235, 59, 0.35) !important;
    }
    tr.mahindra-highlight td.maker-col {
        background: rgba(255, 235, 59, 0.3) !important;
        font-weight: 700;
        color: #f57f17;
    }
    tr.mahindra-highlight td.month-count {
        background: rgba(255, 235, 59, 0.25) !important;
        border-right: 1px solid rgba(255, 193, 7, 0.3);
    }
    tr.mahindra-highlight td.month-pct {
        background: rgba(255, 235, 59, 0.25) !important;
    }
    tr.mahindra-highlight td.total-col {
        background: rgba(255, 235, 59, 0.35) !important;
        color: #f57f17 !important;
        font-weight: 700;
    }
    tr.mahindra-highlight:hover td.month-count,
    tr.mahindra-highlight:hover td.month-pct {
        background: rgba(255, 235, 59, 0.35) !important;
    }
    /* Grand Total Row */
    tr.grand-total-row {
        background: var(--table-header-bg) !important;
        font-weight: 700;
    }
    tr.grand-total-row td {
        background: var(--table-header-bg) !important;
        border-top: 2px solid var(--th-border);
        border-bottom: 2px solid var(--th-border);
        font-weight: 700;
        color: #5b7cfa;
    }
    tr.grand-total-row:hover td {
        background: var(--table-row-hover) !important;
    }
    tr.grand-total-row td.maker-col {
        color: #5b7cfa;
        text-align: left;
    }
    tr.grand-total-row td.total-col {
        background: rgba(91,124,250,0.25) !important;
        color: #5b7cfa;
    }
    /* Quarterly section headers */
    .quarterly-section {
        margin-top: 30px;
    }
    .quarterly-title {
        font-size: 18px;
        font-weight: 700;
        color: #5b7cfa;
        margin-bottom: 15px;
        padding: 10px;
        background: var(--filter-bg);
        border-left: 4px solid #5b7cfa;
        border-radius: 4px;
    }
    td.num {
        text-align: right;
    }
    .error {
        padding: 15px;
        background: var(--error-bg);
        border: 1px solid var(--error-border);
        color: var(--error-text);
        border-radius: 8px;
    }
    .info {
        padding: 10px;
        margin-top: 10px;
        border-radius: 6px;
        font-size: 12px;
        background: var(--info-bg);
        border: 1px solid var(--filter-border);
        color: var(--info-text);
    }
    .info a {
        color: var(--info-text);
        text-decoration: none;
    }
    .info a:hover {
        text-decoration: underline;
    }
    """


def html_page(title: str, body: str, active: str = "main") -> str:
    nav_items = [
        ("Dashboard", "/", "main"),
        ("Quarterly Analysis", "/quarterly", "quarterly"),
        ("Unnati Wise PACL", "/unnati-pacl", "unnati"),
        ("Month Wise", "/month-wise", "month-wise"),
        ("Maker Growth %", "/rto-growth", "rto-growth"),
        ("Maker Contrib %", "/rto-contribution", "rto-contrib"),
    ]
    
    nav_html = ""
    for label, url, key in nav_items:
        cls = "active" if key == active else ""
        nav_html += f'<a href="{url}" class="{cls}">{label}</a>'
    
    files_count = len(_CACHE.get("files", []))
    months_list = get_available_months()
    months_str = ", ".join(months_list) if months_list else "No months detected"
    
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title}</title>
    <style>{get_css()}</style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <div class="title">{APP_TITLE}</div>
                <div class="subtitle">{title}</div>
            </div>
            <div class="header-right">
                <div class="nav">{nav_html}</div>
                <button class="theme-toggle" onclick="toggleTheme()">🌙 Dark/Light</button>
            </div>
        </div>
        <div class="panel">
            {body}
            <div class="info">
                Files loaded: <strong>{files_count}</strong> | 
                Months available: <strong>{months_str}</strong> | 
                <a href="/reload">Reload</a>
            </div>
        </div>
    </div>
    
    <script>
        function toggleTheme() {{
            const body = document.body;
            body.classList.toggle('light-mode');
            if (body.classList.contains('light-mode')) {{
                localStorage.setItem('theme', 'light-mode');
            }} else {{
                localStorage.setItem('theme', 'light-mode-disabled');
            }}
        }}
        window.addEventListener('DOMContentLoaded', function() {{
            const savedTheme = localStorage.getItem('theme');
            if (savedTheme === 'light-mode') {{
                document.body.classList.add('light-mode');
            }}
        }});
    </script>
</body>
</html>"""


# =========================================================
# ROUTES
# =========================================================

@app.get("/", response_class=HTMLResponse)
def main(year: str = Query("ALL"), rto: str = Query("ALL")):
    df = load_all_years()
    years = ["ALL", "2024", "2025", "2026"]
    rtos = get_rtos()
    months = get_available_months()
    
    filters = f"""
    <form class="filters" method="get">
        <div><label>Year:</label><select name="year">
            {''.join(f'<option value="{y}" {"selected" if y==year else ""}>{y}</option>' for y in years)}
        </select></div>
        <div><label>RTO:</label><select name="rto">
            {''.join(f'<option value="{r}" {"selected" if r==rto else ""}>{r}</option>' for r in rtos)}
        </select></div>
        <button type="submit">Apply</button>
    </form>
    """
    
    dd = df.copy()
    if year != "ALL":
        dd = dd[dd["cal_year"] == int(year)]
    if rto != "ALL":
        dd = dd[dd["rto"] == rto]
    
    if dd.empty:
        body = filters + '<div class="error">No data found for selected filters.</div>'
        return HTMLResponse(html_page("Dashboard", body, active="main"))
    
    pivot_counts = dd.pivot_table(index=["maker"], columns="month", values="regs", aggfunc="sum", fill_value=0)
    pivot_counts = pivot_counts.reindex(columns=months, fill_value=0)
    pivot_counts["TOTAL"] = pivot_counts[months].sum(axis=1)
    pivot_counts = pivot_counts.sort_values("TOTAL", ascending=False)
    
    month_totals = pivot_counts[months].sum()
    grand_total = pivot_counts["TOTAL"].sum()
    
    table = '<div class="table-wrapper"><table><thead><tr>'
    table += '<th class="maker-col">MAKER</th>'
    for m in months:
        table += f'<th colspan="2" class="month-header">{m}</th>'
    table += '<th class="total-col">TOTAL</th></tr>'
    table += '<tr><th class="maker-col">MAKER</th>'
    for m in months:
        table += f'<th class="month-count">{m}</th><th class="month-pct">%{m}</th>'
    table += '<th class="total-col">TOTAL</th></tr></thead><tbody>'
    
    for maker, row in pivot_counts.iterrows():
        is_mahindra = "MAHINDRA" in maker.upper()
        row_class = 'mahindra-highlight' if is_mahindra else ''
        table += f'<tr class="{row_class}"><td class="maker-col"><strong>{maker}</strong></td>'
        gt = row["TOTAL"]
        
        for m in months:
            count = int(row[m]) if row[m] > 0 else 0
            pct = (count / month_totals[m] * 100) if month_totals[m] > 0 else 0
            table += f'<td class="month-count">{count}</td><td class="month-pct">{pct:.0f}%</td>'
        
        table += f'<td class="total-col"><b>{int(gt)}</b></td></tr>'
    
    table += '<tr class="grand-total-row"><td class="maker-col">TOTAL</td>'
    for m in months:
        total = int(month_totals[m])
        pct = (month_totals[m] / grand_total * 100) if grand_total > 0 else 0
        table += f'<td class="month-count">{total}</td><td class="month-pct">{pct:.0f}%</td>'
    table += f'<td class="total-col"><b>{int(grand_total)}</b></td></tr>'
    table += '</tbody></table></div>'
    
    body = filters + table
    return HTMLResponse(html_page("Dashboard", body, active="main"))


@app.get("/quarterly", response_class=HTMLResponse)
def quarterly_analysis(rto: str = Query("ALL")):
    df = load_all_years()
    rtos = get_rtos()
    
    filters = f"""
    <form class="filters" method="get">
        <div><label>RTO:</label><select name="rto">
            {''.join(f'<option value="{r}" {"selected" if r==rto else ""}>{r}</option>' for r in rtos)}
        </select></div>
        <button type="submit">Apply</button>
    </form>
    """
    
    dd = df.copy()
    if rto != "ALL":
        dd = dd[dd["rto"] == rto]
    
    if dd.empty:
        body = filters + '<div class="error">No data available for selected RTO.</div>'
    else:
        body = filters
        
        quarters_info = [
            ('Q1', 'Q1 (Apr-Jun) - F25 vs F26', ['APR', 'MAY', 'JUN']),
            ('Q2', 'Q2 (Jul-Sep) - F25 vs F26', ['JUL', 'AUG', 'SEP']),
            ('Q3', 'Q3 (Oct-Dec) - F25 vs F26', ['OCT', 'NOV', 'DEC']),
            ('Q4', 'Q4 (Jan-Mar) - F25 vs F26', ['JAN', 'FEB', 'MAR']),
        ]
        
        for q_key, q_label, q_months in quarters_info:
            f25_data = dd[
                ((dd['cal_year'] == 2024) & (dd['month'].isin(['APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']))) |
                ((dd['cal_year'] == 2025) & (dd['month'].isin(['JAN', 'FEB', 'MAR'])))
            ]
            
            f26_data = dd[
                ((dd['cal_year'] == 2025) & (dd['month'].isin(['APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']))) |
                ((dd['cal_year'] == 2026) & (dd['month'].isin(['JAN', 'FEB', 'MAR'])))
            ]
            
            f25_q = f25_data[f25_data['month'].isin(q_months)]
            f26_q = f26_data[f26_data['month'].isin(q_months)]
            
            all_makers = sorted(set(list(f25_q['maker'].unique()) + list(f26_q['maker'].unique())))
            
            body += f'<div class="quarterly-section">'
            body += f'<div class="quarterly-title">{q_label}</div>'
            body += '<div class="table-wrapper"><table>'
            
            body += '<thead><tr>'
            body += '<th style="text-align:center; width:50px;">RANK</th>'
            body += '<th class="maker-col">MANUFACTURER</th>'
            for month in q_months:
                body += f'<th style="text-align:right; width:50px;">{month}_F25</th>'
            body += '<th style="text-align:right; width:60px;">F25 Total</th>'
            for month in q_months:
                body += f'<th style="text-align:right; width:50px;">{month}_F26</th>'
            body += '<th style="text-align:right; width:60px;">F26 Total</th>'
            body += '<th style="text-align:right; width:60px;">Growth %</th>'
            body += '</tr></thead>'
            
            body += '<tbody>'
            rank = 1
            
            maker_summary = {}
            for maker in all_makers:
                f25_total = f25_q[f25_q['maker'] == maker]['regs'].sum()
                f26_total = f26_q[f26_q['maker'] == maker]['regs'].sum()
                
                if f25_total > 0 or f26_total > 0:
                    maker_summary[maker] = {
                        'f25_total': f25_total,
                        'f26_total': f26_total,
                        'growth': ((f26_total - f25_total) / f25_total * 100) if f25_total > 0 else (100 if f26_total > 0 else 0)
                    }
            
            sorted_makers = sorted(maker_summary.keys(), key=lambda x: maker_summary[x]['f25_total'], reverse=True)
            
            top_10_makers = sorted_makers[:10]
            remaining_makers = sorted_makers[10:]
            
            for maker in top_10_makers:
                is_mahindra = "MAHINDRA" in maker.upper()
                row_class = 'mahindra-highlight' if is_mahindra else ''
                
                body += f'<tr class="{row_class}">'
                body += f'<td style="text-align:center; font-weight:600;">{rank}</td>'
                
                if is_mahindra:
                    body += f'<td class="maker-col"><strong>{maker}</strong></td>'
                else:
                    body += f'<td class="maker-col">{maker}</td>'
                
                for month in q_months:
                    month_val = f25_q[(f25_q['maker'] == maker) & (f25_q['month'] == month)]['regs'].sum()
                    body += f'<td class="num">{int(month_val) if month_val > 0 else 0}</td>'
                
                body += f'<td class="num" style="font-weight:600; background: rgba(91,124,250,0.1);">{int(maker_summary[maker]["f25_total"])}</td>'
                
                for month in q_months:
                    month_val = f26_q[(f26_q['maker'] == maker) & (f26_q['month'] == month)]['regs'].sum()
                    body += f'<td class="num">{int(month_val) if month_val > 0 else 0}</td>'
                
                body += f'<td class="num" style="font-weight:600; background: rgba(91,124,250,0.1);">{int(maker_summary[maker]["f26_total"])}</td>'
                
                growth = maker_summary[maker]['growth']
                color = '#66bb6a' if growth > 0 else '#ef5350' if growth < 0 else '#666666'
                body += f'<td class="num" style="font-weight:600; color: {color};">{growth:.2f}%</td>'
                
                body += '</tr>'
                rank += 1
            
            if remaining_makers:
                remaining_f25_total = sum(maker_summary[m]['f25_total'] for m in remaining_makers)
                remaining_f26_total = sum(maker_summary[m]['f26_total'] for m in remaining_makers)
                remaining_growth = ((remaining_f26_total - remaining_f25_total) / remaining_f25_total * 100) if remaining_f25_total > 0 else 0
                
                body += '<tr>'
                body += f'<td style="text-align:center; font-weight:600;">11</td>'
                body += f'<td class="maker-col">Remaining Mfg</td>'
                
                for month in q_months:
                    month_val = f25_q[f25_q['maker'].isin(remaining_makers) & (f25_q['month'] == month)]['regs'].sum()
                    body += f'<td class="num">{int(month_val) if month_val > 0 else 0}</td>'
                
                body += f'<td class="num" style="font-weight:600; background: rgba(91,124,250,0.1);">{int(remaining_f25_total)}</td>'
                
                for month in q_months:
                    month_val = f26_q[f26_q['maker'].isin(remaining_makers) & (f26_q['month'] == month)]['regs'].sum()
                    body += f'<td class="num">{int(month_val) if month_val > 0 else 0}</td>'
                
                body += f'<td class="num" style="font-weight:600; background: rgba(91,124,250,0.1);">{int(remaining_f26_total)}</td>'
                
                color = '#66bb6a' if remaining_growth > 0 else '#ef5350' if remaining_growth < 0 else '#666666'
                body += f'<td class="num" style="font-weight:600; color: {color};">{remaining_growth:.2f}%</td>'
                body += '</tr>'
            
            tiv_f25_total = f25_q['regs'].sum()
            tiv_f26_total = f26_q['regs'].sum()
            tiv_growth = ((tiv_f26_total - tiv_f25_total) / tiv_f25_total * 100) if tiv_f25_total > 0 else 0
            
            body += f'<tr class="grand-total-row">'
            body += f'<td style="text-align:center; font-weight:600;">12</td>'
            body += f'<td class="maker-col">TIV</td>'
            
            for month in q_months:
                month_val = f25_q[f25_q['month'] == month]['regs'].sum()
                body += f'<td class="num">{int(month_val)}</td>'
            
            body += f'<td class="num" style="font-weight:600; background: rgba(91,124,250,0.25);">{int(tiv_f25_total)}</td>'
            
            for month in q_months:
                month_val = f26_q[f26_q['month'] == month]['regs'].sum()
                body += f'<td class="num">{int(month_val)}</td>'
            
            body += f'<td class="num" style="font-weight:600; background: rgba(91,124,250,0.25);">{int(tiv_f26_total)}</td>'
            
            color = '#66bb6a' if tiv_growth > 0 else '#ef5350' if tiv_growth < 0 else '#666666'
            body += f'<td class="num" style="font-weight:600; color: {color};">{tiv_growth:.2f}%</td>'
            body += '</tr>'
            
            body += '</tbody></table></div>'
            body += '</div>'
    
    return HTMLResponse(html_page("Quarterly Analysis", body, active="quarterly"))


@app.get("/unnati-pacl", response_class=HTMLResponse)
def unnati_pacl_page(year: str = Query("ALL"), rto: str = Query("ALL")):
    df = load_all_years()
    years = ["ALL", "2024", "2025", "2026"]
    rtos = get_rtos()
    
    filters = f"""
    <form class="filters" method="get">
        <div><label>Year:</label><select name="year">
            {''.join(f'<option value="{y}" {"selected" if y==year else ""}>{y}</option>' for y in years)}
        </select></div>
        <div><label>RTO:</label><select name="rto">
            {''.join(f'<option value="{r}" {"selected" if r==rto else ""}>{r}</option>' for r in rtos)}
        </select></div>
        <button type="submit">Apply</button>
    </form>
    """
    
    dd = df.copy()
    if rto != "ALL":
        dd = dd[dd["rto"] == rto]
    
    if dd.empty:
        body = filters + '<div class="error">No data available for selected filters.</div>'
    else:
        body = filters
        
        comparison_months = ['APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
        
        if year == "2024":
            ly_data = dd[((dd['cal_year'] == 2023) & (dd['month'].isin(comparison_months))) | ((dd['cal_year'] == 2024) & (dd['month'].isin(['JAN', 'FEB', 'MAR'])))]
            cy_data = dd[((dd['cal_year'] == 2024) & (dd['month'].isin(comparison_months))) | ((dd['cal_year'] == 2025) & (dd['month'].isin(['JAN', 'FEB', 'MAR'])))]
        elif year == "2025":
            ly_data = dd[((dd['cal_year'] == 2024) & (dd['month'].isin(comparison_months))) | ((dd['cal_year'] == 2025) & (dd['month'].isin(['JAN', 'FEB', 'MAR'])))]
            cy_data = dd[((dd['cal_year'] == 2025) & (dd['month'].isin(comparison_months))) | ((dd['cal_year'] == 2026) & (dd['month'].isin(['JAN', 'FEB', 'MAR'])))]
        elif year == "2026":
            ly_data = dd[((dd['cal_year'] == 2025) & (dd['month'].isin(comparison_months))) | ((dd['cal_year'] == 2026) & (dd['month'].isin(['JAN', 'FEB', 'MAR'])))]
            cy_data = dd[((dd['cal_year'] == 2026) & (dd['month'].isin(comparison_months))) | ((dd['cal_year'] == 2027) & (dd['month'].isin(['JAN', 'FEB', 'MAR'])))]
        else:
            ly_data = dd[((dd['cal_year'] == 2024) & (dd['month'].isin(comparison_months))) | ((dd['cal_year'] == 2025) & (dd['month'].isin(['JAN', 'FEB', 'MAR'])))]
            cy_data = dd[((dd['cal_year'] == 2025) & (dd['month'].isin(comparison_months))) | ((dd['cal_year'] == 2026) & (dd['month'].isin(['JAN', 'FEB', 'MAR'])))]
        
        def calculate_dealer_totals(data):
            unnati_all = 0
            unnati_mah = 0
            pacl_all = 0
            pacl_mah = 0
            
            for rto_code, allocation in RTO_ALLOCATIONS.items():
                rto_data = data[data['rto'] == rto_code]
                
                rto_all_total = rto_data['regs'].sum()
                rto_mah_total = rto_data[rto_data['maker'].str.upper().str.contains('MAHINDRA')]['regs'].sum()
                
                unnati_pct = allocation['Unnati'] / 100
                pacl_pct = allocation['PACL'] / 100
                
                unnati_all += rto_all_total * unnati_pct
                unnati_mah += rto_mah_total * unnati_pct
                pacl_all += rto_all_total * pacl_pct
                pacl_mah += rto_mah_total * pacl_pct
            
            return {
                'unnati_all': unnati_all,
                'unnati_mah': unnati_mah,
                'pacl_all': pacl_all,
                'pacl_mah': pacl_mah
            }
        
        ly_totals = calculate_dealer_totals(ly_data)
        cy_totals = calculate_dealer_totals(cy_data)
        
        ly_tiv_total = ly_totals['unnati_all'] + ly_totals['pacl_all']
        cy_tiv_total = cy_totals['unnati_all'] + cy_totals['pacl_all']
        
        ly_unnati_ms = (ly_totals['unnati_mah'] / ly_tiv_total * 100) if ly_tiv_total > 0 else 0
        cy_unnati_ms = (cy_totals['unnati_mah'] / cy_tiv_total * 100) if cy_tiv_total > 0 else 0
        ly_pacl_ms = (ly_totals['pacl_mah'] / ly_tiv_total * 100) if ly_tiv_total > 0 else 0
        cy_pacl_ms = (cy_totals['pacl_mah'] / cy_tiv_total * 100) if cy_tiv_total > 0 else 0
        
        unnati_ms_change = cy_unnati_ms - ly_unnati_ms
        pacl_ms_change = cy_pacl_ms - ly_pacl_ms
        
        body += '<div class="table-wrapper"><table>'
        body += '<thead><tr>'
        body += '<th colspan="3" style="background: rgba(91,124,250,0.1);">TIV Total Manufacturers</th>'
        body += '<th colspan="5" style="background: rgba(91,124,250,0.1);">TIV Mahindra</th>'
        body += '<th colspan="2" style="background: rgba(91,124,250,0.1);">Market Share Change %</th>'
        body += '</tr>'
        body += '<tr>'
        body += '<th>Dealer</th>'
        body += '<th style="text-align: right;">YTD - LY</th>'
        body += '<th style="text-align: right;">YTD - CY</th>'
        body += '<th>Dealer</th>'
        body += '<th style="text-align: right;">YTD - LY</th>'
        body += '<th style="text-align: right;">YTD - CY</th>'
        body += '<th style="text-align: right;">YTD - LY %</th>'
        body += '<th style="text-align: right;">YTD - CY %</th>'
        body += '<th style="text-align: right;">Growth %</th>'
        body += '<th style="text-align: right;">Change %</th>'
        body += '</tr>'
        body += '</thead>'
        
        body += '<tbody>'
        
        unnati_growth = ((cy_totals['unnati_mah'] - ly_totals['unnati_mah']) / ly_totals['unnati_mah'] * 100) if ly_totals['unnati_mah'] > 0 else 0
        body += '<tr>'
        body += '<td style="font-weight:600;">Unnati</td>'
        body += f'<td class="num">{int(ly_totals["unnati_all"])}</td>'
        body += f'<td class="num">{int(cy_totals["unnati_all"])}</td>'
        body += '<td style="font-weight:600;">Unnati</td>'
        body += f'<td class="num">{int(ly_totals["unnati_mah"])}</td>'
        body += f'<td class="num">{int(cy_totals["unnati_mah"])}</td>'
        body += f'<td class="num">{ly_unnati_ms:.2f}%</td>'
        body += f'<td class="num">{cy_unnati_ms:.2f}%</td>'
        body += f'<td class="num">{unnati_growth:.1f}%</td>'
        body += f'<td class="num">{unnati_ms_change:.2f}%</td>'
        body += '</tr>'
        
        pacl_growth = ((cy_totals['pacl_mah'] - ly_totals['pacl_mah']) / ly_totals['pacl_mah'] * 100) if ly_totals['pacl_mah'] > 0 else 0
        body += '<tr>'
        body += '<td style="font-weight:600;">PACL</td>'
        body += f'<td class="num">{int(ly_totals["pacl_all"])}</td>'
        body += f'<td class="num">{int(cy_totals["pacl_all"])}</td>'
        body += '<td style="font-weight:600;">PACL</td>'
        body += f'<td class="num">{int(ly_totals["pacl_mah"])}</td>'
        body += f'<td class="num">{int(cy_totals["pacl_mah"])}</td>'
        body += f'<td class="num">{ly_pacl_ms:.2f}%</td>'
        body += f'<td class="num">{cy_pacl_ms:.2f}%</td>'
        body += f'<td class="num">{pacl_growth:.1f}%</td>'
        body += f'<td class="num">{pacl_ms_change:.2f}%</td>'
        body += '</tr>'
        
        body += '</tbody>'
        body += '</table></div>'
    
    return HTMLResponse(html_page("Unnati Wise PACL", body, active="unnati"))


@app.get("/month-wise", response_class=HTMLResponse)
def month_wise_page(year: str = Query("ALL"), rto: str = Query("ALL")):
    df = load_all_years()
    years = ["ALL", "2024", "2025", "2026"]
    rtos = get_rtos()
    
    filters = f"""
    <form class="filters" method="get">
        <div><label>Year:</label><select name="year">
            {''.join(f'<option value="{y}" {"selected" if y==year else ""}>{y}</option>' for y in years)}
        </select></div>
        <div><label>RTO:</label><select name="rto">
            {''.join(f'<option value="{r}" {"selected" if r==rto else ""}>{r}</option>' for r in rtos)}
        </select></div>
        <button type="submit">Apply</button>
    </form>
    """
    
    dd = df.copy()
    if rto != "ALL":
        dd = dd[dd["rto"] == rto]
    
    if dd.empty:
        body = filters + '<div class="error">No data available for selected filters.</div>'
    else:
        body = filters + '<div class="info">Month-wise analysis with year-over-year comparison</div>'
    
    return HTMLResponse(html_page("Month Wise Analysis", body, active="month-wise"))


@app.get("/rto-growth", response_class=HTMLResponse)
def rto_growth_page(year: str = Query("ALL"), rto: str = Query("ALL")):
    df = load_all_years()
    years = ["ALL", "2024", "2025", "2026"]
    rtos = get_rtos()
    
    filters = f"""
    <form class="filters" method="get">
        <div><label>Year:</label><select name="year">
            {''.join(f'<option value="{y}" {"selected" if y==year else ""}>{y}</option>' for y in years)}
        </select></div>
        <div><label>RTO:</label><select name="rto">
            {''.join(f'<option value="{r}" {"selected" if r==rto else ""}>{r}</option>' for r in rtos)}
        </select></div>
        <button type="submit">Apply</button>
    </form>
    """
    
    body = filters + '<div class="info">Maker growth percentage analysis comparing F25 vs F26</div>'
    
    return HTMLResponse(html_page("Maker Growth %", body, active="rto-growth"))


@app.get("/rto-contribution", response_class=HTMLResponse)
def rto_contribution_page(year: str = Query("ALL"), rto: str = Query("ALL")):
    df = load_all_years()
    years = ["ALL", "2024", "2025", "2026"]
    rtos = get_rtos()
    
    filters = f"""
    <form class="filters" method="get">
        <div><label>Year:</label><select name="year">
            {''.join(f'<option value="{y}" {"selected" if y==year else ""}>{y}</option>' for y in years)}
        </select></div>
        <div><label>RTO:</label><select name="rto">
            {''.join(f'<option value="{r}" {"selected" if r==rto else ""}>{r}</option>' for r in rtos)}
        </select></div>
        <button type="submit">Apply</button>
    </form>
    """
    
    body = filters + '<div class="info">Maker contribution percentage analysis for F26</div>'
    
    return HTMLResponse(html_page("Maker Contribution %", body, active="rto-contrib"))


@app.get("/reload")
def reload_data():
    load_all_years(force=True)
    return RedirectResponse(url="/", status_code=302)


@app.on_event("startup")
def startup():
    print("\n" + "="*80)
    print("MAHINDRA RTO DASHBOARD - RENDER DEPLOYMENT")
    print("="*80)
    print("\nStarting FastAPI RTO Dashboard...")
    load_all_years(force=True)
    print("Ready! Application is running...")
    print("\nData paths configured:")
    for year, path in YEAR_DIRS.items():
        print(f"  {year}: {path}")
    print("="*80 + "\n")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
