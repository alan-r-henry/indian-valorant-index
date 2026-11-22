# Indian Valorant Index

**Live site: https://alan-r-henry.github.io/indian-valorant-index/**

A fan-made stats site for the Indian Valorant scene: team rankings, player stats,
circuit tracking and tournament history, built from every match VLR.gg has recorded
for Indian teams since 2020.

## What's on it
- **Team rankings**: map-level Elo, weighted by round margin and opponent strength, with
  foreign teams as anchors. Switch between active teams, a season, the last two years or
  all-time; Open or Game Changers; Indian only or all of South Asia.
- **Team profiles**: rating history, roster, map pool with picks and bans, results by
  circuit, head-to-heads and event history.
- **Players**: the top 100 by an opponent-adjusted rating, with filters for age, role,
  agent, team, period and minimum maps, plus about 18 sortable stat columns. Player
  profiles show role percentiles, season, agent and map splits, and best games.
- **Indians abroad**: Indian-flagged players on teams in other regions (found by scanning every
  roster in VLR's regional rankings), tagged "Abroad" with their region everywhere they appear.
- **Compare**: up to four players side by side, best value per stat highlighted, with form lines.
- **Head-to-head**: every meeting between two teams, map pools side by side and the map, Bo3
  and Bo5 win chances their Elo ratings imply.
- **Results**: every recorded series, searchable by team or event.
- **Circuit tracker**: how far every Indian team got in open qualifiers, Challengers
  South Asia, Ascension/LCQ, VCT Pacific, internationals, Game Changers and third-party cups.
- **Tournaments, meta, records, roll of honour** and a method page explaining every number.

Every filtered view has its own link (for example `#players?role=Duelist&ageMax=21`), tables
export to CSV, and `/` jumps to search.

## Layout
| Path | What it does |
|---|---|
| `scrape/vlr.py` | Cached VLR fetcher (gzip pages in `cache/vlr`, about 2 requests/s) |
| `scrape/lp.py` | Liquipedia API helper (1 request every 2 s, 50 titles per call, cache in `cache/lp`) |
| `scrape/crawl_events.py` | Lists VLR Pacific-region events into `data/vlr_events_pacific.json` |
| `scrape/crawl.py` | Seeds from Indian/South Asian events and expands through every Indian team's match history into `data/matches.jsonl` and `data/teams_raw.json` |
| `scrape/refresh_teams.py` | Re-reads team pages older than five days for teams active in the last 18 months, so new logos, names and rosters reach the site |
| `scrape/find_abroad.py` | Liquipedia players with Indian nationality into `data/lp_indian_players.json` |
| `scrape/crawl_abroad.py` | Scans every VLR regional ranking's rosters for Indian-flagged players abroad and crawls their matches since 2024 (`data/abroad_*.json*`); `ABROAD_RESCAN=0` only fetches new matches |
| `scrape/build.py` | Ratings, aggregates, events and the Liquipedia join, written to `site/data.js` |
| `scrape/og_image.py` | Draws the social preview card `site/og.png` (needs Pillow) |
| `site/` | The static site (plain HTML/JS, no build step), deployed to GitHub Pages |

## Refresh the data
A GitHub Action (`.github/workflows/refresh.yml`) re-crawls every Monday at 08:00 IST, commits
the new data and redeploys. Run it by hand from the Actions tab ("Refresh data"); tick the box
to rescan every region for Indian players abroad.

Locally: Python 3.10+, plus Pillow for the preview image.
```
cd scrape
python -X utf8 crawl_events.py
python -X utf8 crawl.py
python -X utf8 refresh_teams.py
python -X utf8 find_abroad.py
python -X utf8 crawl_abroad.py
python -X utf8 build.py
python -X utf8 og_image.py
```
Team match lists and event lists are re-fetched after 6 hours; match pages are cached
for good. Pushing `site/` to `main` redeploys the site.

Missing an Indian player who plays abroad? Add their VLR player id to `data/abroad_extra.json`
(a JSON list of numbers) or open an issue.

## Data and attribution
- Match, map and player stats: [VLR.gg](https://www.vlr.gg).
- Player biographies (birth dates, real names, roles): [Liquipedia](https://liquipedia.net/valorant),
  licensed [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/).
- Rating ideas (opponent adjustment, peak performance, visible sample sizes) are borrowed
  from [1trick.gg](https://www.1trick.gg).

This is an unofficial fan project. It is not affiliated with or endorsed by Riot Games,
VLR.gg or Liquipedia. Valorant is a trademark of Riot Games, Inc.

Code is MIT licensed (see `LICENSE`).
