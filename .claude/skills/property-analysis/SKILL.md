---
name: property-analysis
description: Full investment property analysis combining all tools — comps, rent estimate, tax estimate, finish grading, appreciation, and refinance. Use when the user wants a comprehensive analysis of a property for investment purposes.
---

# Property Analysis — Full Investment Analysis Workflow

Chains all available tools into a comprehensive rental property investment analysis. This is the meta-skill that ties everything together.

## Gather from user

| Parameter | Required | Description |
|---|---|---|
| Address | Yes | Full street address of the subject property |
| City/Zip | Yes | City and zip code |
| County | Yes | denver, douglas, adams, arapahoe, or jefferson |
| Bedrooms | Yes | Number of bedrooms |
| Bathrooms | Yes | Number of bathrooms |
| Square footage | Yes | Interior square footage |
| Purchase price | Yes | Asking price or intended purchase price |
| Property type | No | sfh, townhome, condo, duplex (default: sfh) |
| Year built | No | Year the property was built |

## Workflow

### Step 1: Property tax estimate

Run the county-specific property tax estimator:
```bash
uv run property-tax --county <COUNTY> --value <PURCHASE_PRICE>
```

### Step 2: Rent estimate

Get a rent estimate with the default C grade first:
```bash
uv run rent-estimator --county <COUNTY> --beds <N> --baths <N> --sqft <N> --type <TYPE> --grade C
```

### Step 3: Check existing comps in database

Query nearby comps from the database before scraping new ones:
```bash
uv run comps-db query --type rental --near "<ADDRESS>, <CITY>, CO" --radius 2
uv run comps-db query --type sale --near "<ADDRESS>, <CITY>, CO" --radius 2
```

If insufficient comps exist, use the **comps** skill to scrape more.

### Step 4: Appreciation lookup

Check historical appreciation for the zip code:
```bash
uv run appreciation-tracker --zip <ZIPCODE>
```

### Step 5: Finish grading (if photos available)

If listing photos are available, use the **finish-grade** skill to assess kitchen and bathroom quality. Then re-run the rent estimate with the actual grade:
```bash
uv run rent-estimator --county <COUNTY> --beds <N> --baths <N> --sqft <N> --grade <A-F>
```

### Step 6: Investment summary

Present a consolidated report:

1. **Property details** — address, beds/baths, sqft, year built, type
2. **Purchase** — price, price per sqft, county
3. **Estimated rent** — monthly rent range, annual gross, rent per sqft
4. **Property tax** — annual tax estimate, effective rate
5. **Cash flow estimate** — gross rent minus taxes, insurance (~$150/mo), maintenance (~5% of rent), vacancy (~5-7%), property management (~8-10%)
6. **Cap rate** — NOI / purchase price
7. **Appreciation** — historical CAGR for the zip code
8. **Comparable properties** — nearby comps with prices and distances
9. **Finish grade** — kitchen/bath quality and rent impact (if assessed)

### Step 7: Refinance analysis (optional)

If the user has an existing loan or wants to evaluate financing:
```bash
uv run refinance-analyzer --balance <BALANCE> --current-rate <RATE> --new-rate <RATE>
```

## Quick reference — key metrics

| Metric | Formula |
|---|---|
| Gross yield | (Annual rent / Purchase price) x 100 |
| Cap rate | (Annual rent - Operating expenses) / Purchase price x 100 |
| Cash-on-cash | Annual cash flow / Total cash invested x 100 |
| 1% rule | Monthly rent >= 1% of purchase price |
| GRM | Purchase price / Annual gross rent |
