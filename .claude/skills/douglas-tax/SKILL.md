---
name: douglas-tax
description: Estimate property tax for Douglas County, Colorado. Use when the user asks about Douglas County property taxes, Douglas County tax estimates, or wants to look up property tax in Castle Rock, Parker, Highlands Ranch, Lone Tree, or Castle Pines.
---

# Douglas County Property Tax Estimator

Estimate residential property tax for Douglas County, Colorado.

## How to use

Run the property tax estimator module for Douglas County:

```bash
uv run property-tax --county douglas --value <MARKET_VALUE>
```

Replace `<MARKET_VALUE>` with the property's market value in dollars. Ask the user for this value if not provided.

## Key Douglas County tax facts

- Sample total mill levy: **75.541 mills** (23.425 local + 52.116 school)
- Colorado split assessment: 6.25% local / 7.05% school
- Effective rate: ~0.64% of market value (highest median tax bill in CO due to high home values)
- **Metro districts** in newer developments (e.g., Highlands Ranch, Sterling Ranch) can add 30-50+ mills

## Override mill levies

If the user has specific mill levy numbers or is in a metro district:

```bash
uv run property-tax --county douglas --value <VALUE> --school-mills <SCHOOL> --local-mills <LOCAL>
```

## Look up actual tax records

Direct the user to these official Douglas County sites:
- **Property search:** https://apps.douglas.co.us/assessor/web/
- **Tax payments:** https://apps.douglas.co.us/treasurer/treasurerweb/search.jsp?guest=true
- **Tax calculation explanation:** https://www.douglas.co.us/assessor/residential-property-tax-calculations/

## Compare with neighboring counties

```bash
uv run property-tax --all --value <MARKET_VALUE>
```

## After running

Present the results clearly. Remind the user that:
1. Douglas County metro districts can significantly increase the total levy — ask if they know their metro district
2. They can look up their exact tax at the assessor URL above
3. For rental properties, mortgage interest and property taxes are deductible against rental income
