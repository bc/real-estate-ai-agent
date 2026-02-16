---
name: sold-comps
description: Find recently sold comparable properties (sale comps) in the Denver metro area. Use when the user asks about recently sold homes, sale comps, what houses sold for, sold price data, or wants to value a property based on recent sales in Denver, Douglas, Adams, Arapahoe, or Jefferson county.
---

# Recently Sold Comps

Find recently sold comparable properties to value a subject property.

## Gather info from user

Ask for (or infer from context):
- County (denver, douglas, adams, arapahoe, jefferson)
- Bedrooms
- Square footage
- Target/asking price
- Address (optional)

## Step 1: Check the database first

```bash
python comp_extractor.py --db-query --type sale --county <COUNTY> --beds <N>
```

If there are existing comps in the database, show them. Ask if the user wants fresh data.

## Step 2: Generate scraping URLs

```bash
python comp_extractor.py --type sale --county <COUNTY> --beds <N> --price <N>
```

This generates URLs for:
- Zillow (Recently Sold)
- Redfin (Recently Sold, last 90 days)
- Trulia (Recently Sold)
- Realtor.com (Recently Sold)

## Step 3: Scrape and save

Follow the **comps-search** sub-skill workflow:
1. Use WebFetch on each URL to get listings
2. Extract: address, sold price, beds, baths, sqft, sold date, price/sqft
3. Extract photo URLs
4. Save to JSON, then load into DB:
   ```bash
   python comp_extractor.py --load comps.json --type sale --price <SUBJECT_PRICE> --sqft <SUBJECT_SQFT>
   ```

## Step 4: Analyze

The `--load` command automatically runs comp analysis showing:
- Average and median sold price
- Price per sq ft comparison
- Suggested value range for the subject
- Individual comp details

## Step 5: Grade finishes (optional)

Download photos and use the **finish-grade** skill to assess kitchen/bathroom quality for each comp.

## After running

Present:
1. Number of comps found and date range
2. Average/median sold price and $/sqft
3. Suggested value range for the subject property
4. How the subject compares (above/below market)
5. Any notable outliers or patterns
6. Link to DB for future queries: `python comps_db.py stats`
