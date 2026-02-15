---
name: jefferson-tax
description: Estimate property tax for Jefferson County, Colorado. Use when the user asks about Jefferson County (Jeffco) property taxes, Jeffco tax estimates, or wants to look up property tax in Lakewood, Arvada, Golden, Wheat Ridge, or Evergreen.
---

# Jefferson County Property Tax Estimator

Estimate residential property tax for Jefferson County, Colorado.

## How to use

Run the property tax estimator module for Jefferson County:

```bash
python property_tax_estimator.py --county jefferson --value <MARKET_VALUE>
```

Replace `<MARKET_VALUE>` with the property's market value in dollars. Ask the user for this value if not provided.

## Key Jefferson County tax facts

- Sample total mill levy: **90.639 mills** (43.564 local + 47.075 school)
- Colorado split assessment: 6.25% local / 7.05% school
- Fire district levy is a significant component (~14.9 mills)
- Effective rate: ~0.51% of market value
- Median home value: ~$632,958

## Override mill levies

If the user has specific mill levy numbers from their tax bill:

```bash
python property_tax_estimator.py --county jefferson --value <VALUE> --school-mills <SCHOOL> --local-mills <LOCAL>
```

## Look up actual tax records

Direct the user to these official Jefferson County sites:
- **Property search:** https://propertysearch.jeffco.us/propertyrecordssearch/address
- **Tax payments:** https://treasurerpropertysearch.jeffco.us/
- **How taxes are calculated:** https://www.jeffco.us/820/How-Property-Taxes-are-Calculated

## Compare with neighboring counties

```bash
python property_tax_estimator.py --all --value <MARKET_VALUE>
```

## After running

Present the results clearly. Remind the user that:
1. Jefferson County mill levies vary significantly by fire district and municipality
2. They can look up their exact tax at the assessor URL above
3. For rental properties, mortgage interest and property taxes are deductible against rental income
