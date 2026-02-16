# CLAUDE.md

## Project Overview

Real Estate AI Agent System — a Python toolkit for Denver metro real estate investment analysis. Includes property scraping via CrewAI + Bright Data MCP, comparable property database (SQLite), tax estimation, rent estimation, finish quality grading, and appreciation tracking.

## Repository Structure

```
real-estate-ai-agent/
├── real_estate_agents.py       # CrewAI scraper agent (Bright Data MCP)
├── refinance_analyzer.py       # Mortgage refinancing tradeoff analysis
├── property_tax_estimator.py   # Property tax estimation (5 Denver metro counties)
├── rent_estimator.py           # Rent estimation with grade adjustments
├── comp_extractor.py           # Comp search URLs, scraping helpers, DB bridge
├── comps_db.py                 # SQLite database for all comps + geocoding
├── finish_grader.py            # Kitchen/bathroom finish quality grading (A-F)
├── appreciation_tracker.py     # Zillow ZHVI data sync + zip-code appreciation
├── browser_scraper.py         # Stealth headless browser scraper (Playwright)
├── pyproject.toml              # uv project config with dependencies + entry points
├── uv.lock                     # Locked dependency versions
├── CLAUDE.md                   # This file
├── README.md                   # User-facing documentation
├── .gitignore                  # Ignores .env, .venv, data/, photos, pycache
├── .env                        # Required: API keys (not committed)
└── .claude/skills/             # Claude Code skills for guided workflows
    ├── comps/                  # Sale + rental comp routing
    ├── sold-comps/             # Recently sold comp workflow
    ├── comps-search/           # Shared scrape-and-store pipeline
    ├── rent-estimate/          # Rent estimation workflow
    ├── finish-grade/           # Photo-based finish quality grading
    ├── appreciation/           # Zip-code appreciation lookup
    ├── denver-tax/             # Denver County property tax
    ├── douglas-tax/            # Douglas County property tax
    ├── adams-tax/              # Adams County property tax
    ├── arapahoe-tax/           # Arapahoe County property tax
    └── jefferson-tax/          # Jefferson County property tax
```

## Tech Stack

- **Language:** Python 3.10+ (all modules use stdlib except real_estate_agents.py)
- **Package manager:** uv — `uv sync` to install, `uv run <command>` to execute
- **Agent framework:** CrewAI (orchestrates AI agents with tools)
- **MCP integration:** `crewai-tools[mcp]` + `mcp` (Model Context Protocol for Bright Data)
- **LLM:** Nebius Qwen (`nebius/Qwen/Qwen3-235B-A22B`) via CrewAI's LLM wrapper
- **Web scraping infrastructure:** Bright Data MCP server (`@brightdata/mcp` npm package); Playwright + playwright-stealth for headless browser scraping
- **Database:** SQLite (comps.db in data/ directory, WAL mode)
- **Geocoding:** OpenStreetMap Nominatim (free, no API key)
- **Data handling:** pandas, json (stdlib)
- **Environment management:** python-dotenv

## Required Environment Variables

A `.env` file is required at the project root with these keys:

| Variable | Purpose |
|---|---|
| `BRIGHT_DATA_API_TOKEN` | Bright Data API authentication |
| `WEB_UNLOCKER_ZONE` | Bright Data Web Unlocker zone name |
| `BROWSER_ZONE` | Bright Data Browser zone name |
| `NEBIUS_API_KEY` | Nebius AI platform API key for Qwen LLM |

**Never commit `.env` files or hardcode API keys.**

## How to Run

### Prerequisites
- Python 3.10+
- uv (`pip install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Node.js + npm (required for Bright Data MCP server via `npx`)
- Valid API credentials in `.env`

### Setup
```sh
uv sync
uv run playwright install chromium   # one-time: install headless browser
```

### Available Commands

All tools are available via `uv run`:

```sh
uv run real-estate-agents                    # Run the CrewAI scraper
uv run refinance-analyzer --help             # Mortgage refinancing analysis
uv run property-tax --county denver --value 625000  # Property tax estimate
uv run rent-estimator --county denver --beds 3      # Rent estimate
uv run comp-extractor --type sale --county denver    # Comp search URLs
uv run comp-extractor --db-query --type sale --near "39.75,-104.99" --radius 2
uv run comp-extractor --geocode              # Batch geocode comps
uv run comps-db stats                        # Database overview
uv run comps-db query --type sale --county denver --beds 3
uv run browser-scraper --rental --zip 80205 --beds 3   # Stealth scrape rentals
uv run browser-scraper --sold --zip 80205 --price 475000  # Stealth scrape sold
uv run finish-grader --rubric                # Finish quality rubric
uv run appreciation-tracker --county denver  # Appreciation by county
```

### Adding Dependencies

```sh
uv add <package-name>
```

## Development Conventions

### Code Style
- No linter or formatter is configured. When making changes, match the existing style:
  - 4-space indentation
  - Double-quoted strings for multi-line text, mixed quoting elsewhere
  - Functions use snake_case
  - Inline comments are minimal; docstrings are brief

### Dependencies
- Managed via uv. `pyproject.toml` declares dependencies; `uv.lock` pins exact versions.
- Most modules use only Python stdlib. Exceptions: `real_estate_agents.py` (CrewAI/MCP) and `browser_scraper.py` (Playwright).

### No Tests
- There are no tests, no test framework, and no CI/CD pipeline.
- If adding tests, `pytest` would be the conventional choice.

### No Docker
- No containerization is set up.

## Security Notes

- All API keys must be stored in `.env` and loaded via `python-dotenv`.
- Do not commit `.env` or any file containing secrets.
- Respect `robots.txt` and website terms of service when scraping.
