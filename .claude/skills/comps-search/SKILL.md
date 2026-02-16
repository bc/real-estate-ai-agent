---
name: comps-search
description: Shared workflow for searching, scraping, and storing property comps (both sales and rentals) in the SQLite database. Use as a sub-skill when the user wants to find and save comps from Zillow, Redfin, Trulia, etc.
---

# Comps Search — Shared Scraping & Storage Workflow

This is a shared workflow for both sale comps and rental comps. It handles:
1. Generating search URLs for the right comp type
2. Scraping listings from Zillow/Redfin/Trulia/etc.
3. Downloading listing photos
4. Storing everything in the SQLite database (data/comps.db)

## Step 1: Generate search URLs

For **sale** comps (recently sold):
```bash
uv run comp-extractor --type sale --county <COUNTY> --beds <N> --price <N>
```

For **rental** comps:
```bash
uv run comp-extractor --type rental --county <COUNTY> --beds <N>
```

## Step 2: Scrape with stealth browser (preferred)

The **browser-scraper** uses Playwright + stealth to bypass bot detection on Zillow, Redfin, etc.:

```bash
# Rental comps — scrapes Zillow, Trulia, Apartments.com, Craigslist
uv run browser-scraper --rental --zip 80205 --beds 3

# Recently sold comps
uv run browser-scraper --sold --zip 80205 --beds 3 --price 475000

# Scrape a specific URL
uv run browser-scraper --url "https://www.trulia.com/for_rent/80205_zip/3p_beds/"

# Also grab listing photos
uv run browser-scraper --rental --zip 80205 --beds 3 --photos

# Export to JSON instead of DB
uv run browser-scraper --rental --zip 80205 --json comps.json
```

Results are auto-saved to the database and geocoded. First-time setup: `uv run playwright install chromium`

## Step 2b: Alternative — WebFetch + manual JSON

If the browser scraper hits CAPTCHAs, use **WebFetch** and build comp records manually:

1. Use WebFetch on each URL to extract listing data
2. Build a JSON array with CompRecord objects (address, price, beds, baths, sqft, etc.)
3. Include `latitude`/`longitude` if available, or geocode later with `uv run comp-extractor --geocode`
4. Load into DB:
   ```bash
   uv run comp-extractor --load comps.json --type sale --price 625000 --sqft 1800
   uv run comp-extractor --load comps.json --type rental --price 3000 --sqft 1600
   ```

## Step 3: Download photos for finish grading

```bash
uv run browser-scraper --rental --zip 80205 --beds 3 --photos
```

Or programmatically:
```python
from comp_extractor import download_comp_photos
for comp in comps:
    paths = download_comp_photos(comp)
```

Then use the **finish-grade** skill to view and grade kitchen/bathroom photos.

## Step 6: Geocode saved comps

After saving, geocode comps for distance searching:
```bash
uv run comp-extractor --geocode            # batch geocode all missing
uv run comp-extractor --geocode-id <ID>    # geocode a single comp
uv run comps-db geocode                    # via DB CLI
```

## Step 7: Query saved comps

By county/beds:
```bash
uv run comp-extractor --db-query --type sale --county denver --beds 3
uv run comp-extractor --db-query --type rental --county denver --beds 3
uv run comp-extractor --db-stats
```

By distance (requires geocoded comps):
```bash
uv run comp-extractor --db-query --type sale --near "123 Main St, Denver, CO" --radius 1.5
uv run comp-extractor --db-query --type sale --near "39.75,-104.99" --radius 2
uv run comps-db query --type sale --near "39.75,-104.99" --radius 2
```

Full DB CLI:
```bash
uv run comps-db query --type sale --county denver --beds 3 --min-price 500000
uv run comps-db query --type rental --county denver --beds 3 --max-price 3500
uv run comps-db stats
uv run comps-db export --type sale --format csv --output sale_comps.csv
```

## Database schema

The SQLite database (`data/comps.db`) stores both sale and rental comps in a single `comps` table:
- `comp_type`: "sale" or "rental"
- `price`: sale price or monthly rent
- `latitude`/`longitude`: geocoded location for distance search
- Common fields: address, city, county, zip, beds, baths, sqft, etc.
- Sale-specific: sale_date, days_on_market, list_price, sale_to_list
- Rental-specific: lease_type, available_date, deposit, pet_policy
- Photos stored as JSON array of URLs
- Automatic dedup on (comp_type, address, price, source)
- Spatial index on (latitude, longitude) for fast nearby queries
