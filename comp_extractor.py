"""
Comparable property extractor for Denver metro area.

Generates scraping URLs and structures for extracting recently sold AND
rental comparable properties from Redfin, Zillow, Trulia, and more.
All scraped comps are stored in a shared SQLite database (data/comps.db)
via the comps_db module.

Usage:
    python comp_extractor.py --type sale --county denver --beds 3 --price 625000
    python comp_extractor.py --type rental --county denver --beds 3
    python comp_extractor.py --load comps.json --type sale --price 625000 --sqft 1800
    python comp_extractor.py --db-query --type sale --county denver --beds 3
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


def generate_rental_comp_urls(county_key: str, beds: int,
                               max_rent: int | None = None) -> list[dict]:
    """Generate URLs for scraping rental comps."""
    params = COUNTY_SEARCH_PARAMS.get(county_key, COUNTY_SEARCH_PARAMS["denver"])
    urls = []

    zillow_slug = params["zillow_slug"]
    trulia_slug = params["trulia_slug"]

    urls.append({
        "site": "Zillow (Rentals)",
        "url": f"https://www.zillow.com/{zillow_slug}/rentals/{beds}-_beds/",
        "scrape_target": "Rental listing cards: address, rent/mo, beds, baths, sqft",
        "photo_access": "Click listing -> Photos tab -> scrape img src URLs",
        "notes": "Best for SFH rentals. Filter by price and type.",
    })
    urls.append({
        "site": "Trulia (Rentals)",
        "url": f"https://www.trulia.com/for_rent/{trulia_slug}/{beds}p_beds/",
        "scrape_target": "Cards: address, rent, beds, baths, sqft, days listed",
        "photo_access": "Click listing for photo carousel.",
        "notes": "Same data as Zillow. Neighborhood insight overlays.",
    })

    # Apartments.com city slug mapping
    apt_slugs = {
        "denver": "denver-co", "douglas": "castle-rock-co",
        "adams": "thornton-co", "arapahoe": "centennial-co",
        "jefferson": "lakewood-co",
    }
    apt_slug = apt_slugs.get(county_key, "denver-co")
    urls.append({
        "site": "Apartments.com (Houses)",
        "url": f"https://www.apartments.com/houses/{apt_slug}/{beds}-bedrooms/",
        "scrape_target": "Listing cards: address, rent, beds, baths, sqft",
        "photo_access": "Click listing -> photo gallery.",
        "notes": "Good for rent trend charts. Also lists SFH.",
    })
    urls.append({
        "site": "Craigslist Denver",
        "url": f"https://denver.craigslist.org/search/apa?min_bedrooms={beds}&max_bedrooms={beds}",
        "scrape_target": "Post titles with price, location, beds, sqft",
        "photo_access": "Click post for photos.",
        "notes": "Private landlord pricing. Market floor indicator.",
    })
    urls.append({
        "site": "Rentometer",
        "url": "https://www.rentometer.com/",
        "scrape_target": "Enter address for free estimate",
        "photo_access": "N/A",
        "notes": "1 free lookup/day. Quick median rent + range.",
    })

    return urls


def fmt(val) -> str:
    return f"${val:,}"


def print_comp_urls(county_key: str, beds: int, price: int | None,
                    comp_type: str = "sale"):
    """Print comp scraping URLs with instructions."""
    county_name = COUNTY_SEARCH_PARAMS[county_key].get("trulia_slug", county_key).replace("_", " ")
    type_label = "RECENTLY SOLD" if comp_type == "sale" else "RENTAL"
    print(f"\n{'=' * 76}")
    print(f"  {type_label} COMP URLS — {county_name} — {beds}BR")
    if price and comp_type == "sale":
        print(f"  Price range: {fmt(int(price * 0.75))} — {fmt(int(price * 1.25))}")
    print(f"{'=' * 76}\n")

    if comp_type == "rental":
        urls = generate_rental_comp_urls(county_key, beds, price)
    else:
        urls = generate_comp_urls(county_key, beds, price)

    for u in urls:
        print(f"  {u['site']}")
        print(f"    URL:    {u['url']}")
        print(f"    Target: {u['scrape_target']}")
        print(f"    Photos: {u['photo_access']}")
        print(f"    Notes:  {u['notes']}")
        print()

    price_field = "rent" if comp_type == "rental" else "sale_price"
    print(f"  --- Scraping Instructions ---")
    print(f"  1. Use WebFetch or Bright Data MCP to load each URL above")
    print(f"  2. Extract listing data into CompRecord objects:")
    print(f"     address, {price_field}, beds, baths, sqft, price_per_sqft")
    print(f"  3. For each listing, grab ALL photo URLs (img src / data-src)")
    print(f"  4. Download photos locally, then use Read tool to view kitchen/bath images")
    print(f"  5. Save to DB: python comp_extractor.py --load comps.json --type {comp_type}")
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


def comps_to_db_rows(comps: list[CompRecord], comp_type: str = "sale"):
    """Convert CompRecord list to CompRow list for database storage."""
    from comps_db import CompRow
    rows = []
    for c in comps:
        rows.append(CompRow(
            comp_type=comp_type,
            address=c.address,
            city=c.city,
            county=c.county,
            zip_code=c.zip_code,
            price=c.sale_price,
            price_per_sqft=c.price_per_sqft,
            beds=c.beds,
            baths=c.baths,
            sqft=c.sqft,
            lot_sqft=c.lot_sqft,
            year_built=c.year_built,
            property_type=c.property_type,
            listing_url=c.listing_url,
            source=c.source,
            photo_urls=c.photo_urls,
            photo_count=len(c.photo_urls),
            sale_date=c.sale_date,
            days_on_market=c.days_on_market,
            garage=c.garage,
            hoa=c.hoa,
            notes=c.notes,
        ))
    return rows


def save_comps_to_db(comps: list[CompRecord], comp_type: str = "sale") -> int:
    """Save CompRecords to the SQLite database. Returns count inserted."""
    from comps_db import CompsDB
    rows = comps_to_db_rows(comps, comp_type)
    with CompsDB() as db:
        count = db.insert_many(rows)
        total = db.count(comp_type)
    print(f"  Saved {count} new {comp_type} comps to database ({total} total {comp_type} comps)")
    return count


def main():
    county_choices = list(COUNTY_SEARCH_PARAMS.keys())
    parser = argparse.ArgumentParser(
        description="Extract and analyze comparable properties for Denver metro"
    )
    parser.add_argument("--type", "-t", choices=["sale", "rental"], default="sale",
                        help="Comp type: sale (recently sold) or rental (default: sale)")
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
                        help="Load comps from JSON file, analyze, and save to DB")
    parser.add_argument("--urls-only", action="store_true",
                        help="Only print scraping URLs (don't try to scrape)")
    parser.add_argument("--db-query", action="store_true",
                        help="Query existing comps from the database")
    parser.add_argument("--db-stats", action="store_true",
                        help="Show database statistics")

    args = parser.parse_args()

    # DB stats
    if args.db_stats:
        from comps_db import CompsDB, print_stats
        with CompsDB() as db:
            print_stats(db)
        return

    # DB query
    if args.db_query:
        from comps_db import CompsDB, print_query_results
        with CompsDB() as db:
            comps = db.query(
                comp_type=args.type, county=args.county,
                beds=args.beds, limit=50,
            )
            print_query_results(comps, args.type)
        return

    # Load from JSON, analyze, and save to DB
    if args.load:
        comps = load_comps_json(args.load)
        analysis = analyze_comps(args.price, args.sqft, comps)
        print_comp_analysis(analysis, comps)
        save_comps_to_db(comps, args.type)
        return

    # Show URLs for the requested comp type
    print_comp_urls(args.county, args.beds, args.price, args.type)

    if not args.urls_only:
        print(f"\n  To analyze comps after scraping:")
        print(f"  1. Save scraped data to comps.json (array of CompRecord objects)")
        print(f"  2. Run: python comp_extractor.py --load comps.json --type {args.type} --price {args.price} --sqft {args.sqft}")
        print(f"  3. Query saved comps: python comp_extractor.py --db-query --type {args.type} --county {args.county}")
        print(f"  4. DB stats: python comp_extractor.py --db-stats")


if __name__ == "__main__":
    main()
