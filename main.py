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
# CONFIG - YOUR LOCAL WINDOWS PATHS
# =========================================================
APP_TITLE = "Mahindra Personal RTO Dashboard"

# YOUR SPECIFIC WINDOWS PATHS
YEAR_DIRS: Dict[int, Path] = {
    2024: Path(r"D:\PythonCodes\xl\MahindraPersonal"),
    2025: Path(r"D:\PythonCodes\xl\MahindraPersonal25"),
    2026: Path(r"D:\PythonCodes\xl\MahindraPersonal26"),
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

# Add CORS middleware
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
    print("LOADING EXCEL FILES FROM YOUR WINDOWS PATHS")
    print("=" * 80)

    parts = []
    used = []
    found_months: Set[str] = set()

    for year, dir_path in YEAR_DIRS.items():
        print(f"\nYear: {year}")
        print(f"Path: {dir_path}")
        
        if not dir_path.exists():
            print(f"WARNING: Path does not exist: {dir_path}")
            continue

        files = list(dir_path.glob(FILE_GLOB))
        print(f"Found {len(files)} Excel files")

        if len(files) == 0:
            print(f"  No MH*.xlsx files found in {dir_path}")
            continue

        for fp in sorted(files):
            print(f"\n  Processing: {fp.name}")
            dfp = _parse_excel_format(fp, cal_year=year)
            if not dfp.empty:
                parts.append(dfp)
                used.append(str(fp))
                file_months = set(dfp["month"].unique())
                found_months.update(file_months)
                print(f"    ✓ Successfully loaded {len(dfp)} records")
            else:
                print(f"    ✗ Could not parse this file")

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

    print(f"\n✓ LOADING COMPLETE")
    print(f"  Months detected: {', '.join(sorted_months)}")
    print(f"  Total records: {len(df)}")
    print(f"  Files loaded: {len(used)}")
    print("=" * 80 + "\n")

    return df


# =========================================================
# HTML TEMPLATE & CSS
# =========================================================

def get_css() -> str:
    return """
    * { box-sizing: border-box; }
    body {
        margin: 0;
        padding: 20px;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        background: linear-gradient(135deg, #5b7cfa, #6c7be5);
        color: #ffffff;
        min-height: 100vh;
    }
    .container { max-width: 2200px; margin: 0 auto; }
    .header {
        background: rgba(255,255,255,0.95);
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
        color: #1a1a1a;
    }
    .subtitle { 
        font-size: 13px; 
        color: #1a1a1a;
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
        color: #1a1a1a;
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
        color: #1a1a1a;
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
        background: rgba(255,255,255,0.95);
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
        background: rgba(91,124,250,0.05);
        border-radius: 8px;
        border: 1px solid rgba(91,124,250,0.15);
    }
    label { 
        font-size: 13px; 
        color: #333333;
        font-weight: 600; 
    }
    select, input {
        padding: 10px 12px;
        background: rgba(255,255,255,0.8);
        border: 1px solid rgba(91,124,250,0.2);
        color: #333333;
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
        border: 1px solid rgba(91,124,250,0.2);
    }
    table {
        width: 100%;
        border-collapse: collapse;
        min-width: 900px;
    }
    th {
        background: rgba(91,124,250,0.1);
        padding: 12px 8px;
        text-align: center;
        font-weight: 600;
        color: #333333;
        font-size: 10px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        border-bottom: 1px solid rgba(91,124,250,0.2);
    }
    td {
        padding: 10px 8px;
        border-bottom: 1px solid rgba(91,124,250,0.08);
        font-size: 12px;
        color: #333333;
    }
    tr:hover td { 
        background: rgba(91,124,250,0.05);
    }
    td.maker-col, th.maker-col { 
        min-width: 140px;
        text-align: left;
        font-weight: 500;
    }
    td.total-col, th.total-col { 
        text-align: right; 
        font-weight: 600; 
        background: rgba(91,124,250,0.1);
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
        border-right: 1px solid rgba(91,124,250,0.15);
        text-align: right;
        padding-right: 6px !important;
        width: 45px;
        font-weight: 500;
    }
    .month-pct {
        text-align: right;
        padding-left: 2px !important;
        padding-right: 6px !important;
        width: 35px;
        font-size: 11px;
        opacity: 0.8;
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
    tr.mahindra-highlight td.total-col {
        background: rgba(255, 235, 59, 0.35) !important;
        color: #f57f17 !important;
        font-weight: 700;
    }
    /* Grand Total Row */
    tr.grand-total-row {
        background: rgba(91,124,250,0.1) !important;
        font-weight: 700;
    }
    tr.grand-total-row td {
        background: rgba(91,124,250,0.1) !important;
        border-top: 2px solid rgba(91,124,250,0.2);
        border-bottom: 2px solid rgba(91,124,250,0.2);
        font-weight: 700;
        color: #5b7cfa;
    }
    tr.grand-total-row:hover td {
        background: rgba(91,124,250,0.15) !important;
    }
    .error {
        padding: 15px;
        background: rgba(255,100,100,0.1);
        border: 1px solid rgba(255,100,100,0.3);
        color: #e53935;
        border-radius: 8px;
    }
    .info {
        padding: 10px;
        margin-top: 10px;
        border-radius: 6px;
        font-size: 12px;
        background: rgba(91,124,250,0.1);
        border: 1px solid rgba(91,124,250,0.15);
        color: #5b7cfa;
    }
    .info a {
        color: #5b7cfa;
        text-decoration: none;
        font-weight: 600;
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
                <button class="theme-toggle" onclick="alert('Theme toggle - coming soon')">🌙 Theme</button>
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
    
    body = filters + '<div class="info">Quarterly analysis comparing F25 (Apr2024-Mar2025) vs F26 (Apr2025-Mar2026)</div>'
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
    
    body = filters + '<div class="info">Unnati vs PACL dealer allocation analysis</div>'
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
    
    body = filters + '<div class="info">Maker growth percentage analysis</div>'
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
    
    body = filters + '<div class="info">Maker contribution percentage analysis</div>'
    return HTMLResponse(html_page("Maker Contribution %", body, active="rto-contrib"))


@app.get("/reload")
def reload_data():
    load_all_years(force=True)
    return RedirectResponse(url="/", status_code=302)


@app.on_event("startup")
def startup():
    print("\n" + "="*80)
    print("MAHINDRA RTO DASHBOARD - STARTING")
    print("="*80)
    print("\nLoading data from your Windows paths...")
    print(f"2024: {YEAR_DIRS[2024]}")
    print(f"2025: {YEAR_DIRS[2025]}")
    print(f"2026: {YEAR_DIRS[2026]}")
    load_all_years(force=True)
    print("\n✓ Dashboard ready! Visit: http://localhost:8000")
    print("="*80 + "\n")


if __name__ == "__main__":
    import uvicorn
    print("\n🚀 Starting Mahindra RTO Dashboard...")
    print("Open your browser to: http://localhost:8000\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
