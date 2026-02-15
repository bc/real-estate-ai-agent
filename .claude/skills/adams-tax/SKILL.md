---
name: adams-tax
description: Estimate property tax for Adams County, Colorado. Use when the user asks about Adams County property taxes, Adams County tax estimates, or wants to look up property tax in Brighton, Thornton, Westminster, Commerce City, Northglenn, or Federal Heights.
---

# Adams County Property Tax Estimator

Estimate residential property tax for Adams County, Colorado.

## How to use

Run the property tax estimator module for Adams County:

```bash
python property_tax_estimator.py --county adams --value <MARKET_VALUE>
```

Replace `<MARKET_VALUE>` with the property's market value in dollars. Ask the user for this value if not provided.

## Key Adams County tax facts

- Example local mills: ~55.884, school mills: ~69.071
- Colorado split assessment: 6.25% local / 7.05% school
- Effective rate: ~0.57-0.60% of market value
- Mill levies vary significantly between municipalities in the county

## Override mill levies

If the user has specific mill levy numbers from their tax bill:

```bash
python property_tax_estimator.py --county adams --value <VALUE> --school-mills <SCHOOL> --local-mills <LOCAL>
```

## Look up actual tax records

Direct the user to these official Adams County sites:
- **Property search:** https://adamscountyco.gov/service/search-real-property/
- **Tax payments:** https://adcotax.com/treasurer/web/login.jsp
- **Assessment process:** https://adamscountyco.gov/property-assessment-process

## Compare with neighboring counties

```bash
python property_tax_estimator.py --all --value <MARKET_VALUE>
```

## After running

Present the results clearly. Remind the user that:
1. Mill levies vary significantly between municipalities within Adams County
2. They can look up their exact tax at the assessor URL above
3. For rental properties, mortgage interest and property taxes are deductible against rental income
