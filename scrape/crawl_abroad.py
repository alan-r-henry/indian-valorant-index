"""Find Indian-flagged players on teams outside South Asia and crawl their recent matches.

Sources of candidates:
  1. every team in VLR's regional rankings (all regions): roster players flagged India;
  2. Liquipedia players with Indian nationality that have a VLR id (data/lp_indian_players.json);
  3. data/abroad_extra.json: a hand-kept list of VLR player ids, e.g. [12345, 67890].

Outputs:
  data/abroad_players.json   {pid: {alias, real, team_id, team, team_flag, region, source}}
  data/abroad_matches.jsonl  parsed matches for those players that the main crawl does not have
These matches only feed player stats; build.py keeps them out of team ratings and results.
"""
import sys, os, re, json
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vlr, parse_match, crawl

DATA = crawl.DATA
OUT_PLAYERS = os.path.join(DATA, "abroad_players.json")
OUT_MATCHES = os.path.join(DATA, "abroad_matches.jsonl")
REGIONS = {"asia-pacific": "Asia-Pacific", "japan": "Japan", "korea": "Korea", "china": "China", "oceania": "Oceania",
           "europe": "EMEA", "mena": "MENA", "north-america": "North America", "brazil": "Brazil",
           "la-s": "LATAM South", "la-n": "LATAM North", "gc": "Game Changers", "collegiate": "Collegiate"}
WEEK = 7 * 86400
SINCE = "2024-01-01"     # how far back to crawl an abroad player's matches
MAX_PAGES = 4            # player match-list pages (about 50 matches each)


def ranked_teams():
    """team id -> region label, from every VLR regional ranking."""
    out = {}
    for slug, label in REGIONS.items():
        h = vlr.get(f"https://www.vlr.gg/rankings/{slug}", max_age=WEEK) or ""
        for tid in re.findall(r'href="/team/(\d+)/', h):
            out.setdefault(int(tid), label)
        print(f"rankings {slug}: {len(out)} teams so far", flush=True)
    return out


def player_match_ids(pid):
    ids = []
    for page in range(1, MAX_PAGES + 1):
        h = vlr.get(f"https://www.vlr.gg/player/matches/{pid}/x/?page={page}", max_age=3 * 86400 if page == 1 else WEEK)
        if not h:
            break
        items = re.findall(r'<a href="/(\d+)/([^"]+)" class="wf-card[^"]*m-item', h)
        dates = re.findall(r'm-item-date[^>]*>\s*<div>\s*([0-9/]+)', h)
        if not items:
            break
        seen = {m for m, _ in ids}
        for m, s in items:
            if int(m) not in seen:
                seen.add(int(m)); ids.append((int(m), s.split("?")[0].rstrip("/")))
        # VLR lists newest first; stop once the page reaches back past SINCE
        if dates and dates[-1].replace("/", "-") < SINCE:
            break
        if f"page={page + 1}" not in h:
            break
    return ids


def main():
    sa_teams = set()
    teams_raw = json.load(open(crawl.TEAMS, encoding="utf8"))
    for tid, t in teams_raw.items():
        if crawl.is_indian_team(t) or t.get("flag") in crawl.SA_FLAGS:
            sa_teams.add(int(tid))

    # ABROAD_RESCAN=0 reuses the last player list and only fetches their new matches (quick weekly run)
    if os.environ.get("ABROAD_RESCAN", "1") == "0" and os.path.exists(OUT_PLAYERS):
        players = {int(k): v for k, v in json.load(open(OUT_PLAYERS, encoding="utf8")).items()}
        print("reusing", len(players), "abroad players", flush=True)
        return crawl_matches(players)

    region_of = ranked_teams()
    todo = [t for t in region_of if t not in sa_teams]
    print("team pages to scan", len(todo), flush=True)
    team_info = {}

    def scan(tid):
        h = vlr.get(f"https://www.vlr.gg/team/{tid}/x", max_age=WEEK)
        if not h:
            return tid, None
        try:
            return tid, crawl.parse_team(h, tid)
        except Exception as ex:
            print("team fail", tid, ex, flush=True)
            return tid, None

    players = {}
    with ThreadPoolExecutor(3) as ex:
        for k, (tid, t) in enumerate(ex.map(scan, todo)):
            if k % 200 == 0:
                print(f"scanned {k}/{len(todo)} teams, found {len(players)} players", flush=True)
            if not t:
                continue
            team_info[tid] = t
            if t.get("flag") in crawl.SA_FLAGS:
                continue
            for r in t.get("roster", []):
                role = (r.get("role") or "player").lower()
                if r.get("flag") == "in" and (role == "player" or "sub" in role):
                    players[r["pid"]] = dict(alias=r.get("alias", ""), real=r.get("real", ""), team_id=tid,
                                             team=t.get("name", ""), team_flag=t.get("flag", ""),
                                             team_logo=t.get("logo", ""), region=region_of.get(tid, ""),
                                             inactive=t.get("inactive", False), source="vlr-roster")

    # Liquipedia and hand-kept extras: we only know the player, so their current team comes from the match data
    extra = []
    lp_fn = os.path.join(DATA, "lp_indian_players.json")
    if os.path.exists(lp_fn):
        extra += [x["vlr"] for x in json.load(open(lp_fn, encoding="utf8")) if x.get("vlr")]
    ex_fn = os.path.join(DATA, "abroad_extra.json")
    if os.path.exists(ex_fn):
        extra += [int(x) for x in json.load(open(ex_fn, encoding="utf8"))]
    for pid in extra:
        players.setdefault(pid, dict(alias="", real="", team_id=None, team="", team_flag="", team_logo="",
                                     region="", inactive=False, source="liquipedia/extra"))
    print("abroad candidates", len(players), flush=True)
    crawl_matches(players)


def crawl_matches(players):
    """Fetch the matches of these players that neither crawl has yet."""
    done = set(crawl.load_done())
    abroad_done = {}
    if os.path.exists(OUT_MATCHES):
        for line in open(OUT_MATCHES, encoding="utf8"):
            try:
                d = json.loads(line); abroad_done[d["id"]] = d
            except Exception:
                pass
    queue = {}
    with ThreadPoolExecutor(3) as ex:
        for pid, ids in zip(players, ex.map(player_match_ids, list(players))):
            for mid, slug in ids:
                if mid not in done and mid not in abroad_done:
                    queue[mid] = slug
    print("abroad matches to fetch", len(queue), flush=True)

    def fetch(item):
        mid, slug = item
        h = vlr.get(f"https://www.vlr.gg/{mid}/{slug}")
        if not h:
            return None
        try:
            d = parse_match.parse(h, mid)
        except Exception as ex:
            print("parse fail", mid, ex, flush=True)
            return None
        d["slug"] = slug
        return d

    with open(OUT_MATCHES, "a", encoding="utf8") as out, ThreadPoolExecutor(3) as ex:
        for k, d in enumerate(ex.map(fetch, list(queue.items()))):
            if d and (d.get("date") or "")[:10] >= SINCE:
                out.write(json.dumps(d, ensure_ascii=False, separators=(",", ":")) + "\n")
            if k % 100 == 0:
                print(f"match {k}/{len(queue)}", flush=True)

    # teams met in abroad matches: name/logo/flag for display
    json.dump({str(k): v for k, v in players.items()}, open(OUT_PLAYERS, "w", encoding="utf8"), ensure_ascii=False, indent=1)
    print("players", len(players), "done", flush=True)


if __name__ == "__main__":
    main()
