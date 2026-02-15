---
name: rent-estimate
description: Estimate monthly rent for a property in the Denver metro area. Use when the user asks about rent estimates, rental income, how much a property would rent for, or rental comps in Denver, Douglas, Adams, Arapahoe, or Jefferson county.
---

# Rent Estimator

Estimate monthly rent for residential properties in Denver metro counties.

## Gather info from user

Ask the user for (or infer from context):
- County (denver, douglas, adams, arapahoe, jefferson)
- Bedrooms
- Bathrooms
- Square footage
- Finish grade (A/B/C/D/F) — if unknown, default to C or use the finish-grade skill first
- Property type (sfh, townhome, condo, duplex)
- Year built (optional)
- Features (optional): garage_2car, finished_basement, fenced_yard, central_ac, in_unit_laundry, updated_kitchen, updated_bathrooms, pet_friendly, mountain_views

## Run the estimate

```bash
python rent_estimator.py --county <COUNTY> --beds <N> --baths <N> --sqft <N> --grade <A-F> --type <TYPE>
```

Add `--urls` to also show rental comp scraping URLs for live market verification.

Add features with `--features garage_2car finished_basement fenced_yard`

## Show rental comp URLs

```bash
python rent_estimator.py --county <COUNTY> --beds <N> --urls
```

This generates search URLs for Zillow, Trulia, Apartments.com, Craigslist, and Rentometer. Use WebFetch on these URLs to pull live rental listings for verification.

## After running

Present the estimate clearly, including:
1. The monthly rent range (low/mid/high)
2. Annual gross rent
3. Rent per square foot
4. How the finish grade affects the number
5. Suggest using `--urls` if they want live comp verification
6. For investment analysis, connect to refinance_analyzer.py for cash flow modeling
