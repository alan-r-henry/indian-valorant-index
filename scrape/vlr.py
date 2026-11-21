"""Cached, polite VLR fetcher. Pages stored gzip-compressed under cache/vlr."""
import os, re, time, gzip, hashlib, threading, urllib.request
_lock = threading.Lock()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "cache", "vlr")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
_last = [0.0]
DELAY = 0.45
def path_for(url):
    key = re.sub(r'[^A-Za-z0-9]+', '_', url.replace("https://www.vlr.gg", ""))[:150]
    h = hashlib.md5(url.encode()).hexdigest()[:8]
    return os.path.join(CACHE, f"{key}_{h}.html.gz")
def get(url, refresh=False, max_age=None):
    if url.startswith("/"): url = "https://www.vlr.gg" + url
    fn = path_for(url)
    if os.path.exists(fn) and not refresh:
        if max_age is None or time.time() - os.path.getmtime(fn) < max_age:
            with gzip.open(fn, "rt", encoding="utf8") as f: return f.read()
    for attempt in range(5):
        with _lock:
            wait = DELAY - (time.time() - _last[0])
            if wait > 0: time.sleep(wait)
            _last[0] = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
            r = urllib.request.urlopen(req, timeout=60)
            data = r.read()
            if data[:2] == b"\x1f\x8b": data = gzip.decompress(data)
            txt = data.decode("utf8", "replace")
            with gzip.open(fn, "wt", encoding="utf8") as f: f.write(txt)
            return txt
        except urllib.error.HTTPError as e:
            if e.code == 404: return ""
            time.sleep(5 * (attempt + 1))
        except Exception:
            time.sleep(5 * (attempt + 1))
    return None
