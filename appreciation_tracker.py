"""
Property appreciation tracker by zip code for Denver metro area.

Downloads and caches Zillow Home Value Index (ZHVI) data locally,
then computes appreciation rates over configurable time windows
for any zip code. Also supports FHFA House Price Index data.

Data sources (all free, public, no API key needed):
  - Zillow ZHVI: Monthly home values by zip code (2000-present)
  - FHFA HPI: Annual house price index by zip code

Usage:
    python appreciation_tracker.py --sync                          # download latest data
    python appreciation_tracker.py --zip 80202                     # Denver downtown
    python appreciation_tracker.py --zip 80104 --years 5           # Castle Rock, 5yr
    python appreciation_tracker.py --zip 80202 80204 80211 80205   # compare zips
    python appreciation_tracker.py --county denver                 # all Denver zips
    python appreciation_tracker.py --help
"""

import argparse
import csv
import gzip
import io
import json
import os
import sys
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path


# ---------------------------------------------------------------------------
# Data directories and URLs
# ---------------------------------------------------------------------------

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
ZHVI_CSV = os.path.join(DATA_DIR, "zhvi_zip.csv")
FHFA_CSV = os.path.join(DATA_DIR, "fhfa_zip.csv")
SYNC_META = os.path.join(DATA_DIR, "sync_meta.json")

ZHVI_URL = "https://files.zillowstatic.com/research/public_csvs/zhvi/Zip_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv"
FHFA_URL = "https://www.fhfa.gov/hpi/download/annual/hpi_at_zip5.xlsx"

# Denver metro zip codes by county (not exhaustive, covers major areas)
COUNTY_ZIPS = {
    "denver": [
        "80202", "80203", "80204", "80205", "80206", "80207", "80209",
        "80210", "80211", "80212", "80216", "80218", "80219", "80220",
        "80222", "80223", "80224", "80227", "80230", "80231", "80236",
        "80237", "80238", "80239", "80246", "80247", "80249",
    ],
    "douglas": [
        "80104", "80108", "80109", "80124", "80125", "80126",
        "80129", "80130", "80131", "80134", "80138",
    ],
    "adams": [
        "80020", "80021", "80022", "80023", "80024", "80030", "80031",
        "80221", "80229", "80233", "80234", "80241", "80260",
        "80601", "80602", "80603", "80640", "80642",
    ],
    "arapahoe": [
        "80010", "80011", "80012", "80013", "80014", "80015", "80016",
        "80017", "80018", "80110", "80111", "80112", "80113",
        "80120", "80121", "80122",
    ],
    "jefferson": [
        "80002", "80003", "80004", "80005", "80033", "80123",
        "80127", "80128", "80214", "80215", "80226", "80227",
        "80228", "80232", "80235", "80401", "80403", "80465",
    ],
}

ALL_METRO_ZIPS = sorted(set(z for zips in COUNTY_ZIPS.values() for z in zips))


# ---------------------------------------------------------------------------
# Data sync
# ---------------------------------------------------------------------------

def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def download_file(url: str, dest: str, label: str = ""):
    """Download a URL to a local file with progress."""
    ensure_data_dir()
    print(f"  Downloading {label or url}...")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (real-estate-ai-agent)"
    })
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            total = resp.headers.get("Content-Length")
            total = int(total) if total else None
            data = b""
            downloaded = 0
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                data += chunk
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    print(f"\r    {downloaded:,} / {total:,} bytes ({pct:.1f}%)", end="", flush=True)
                else:
                    print(f"\r    {downloaded:,} bytes", end="", flush=True)
            print()

        with open(dest, "wb") as f:
            f.write(data)
        print(f"  Saved to {dest} ({downloaded:,} bytes)")
        return True
    except Exception as e:
        print(f"  ERROR downloading {url}: {e}")
        return False


def sync_zhvi() -> bool:
    """Download latest Zillow ZHVI data (zip code level)."""
    return download_file(ZHVI_URL, ZHVI_CSV, "Zillow ZHVI (zip code)")


def sync_data():
    """Download all data sources."""
    ensure_data_dir()
    print(f"\n{'=' * 60}")
    print(f"  SYNCING PROPERTY APPRECIATION DATA")
    print(f"{'=' * 60}\n")

    success = sync_zhvi()

    # Save sync metadata
    meta = {
        "last_sync": datetime.now().isoformat(),
        "zhvi_synced": success,
        "zhvi_path": ZHVI_CSV,
    }
    with open(SYNC_META, "w") as f:
        json.dump(meta, f, indent=2)

    if success:
        # Count Colorado zip codes in the data
        co_count = 0
        try:
            with open(ZHVI_CSV, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("StateName", "").strip() == "CO":
                        co_count += 1
        except Exception:
            pass
        print(f"\n  Colorado zip codes in dataset: {co_count}")
        print(f"  Sync complete. Data saved to {DATA_DIR}/")
    else:
        print(f"\n  Sync failed. Check network connection.")

    print(f"{'=' * 60}")
    return success


def get_sync_age() -> str:
    """Return how old the synced data is."""
    if not os.path.exists(SYNC_META):
        return "never synced"
    try:
        with open(SYNC_META) as f:
            meta = json.load(f)
        last = datetime.fromisoformat(meta["last_sync"])
        delta = datetime.now() - last
        if delta.days == 0:
            return "today"
        elif delta.days == 1:
            return "1 day ago"
        else:
            return f"{delta.days} days ago"
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Data loading and appreciation calculation
# ---------------------------------------------------------------------------

@dataclass
class ZipAppreciation:
    zip_code: str
    city: str
    county: str
    state: str
    current_value: float
    periods: dict  # {period_label: {start_value, end_value, appreciation_pct, cagr_pct}}


def load_zhvi_for_zip(zip_code: str) -> dict | None:
    """Load ZHVI time series for a single zip code. Returns {date_str: value}."""
    if not os.path.exists(ZHVI_CSV):
        return None

    with open(ZHVI_CSV, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if str(row.get("RegionName", "")).strip().zfill(5) == zip_code:
                # Extract metadata
                meta = {
                    "city": row.get("City", ""),
                    "state": row.get("StateName", row.get("State", "")),
                    "county": row.get("CountyName", ""),
                    "metro": row.get("Metro", ""),
                }
                # Extract monthly values (columns that look like dates)
                values = {}
                for key, val in row.items():
                    if key and len(key) == 10 and key[4] == "-":
                        try:
                            if val and float(val) > 0:
                                values[key] = float(val)
                        except (ValueError, TypeError):
                            pass
                return {"meta": meta, "values": values}
    return None


def compute_appreciation(values: dict[str, float], years: int) -> dict | None:
    """Compute appreciation over N years from the latest data point."""
    if not values:
        return None

    sorted_dates = sorted(values.keys())
    end_date = sorted_dates[-1]
    end_value = values[end_date]

    # Find the closest date N years ago
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    target_dt = end_dt - timedelta(days=years * 365.25)
    target_str = target_dt.strftime("%Y-%m-%d")

    # Find closest available date
    closest = min(sorted_dates, key=lambda d: abs(
        datetime.strptime(d, "%Y-%m-%d") - target_dt
    ))
    start_value = values[closest]

    if start_value <= 0:
        return None

    total_pct = (end_value - start_value) / start_value * 100
    # CAGR
    actual_years = (end_dt - datetime.strptime(closest, "%Y-%m-%d")).days / 365.25
    if actual_years > 0:
        cagr = ((end_value / start_value) ** (1 / actual_years) - 1) * 100
    else:
        cagr = 0

    return {
        "start_date": closest,
        "end_date": end_date,
        "start_value": start_value,
        "end_value": end_value,
        "total_appreciation_pct": round(total_pct, 2),
        "cagr_pct": round(cagr, 2),
        "actual_years": round(actual_years, 1),
        "dollar_change": round(end_value - start_value),
    }


def analyze_zip(zip_code: str, year_windows: list[int] | None = None) -> ZipAppreciation | None:
    """Full appreciation analysis for a zip code."""
    if year_windows is None:
        year_windows = [1, 3, 5, 10]

    data = load_zhvi_for_zip(zip_code)
    if not data:
        return None

    meta = data["meta"]
    values = data["values"]
    if not values:
        return None

    sorted_dates = sorted(values.keys())
    current_value = values[sorted_dates[-1]]

    periods = {}
    for yrs in year_windows:
        result = compute_appreciation(values, yrs)
        if result:
            periods[f"{yrs}yr"] = result

    return ZipAppreciation(
        zip_code=zip_code,
        city=meta.get("city", ""),
        county=meta.get("county", ""),
        state=meta.get("state", ""),
        current_value=current_value,
        periods=periods,
    )


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def fmt(val: float) -> str:
    return f"${val:,.0f}"


def print_zip_analysis(za: ZipAppreciation):
    """Print appreciation analysis for a single zip code."""
    w = 38
    print(f"\n{'=' * 66}")
    print(f"  ZIP {za.zip_code} — {za.city}, {za.county}")
    print(f"{'=' * 66}\n")
    print(f"  {'Current Zillow Home Value (ZHVI)':{w}s} {fmt(za.current_value)}")
    print(f"  {'Data last synced':{w}s} {get_sync_age()}")
    print()

    if za.periods:
        print(f"  {'Period':<10s} {'Start Value':>14s} {'End Value':>14s} {'Total':>10s} {'CAGR':>8s} {'$ Change':>12s}")
        print(f"  {'-'*10:<10s} {'-'*14:>14s} {'-'*14:>14s} {'-'*10:>10s} {'-'*8:>8s} {'-'*12:>12s}")
        for label, p in za.periods.items():
            total = f"{p['total_appreciation_pct']:+.1f}%"
            cagr = f"{p['cagr_pct']:.1f}%"
            change = fmt(p["dollar_change"])
            print(f"  {label:<10s} {fmt(p['start_value']):>14s} {fmt(p['end_value']):>14s} {total:>10s} {cagr:>8s} {change:>12s}")
    else:
        print(f"  No historical data available for this zip code.")

    print(f"\n{'=' * 66}")


def print_comparison(zip_analyses: list[ZipAppreciation], period: str = "10yr"):
    """Print comparison table across multiple zip codes."""
    valid = [za for za in zip_analyses if za and period in za.periods]
    if not valid:
        print(f"  No data for period '{period}' across selected zip codes.")
        return

    print(f"\n{'=' * 86}")
    print(f"  ZIP CODE COMPARISON — {period.upper()} APPRECIATION")
    print(f"{'=' * 86}\n")

    headers = ["Zip", "City", "Current Value", "Start Value", "Total", "CAGR", "$ Change"]
    widths = [7, 18, 14, 14, 9, 7, 12]
    print("  " + "  ".join(h.rjust(w) for h, w in zip(headers, widths)))
    print("  " + "  ".join("-" * w for w in widths))

    sorted_zas = sorted(valid, key=lambda za: za.periods[period]["cagr_pct"], reverse=True)
    for za in sorted_zas:
        p = za.periods[period]
        row = [
            za.zip_code,
            za.city[:18],
            fmt(za.current_value),
            fmt(p["start_value"]),
            f"{p['total_appreciation_pct']:+.1f}%",
            f"{p['cagr_pct']:.1f}%",
            fmt(p["dollar_change"]),
        ]
        print("  " + "  ".join(str(c).rjust(w) for c, w in zip(row, widths)))

    best = sorted_zas[0]
    worst = sorted_zas[-1]
    print(f"\n  Highest CAGR:  {best.zip_code} ({best.city}) — {best.periods[period]['cagr_pct']:.1f}%/yr")
    print(f"  Lowest CAGR:   {worst.zip_code} ({worst.city}) — {worst.periods[period]['cagr_pct']:.1f}%/yr")
    avg_cagr = sum(za.periods[period]["cagr_pct"] for za in sorted_zas) / len(sorted_zas)
    print(f"  Average CAGR:  {avg_cagr:.1f}%/yr across {len(sorted_zas)} zips")
    print(f"\n{'=' * 86}")


def print_county_summary(county_key: str, year_windows: list[int] | None = None):
    """Analyze all zips in a county."""
    if year_windows is None:
        year_windows = [1, 3, 5, 10]

    zips = COUNTY_ZIPS.get(county_key, [])
    if not zips:
        print(f"  Unknown county: {county_key}")
        return

    analyses = []
    for z in zips:
        za = analyze_zip(z, year_windows)
        if za:
            analyses.append(za)

    if not analyses:
        print(f"  No ZHVI data found for {county_key} county zips.")
        print(f"  Run: python appreciation_tracker.py --sync")
        return

    county_name = county_key.title()
    print(f"\n{'=' * 86}")
    print(f"  {county_name.upper()} COUNTY — APPRECIATION BY ZIP CODE")
    print(f"{'=' * 86}")

    for period_key in [f"{y}yr" for y in year_windows]:
        valid = [za for za in analyses if period_key in za.periods]
        if valid:
            print_comparison(valid, period_key)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    county_choices = list(COUNTY_ZIPS.keys())
    parser = argparse.ArgumentParser(
        description="Track property appreciation by zip code (Denver metro)"
    )
    parser.add_argument("--sync", action="store_true",
                        help="Download/refresh Zillow ZHVI data locally")
    parser.add_argument("--zip", "-z", nargs="+", default=None,
                        help="One or more zip codes to analyze")
    parser.add_argument("--county", "-c", choices=county_choices, default=None,
                        help="Analyze all zips in a county")
    parser.add_argument("--years", "-y", type=int, nargs="+", default=[1, 3, 5, 10],
                        help="Year windows for appreciation (default: 1 3 5 10)")
    parser.add_argument("--compare", action="store_true",
                        help="Show comparison table (default with multiple zips)")

    args = parser.parse_args()

    if args.sync:
        sync_data()
        if not args.zip and not args.county:
            return

    # Check if data exists
    if not os.path.exists(ZHVI_CSV):
        print(f"\n  No local data found. Run sync first:")
        print(f"    python appreciation_tracker.py --sync\n")
        return

    if args.county:
        print_county_summary(args.county, args.years)
        return

    if args.zip:
        analyses = []
        for z in args.zip:
            z = z.strip().zfill(5)
            za = analyze_zip(z, args.years)
            if za:
                analyses.append(za)
                if len(args.zip) == 1:
                    print_zip_analysis(za)
            else:
                print(f"  No data for zip {z}. Is it a valid Colorado zip?")

        if len(analyses) > 1:
            # Pick the longest period available for comparison
            for period in [f"{y}yr" for y in sorted(args.years, reverse=True)]:
                if any(period in za.periods for za in analyses):
                    print_comparison(analyses, period)
                    break
        return

    parser.print_help()


if __name__ == "__main__":
    main()
