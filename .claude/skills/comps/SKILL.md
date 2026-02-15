---
name: comps
description: Find comparable sales (comps) for a property in the Denver metro area. Use when the user asks about comps, comparable sales, recently sold properties, neighborhood sales data, or property valuation from Redfin/Zillow/Trulia.
---

# Comparable Sales Extractor

Find and analyze recently sold comparable properties from Redfin, Zillow, Trulia, and Realtor.com.

## Gather info from user

Ask the user for (or infer from context):
- County (denver, douglas, adams, arapahoe, jefferson)
- Bedrooms
- Square footage
- Target price or current value
- Address (optional, for reference)

## Step 1: Generate scraping URLs

```bash
python comp_extractor.py --county <COUNTY> --beds <N> --sqft <N> --price <N>
```

This prints URLs for Zillow, Redfin, Trulia, and Realtor.com filtered to recently sold properties matching the criteria.

## Step 2: Scrape the listings

For each URL generated:
1. Use WebFetch to load the page
2. Extract listing data: address, sold price, beds, baths, sqft, sold date, price per sqft
3. Extract ALL photo URLs from each listing

## Step 3: Download photos

Use the download functions or Bash curl to save listing photos:
```python
from comp_extractor import download_comp_photos, CompRecord
comp = CompRecord(address="123 Main St", photo_urls=["https://..."])
paths = download_comp_photos(comp)
```

Or via Bash:
```bash
mkdir -p comp_photos/123_Main_St
curl -o comp_photos/123_Main_St/photo_001.jpg "https://photo-url..."
```

## Step 4: Analyze comps

Save scraped comps to JSON and analyze:
```bash
python comp_extractor.py --load comps.json --price <SUBJECT_PRICE> --sqft <SUBJECT_SQFT>
```

Or programmatically:
```python
from comp_extractor import CompRecord, analyze_comps, print_comp_analysis
comps = [CompRecord(address="...", sale_price=600000, sqft=1800, ...)]
analysis = analyze_comps(subject_price=625000, subject_sqft=1600, comps=comps)
print_comp_analysis(analysis, comps)
```

## Step 5: Grade the finish quality

For each comp's kitchen/bathroom photos, use the finish-grade skill to assess quality.

## After running

Present: comp count, average/median price, price per sqft, suggested value range, and individual comp details. Highlight how the subject compares to the market.
