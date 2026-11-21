import sys, json, os
sys.path.insert(0, '.')
import vlr, crawl
from concurrent.futures import ThreadPoolExecutor
done = crawl.load_done()
tids = sorted({str(t["id"]) for d in done.values() for t in d.get("teams", [])})
with ThreadPoolExecutor(3) as ex:
    pages = list(ex.map(lambda t: vlr.get(f"https://www.vlr.gg/team/{t}/x"), tids))
teams = {t: crawl.parse_team(h, int(t)) for t, h in zip(tids, pages) if h}
fn = os.path.join(crawl.DATA, "teams_raw.json")
if not os.path.exists(fn):
    json.dump(teams, open(fn, "w", encoding="utf8"), ensure_ascii=False)
print(len(teams), sum(1 for t in teams.values() if crawl.is_indian_team(t)))
