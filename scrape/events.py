"""Fetch + parse VLR event pages (header, sub-stages, prize/placement table)."""
import sys, os, re, json, html as H
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vlr


def txt(s):
    return H.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', s))).strip()


def parse_event(h, eid):
    h = re.sub(r'<svg.*?</svg>', '', h, flags=re.S)
    e = {"id": eid}
    m = re.search(r'event-header-main-title">(.*?)</h1>', h, re.S)
    e["title"] = txt(m.group(1)) if m else ''
    bc = re.search(r'event-header-main-bc">(.*?)</div>\s*</div>', h, re.S)
    e["series"] = []
    if bc:
        e["series"] = [txt(x) for x in re.findall(r'<a [^>]*>(.*?)</a>', bc.group(1), re.S)]
    m = re.search(r'event-header-thumb">.*?<img src="([^"]+)"', h, re.S)
    e["logo"] = m.group(1) if m else ''
    fields = {}
    for lab, val in re.findall(r'class="ge-text-light label">\s*(.*?)\s*</div>\s*<div class="value"[^>]*>(.*?)</div>', h, re.S):
        fl = re.search(r'flag mod-([a-z0-9-]+)', val)
        fields[txt(lab).lower()] = (txt(val) + (" [" + fl.group(1) + "]" if fl else "")).strip()
    e["fields"] = fields
    e["stages"] = [(href, txt(d), txt(t)) for href, d, t in re.findall(
        r'<a href="(/event/\d+/[^"]+)" class="wf-subnav-item[^"]*">\s*<div>\s*<div[^>]*>(.*?)</div>\s*<div class="wf-subnav-item-title">(.*?)</div>', h, re.S)]
    places = []
    tbl = re.search(r'wf-ptable--standings"(.*?)(?:<div class="wf-label|<div class="event-sidebar|$)', h, re.S)
    if tbl:
        for row in re.split(r'<div class="row\s*[^"]*" role="row">', tbl.group(1))[2:]:
            cells = re.findall(r'<div class="cell[^"]*" role="cell"[^>]*>(.*?)</div>\s*(?=<div class="cell|$)', row, re.S)
            place = re.search(r'role="cell" style="white-space: nowrap;">\s*(.*?)\s*</div>', row, re.S)
            prize = re.search(r'justify-content: flex-end">\s*(.*?)\s*</div>', row, re.S)
            team = re.search(r'href="/team/(\d+)/[^"]*".*?class="text-of">\s*(.*?)\s*<div', row, re.S)
            note = re.findall(r'line-height: 1.5;">\s*<div>(.*?)</div>', row, re.S)
            if not team:
                tname = re.search(r'class="text-of">\s*(.*?)\s*<div', row, re.S)
                if not tname:
                    continue
            places.append({"place": txt(place.group(1)) if place else '', "prize": txt(prize.group(1)) if prize else '',
                           "team_id": int(team.group(1)) if team else None,
                           "team": txt(team.group(2)) if team else '',
                           "note": txt(note[0]) if note else ''})
    e["places"] = places
    return e


def get_event(eid):
    h = vlr.get(f"https://www.vlr.gg/event/{eid}/x")
    if not h:
        return {"id": eid}
    return parse_event(h, eid)


if __name__ == "__main__":
    for a in sys.argv[1:]:
        print(json.dumps(get_event(int(a)), ensure_ascii=False, indent=1)[:2500])
