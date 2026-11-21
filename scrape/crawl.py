"""Resumable VLR crawl of the Indian scene.
Seeds: Indian/South Asian events. Expands through Indian teams' full match histories."""
import sys, os, re, json, html as H
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vlr, parse_match

# Optional local progress reporting (JobTray). Set JOB_STEWARD_PATH to enable; otherwise a no-op.
if os.environ.get("JOB_STEWARD_PATH"):
    sys.path.insert(0, os.environ["JOB_STEWARD_PATH"])
    import jobstatus
else:
    class _NoJob:
        def __init__(self, *a, **k): pass
        def update(self, **k): pass
        def finish(self, **k): print(k.get("message", "done"))

    class jobstatus:  # noqa: N801
        Job = _NoJob

DATA = os.path.join(vlr.ROOT, "data")
MATCHES = os.path.join(DATA, "matches.jsonl")
TEAMS = os.path.join(DATA, "teams_raw.json")
SA_FLAGS = {"in", "bd", "pk", "np", "lk", "mv", "bt", "af"}


def txt(s):
    return H.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', s))).strip()


def load_done():
    done = {}
    if os.path.exists(MATCHES):
        for line in open(MATCHES, encoding="utf8"):
            try:
                d = json.loads(line)
                done[d["id"]] = d
            except Exception:
                pass
    return done


def parse_team(h, tid):
    h = re.sub(r'<svg.*?</svg>', '', h, flags=re.S)
    t = {"id": tid}
    m = re.search(r'<h1 class="wf-title"[^>]*>(.*?)</h1>', h, re.S)
    t["name"] = txt(m.group(1)) if m else ''
    m = re.search(r'team-header-tag">(.*?)</h2>', h, re.S)
    t["tag"] = txt(m.group(1)) if m else ''
    m = re.search(r'team-header-country">\s*<i class="flag mod-([a-z0-9-]+)"></i>\s*(.*?)\s*</div>', h, re.S)
    t["flag"] = m.group(1) if m else ''
    t["country"] = txt(m.group(2)) if m else ''
    m = re.search(r'team-header-logo">\s*<div>\s*<img src="([^"]+)"', h, re.S)
    t["logo"] = m.group(1) if m else ''
    head = re.search(r'team-header-name">(.*?)team-header-links', h, re.S)
    t["inactive"] = bool(head and 'inactive' in head.group(1).lower())
    succ = re.search(r'team-header-name-successor">(.*?)</div>', h, re.S)
    t["successor"] = txt(succ.group(1)) if succ else ''
    links = re.search(r'team-header-links">(.*?)</div>', h, re.S)
    t["links"] = re.findall(r'href="([^"]+)"', links.group(1)) if links else []
    roster = []
    for blk in re.findall(r'<div class="team-roster-item">(.*?)</a>\s*</div>', h, re.S):
        pm = re.search(r'href="/player/(\d+)/([^"]*)"', blk)
        if not pm:
            continue
        fl = re.search(r'flag mod-([a-z0-9-]+)', blk)
        alias = re.search(r'team-roster-item-name-alias">(.*?)</div>', blk, re.S)
        real = re.search(r'team-roster-item-name-real">(.*?)</div>', blk, re.S)
        role = re.search(r'team-roster-item-name-role">(.*?)</div>', blk, re.S)
        img = re.search(r'<img src="([^"]+)"', blk)
        roster.append({"pid": int(pm.group(1)), "alias": txt(alias.group(1)) if alias else pm.group(2),
                       "real": txt(real.group(1)) if real else '', "flag": fl.group(1) if fl else '',
                       "role": txt(role.group(1)).lower() if role else 'player',
                       "img": img.group(1) if img else '', "captain": 'fa-star' in blk})
    t["roster"] = roster
    rk = re.search(r'rank-num[^>]*>\s*#?(\d+)', h)
    t["vlr_rank"] = int(rk.group(1)) if rk else None
    rr = re.search(r'mod-rating">.*?rating-num">\s*([\d,]+)', h, re.S)
    t["vlr_rating"] = rr.group(1) if rr else None
    w = re.search(r'Total Winnings.*?<span[^>]*>\s*(\$[\d,\.]+)', h, re.S)
    t["winnings"] = w.group(1) if w else None
    return t


def is_indian_team(t):
    if t.get("flag") == "in":
        return True
    pl = [p for p in t.get("roster", []) if p["role"] in ("player", "") or "sub" in p["role"]]
    return sum(1 for p in pl if p["flag"] == "in") >= 3


def team_match_list(tid, refresh_first=True):
    urls = []
    page = 1
    while page < 80:
        h = vlr.get(f"https://www.vlr.gg/team/matches/{tid}/x/?page={page}",
                    max_age=6 * 3600 if (page == 1 and refresh_first) else None)
        if not h:
            break
        items = re.findall(r'<a href="/(\d+)/([^"]+)" class="wf-card fc-flex m-item', h)
        if not items:
            break
        for mid, slug in items:
            urls.append((int(mid), slug))
        pages = [int(x) for x in re.findall(r'[?&]page=(\d+)', h)]
        if page >= (max(pages) if pages else 1):
            break
        page += 1
    return urls


def event_match_list(eid):
    h = vlr.get(f"https://www.vlr.gg/event/matches/{eid}/x/?series_id=all&group=all", max_age=6 * 3600)
    if not h:
        return []
    return [(int(a), b) for a, b in re.findall(r'href="/(\d+)/([^"]+)" class="wf-module-item match-item', h)]


def main():
    job = jobstatus.Job("ivs-crawl", "Indian Valorant site: VLR crawl", unit="matches")
    done = load_done()
    teams = json.load(open(TEAMS, encoding="utf8")) if os.path.exists(TEAMS) else {}
    events = json.load(open(os.path.join(DATA, "vlr_events_pacific.json"), encoding="utf8"))
    seed_events = [e for e in events if e["flag"] in SA_FLAGS or re.search(r'india|south asia', e["title"], re.I)]
    queue = {}
    for i, e in enumerate(seed_events):
        job.update(message=f"event lists {i + 1}/{len(seed_events)}")
        for mid, slug in event_match_list(e["id"]):
            queue[mid] = slug
    for mid, d in done.items():
        queue.setdefault(mid, d.get("slug", "x"))
    expanded = set()
    out = open(MATCHES, "a", encoding="utf8")
    rnd = 0
    while True:
        rnd += 1
        todo = [m for m in queue if m not in done]
        print(f"round {rnd}: {len(todo)} matches to fetch, {len(done)} done", flush=True)
        from concurrent.futures import ThreadPoolExecutor
        def fetch(mid):
            h = vlr.get(f"https://www.vlr.gg/{mid}/{queue[mid]}")
            if not h:
                return None
            try:
                d = parse_match.parse(h, mid)
            except Exception as ex:
                print("parse fail", mid, ex, flush=True)
                return None
            d["slug"] = queue[mid]
            return d
        with ThreadPoolExecutor(3) as ex:
            for k, d in enumerate(ex.map(fetch, todo)):
                if d is None:
                    continue
                done[d["id"]] = d
                out.write(json.dumps(d, ensure_ascii=False, separators=(",", ":")) + "\n")
                if k % 25 == 0:
                    out.flush()
                    job.update(done=len(done), total=len(done) + len(todo) - k - 1,
                               message=f"round {rnd}: match {k + 1}/{len(todo)}")
        out.flush()
        tids = set()
        for d in done.values():
            for t in d.get("teams", []):
                tids.add(str(t["id"]))
        newt = [t for t in tids if t not in teams]
        with ThreadPoolExecutor(3) as ex:
            list(ex.map(lambda t: vlr.get(f"https://www.vlr.gg/team/{t}/x"), newt))
        for k, tid in enumerate(newt):
            h = vlr.get(f"https://www.vlr.gg/team/{tid}/x")
            if h:
                try:
                    teams[tid] = parse_team(h, int(tid))
                except Exception as ex:
                    print("team fail", tid, ex, flush=True)
                    teams[tid] = {"id": int(tid)}
            if k % 25 == 0:
                job.update(message=f"round {rnd}: team pages {k + 1}/{len(newt)}")
                json.dump(teams, open(TEAMS, "w", encoding="utf8"), ensure_ascii=False)
        json.dump(teams, open(TEAMS, "w", encoding="utf8"), ensure_ascii=False)
        grow = 0
        ind = [tid for tid, t in teams.items() if is_indian_team(t) and tid not in expanded]
        with ThreadPoolExecutor(3) as ex:
            lists = list(ex.map(team_match_list, ind))
        for k, tid in enumerate(ind):
            expanded.add(tid)
            for mid, slug in lists[k]:
                if mid not in queue:
                    queue[mid] = slug
                    grow += 1
            if k % 10 == 0:
                job.update(message=f"round {rnd}: team histories {k + 1}/{len(ind)}")
        n_ind = sum(1 for t in teams.values() if is_indian_team(t))
        print(f"round {rnd}: teams {len(teams)}, indian {n_ind}, new matches {grow}", flush=True)
        if grow == 0 and not [m for m in queue if m not in done]:
            break
    job.finish(message=f"{len(done)} matches, {len(teams)} teams")


if __name__ == "__main__":
    main()
