# CLAUDE.md

## Project Overview

Real Estate AI Agent System — a Python CLI tool that uses CrewAI agents and Bright Data's MCP server to extract structured property data from real estate listing websites (Zillow, Realtor.com, Redfin). It outputs strict snake_case JSON with property details.

This is a single-script application with no web server, no database, and no API. It runs as a batch process.

## Repository Structure

```
real-estate-ai-agent/
├── real_estate_agents.py   # Entire application logic (single entry point)
├── pyproject.toml           # Project metadata and Python version constraint
├── README.md                # User-facing documentation
└── .env                     # Required: API keys (not committed)
```

There are no subdirectories, test files, or configuration for linting/CI.

## Tech Stack

- **Language:** Python 3.9 (exact version constraint in pyproject.toml: `== 3.9.*`)
- **Agent framework:** CrewAI (orchestrates AI agents with tools)
- **MCP integration:** `crewai-tools[mcp]` + `mcp` (Model Context Protocol for Bright Data)
- **LLM:** Nebius Qwen (`nebius/Qwen/Qwen3-235B-A22B`) via CrewAI's LLM wrapper
- **Web scraping infrastructure:** Bright Data MCP server (`@brightdata/mcp` npm package)
- **Data handling:** pandas, json (stdlib)
- **Environment management:** python-dotenv
- **Package manager:** uv (configured in pyproject.toml)

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
- Python 3.9+
- Node.js + npm (required for the Bright Data MCP server spawned via `npx`)
- Valid API credentials in `.env`

### Setup
```sh
python3.9 -m venv venv
source venv/bin/activate          # macOS/Linux
pip install "crewai-tools[mcp]" crewai mcp python-dotenv pandas
```

### Execute
```sh
python real_estate_agents.py
```

Output is printed to stdout as JSON on success, or an error message on failure.

## Architecture & Code Flow

The application follows a linear CrewAI agent pipeline in `real_estate_agents.py`:

1. **Initialization (lines 1-12):** Import dependencies, load `.env` variables.
2. **LLM setup (lines 15-19):** Configure Nebius Qwen LLM with API key.
3. **MCP server config (lines 22-30):** Define Bright Data MCP server parameters (spawned as a child process via `npx`).
4. **`build_scraper_agent()` (lines 32-51):** Creates a CrewAI Agent with role "Senior Real Estate Data Extractor", MCP tools, and max 3 iterations.
5. **`build_scraping_task()` (lines 53-76):** Defines the scraping task with a target URL and expected JSON output schema.
6. **`scrape_property_data()` (lines 79-91):** Assembles the Crew (sequential process) and kicks off execution.
7. **`__main__` block (lines 93-100):** Entry point with try/except error handling.

### Key Patterns
- **Single-agent crew:** Only one agent (`scraper_agent`) and one task (`scraping_task`).
- **MCP context manager:** `MCPServerAdapter(server_params)` is used as a context manager that starts/stops the Bright Data MCP server subprocess.
- **Sequential process:** `Process.sequential` (only one task, so order is trivial).
- **Hardcoded target URL:** The Zillow URL in `build_scraping_task()` is hardcoded — modify it to scrape a different listing.

## Output Schema

The agent returns JSON with these snake_case keys:

```
address, price, bedrooms, bathrooms, square_feet, lot_size,
year_built, property_type, listing_agent, days_on_market,
mls_number, description, image_urls, neighborhood
```

## Development Conventions

### Code Style
- No linter or formatter is configured. When making changes, match the existing style:
  - 4-space indentation
  - Double-quoted strings for multi-line text, mixed quoting elsewhere
  - Functions use snake_case
  - Inline comments are minimal; docstrings are brief

### Dependencies
- Managed via `pip install` directly (not locked). `pyproject.toml` lists them as a comment only.
- The `[tool.uv]` section in `pyproject.toml` is a placeholder — uv-specific config is not actively used.

### No Tests
- There are no tests, no test framework, and no CI/CD pipeline.
- If adding tests, `pytest` would be the conventional choice for a Python project of this type.

### No Docker
- No containerization is set up. The app requires Python 3.9+ and Node.js installed locally.

## Common Modifications

- **Change target URL:** Edit the URL string in `build_scraping_task()` at line 56.
- **Add output fields:** Update the `goal` string in `build_scraper_agent()` and the `expected_output` in `build_scraping_task()`.
- **Switch LLM:** Change the `model` parameter in the `LLM()` constructor at line 17.
- **Increase agent iterations:** Adjust `max_iter` in `build_scraper_agent()` at line 49.

## Security Notes

- All API keys must be stored in `.env` and loaded via `python-dotenv`.
- Do not commit `.env` or any file containing secrets.
- Respect `robots.txt` and website terms of service when scraping.
