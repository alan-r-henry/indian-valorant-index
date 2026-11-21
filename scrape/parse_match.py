"""Parse a VLR match page into a compact dict."""
import re, html as H

def _txt(s):
    return H.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', s))).strip()

def _num(s):
    s = s.strip().replace('%', '')
    if s in ('', '-', '\xa0'): return None
    try: return float(s)
    except ValueError: return None

def parse(h, mid):
    h = re.sub(r'<svg.*?</svg>', '', h, flags=re.S)
    d = {"id": mid}
    ev = re.search(r'href="/event/(\d+)/[^"]*" class="match-header-event">.*?<div style="font-weight: 700;">\s*(.*?)\s*</div>\s*<div class="match-header-event-series">\s*(.*?)\s*</div>', h, re.S)
    if ev:
        d["event_id"] = int(ev.group(1)); d["event"] = _txt(ev.group(2)); d["series"] = _txt(ev.group(3))
    ts = re.search(r'data-utc-ts="([^"]+)"', h)
    d["date"] = ts.group(1) if ts else None
    teams = re.findall(r'match-header-link wf-link-hover mod-(\d)"\s*href="/team/(\d+)/[^"]*"\s*>.*?wf-title-med[^>]*>\s*(.*?)\s*</div>', h, re.S)
    d["teams"] = [{"id": int(t[1]), "name": _txt(t[2])} for t in teams]
    sc = re.search(r'match-header-vs-score">\s*<div class="match-header-vs-note">.*?</div>\s*<div class="match-header-vs-score">\s*<div class="(?:sp-hide|js-spoiler)[^"]*">\s*<span class="[^"]*">\s*(\d+)\s*</span>.*?<span class="[^"]*">\s*(\d+)\s*</span>', h, re.S)
    d["score"] = [int(sc.group(1)), int(sc.group(2))] if sc else None
    notes = re.findall(r'match-header-vs-note[^"]*">\s*(.*?)\s*</div>', h, re.S)
    d["status"] = _txt(notes[0]) if notes else ''
    d["bo"] = _txt(notes[1]) if len(notes) > 1 else ''
    vt = re.search(r'match-header-note">\s*(.*?)\s*</div>', h, re.S)
    d["veto"] = _txt(vt.group(1)) if vt else ''
    # games
    games = []
    parts = re.split(r'<div class="vm-stats-game\s*(?:mod-active)?\s*" data-game-id="', h)
    for p in parts[1:]:
        gid = p[:p.index('"')]
        hdr = re.search(r'vm-stats-game-header">(.*?)<div class="(?:ovw-filter|vlr-rounds)', p, re.S)
        g = {"gid": gid}
        if gid != 'all':
            if not hdr: continue
            hh = hdr.group(1)
            scores = re.findall(r'class="score[^"]*"[^>]*>\s*(\d+)', hh)
            mp = re.search(r'map-name">\s*<span[^>]*>\s*([A-Za-z ]+?)\s*<', hh)
            half = re.findall(r'<span class="mod-(ct|t|ot)">(\d+)</span>', hh)
            g["map"] = mp.group(1).strip() if mp else None
            g["score"] = [int(x) for x in scores[:2]] if len(scores) >= 2 else None
            g["halves"] = half
            pick = re.search(r'picked mod-(\d)', hh)
            g["pick"] = int(pick.group(1)) if pick else None
            dur = re.search(r'map-duration[^>]*>\s*([\d:]+)', hh)
            g["dur"] = dur.group(1) if dur else None
            if g["map"] in (None, 'TBD') or g["score"] is None: continue
        rows = re.split(r'<div class="ovw-row"', p)
        players = []
        for r in rows[1:]:
            pl = re.search(r'href="/player/(\d+)/[^"]*">\s*<div class="ovw-player-name[^>]*>(.*?)</div>\s*<div class="ovw-player-tag[^>]*>(.*?)</div>', r, re.S)
            if not pl: continue
            fl = re.search(r'flag mod-([a-z0-9-]+)"(?: title="([^"]*)")?', r)
            agents = re.findall(r'agents/([a-z0-9_]+)\.png', r)
            stats = {}
            cols = list(re.finditer(r'data-col="([\w-]+)"', r))
            for k, m in enumerate(cols):
                seg = r[m.end(): cols[k+1].start() if k + 1 < len(cols) else len(r)]
                b = re.search(r'side mod-both[^"]*">(.*?)</span>', seg)
                t = re.search(r'side mod-t[^"]*">(.*?)</span>', seg)
                c = re.search(r'side mod-ct[^"]*">(.*?)</span>', seg)
                if b:
                    stats[m.group(1)] = [_num(_txt(b.group(1))), _num(_txt(t.group(1))) if t else None, _num(_txt(c.group(1))) if c else None]
            players.append({"pid": int(pl.group(1)), "name": _txt(pl.group(2)), "tag": _txt(pl.group(3)),
                            "flag": fl.group(1) if fl else '', "agents": agents, "s": stats})
        g["players"] = players
        games.append(g)
    # de-dup (all appears twice in markup sometimes)
    seen = set(); out = []
    for g in games:
        if g["gid"] in seen: continue
        seen.add(g["gid"]); out.append(g)
    d["games"] = out
    return d

if __name__ == "__main__":
    import sys, json
    sys.path.insert(0, '.')
    import vlr
    h = vlr.get(sys.argv[1])
    d = parse(h, 0)
    g = d.pop("games")
    print(json.dumps(d, ensure_ascii=False))
    for x in g:
        print(x["gid"], x.get("map"), x.get("score"), x.get("halves"), x.get("pick"), x.get("dur"), len(x["players"]))
        for p in x["players"][:2]: print("   ", p["name"], p["tag"], p["flag"], p["agents"], json.dumps(p["s"]))
