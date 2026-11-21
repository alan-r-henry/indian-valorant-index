"""Liquipedia API helper (respects 1 request / 2 s; batches 50 titles per query)."""
import os, re, json, time, gzip, urllib.request, urllib.parse
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "cache", "lp")
os.makedirs(CACHE, exist_ok=True)
UA = "IndianValorantIndex/1.0 (non-commercial fan stats; https://github.com/alan-r-henry/indian-valorant-index)"
API = "https://liquipedia.net/valorant/api.php"
_last = [0.0]


def call(params):
    params = dict(params, format="json")
    url = API + "?" + urllib.parse.urlencode(params)
    for attempt in range(6):
        wait = 2.2 - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
            data = urllib.request.urlopen(req, timeout=60).read()
            if data[:2] == b"\x1f\x8b":
                data = gzip.decompress(data)
            return json.loads(data)
        except Exception as e:
            time.sleep(15 * (attempt + 1))
    raise RuntimeError("liquipedia failed: " + url)


def category(cat, ns=0):
    out, cont = [], {}
    while True:
        j = call(dict(action="query", list="categorymembers", cmtitle="Category:" + cat, cmlimit=500, cmnamespace=ns, **cont))
        out += [m["title"] for m in j["query"]["categorymembers"]]
        if "continue" in j:
            cont = {"cmcontinue": j["continue"]["cmcontinue"]}
        else:
            return out


def _fn(title):
    return os.path.join(CACHE, re.sub(r'[^A-Za-z0-9_.-]', '_', title)[:150] + ".wt")


def pages(titles, max_age=None):
    """Return {title: wikitext}; fetched 50 at a time, cached."""
    res, need = {}, []
    for t in titles:
        fn = _fn(t)
        if os.path.exists(fn) and (max_age is None or time.time() - os.path.getmtime(fn) < max_age):
            res[t] = open(fn, encoding="utf8").read()
        else:
            need.append(t)
    for i in range(0, len(need), 50):
        chunk = need[i:i + 50]
        j = call(dict(action="query", prop="revisions", rvprop="content", rvslots="main", redirects=1, titles="|".join(chunk)))
        q = j.get("query", {})
        back = {}
        for r in q.get("normalized", []) + q.get("redirects", []):
            back[r["to"]] = back.get(r["from"], r["from"])
        for p in q.get("pages", {}).values():
            title = p["title"]
            orig = back.get(title, title)
            orig = back.get(orig, orig)
            txt = ""
            if "revisions" in p:
                txt = p["revisions"][0]["slots"]["main"]["*"]
            for t in {orig, title}:
                if t in chunk:
                    open(_fn(t), "w", encoding="utf8").write(txt)
                    res[t] = txt
        for t in chunk:
            if t not in res:
                open(_fn(t), "w", encoding="utf8").write("")
                res[t] = ""
    return res


def infobox(wt, name=None):
    """Very small template-arg parser for the first Infobox."""
    m = re.search(r'\{\{\s*Infobox ' + (name or r'\w+'), wt or "")
    if not m:
        return {}
    i, depth, start = m.start(), 0, m.start()
    while i < len(wt):
        if wt.startswith("{{", i):
            depth += 1; i += 2; continue
        if wt.startswith("}}", i):
            depth -= 1; i += 2
            if depth == 0:
                break
            continue
        i += 1
    body = wt[start + 2:i - 2]
    args, depth, cur = [], 0, ""
    j = 0
    while j < len(body):
        c2 = body[j:j + 2]
        if c2 in ("{{", "[["):
            depth += 1; cur += c2; j += 2; continue
        if c2 in ("}}", "]]"):
            depth -= 1; cur += c2; j += 2; continue
        if body[j] == "|" and depth == 0:
            args.append(cur); cur = ""; j += 1; continue
        cur += body[j]; j += 1
    args.append(cur)
    out = {}
    for a in args[1:]:
        if "=" in a:
            k, v = a.split("=", 1)
            out[k.strip()] = v.strip()
    return out
