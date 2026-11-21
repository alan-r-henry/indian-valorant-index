import sys, re, json, html
sys.path.insert(0, '.')
import vlr
out = []
seen = set()
page = 1
empty = 0
while page < 400:
    h = vlr.get(f"https://www.vlr.gg/events/?region=28&page={page}", max_age=6 * 3600)
    if h is None: break
    items = re.findall(r'<a class="wf-card mod-flex event-item" href="(/event/(\d+)/[^"]+)"(.*?)</a>', h, re.S)
    new = 0
    for href, eid, body in items:
        if eid in seen: continue
        seen.add(eid); new += 1
        title = html.unescape(re.sub(r'\s+', ' ', re.search(r'event-item-title">(.*?)</div>', body, re.S).group(1))).strip()
        status = re.search(r'event-item-desc-item-status[^"]*">(\w+)', body)
        prize = re.search(r'mod-prize">\s*(.*?)\s*<', body, re.S)
        dates = re.search(r'mod-dates">\s*(.*?)\s*<', body, re.S)
        flag = re.search(r'flag mod-([a-z0-9-]+)', body)
        out.append(dict(id=int(eid), href=href, title=title, status=status.group(1) if status else '',
                        prize=html.unescape(prize.group(1)) if prize else '', dates=html.unescape(dates.group(1)) if dates else '',
                        flag=flag.group(1) if flag else ''))
    print(page, len(items), new, out[-1]['title'] if out else '', flush=True)
    if new == 0:
        empty += 1
        if empty >= 2: break
    else: empty = 0
    page += 1
json.dump(out, open('../data/vlr_events_pacific.json', 'w', encoding='utf8'), ensure_ascii=False, indent=0)
print('total', len(out))
