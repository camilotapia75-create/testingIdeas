# Autonomous Ad Agent

This agent runs every night via GitHub Actions, generates high-quality social media ad copy using Claude, tracks which ad styles perform best, and gets smarter over time by biasing generation toward winning patterns.

## Setup (5 minutes)

### 1. Add your Anthropic API key as a GitHub Secret
- Go to your repo → **Settings → Secrets and variables → Actions**
- Click **New repository secret**
- Name: `ANTHROPIC_API_KEY`
- Value: your key from https://console.anthropic.com

### 2. Configure your websites and products
Edit `config.json` — add your website URLs, product descriptions, and target audiences.

### 3. (Optional) Score your ads
After posting ads, edit `performance.json` to record which ones got the best engagement (likes, clicks, conversions). The agent reads these scores and generates more ads in the style of your winners.

## How it works

```
Every night at 2am UTC:
  1. Reads config.json (your websites/products)
  2. Reads performance.json (which past ads scored highest)
  3. Extracts winning patterns (hooks, CTAs, tone, length)
  4. Generates 10 new social media ads biased toward those patterns
  5. Saves them to ads/YYYY-MM-DD.json
  6. Commits and pushes to the repo
```

## File structure

```
ads/                    # Generated ad copy, one file per day
  2024-01-15.json
  2024-01-16.json
performance.json        # Your scores — edit this to teach the agent
config.json             # Your websites, products, audiences
generate_ads.py         # The agent script
.github/workflows/
  nightly_ads.yml       # GitHub Actions cron job
```

## Scoring ads

Open `performance.json` and set scores (0–10) on any ads you've posted:

```json
{
  "ads": [
    {
      "id": "2024-01-15-003",
      "score": 9,
      "notes": "Got 400 clicks, high CTR on Instagram"
    }
  ]
}
```

The agent will automatically learn from scores ≥ 7 and replicate their style.
