"""
Comparable sales (comps) extractor for Denver metro area.

Generates scraping URLs and structures for extracting recently sold
comparable properties from Redfin, Zillow, and Trulia. Also provides
analysis functions for comparing comps to a subject property.

Usage:
    python comp_extractor.py --county denver --beds 3 --baths 2 --sqft 1800 --price 625000
    python comp_extractor.py --county douglas --beds 4 --sqft 2400 --radius 2
    python comp_extractor.py --address "1234 Main St, Denver, CO 80202" --beds 3
    python comp_extractor.py --help
"""

import argparse
import json
import os
import re
import urllib.request
from dataclasses import dataclass, field, asdict


# ---------------------------------------------------------------------------
# Comp search URL templates by site
# ---------------------------------------------------------------------------

COUNTY_SEARCH_PARAMS = {
    "denver": {
        "zillow_slug": "denver-co",
        "redfin_slug": "city/30772/CO/Denver",
        "redfin_region_id": "30772",
        "redfin_region_type": "6",
        "trulia_slug": "Denver,CO",
        "zip_codes": ["80202", "80203", "80204", "80205", "80206", "80207",
                       "80209", "80210", "80211", "80212", "80216", "80218",
                       "80219", "80220", "80222", "80223", "80224", "80227",
                       "80230", "80231", "80236", "80237", "80238", "80239",
                       "80246", "80247", "80249", "80264"],
    },
    "douglas": {
        "zillow_slug": "douglas-county-co",
        "redfin_slug": "county/570/CO/Douglas-County",
        "redfin_region_id": "570",
        "redfin_region_type": "4",
        "trulia_slug": "Douglas_County,CO",
        "zip_codes": ["80104", "80108", "80109", "80124", "80125", "80126",
                       "80129", "80130", "80131", "80134", "80138"],
    },
    "adams": {
        "zillow_slug": "adams-county-co",
        "redfin_slug": "county/567/CO/Adams-County",
        "redfin_region_id": "567",
        "redfin_region_type": "4",
        "trulia_slug": "Adams_County,CO",
        "zip_codes": ["80020", "80021", "80022", "80023", "80024", "80030",
                       "80031", "80037", "80102", "80136", "80221", "80229",
                       "80233", "80234", "80241", "80260", "80601", "80602",
                       "80603", "80640", "80642"],
    },
    "arapahoe": {
        "zillow_slug": "arapahoe-county-co",
        "redfin_slug": "county/568/CO/Arapahoe-County",
        "redfin_region_id": "568",
        "redfin_region_type": "4",
        "trulia_slug": "Arapahoe_County,CO",
        "zip_codes": ["80010", "80011", "80012", "80013", "80014", "80015",
                       "80016", "80017", "80018", "80019", "80102", "80110",
                       "80111", "80112", "80113", "80120", "80121", "80122",
                       "80160", "80161"],
    },
    "jefferson": {
        "zillow_slug": "jefferson-county-co",
        "redfin_slug": "county/582/CO/Jefferson-County",
        "redfin_region_id": "582",
        "redfin_region_type": "4",
        "trulia_slug": "Jefferson_County,CO",
        "zip_codes": ["80001", "80002", "80003", "80004", "80005", "80033",
                       "80040", "80123", "80127", "80128", "80214", "80215",
                       "80226", "80227", "80228", "80232", "80235", "80401",
                       "80403", "80419", "80439", "80453", "80465"],
    },
}


@dataclass
class CompRecord:
    """A single comparable sale."""
    address: str = ""
    city: str = ""
    county: str = ""
    zip_code: str = ""
    sale_price: int = 0
    sale_date: str = ""
    beds: int = 0
    baths: float = 0
    sqft: int = 0
    lot_sqft: int = 0
    year_built: int = 0
    price_per_sqft: float = 0
    property_type: str = ""
    listing_url: str = ""
    photo_urls: list[str] = field(default_factory=list)
    days_on_market: int = 0
    garage: str = ""
    hoa: int = 0
    source: str = ""
    notes: str = ""


@dataclass
class CompAnalysis:
    """Analysis of comps relative to a subject property."""
    subject_price: int
    subject_sqft: int
    subject_price_per_sqft: float
    comp_count: int
    avg_price: int
    median_price: int
    avg_price_per_sqft: float
    avg_sqft: int
    price_range_low: int
    price_range_high: int
    suggested_value_low: int
    suggested_value_high: int
    suggested_value_mid: int


def analyze_comps(subject_price: int, subject_sqft: int,
                  comps: list[CompRecord]) -> CompAnalysis:
    """Analyze a list of comps relative to a subject property."""
    if not comps:
        return CompAnalysis(
            subject_price=subject_price, subject_sqft=subject_sqft,
            subject_price_per_sqft=round(subject_price / subject_sqft, 2) if subject_sqft else 0,
            comp_count=0, avg_price=0, median_price=0,
            avg_price_per_sqft=0, avg_sqft=0,
            price_range_low=0, price_range_high=0,
            suggested_value_low=0, suggested_value_high=0, suggested_value_mid=0,
        )

    prices = sorted(c.sale_price for c in comps if c.sale_price > 0)
    sqfts = [c.sqft for c in comps if c.sqft > 0]
    ppsfs = [c.price_per_sqft for c in comps if c.price_per_sqft > 0]

    avg_price = int(sum(prices) / len(prices)) if prices else 0
    median_price = prices[len(prices) // 2] if prices else 0
    avg_sqft = int(sum(sqfts) / len(sqfts)) if sqfts else 0
    avg_ppsf = round(sum(ppsfs) / len(ppsfs), 2) if ppsfs else 0

    # Value suggestion based on avg $/sqft applied to subject sqft
    suggested_mid = int(avg_ppsf * subject_sqft) if avg_ppsf else avg_price
    suggested_low = int(suggested_mid * 0.95)
    suggested_high = int(suggested_mid * 1.05)

    return CompAnalysis(
        subject_price=subject_price,
        subject_sqft=subject_sqft,
        subject_price_per_sqft=round(subject_price / subject_sqft, 2) if subject_sqft else 0,
        comp_count=len(comps),
        avg_price=avg_price,
        median_price=median_price,
        avg_price_per_sqft=avg_ppsf,
        avg_sqft=avg_sqft,
        price_range_low=prices[0] if prices else 0,
        price_range_high=prices[-1] if prices else 0,
        suggested_value_low=suggested_low,
        suggested_value_high=suggested_high,
        suggested_value_mid=suggested_mid,
    )


def generate_comp_urls(county_key: str, beds: int, price: int | None = None,
                       sold_days: int = 90) -> list[dict]:
    """Generate URLs for scraping recently sold comps."""
    params = COUNTY_SEARCH_PARAMS.get(county_key, COUNTY_SEARCH_PARAMS["denver"])
    urls = []

    # --- Zillow recently sold ---
    price_filter = ""
    if price:
        low = int(price * 0.75)
        high = int(price * 1.25)
        price_filter = f"{low}-{high}_price/"
    urls.append({
        "site": "Zillow (Recently Sold)",
        "url": f"https://www.zillow.com/{params['zillow_slug']}/sold/{beds}-_beds/{price_filter}",
        "scrape_target": "Listing cards with address, price, beds, baths, sqft, sold date",
        "photo_access": "Click each listing -> Photos tab -> scrape all img src URLs",
        "notes": f"Shows last {sold_days}+ days of sold listings. Filter by price range.",
    })

    # --- Redfin recently sold ---
    redfin_filters = f"min-beds={beds},max-beds={beds + 1}"
    if price:
        redfin_filters += f",min-price={int(price * 0.75)},max-price={int(price * 1.25)}"
    urls.append({
        "site": "Redfin (Recently Sold)",
        "url": f"https://www.redfin.com/{params['redfin_slug']}/filter/{redfin_filters},include=sold-3mo",
        "scrape_target": "Property cards with address, sold price, beds, baths, sqft, date",
        "photo_access": "Click listing -> scroll to photos. URLs in img tags or data-src.",
        "notes": "Redfin has the best structured data. '/sold-3mo' = last 90 days.",
    })

    # --- Trulia recently sold ---
    urls.append({
        "site": "Trulia (Recently Sold)",
        "url": f"https://www.trulia.com/sold/{params['trulia_slug']}/{beds}p_beds/",
        "scrape_target": "Cards with address, sale price, beds, baths, sqft",
        "photo_access": "Click listing for photo carousel. Scrape img src attributes.",
        "notes": "Trulia = Zillow backend. Different UI, same data.",
    })

    # --- Realtor.com recently sold ---
    urls.append({
        "site": "Realtor.com (Recently Sold)",
        "url": f"https://www.realtor.com/realestateandhomes-search/{params['zillow_slug'].replace('-', '_')}/beds-{beds}/show-recently-sold",
        "scrape_target": "Cards with address, sold price, beds, baths, sqft, sold date",
        "photo_access": "Click listing -> Photos. Scrape the <img> src URLs.",
        "notes": "MLS-sourced data. Good for accurate sqft and lot sizes.",
    })

    return urls


def fmt(val) -> str:
    return f"${val:,}"


def print_comp_urls(county_key: str, beds: int, price: int | None):
    """Print comp scraping URLs with instructions."""
    county_name = COUNTY_SEARCH_PARAMS[county_key].get("trulia_slug", county_key).replace("_", " ")
    print(f"\n{'=' * 76}")
    print(f"  COMP SEARCH URLS — {county_name} — {beds}BR")
    if price:
        print(f"  Price range: {fmt(int(price * 0.75))} — {fmt(int(price * 1.25))}")
    print(f"{'=' * 76}\n")

    urls = generate_comp_urls(county_key, beds, price)
    for u in urls:
        print(f"  {u['site']}")
        print(f"    URL:    {u['url']}")
        print(f"    Target: {u['scrape_target']}")
        print(f"    Photos: {u['photo_access']}")
        print(f"    Notes:  {u['notes']}")
        print()

    print(f"  --- Scraping Instructions ---")
    print(f"  1. Use WebFetch or Bright Data MCP to load each URL above")
    print(f"  2. Extract listing data into CompRecord objects:")
    print(f"     address, sale_price, beds, baths, sqft, sale_date, price_per_sqft")
    print(f"  3. For each listing, grab ALL photo URLs (img src / data-src)")
    print(f"  4. Download photos locally, then use Read tool to view kitchen/bath images")
    print(f"  5. Run analyze_comps() to get valuation range")
    print(f"\n  --- Photo Extraction Tip ---")
    print(f"  Listing photo URLs typically follow patterns like:")
    print(f"    Zillow:  photos.zillowstatic.com/fp/<id>-uncropped_scaled_within_1536_1152.webp")
    print(f"    Redfin:  ssl.cdn-redfin.com/photo/<id>/bigphoto/<n>/<hash>.jpg")
    print(f"    Trulia:  Same as Zillow (shared backend)")
    print(f"{'=' * 76}")


def print_comp_analysis(analysis: CompAnalysis, comps: list[CompRecord]):
    """Print formatted comp analysis."""
    w = 38
    print(f"\n{'=' * 66}")
    print(f"  COMPARABLE SALES ANALYSIS")
    print(f"{'=' * 66}\n")

    print(f"  --- Subject Property ---")
    print(f"  {'Asking/target price':{w}s} {fmt(analysis.subject_price)}")
    print(f"  {'Square feet':{w}s} {analysis.subject_sqft:,}")
    print(f"  {'Price per sq ft':{w}s} ${analysis.subject_price_per_sqft:.2f}")
    print()

    print(f"  --- Comp Summary ({analysis.comp_count} comps) ---")
    print(f"  {'Average sold price':{w}s} {fmt(analysis.avg_price)}")
    print(f"  {'Median sold price':{w}s} {fmt(analysis.median_price)}")
    print(f"  {'Avg price per sq ft':{w}s} ${analysis.avg_price_per_sqft:.2f}")
    print(f"  {'Avg square feet':{w}s} {analysis.avg_sqft:,}")
    print(f"  {'Price range':{w}s} {fmt(analysis.price_range_low)} — {fmt(analysis.price_range_high)}")
    print()

    print(f"  --- Suggested Value (based on $/sqft) ---")
    print(f"  {'Low (95%)':{w}s} {fmt(analysis.suggested_value_low)}")
    print(f"  {'Mid':{w}s} {fmt(analysis.suggested_value_mid)}")
    print(f"  {'High (105%)':{w}s} {fmt(analysis.suggested_value_high)}")
    print()

    if comps:
        print(f"  --- Individual Comps ---")
        print(f"  {'Address':35s} {'Price':>12s} {'$/sqft':>8s} {'Sqft':>7s} {'Sold':>12s}")
        print(f"  {'-'*35:35s} {'-'*12:>12s} {'-'*8:>8s} {'-'*7:>7s} {'-'*12:>12s}")
        for c in sorted(comps, key=lambda x: x.sale_price, reverse=True):
            addr = (c.address[:33] + "..") if len(c.address) > 35 else c.address
            print(f"  {addr:35s} {fmt(c.sale_price):>12s} ${c.price_per_sqft:>6.2f} {c.sqft:>7,} {c.sale_date:>12s}")
            if c.photo_urls:
                print(f"    -> {len(c.photo_urls)} photos scraped")
    print(f"\n{'=' * 66}")


def save_comps_json(comps: list[CompRecord], path: str):
    """Save comps to a JSON file."""
    data = [asdict(c) for c in comps]
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  Saved {len(comps)} comps to {path}")


def load_comps_json(path: str) -> list[CompRecord]:
    """Load comps from a JSON file."""
    with open(path) as f:
        data = json.load(f)
    comps = []
    for d in data:
        comps.append(CompRecord(**d))
    return comps


def download_photo(url: str, dest_dir: str, filename: str | None = None) -> str:
    """Download a single photo. Returns local file path."""
    os.makedirs(dest_dir, exist_ok=True)
    if filename is None:
        filename = url.split("/")[-1].split("?")[0]
        if not filename:
            filename = "photo.jpg"
    dest = os.path.join(dest_dir, filename)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            with open(dest, "wb") as f:
                f.write(resp.read())
    except Exception as e:
        print(f"  WARNING: Failed to download {url}: {e}")
        return ""
    return dest


def download_comp_photos(comp: CompRecord, base_dir: str = "comp_photos") -> list[str]:
    """Download all photos for a comp into a subfolder. Returns local paths."""
    if not comp.photo_urls:
        return []
    safe_addr = re.sub(r'[^\w\-]', '_', comp.address)[:60]
    dest_dir = os.path.join(base_dir, safe_addr)
    paths = []
    for i, url in enumerate(comp.photo_urls):
        ext = "jpg"
        if ".png" in url:
            ext = "png"
        elif ".webp" in url:
            ext = "webp"
        path = download_photo(url, dest_dir, f"photo_{i:03d}.{ext}")
        if path:
            paths.append(path)
    return paths


def main():
    county_choices = list(COUNTY_SEARCH_PARAMS.keys())
    parser = argparse.ArgumentParser(
        description="Extract and analyze comparable sales for Denver metro properties"
    )
    parser.add_argument("--county", "-c", choices=county_choices, default="denver",
                        help="County (default: denver)")
    parser.add_argument("--beds", "-b", type=int, default=3,
                        help="Bedrooms (default: 3)")
    parser.add_argument("--baths", type=float, default=2.0,
                        help="Bathrooms (default: 2)")
    parser.add_argument("--sqft", "-s", type=int, default=1600,
                        help="Subject property sqft (default: 1600)")
    parser.add_argument("--price", "-p", type=int, default=625000,
                        help="Subject property price/value (default: 625000)")
    parser.add_argument("--address", type=str, default=None,
                        help="Subject property address (for reference)")
    parser.add_argument("--load", type=str, default=None,
                        help="Load comps from JSON file and analyze")
    parser.add_argument("--urls-only", action="store_true",
                        help="Only print scraping URLs (don't try to scrape)")

    args = parser.parse_args()

    if args.load:
        comps = load_comps_json(args.load)
        analysis = analyze_comps(args.price, args.sqft, comps)
        print_comp_analysis(analysis, comps)
        return

    # Always show URLs
    print_comp_urls(args.county, args.beds, args.price)

    if not args.urls_only:
        # Show empty analysis template
        print(f"\n  To analyze comps after scraping:")
        print(f"  1. Save scraped data to comps.json (array of CompRecord objects)")
        print(f"  2. Run: python comp_extractor.py --load comps.json --price {args.price} --sqft {args.sqft}")
        print(f"  3. Or import and use programmatically:")
        print(f"     from comp_extractor import CompRecord, analyze_comps, print_comp_analysis")


if __name__ == "__main__":
    main()
