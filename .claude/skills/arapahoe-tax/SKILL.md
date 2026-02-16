---
name: arapahoe-tax
description: Estimate property tax for Arapahoe County, Colorado. Use when the user asks about Arapahoe County property taxes, Arapahoe County tax estimates, or wants to look up property tax in Aurora, Centennial, Littleton, Englewood, Greenwood Village, or Cherry Hills Village.
---

# Arapahoe County Property Tax Estimator

Estimate residential property tax for Arapahoe County, Colorado.

## How to use

Run the property tax estimator module for Arapahoe County:

```bash
uv run property-tax --county arapahoe --value <MARKET_VALUE>
```

Replace `<MARKET_VALUE>` with the property's market value in dollars. Ask the user for this value if not provided.

## Key Arapahoe County tax facts

- County levy: **15.855 mills** (2025); total depends on overlapping districts
- Colorado split assessment: 6.25% local / 7.05% school
- School district portion is typically 45-50% of total tax bill
- Effective rate: ~0.52% of market value
- Voters passed Measure 1A in Nov 2024, removing a temporary TABOR mill levy credit

## Override mill levies

If the user has specific mill levy numbers from their tax bill:

```bash
uv run property-tax --county arapahoe --value <VALUE> --school-mills <SCHOOL> --local-mills <LOCAL>
```

## Look up actual tax records

Direct the user to these official Arapahoe County sites:
- **Property search:** https://www.arapahoeco.gov/your_county/county_departments/assessor/property_search/index.php
- **Tax payments:** https://www.arapahoeco.gov/your_county/county_departments/treasurer/tax_search.php
- **Mill levies & districts:** https://www.arapahoeco.gov/your_county/county_departments/assessor/mill_levies_and_tax_districts.php

## Compare with neighboring counties

```bash
uv run property-tax --all --value <MARKET_VALUE>
```

## After running

Present the results clearly. Remind the user that:
1. Arapahoe has many overlapping taxing districts — exact levy depends on address
2. They can look up their exact tax at the assessor URL above
3. For rental properties, mortgage interest and property taxes are deductible against rental income
