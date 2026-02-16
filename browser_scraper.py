"""
Stealth headless browser scraper for real estate listing sites.

Uses Playwright + playwright-stealth to scrape Zillow, Trulia, Redfin,
Apartments.com, and Craigslist while appearing as a normal desktop browser.
Extracts rental and sale comp data and photos, saves to the comps database.

Setup (one-time):
    uv run playwright install chromium

Usage:
    uv run browser-scraper --rental --zip 80205 --beds 3
    uv run browser-scraper --rental --near "3700 Jackson St, Denver, CO" --beds 3
    uv run browser-scraper --sold --zip 80205 --beds 3 --price 475000
    uv run browser-scraper --url "https://www.trulia.com/for_rent/Denver,CO/3p_beds/80205_zip/"
    uv run browser-scraper --url "https://www.zillow.com/..." --save rental
"""

import argparse
import json
import math
import os
import random
import re
import time
from dataclasses import dataclass, field

# Lazy imports — only loaded when actually scraping
_pw = None
_stealth = None


def _ensure_imports():
    """Lazy-import playwright and stealth to keep module importable without them."""
    global _pw, _stealth
    if _pw is None:
        from playwright.sync_api import sync_playwright
        from playwright_stealth import Stealth
        _pw = sync_playwright
        _stealth = Stealth()


# ---------------------------------------------------------------------------
# Browser context manager
# ---------------------------------------------------------------------------

@dataclass
class BrowserConfig:
    """Configuration for the stealth browser."""
    headless: bool = True
    slow_mo: int = 0            # ms delay between actions (0 = fast)
    timeout: int = 30_000       # default navigation timeout ms
    viewport_width: int = 1920
    viewport_height: int = 1080
    locale: str = "en-US"
    timezone: str = "America/Denver"
    user_agent: str = ""        # auto-selected if empty
    scroll_pause: float = 1.5   # seconds between scrolls
    page_load_wait: float = 3.0 # extra wait after navigation (sec)

# Realistic user agents (Chrome on Windows/Mac)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.6723.116 Safari/537.36",
]


class StealthBrowser:
    """Playwright browser with stealth anti-detection patches."""

    def __init__(self, config: BrowserConfig | None = None):
        _ensure_imports()
        self.config = config or BrowserConfig()
        self._pw_ctx = None
        self._browser = None
        self._context = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.close()

    def start(self):
        cfg = self.config
        ua = cfg.user_agent or random.choice(USER_AGENTS)

        self._pw_ctx = _stealth.use_sync(_pw())
        pw = self._pw_ctx.__enter__()

        self._browser = pw.chromium.launch(
            headless=cfg.headless,
            slow_mo=cfg.slow_mo,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-infobars",
                "--window-size=1920,1080",
            ],
        )

        self._context = self._browser.new_context(
            viewport={"width": cfg.viewport_width, "height": cfg.viewport_height},
            user_agent=ua,
            locale=cfg.locale,
            timezone_id=cfg.timezone,
            java_script_enabled=True,
            ignore_https_errors=True,
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            },
        )

    def new_page(self):
        """Create a new stealth page (stealth already applied via context)."""
        page = self._context.new_page()
        page.set_default_timeout(self.config.timeout)
        return page

    def close(self):
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._pw_ctx:
            self._pw_ctx.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# Page interaction helpers
# ---------------------------------------------------------------------------

def human_scroll(page, scrolls: int = 3, pause: float = 1.5):
    """Scroll down the page like a human to trigger lazy-loaded content."""
    for i in range(scrolls):
        distance = random.randint(400, 900)
        page.mouse.wheel(0, distance)
        time.sleep(pause + random.uniform(0, 0.8))


def wait_and_scroll(page, url: str, config: BrowserConfig | None = None):
    """Navigate to URL, wait for load, scroll to load lazy content."""
    cfg = config or BrowserConfig()
    page.goto(url, wait_until="domcontentloaded")
    time.sleep(cfg.page_load_wait + random.uniform(0, 1.5))
    human_scroll(page, scrolls=4, pause=cfg.scroll_pause)
    time.sleep(1)


# ---------------------------------------------------------------------------
# Listing data extraction — each site gets its own parser
# ---------------------------------------------------------------------------

@dataclass
class ScrapedListing:
    """Raw listing data extracted from a page."""
    address: str = ""
    city: str = ""
    state: str = "CO"
    zip_code: str = ""
    price: int = 0           # rent/mo or sale price
    beds: int = 0
    baths: float = 0
    sqft: int = 0
    lot_sqft: int = 0
    year_built: int = 0
    property_type: str = ""  # sfh, condo, townhome, etc.
    listing_url: str = ""
    photo_urls: list[str] = field(default_factory=list)
    days_on_market: int = 0
    source: str = ""
    sale_date: str = ""
    notes: str = ""


def _parse_price(text: str) -> int:
    """Extract dollar amount from text like '$3,250/mo' or '$475,000'."""
    m = re.search(r'\$[\d,]+', text.replace(" ", ""))
    if m:
        return int(m.group().replace("$", "").replace(",", ""))
    # Try plain digits
    m = re.search(r'[\d,]{4,}', text.replace(" ", ""))
    if m:
        return int(m.group().replace(",", ""))
    return 0


def _parse_int(text: str) -> int:
    m = re.search(r'[\d,]+', text)
    if m:
        return int(m.group().replace(",", ""))
    return 0


def _parse_float(text: str) -> float:
    m = re.search(r'[\d.]+', text)
    if m:
        return float(m.group())
    return 0


# --- Zillow ---

def extract_zillow(page) -> list[ScrapedListing]:
    """Extract listings from a Zillow search results page."""
    listings = []
    cards = page.query_selector_all('article[data-test="property-card"], li[class*="ListItem"] article, div[id^="zpid"]')
    if not cards:
        # Fallback: try broader selectors
        cards = page.query_selector_all('[class*="property-card"], [class*="StyledPropertyCard"]')

    for card in cards:
        try:
            listing = ScrapedListing(source="zillow")

            # Address
            addr_el = card.query_selector('[data-test="property-card-addr"], address, [class*="address"]')
            if addr_el:
                listing.address = addr_el.inner_text().strip()

            # Price
            price_el = card.query_selector('[data-test="property-card-price"], [class*="price"], span[class*="Price"]')
            if price_el:
                listing.price = _parse_price(price_el.inner_text())

            # Beds, baths, sqft from the details line
            details = card.query_selector_all('[class*="StyledPropertyCardHomeDetails"] li, [class*="details"] b, [data-test="property-card-details"] li')
            for detail in details:
                txt = detail.inner_text().lower()
                if "bd" in txt or "bed" in txt:
                    listing.beds = _parse_int(txt)
                elif "ba" in txt or "bath" in txt:
                    listing.baths = _parse_float(txt)
                elif "sqft" in txt or "sq ft" in txt:
                    listing.sqft = _parse_int(txt)

            # Link
            link = card.query_selector('a[href*="/homedetails/"], a[href*="/b/"], a[data-test="property-card-link"]')
            if link:
                href = link.get_attribute("href") or ""
                if href.startswith("/"):
                    href = "https://www.zillow.com" + href
                listing.listing_url = href

            # Photo
            img = card.query_selector('img[src*="zillowstatic"], img[src*="photo"], img[data-src]')
            if img:
                src = img.get_attribute("src") or img.get_attribute("data-src") or ""
                if src and "svg" not in src:
                    listing.photo_urls.append(src)

            if listing.address and listing.price:
                listings.append(listing)
        except Exception:
            continue

    return listings


# --- Trulia ---

def extract_trulia(page) -> list[ScrapedListing]:
    """Extract listings from a Trulia search results page."""
    listings = []
    cards = page.query_selector_all('[data-testid="search-result-list-container"] li, div[class*="PropertyCard"], div[data-testid*="property"]')
    if not cards:
        cards = page.query_selector_all('li[class*="result"]')

    for card in cards:
        try:
            listing = ScrapedListing(source="trulia")

            # Address — usually in a div with address or heading
            addr_el = card.query_selector('[data-testid="property-address"], [class*="Address"], h3, [class*="address"]')
            if addr_el:
                listing.address = addr_el.inner_text().strip().split("\n")[0]

            # Price
            price_el = card.query_selector('[data-testid="property-price"], [class*="price"], [class*="Price"]')
            if price_el:
                listing.price = _parse_price(price_el.inner_text())

            # Beds, baths, sqft
            detail_els = card.query_selector_all('[data-testid*="bed"], [data-testid*="bath"], [data-testid*="floor"], [class*="Detail"] span, [class*="Beds"], [class*="Baths"]')
            for el in detail_els:
                txt = el.inner_text().lower()
                if "bd" in txt or "bed" in txt:
                    listing.beds = _parse_int(txt)
                elif "ba" in txt or "bath" in txt:
                    listing.baths = _parse_float(txt)
                elif "sqft" in txt or "sq ft" in txt:
                    listing.sqft = _parse_int(txt)

            # Fallback: parse the whole card text for bed/bath/sqft
            if not listing.beds:
                txt = card.inner_text()
                m = re.search(r'(\d+)\s*bd', txt, re.IGNORECASE)
                if m:
                    listing.beds = int(m.group(1))
                m = re.search(r'([\d.]+)\s*ba', txt, re.IGNORECASE)
                if m:
                    listing.baths = float(m.group(1))
                m = re.search(r'([\d,]+)\s*(?:sq\s*ft|sqft)', txt, re.IGNORECASE)
                if m:
                    listing.sqft = int(m.group(1).replace(",", ""))

            # Link
            link = card.query_selector('a[href*="/p/"], a[href*="/building/"]')
            if link:
                href = link.get_attribute("href") or ""
                if href.startswith("/"):
                    href = "https://www.trulia.com" + href
                listing.listing_url = href

            # Photo
            img = card.query_selector('img[src*="static"], img[src*="photo"]')
            if img:
                src = img.get_attribute("src") or ""
                if src and "svg" not in src:
                    listing.photo_urls.append(src)

            if listing.address and listing.price:
                listings.append(listing)
        except Exception:
            continue

    return listings


# --- Redfin ---

def extract_redfin(page) -> list[ScrapedListing]:
    """Extract listings from a Redfin search results page."""
    listings = []
    cards = page.query_selector_all('[class*="HomeCard"], [class*="homecard"], div[class*="MapHomeCard"]')

    for card in cards:
        try:
            listing = ScrapedListing(source="redfin")

            addr_el = card.query_selector('[class*="homeAddress"], [class*="address"], .link-and-anchor')
            if addr_el:
                listing.address = addr_el.inner_text().strip()

            price_el = card.query_selector('[class*="homecardV2Price"], [class*="price"]')
            if price_el:
                listing.price = _parse_price(price_el.inner_text())

            stats = card.query_selector_all('[class*="HomeStatsV2"] div, [class*="stats"] div')
            for stat in stats:
                txt = stat.inner_text().lower()
                if "bed" in txt:
                    listing.beds = _parse_int(txt)
                elif "bath" in txt:
                    listing.baths = _parse_float(txt)
                elif "sq ft" in txt or "sqft" in txt:
                    listing.sqft = _parse_int(txt)

            link = card.query_selector('a[href*="/CO/"]')
            if link:
                href = link.get_attribute("href") or ""
                if href.startswith("/"):
                    href = "https://www.redfin.com" + href
                listing.listing_url = href

            img = card.query_selector('img[src*="ssl.cdn-redfin"], img[src*="photo"]')
            if img:
                src = img.get_attribute("src") or ""
                if src:
                    listing.photo_urls.append(src)

            if listing.address and listing.price:
                listings.append(listing)
        except Exception:
            continue

    return listings


# --- Apartments.com ---

def extract_apartments(page) -> list[ScrapedListing]:
    """Extract listings from an Apartments.com search page."""
    listings = []
    cards = page.query_selector_all('li[class*="mortar--result"], article[data-listingid], li.mortar-wrapper')

    for card in cards:
        try:
            listing = ScrapedListing(source="apartments.com")

            addr_el = card.query_selector('[class*="property-address"], [class*="location"], .property-title')
            if addr_el:
                listing.address = addr_el.inner_text().strip()

            price_el = card.query_selector('[class*="price-range"], [class*="property-pricing"]')
            if price_el:
                listing.price = _parse_price(price_el.inner_text())

            detail_el = card.query_selector('[class*="property-beds"], [class*="bed-range"]')
            if detail_el:
                txt = detail_el.inner_text()
                m = re.search(r'(\d+)\s*(?:Bed|BR)', txt, re.IGNORECASE)
                if m:
                    listing.beds = int(m.group(1))
                m = re.search(r'([\d.]+)\s*(?:Bath|BA)', txt, re.IGNORECASE)
                if m:
                    listing.baths = float(m.group(1))
                m = re.search(r'([\d,]+)\s*(?:Sq Ft|SF|sqft)', txt, re.IGNORECASE)
                if m:
                    listing.sqft = int(m.group(1).replace(",", ""))

            link = card.query_selector('a[href*="apartments.com"]')
            if link:
                listing.listing_url = link.get_attribute("href") or ""

            img = card.query_selector('img[src*="image"], img[class*="photo"]')
            if img:
                src = img.get_attribute("src") or ""
                if src and "svg" not in src:
                    listing.photo_urls.append(src)

            if listing.address and listing.price:
                listings.append(listing)
        except Exception:
            continue

    return listings


# --- Craigslist ---

def extract_craigslist(page) -> list[ScrapedListing]:
    """Extract listings from a Craigslist housing search."""
    listings = []
    rows = page.query_selector_all('li.cl-static-search-result, li.cl-search-result, div.result-row')

    for row in rows:
        try:
            listing = ScrapedListing(source="craigslist")

            title_el = row.query_selector('.title-blob .titlestring, a.posting-title .label, .result-title')
            if title_el:
                listing.address = title_el.inner_text().strip()

            price_el = row.query_selector('.priceinfo, .result-price, .price')
            if price_el:
                listing.price = _parse_price(price_el.inner_text())

            # Craigslist shows "3br" in the meta or title
            meta = row.inner_text()
            m = re.search(r'(\d+)\s*br', meta, re.IGNORECASE)
            if m:
                listing.beds = int(m.group(1))
            m = re.search(r'([\d,]+)\s*ft', meta, re.IGNORECASE)
            if m:
                listing.sqft = int(m.group(1).replace(",", ""))

            link = row.query_selector('a[href*="/apa/"], a[href*="/hou/"], a.posting-title')
            if link:
                href = link.get_attribute("href") or ""
                if href.startswith("/"):
                    href = "https://denver.craigslist.org" + href
                listing.listing_url = href

            if listing.address and listing.price:
                listings.append(listing)
        except Exception:
            continue

    return listings


# --- Generic / auto-detect ---

SITE_EXTRACTORS = {
    "zillow.com": extract_zillow,
    "trulia.com": extract_trulia,
    "redfin.com": extract_redfin,
    "apartments.com": extract_apartments,
    "craigslist.org": extract_craigslist,
}


def detect_site(url: str) -> str:
    """Detect which site a URL belongs to."""
    for domain in SITE_EXTRACTORS:
        if domain in url:
            return domain
    return ""


def extract_listings(page, url: str) -> list[ScrapedListing]:
    """Auto-detect site and extract listings."""
    site = detect_site(url)
    if site in SITE_EXTRACTORS:
        return SITE_EXTRACTORS[site](page)
    # Fallback: return page text for manual parsing
    print(f"  WARNING: No extractor for {url}, returning empty list")
    return []


# ---------------------------------------------------------------------------
# Photo scraper — get all photos from an individual listing page
# ---------------------------------------------------------------------------

def scrape_listing_photos(page, listing_url: str) -> list[str]:
    """Visit an individual listing page and extract all photo URLs."""
    try:
        page.goto(listing_url, wait_until="domcontentloaded")
        time.sleep(2 + random.uniform(0, 1))

        # Collect all large image URLs
        photos = set()
        for img in page.query_selector_all("img"):
            src = img.get_attribute("src") or img.get_attribute("data-src") or ""
            if not src or "svg" in src or "logo" in src or "icon" in src:
                continue
            # Filter for listing photos (usually > 200px wide in URL or data)
            if any(k in src for k in ["photo", "fp/", "image", "listing", "static", "cdn", "media"]):
                photos.add(src)

        return list(photos)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# URL generators for scraping
# ---------------------------------------------------------------------------

def rental_urls_for_zip(zip_code: str, beds: int) -> list[dict]:
    """Generate rental search URLs for a zip code."""
    return [
        {"url": f"https://www.zillow.com/homes/for_rent/{zip_code}_rb/{beds}-_beds/", "site": "zillow.com"},
        {"url": f"https://www.trulia.com/for_rent/{zip_code}_zip/{beds}p_beds/SINGLE-FAMILY_HOME_type/", "site": "trulia.com"},
        {"url": f"https://www.apartments.com/houses/{zip_code}/{beds}-bedrooms/", "site": "apartments.com"},
        {"url": f"https://denver.craigslist.org/search/apa?min_bedrooms={beds}&max_bedrooms={beds+1}&postal={zip_code}&search_distance=2", "site": "craigslist.org"},
    ]


def sold_urls_for_zip(zip_code: str, beds: int, price: int | None = None) -> list[dict]:
    """Generate recently-sold search URLs for a zip code."""
    price_filter = ""
    if price:
        lo, hi = int(price * 0.75), int(price * 1.25)
        price_filter = f"/{lo}-{hi}_price"
    return [
        {"url": f"https://www.zillow.com/homes/recently_sold/{zip_code}_rb/{beds}-_beds{price_filter}/", "site": "zillow.com"},
        {"url": f"https://www.trulia.com/sold/{zip_code}_zip/{beds}p_beds/", "site": "trulia.com"},
        {"url": f"https://www.redfin.com/zipcode/{zip_code}/filter/min-beds={beds},max-beds={beds+1},include=sold-3mo", "site": "redfin.com"},
    ]


# ---------------------------------------------------------------------------
# Main scraping pipeline
# ---------------------------------------------------------------------------

def scrape_urls(urls: list[dict], config: BrowserConfig | None = None,
                fetch_photos: bool = False) -> list[ScrapedListing]:
    """Scrape multiple search URLs and return all extracted listings."""
    cfg = config or BrowserConfig()
    all_listings = []

    try:
        return _scrape_urls_inner(urls, cfg, fetch_photos)
    except Exception as e:
        if "Executable doesn't exist" in str(e) or "playwright install" in str(e).lower():
            print("\n  ERROR: Chromium browser not installed.")
            print("  Run this once to set it up:\n")
            print("    uv run playwright install chromium\n")
            return []
        raise


def _scrape_urls_inner(urls, cfg, fetch_photos):
    all_listings = []

    with StealthBrowser(cfg) as browser:
        page = browser.new_page()

        for entry in urls:
            url = entry["url"]
            site = entry.get("site", detect_site(url))
            print(f"\n  Scraping {site}: {url}")

            try:
                wait_and_scroll(page, url, cfg)
                listings = extract_listings(page, url)
                print(f"    -> Found {len(listings)} listings")

                # Optionally visit each listing for photos
                if fetch_photos:
                    for i, listing in enumerate(listings):
                        if listing.listing_url:
                            print(f"    -> Photos for {listing.address}... ", end="", flush=True)
                            photos = scrape_listing_photos(page, listing.listing_url)
                            listing.photo_urls.extend(photos)
                            print(f"{len(photos)} photos")
                            time.sleep(random.uniform(1.5, 3.0))

                all_listings.extend(listings)

            except Exception as e:
                print(f"    -> ERROR: {e}")

            # Pause between sites
            time.sleep(random.uniform(2, 4))

        page.close()

    return all_listings


def listings_to_comp_records(listings: list[ScrapedListing], zip_code: str = "",
                              county: str = "denver"):
    """Convert ScrapedListings to CompRecords for the database."""
    from comp_extractor import CompRecord
    comps = []
    for l in listings:
        # Parse zip from address if not set
        zc = l.zip_code or zip_code
        if not zc:
            m = re.search(r'\b(80\d{3})\b', l.address)
            if m:
                zc = m.group(1)

        comps.append(CompRecord(
            address=l.address,
            city=l.city or "Denver",
            county=county,
            zip_code=zc,
            sale_price=l.price,
            sale_date=l.sale_date,
            beds=l.beds,
            baths=l.baths,
            sqft=l.sqft,
            lot_sqft=l.lot_sqft,
            year_built=l.year_built,
            price_per_sqft=round(l.price / l.sqft, 2) if l.sqft else 0,
            property_type=l.property_type,
            listing_url=l.listing_url,
            photo_urls=l.photo_urls,
            days_on_market=l.days_on_market,
            source=l.source,
            notes=l.notes,
        ))
    return comps


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Stealth browser scraper for real estate listings"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--rental", action="store_true",
                      help="Scrape rental listings")
    mode.add_argument("--sold", action="store_true",
                      help="Scrape recently sold listings")
    mode.add_argument("--url", type=str, default=None,
                      help="Scrape a specific URL")

    parser.add_argument("--zip", type=str, default="80205",
                        help="Zip code to search (default: 80205)")
    parser.add_argument("--beds", type=int, default=3,
                        help="Bedrooms (default: 3)")
    parser.add_argument("--price", type=int, default=None,
                        help="Target price for sold comps price range filter")
    parser.add_argument("--county", type=str, default="denver",
                        help="County for DB storage (default: denver)")
    parser.add_argument("--photos", action="store_true",
                        help="Also scrape photos from each listing page")
    parser.add_argument("--save", choices=["rental", "sale"], default=None,
                        help="Save results to comps database (rental or sale)")
    parser.add_argument("--visible", action="store_true",
                        help="Run browser in visible (non-headless) mode")
    parser.add_argument("--json", type=str, default=None,
                        help="Export results to JSON file")

    args = parser.parse_args()

    config = BrowserConfig(headless=not args.visible)

    # Build URL list
    if args.url:
        urls = [{"url": args.url, "site": detect_site(args.url)}]
    elif args.sold:
        urls = sold_urls_for_zip(args.zip, args.beds, args.price)
    else:
        # Default to rental
        urls = rental_urls_for_zip(args.zip, args.beds)

    comp_type = "sale" if args.sold else "rental"

    print(f"\n{'=' * 70}")
    print(f"  STEALTH BROWSER SCRAPER — {comp_type.upper()} — {args.zip}")
    print(f"  Sites: {', '.join(u['site'] for u in urls)}")
    print(f"{'=' * 70}")

    # Scrape
    listings = scrape_urls(urls, config, fetch_photos=args.photos)

    if not listings:
        print("\n  No listings found. Sites may require CAPTCHA or login.")
        return

    # Display results
    print(f"\n  --- Results: {len(listings)} listings ---\n")
    price_label = "Rent/mo" if comp_type == "rental" else "Price"
    print(f"  {'Address':35s} {price_label:>10s} {'Bed':>4s} {'Bath':>5s} {'Sqft':>7s} {'Source':>14s}")
    print(f"  {'-'*35} {'-'*10} {'-'*4} {'-'*5} {'-'*7} {'-'*14}")
    for l in sorted(listings, key=lambda x: x.price, reverse=True):
        addr = (l.address[:33] + "..") if len(l.address) > 35 else l.address
        sqft = f"{l.sqft:>7,}" if l.sqft else "      -"
        photos = f" [{len(l.photo_urls)} photos]" if l.photo_urls else ""
        print(f"  {addr:35s} ${l.price:>9,} {l.beds:>4d} {l.baths:>5.1f} {sqft} {l.source:>14s}{photos}")

    # Save to JSON
    if args.json:
        comps = listings_to_comp_records(listings, args.zip, args.county)
        from dataclasses import asdict
        data = [asdict(c) for c in comps]
        with open(args.json, "w") as f:
            json.dump(data, f, indent=2)
        print(f"\n  Exported {len(comps)} listings to {args.json}")

    # Save to database
    save = args.save or comp_type
    if save:
        comps = listings_to_comp_records(listings, args.zip, args.county)
        from comp_extractor import save_comps_to_db
        count = save_comps_to_db(comps, comp_type=save)
        print(f"\n  Geocoding new comps...")
        from comps_db import CompsDB
        with CompsDB() as db:
            geocoded = db.geocode_missing(limit=count, delay=1.1)
            print(f"  Geocoded {geocoded} comps")

    print(f"\n{'=' * 70}")


if __name__ == "__main__":
    main()
