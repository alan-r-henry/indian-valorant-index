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
- **Circuit tracker**: how far every Indian team got in open qualifiers, Challengers
  South Asia, Ascension/LCQ, VCT Pacific, internationals, Game Changers and third-party cups.
- **Tournaments, meta, records, roll of honour** and a method page explaining every number.

## Layout
| Path | What it does |
|---|---|
| `scrape/vlr.py` | Cached VLR fetcher (gzip pages in `cache/vlr`, about 2 requests/s) |
| `scrape/lp.py` | Liquipedia API helper (1 request every 2 s, 50 titles per call, cache in `cache/lp`) |
| `scrape/crawl_events.py` | Lists VLR Pacific-region events into `data/vlr_events_pacific.json` |
| `scrape/crawl.py` | Seeds from Indian/South Asian events and expands through every Indian team's match history into `data/matches.jsonl` and `data/teams_raw.json` |
| `scrape/build.py` | Ratings, aggregates, events and the Liquipedia join, written to `site/data.js` |
| `site/` | The static site (plain HTML/JS, no build step), deployed to GitHub Pages |

## Refresh the data
Needs Python 3.10+ and no third-party packages.
```
cd scrape
python -X utf8 crawl_events.py
python -X utf8 crawl.py
python -X utf8 build.py
```
Team match lists and event lists are re-fetched after 6 hours; match pages are cached
for good. Pushing `site/` to `main` redeploys the site.

## Data and attribution
- Match, map and player stats: [VLR.gg](https://www.vlr.gg).
- Player biographies (birth dates, real names, roles): [Liquipedia](https://liquipedia.net/valorant),
  licensed [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/).
- Rating ideas (opponent adjustment, peak performance, visible sample sizes) are borrowed
  from [1trick.gg](https://www.1trick.gg).

This is an unofficial fan project. It is not affiliated with or endorsed by Riot Games,
VLR.gg or Liquipedia. Valorant is a trademark of Riot Games, Inc.

Code is MIT licensed (see `LICENSE`).
