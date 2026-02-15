---
name: denver-tax
description: Estimate property tax for Denver County, Colorado. Use when the user asks about Denver property taxes, Denver tax estimates, or wants to look up property tax in Denver.
---

# Denver County Property Tax Estimator

Estimate residential property tax for Denver (City & County), Colorado.

## How to use

Run the property tax estimator module for Denver:

```bash
python property_tax_estimator.py --county denver --value <MARKET_VALUE>
```

Replace `<MARKET_VALUE>` with the property's market value in dollars. Ask the user for this value if not provided.

## Key Denver tax facts

- Denver is a consolidated city-county (no separate city levy)
- 2025 combined mill levy: **79.602 mills** (27.328 local + 52.274 school)
- Colorado split assessment: 6.25% local / 7.05% school
- Effective rate: ~0.54% of market value

## Override mill levies

If the user has specific mill levy numbers from their tax bill:

```bash
python property_tax_estimator.py --county denver --value <VALUE> --school-mills <SCHOOL> --local-mills <LOCAL>
```

## Look up actual tax records

Direct the user to these official Denver sites:
- **Property search:** https://www.denvergov.org/Property
- **Tax payments:** https://denvergov.org/Government/Agencies-Departments-Offices/Agencies-Departments-Offices-Directory/Department-of-Finance/Our-Divisions/Treasury/Property-Taxes

## Compare with neighboring counties

```bash
python property_tax_estimator.py --all --value <MARKET_VALUE>
```

## After running

Present the results clearly. Remind the user that:
1. Mill levies vary by exact address depending on special districts
2. They can look up their exact tax at the assessor URL above
3. For rental properties, mortgage interest and property taxes are deductible against rental income
