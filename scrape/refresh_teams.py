"""Re-fetch team pages so logos, names and rosters changed on VLR reach the site.

crawl.py fetches a team page only the first time it meets the team; this step
re-reads pages older than five days for every team that played in the last 18 months.
"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vlr, crawl
from concurrent.futures import ThreadPoolExecutor

MAX_AGE = 5 * 86400  # under a week, so every weekly run re-reads them
cutoff = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 548 * 86400))
done = crawl.load_done()
tids = sorted({str(t["id"]) for d in done.values() if (d.get("date") or "") >= cutoff
               for t in d.get("teams", [])})
teams = json.load(open(crawl.TEAMS, encoding="utf8"))


def fetch(tid):
    return tid, vlr.get(f"https://www.vlr.gg/team/{tid}/x", max_age=MAX_AGE)


changed = 0
with ThreadPoolExecutor(3) as ex:
    for tid, h in ex.map(fetch, tids):
        if not h:
            continue
        try:
            t = crawl.parse_team(h, int(tid))
        except Exception as e:
            print("team fail", tid, e, flush=True)
            continue
        if not t.get("name"):
            continue
        old = teams.get(tid, {})
        if old.get("logo") != t.get("logo") or old.get("name") != t.get("name"):
            changed += 1
        teams[tid] = t
json.dump(teams, open(crawl.TEAMS, "w", encoding="utf8"), ensure_ascii=False)
placeholder = sum(1 for t in tids if "/tmp/vlr.png" in (teams.get(t, {}).get("logo") or ""))
print(f"team pages checked {len(tids)}, logo or name changed {changed}, still placeholder {placeholder}", flush=True)
