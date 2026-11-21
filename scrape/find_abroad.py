"""Find Indian-nationality players on Liquipedia (country, country2 or country3 = India)
and record their VLR ids, current team and status -> data/lp_indian_players.json.
Used by crawl_abroad.py to crawl players who play outside South Asia."""
import sys, os, re, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lp, vlr

OUT = os.path.join(vlr.ROOT, "data", "lp_indian_players.json")


def search_all(q):
    titles, off = [], 0
    while True:
        j = lp.call(dict(action="query", list="search", srsearch=q, srnamespace=0, srlimit=500, sroffset=off))
        hits = j.get("query", {}).get("search", [])
        titles += [h["title"] for h in hits]
        off = j.get("continue", {}).get("sroffset")
        if not off or not hits:
            return titles


def main():
    titles = set()
    for f in ("country", "country2", "country3"):
        titles.update(search_all(f'hastemplate:"Infobox player" insource:"{f}=India"'))
        titles.update(search_all(f'hastemplate:"Infobox player" insource:"{f}= India"'))
    print("candidate pages", len(titles))
    wts = lp.pages(sorted(titles), max_age=7 * 86400)
    out = []
    for t, wt in wts.items():
        ib = lp.infobox(wt, "player")
        if not ib:
            continue
        nats = [ib.get(k, "").strip() for k in ("country", "country2", "country3")]
        if "India" not in nats:
            continue
        vlr_id = None
        m = re.search(r'vlr\.gg/player/(\d+)', wt) or re.search(r'^\s*\|\s*vlr\s*=\s*(\d+)', wt, re.M)
        if m:
            vlr_id = int(m.group(1))
        out.append(dict(title=t, id=ib.get("id", t), vlr=vlr_id, nats=[n for n in nats if n],
                        team=ib.get("team", ""), status=ib.get("status", ""), birth=ib.get("birth_date", "")))
    out.sort(key=lambda x: x["title"].lower())
    json.dump(out, open(OUT, "w", encoding="utf8"), ensure_ascii=False, indent=1)
    print("indian players", len(out), "with vlr id", sum(1 for x in out if x["vlr"]),
          "dual nationality", sum(1 for x in out if len(x["nats"]) > 1))


if __name__ == "__main__":
    main()
