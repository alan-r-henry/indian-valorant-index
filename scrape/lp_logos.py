"""Find Liquipedia logos for teams whose VLR page only has the placeholder logo.

Liquipedia keeps a team template (name -> logo files) for every team that has
appeared in one of its brackets, even teams without a page of their own. This
renders {{TeamIcon|<VLR name>}} through the API, 60 teams per call, and reads the
logo files back (separate light/dark versions where Liquipedia has them).
If the template points at a team page whose location disagrees with VLR's
country, the match is rejected (same name, different team).
Writes data/lp_logos.json: {vlr_team_id: {"team", "logo", "dark", "seen_in"}}.
"""
import sys, os, re, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lp, crawl

MONTH = 30 * 86400
OUT = os.path.join(crawl.DATA, "lp_logos.json")
PLACEHOLDER = re.compile(r'^VALORANT (allmode|lightmode|darkmode)\.png$', re.I)


def icons(names):
    """{name: (lp_team, light_file, dark_file)} for names Liquipedia has a template for."""
    out = {}
    names = [n for n in names if not re.search(r'[\[\]{}|<>=\n]', n)]
    for i in range(0, len(names), 60):
        chunk = names[i:i + 60]
        text = "\n".join(f"@@{k}@@{{{{TeamIcon|{n}}}}}" for k, n in enumerate(chunk))
        res = lp.call(dict(action="expandtemplates", text=text, prop="wikitext"))
        wt = res.get("expandtemplates", {}).get("wikitext", "")
        for k, body in re.findall(r'@@(\d+)@@(.*?)(?=\n@@\d+@@|\Z)', wt, re.S):
            team = re.search(r'data-highlighting-class="([^"]*)"', body)
            light = re.search(r'team-template-lightmode">\[\[File:([^|\]]+)', body)
            dark = re.search(r'team-template-darkmode">\[\[File:([^|\]]+)', body)
            plain = re.search(r'team-template-image-icon">\[\[File:([^|\]]+)', body)
            lf = (light or plain).group(1).strip() if (light or plain) else ""
            df = dark.group(1).strip() if dark else ""
            if team and lf and not PLACEHOLDER.match(lf):
                out[chunk[int(k)]] = (team.group(1), lf, "" if PLACEHOLDER.match(df) else df)
    return out


def main():
    teams = json.load(open(crawl.TEAMS, encoding="utf8"))
    need = {tid: t for tid, t in teams.items()
            if t.get("name") and (not t.get("logo") or "/tmp/vlr.png" in t["logo"])}
    got = icons(sorted({t["name"].strip() for t in need.values()}))

    # same name, different team? check the Liquipedia team page's location where one exists
    pages = lp.pages(sorted({v[0] for v in got.values()}), max_age=MONTH)
    found, rejected, played = {}, 0, {}
    for tid, t in need.items():
        hit = got.get(t["name"].strip())
        if not hit:
            continue
        team, lf, df = hit
        ib = lp.infobox(pages.get(team, ""), "team")
        where = " ".join(ib.get(f, "") for f in ("location", "location2", "region")).lower()
        country = (t.get("country") or "").strip().lower()
        if where.strip() and country and country != "international" and country not in where:
            rejected += 1
            continue
        # templates are shared by every Liquipedia game wiki: keep the match only if a
        # Valorant wiki page (a bracket or results table) links to that team
        if team not in played:
            bl = lp.call(dict(action="query", list="backlinks", bltitle=team, blnamespace=0, bllimit=3))
            played[team] = [b["title"] for b in bl.get("query", {}).get("backlinks", [])]
        if not played[team]:
            rejected += 1
            continue
        found[tid] = (team, lf, df)

    files = sorted({f for v in found.values() for f in v[1:] if f})
    urls = {}
    for i in range(0, len(files), 50):
        j = lp.call(dict(action="query", prop="imageinfo", iiprop="url", iiurlwidth=128,
                         redirects=1, titles="|".join("File:" + f for f in files[i:i + 50])))
        q = j.get("query", {})
        back = {}
        for r in q.get("normalized", []) + q.get("redirects", []):
            back[r["to"]] = back.get(r["from"], r["from"])
        for p in q.get("pages", {}).values():
            ii = (p.get("imageinfo") or [{}])[0]
            u = ii.get("thumburl") or ii.get("url")
            # several team files are redirects to Liquipedia's generic VALORANT logo
            if u and not re.search(r'/(\d+px-)?VALORANT_(allmode|lightmode|darkmode)\.png$', u, re.I):
                urls[back.get(p["title"], p["title"])[5:]] = u
    out = {}
    for tid, (team, lf, df) in found.items():
        if urls.get(lf):
            out[tid] = dict(team=team, logo=urls[lf], dark=urls.get(df, "") if df else "", seen_in=played[team][0])
    json.dump(out, open(OUT, "w", encoding="utf8"), ensure_ascii=False, indent=0, sort_keys=True)
    print(f"teams without a VLR logo {len(need)}, Liquipedia logos {len(out)} "
          f"({sum(1 for v in out.values() if v['dark'])} with a dark-mode version), "
          f"rejected (different team or not a Valorant team) {rejected}", flush=True)


if __name__ == "__main__":
    main()
