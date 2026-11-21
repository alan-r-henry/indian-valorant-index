"""Turn crawled VLR + Liquipedia data into the site's data file (site/data.js)."""
import hashlib, functools, sys, os, re, json, math, statistics, collections, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vlr, lp, events as EV

ROOT = vlr.ROOT
DATA = os.path.join(ROOT, "data")
NOW = dt.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
SA = {"in", "bd", "pk", "np", "lk", "mv", "bt", "af"}

AGENT_ROLE = {
    "jett": "Duelist", "reyna": "Duelist", "raze": "Duelist", "phoenix": "Duelist", "yoru": "Duelist", "neon": "Duelist",
    "iso": "Duelist", "waylay": "Duelist",
    "sova": "Initiator", "breach": "Initiator", "skye": "Initiator", "kayo": "Initiator", "fade": "Initiator",
    "gekko": "Initiator", "tejo": "Initiator",
    "brimstone": "Controller", "omen": "Controller", "viper": "Controller", "astra": "Controller", "harbor": "Controller",
    "clove": "Controller", "miks": "Controller",
    "sage": "Sentinel", "cypher": "Sentinel", "killjoy": "Sentinel", "chamber": "Sentinel", "deadlock": "Sentinel",
    "vyse": "Sentinel", "veto": "Sentinel",
}


def _i(x):
    return None if x is None else int(round(x))


def pdate(s):
    try:
        return dt.datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def classify_event(title):
    t = title.lower()
    if "game changers" in t:
        return "gc"
    if re.search(r'nations cup|national|team india|asian games|olympic', t):
        return "national"
    if re.search(r'^(valorant )?champions( tour)? 20\d\d$|valorant champions 20\d\d|^champions 20\d\d|masters', t) and "challengers" not in t and "qualifier" not in t:
        return "international"
    if re.search(r'last chance qualifier|ascension|kickoff - south asia|pacific kickoff', t):
        return "ascension"
    if re.search(r'(vct|champions tour) 20\d\d: pacific|vct pacific|pacific (league|stage|kickoff)', t) and "challengers" not in t:
        return "vct_pacific"
    if re.search(r'challengers|champions tour south asia|challengers league|vcsa|champions tour 2021: south asia|vct 2022: south asia|south asia stage', t):
        return "challengers"
    return "third_party"


TIER_ORDER = ["international", "vct_pacific", "ascension", "challengers", "national", "gc", "third_party"]


def load_matches(fname="matches.jsonl"):
    ms = {}
    fn = os.path.join(DATA, fname)
    if not os.path.exists(fn):
        return []
    for line in open(fn, encoding="utf8"):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        if len(d.get("teams", [])) != 2 or not d.get("date"):
            continue
        ms[d["id"]] = d
    return sorted(ms.values(), key=lambda d: d["date"])


def abroad_opp_elo(title):
    """Matches between two non-South-Asian teams carry no Elo here, so estimate the opponent's level from the event."""
    t = (title or "").lower()
    if re.search(r'masters|champions 20\d\d|vct 20\d\d: (americas|emea|pacific|china)|(americas|emea|pacific|china) (league|stage|kickoff)', t) and "challengers" not in t:
        return 1950.0
    if re.search(r'challengers|ascension|last chance', t):
        return 1650.0
    return 1550.0


def map_rows(m):
    return [g for g in m.get("games", []) if g["gid"] != "all" and g.get("score")]


def main():
    matches = load_matches()
    known = {m["id"] for m in matches}
    abroad_matches = [m for m in load_matches("abroad_matches.jsonl") if m["id"] not in known]
    abroad_fn = os.path.join(DATA, "abroad_players.json")
    abroad_info = {int(k): v for k, v in json.load(open(abroad_fn, encoding="utf8")).items()} if os.path.exists(abroad_fn) else {}
    region_of_team = {v["team_id"]: v["region"] for v in abroad_info.values() if v.get("team_id") and v.get("region")}
    print("abroad matches", len(abroad_matches), "abroad players", len(abroad_info))
    teams_raw = json.load(open(os.path.join(DATA, "teams_raw.json"), encoding="utf8"))
    print("matches", len(matches), "teams", len(teams_raw))

    # ---------- lineup nationality per team ----------
    lineup = collections.defaultdict(collections.Counter)      # tid -> flag counter (recent-weighted)
    last_lineup = {}                                             # tid -> (date, [pids])
    for m in matches:
        d = pdate(m["date"])
        recent = (NOW - d).days < 400
        for g in map_rows(m)[:1]:
            for side, t in enumerate(m["teams"]):
                pl = [p for p in g["players"] if p["tag"] and True]
            # players split: first 5 = team1, next 5 = team2 in VLR order
            ps = g["players"]
            for side, t in enumerate(m["teams"]):
                five = ps[side * 5:(side + 1) * 5]
                for p in five:
                    lineup[t["id"]][p["flag"]] += 3 if recent else 1
                last_lineup[t["id"]] = (m["date"], [p["pid"] for p in five])

    @functools.lru_cache(maxsize=None)
    def team_nat(tid):
        t = teams_raw.get(str(tid), {})
        c = lineup.get(tid, collections.Counter())
        # "un" = no nationality set on VLR; judge the team on players whose flag is known
        tot = sum(v for k, v in c.items() if k not in ("un", ""))
        frac_in = c["in"] / tot if tot else 0
        frac_sa = sum(v for k, v in c.items() if k in SA) / tot if tot else 0
        flag = t.get("flag", "")
        indian = flag == "in" or (tot and frac_in >= 0.5)
        south_asian = indian or flag in SA or frac_sa >= 0.5
        return indian, south_asian, frac_in

    # ---------- events ----------
    ev_ids = sorted({m["event_id"] for m in matches if m.get("event_id")})
    evinfo = {}
    ev_cache_fn = os.path.join(DATA, "events_parsed.json")
    old = json.load(open(ev_cache_fn, encoding="utf8")) if os.path.exists(ev_cache_fn) else {}
    for eid in ev_ids:
        if str(eid) in old and old[str(eid)].get("title"):
            evinfo[eid] = old[str(eid)]
        else:
            evinfo[eid] = EV.get_event(eid)
    json.dump({str(k): v for k, v in evinfo.items()}, open(ev_cache_fn, "w", encoding="utf8"), ensure_ascii=False)

    first_dates = collections.defaultdict(list)
    for m in matches:
        if m.get("event_id"):
            first_dates[m["event_id"]].append(m["date"])

    # ---------- Elo over maps ----------
    def init_rating(tier, tid):
        ind, sa, _ = team_nat(tid)
        if tier == "international":
            return 2050
        if tier == "vct_pacific":
            return 1850
        if tier == "ascension" and not sa:
            return 1700
        if not sa:
            return 1600
        return 1500

    # two rating pools: open circuit and Game Changers (women's circuit plays mostly within itself)
    R, last_seen, nmaps = {}, {}, collections.Counter()
    hist = collections.defaultdict(list)      # (pool, tid) -> [(date, rating)]
    map_elo = {}                               # (mid, gid) -> (Ra, Rb) before
    gc_series = collections.Counter(); all_series = collections.Counter()
    for m in matches:
        d = pdate(m["date"])
        tier = classify_event(m.get("event", ""))
        pool = "gc" if tier == "gc" else "open"
        a0, b0 = m["teams"][0]["id"], m["teams"][1]["id"]
        for tid in (a0, b0):
            all_series[tid] += 1
            if pool == "gc":
                gc_series[tid] += 1
        a, b = (pool, a0), (pool, b0)
        for key in (a, b):
            if key not in R:
                R[key] = init_rating(tier, key[1]) if pool == "open" else 1500
            elif key in last_seen and team_nat(key[1])[1]:
                idle = (d - last_seen[key]).days
                if idle > 60:
                    R[key] = 1500 + (R[key] - 1500) * (0.92 ** (idle / 90))
            last_seen[key] = d
        for g in map_rows(m):
            sa_, sb_ = g["score"]
            if sa_ == sb_:
                continue
            ra, rb = R[a], R[b]
            map_elo[(m["id"], g["gid"])] = (ra, rb)
            ea = 1 / (1 + 10 ** ((rb - ra) / 400))
            res = 1.0 if sa_ > sb_ else 0.0
            diff = abs(sa_ - sb_)
            welo = (ra - rb) if res == 1 else (rb - ra)
            mov = math.log(diff + 1) * (2.2 / (welo * 0.001 + 2.2))
            # foreign teams are only seen when they meet South Asian teams, so keep them as near-fixed anchors
            ka = 6 if not team_nat(a[1])[1] else (40 if nmaps[a] < 15 else 24)
            kb = 6 if not team_nat(b[1])[1] else (40 if nmaps[b] < 15 else 24)
            R[a] = ra + ka * mov * (res - ea)
            R[b] = rb - kb * mov * (res - ea)
            nmaps[a] += 1
            nmaps[b] += 1
        hist[a].append((m["date"][:10], round(R[a])))
        hist[b].append((m["date"][:10], round(R[b])))
    is_gc_team = lambda tid: all_series[tid] > 0 and gc_series[tid] / all_series[tid] >= 0.5

    # ---------- team aggregates ----------
    T = {}
    for tid_s, t in teams_raw.items():
        tid = int(tid_s)
        ind, sa, frac = team_nat(tid)
        if not sa:
            continue
        T[tid] = dict(id=tid, name=t.get("name", ""), tag=t.get("tag", ""), logo=t.get("logo", ""), flag=t.get("flag", ""),
                      country=t.get("country", ""), indian=bool(ind), frac_in=round(frac, 2), inactive=t.get("inactive", False),
                      links=t.get("links", []), vlr_rank=t.get("vlr_rank"), winnings=t.get("winnings"),
                      roster=[r for r in t.get("roster", [])],
                      series=[0, 0], maps=[0, 0], rounds=[0, 0], last=None, first=None, form=[], mapstats={},
                      events={}, h2h=collections.Counter(), y={})

    def ystat(tt, y):
        return tt["y"].setdefault(y, dict(series=[0, 0], maps=[0, 0], rounds=[0, 0]))

    match_out = []
    for m in matches:
        a, b = m["teams"][0]["id"], m["teams"][1]["id"]
        sc = m.get("score")
        maps = map_rows(m)
        ev = m.get("event_id")
        tier = classify_event(m.get("event", ""))
        involved = a in T or b in T
        if not involved:
            continue
        if sc is None and maps:
            sc = [sum(1 for g in maps if g["score"][0] > g["score"][1]), sum(1 for g in maps if g["score"][1] > g["score"][0])]
        mo = dict(id=m["id"], d=m["date"][:10], e=ev, s=m.get("series", ""), t=[a, b], sc=sc or [0, 0],
                  m=[[g.get("map"), g["score"][0], g["score"][1], g.get("pick")] for g in maps], bo=m.get("bo", ""))
        if m.get("veto"):
            mo["v"] = m["veto"]
        match_out.append(mo)
        if not sc or sc[0] == sc[1]:
            continue
        y = m["date"][:4]
        for side, tid in enumerate((a, b)):
            if tid not in T:
                continue
            tt = T[tid]
            opp = b if side == 0 else a
            won = sc[side] > sc[1 - side]
            tt["series"][0 if won else 1] += 1
            ys = ystat(tt, y)
            ys["series"][0 if won else 1] += 1
            tt["last"] = m["date"][:10]
            tt["first"] = tt["first"] or m["date"][:10]
            tt["form"].append("W" if won else "L")
            tt["h2h"][(opp, won)] += 1
            es = tt["events"].setdefault(ev, dict(w=0, l=0, mw=0, ml=0, stages=[], last=m.get("series", ""), tier=tier))
            es["w" if won else "l"] += 1
            es["last"] = m.get("series", "")
            st = (m.get("series", "") or "").split(":")[0].strip()
            if st and st not in es["stages"]:
                es["stages"].append(st)
            for g in maps:
                ms_, os_ = g["score"][side], g["score"][1 - side]
                mw = ms_ > os_
                tt["maps"][0 if mw else 1] += 1
                tt["rounds"][0] += ms_
                tt["rounds"][1] += os_
                ys["maps"][0 if mw else 1] += 1
                ys["rounds"][0] += ms_
                ys["rounds"][1] += os_
                es["mw" if mw else "ml"] += 1
                mp = g.get("map") or "?"
                st_ = tt["mapstats"].setdefault(mp, dict(p=0, w=0, rf=0, ra=0, pick=0, recent=0))
                st_["p"] += 1
                st_["w"] += 1 if mw else 0
                st_["rf"] += ms_
                st_["ra"] += os_
                if g.get("pick") == side + 1:
                    st_["pick"] += 1
                if (NOW - pdate(m["date"])).days < 365:
                    st_["recent"] += 1

    # veto: bans per team tag
    for m in match_out:
        if "v" not in m:
            continue
        for tid in m["t"]:
            if tid not in T:
                continue
            tag = T[tid]["tag"]
            if not tag:
                continue
            for act, mp in re.findall(re.escape(tag) + r' (ban|pick) (\w+)', m["v"]):
                st_ = T[tid]["mapstats"].setdefault(mp, dict(p=0, w=0, rf=0, ra=0, pick=0, recent=0))
                st_["vban" if act == "ban" else "vpick"] = st_.get("vban" if act == "ban" else "vpick", 0) + 1

    # placements from event pages
    for eid, e in evinfo.items():
        for pl in e.get("places", []):
            tid = pl.get("team_id")
            if tid in T:
                es = T[tid]["events"].setdefault(eid, dict(w=0, l=0, mw=0, ml=0, stages=[], last="", tier=classify_event(e.get("title", ""))))
                es["place"] = pl["place"].replace(" ", "")
                es["prize"] = pl["prize"]
                es["note"] = pl["note"]

    # current ratings + ranking
    ranked = []
    for tid, tt in T.items():
        pool = "gc" if is_gc_team(tid) else "open"
        tt["gc"] = pool == "gc"
        tt["nmaps"] = nmaps[(pool, tid)]
        tt["elo"] = round(R.get((pool, tid), 1500))
        # confidence-adjusted: discount teams with few maps (a 5-0 cup run shouldn't outrank a full season)
        tt["rating"] = round(tt["elo"] - 150 * math.exp(-tt["nmaps"] / 10))
        h = hist.get((pool, tid), [])
        # monthly sample for sparkline
        mon = {}
        for d_, r_ in h:
            mon[d_[:7]] = r_
        tt["hist"] = sorted(mon.items())[-36:]
        tt["peak"] = max([r for _, r in h], default=tt["rating"])
        tt["peak_date"] = next((d for d, r in h if r == tt["peak"]), None)
        days_idle = (NOW - dt.datetime.strptime(tt["last"], "%Y-%m-%d")).days if tt["last"] else 9999
        tt["active"] = days_idle <= 365 and not tt["inactive"]
        tt["form"] = tt["form"][-10:]
        streak = 0
        for f in reversed(tt["form"]):
            if f == tt["form"][-1]:
                streak += 1
            else:
                break
        tt["streak"] = (tt["form"][-1] + str(streak)) if tt["form"] else ""
        top_opp = sorted(((k[0], v) for k, v in tt["h2h"].items()), key=lambda x: -x[1])
        h2 = collections.defaultdict(lambda: [0, 0])
        for (o, w), v in tt["h2h"].items():
            h2[o][0 if w else 1] += v
        tt["h2h"] = sorted(([o, wl[0], wl[1]] for o, wl in h2.items()), key=lambda x: -(x[1] + x[2]))[:12]
        evlist = []
        for eid, es in tt["events"].items():
            e = evinfo.get(eid, {})
            evlist.append(dict(e=eid, w=es["w"], l=es["l"], mw=es["mw"], ml=es["ml"], st=es["stages"], last=es["last"],
                               tier=es["tier"], place=es.get("place", ""), prize=es.get("prize", ""), note=es.get("note", ""),
                               d=min(first_dates.get(eid, ["9999"]))[:10]))
        tt["events"] = sorted(evlist, key=lambda x: x["d"], reverse=True)
        if tt["indian"] and not tt["gc"] and tt["series"][0] + tt["series"][1] >= 3:
            ranked.append(tt)

    # ---------- players ----------
    P = {}
    mrows = []        # compact per-map player rows for adjusted ratings
    for m in matches + abroad_matches:
        a, b = m["teams"][0]["id"], m["teams"][1]["id"]
        d = pdate(m["date"])
        tier = classify_event(m.get("event", ""))
        is_abroad = a not in T and b not in T
        for g in map_rows(m):
            rounds = g["score"][0] + g["score"][1]
            if rounds < 13:
                continue
            ps = g["players"]
            elo = map_elo.get((m["id"], g["gid"]))
            for i, p in enumerate(ps[:10]):
                side = 0 if i < 5 else 1
                tid = (a, b)[side]
                opp = (b, a)[side]
                involved = tid in T or p["flag"] == "in"
                if not involved:
                    continue
                if is_abroad and p["flag"] != "in":
                    continue
                s = p["s"]
                def v(k, j=0):
                    x = s.get(k)
                    return x[j] if x else None
                won = g["score"][side] > g["score"][1 - side]
                pp = P.setdefault(p["pid"], dict(id=p["pid"], name=p["name"], flag=p["flag"], rows=[]))
                pp["name"] = p["name"]
                pp["flag"] = p["flag"] or pp["flag"]
                row = dict(d=m["date"][:10], mid=m["id"], tid=tid, opp=opp, map=g.get("map"), r=rounds, won=won,
                           ag=(p["agents"] or [None])[0], tier=tier, e=m.get("event_id"),
                           rt=v("rating2"), acs=v("acs"), k=v("kills"), dth=v("deaths"), a=v("assists"),
                           kast=v("kast"), adr=v("adr"), hs=v("hsp"), fk=v("fb"), fd=v("fd"),
                           rt_t=v("rating2", 1), rt_ct=v("rating2", 2), acs_t=v("acs", 1), acs_ct=v("acs", 2),
                           opp_elo=(elo[1 - side] if elo else (abroad_opp_elo(m.get("event", "")) if is_abroad else None)),
                           team_elo=(elo[side] if elo else None), est=bool(is_abroad and not elo))
                pp["rows"].append(row)

    # opponent adjustment: regress rating on opponent elo (rows with both)
    xs, ys_ = [], []
    for pp in P.values():
        for r in pp["rows"]:
            if r["rt"] is not None and r["opp_elo"] is not None and not r.get("est"):
                xs.append(r["opp_elo"])
                ys_.append(r["rt"])
    beta = 0.0
    if len(xs) > 100:
        mx, my = statistics.fmean(xs), statistics.fmean(ys_)
        cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys_))
        var = sum((x - mx) ** 2 for x in xs)
        beta = cov / var if var else 0.0
    ELO_REF = 1500
    print("opponent beta (rating per elo point):", beta)

    def agg(rows):
        if not rows:
            return None
        R_ = sum(r["r"] for r in rows)
        def wavg(key, w="r"):
            num = den = 0
            for r in rows:
                if r[key] is not None:
                    ww = r[w] if w else 1
                    num += r[key] * ww
                    den += ww
            return round(num / den, 3) if den else None
        k = sum(r["k"] or 0 for r in rows)
        dd = sum(r["dth"] or 0 for r in rows)
        a_ = sum(r["a"] or 0 for r in rows)
        fk = sum(r["fk"] or 0 for r in rows)
        fd = sum(r["fd"] or 0 for r in rows)
        rated = [r for r in rows if r["rt"] is not None]
        adj = None
        if rated:
            num = den = 0
            for r in rated:
                oe = r["opp_elo"] if r["opp_elo"] is not None else ELO_REF
                num += (r["rt"] - beta * (oe - ELO_REF)) * r["r"]
                den += r["r"]
            adj = round(num / den, 3)
        rts = sorted(r["rt"] for r in rated)
        out = dict(maps=len(rows), rounds=R_, wins=sum(1 for r in rows if r["won"]),
                   rating=wavg("rt"), adj=adj, acs=wavg("acs"), kd=round(k / dd, 2) if dd else None,
                   kast=wavg("kast"), adr=wavg("adr"), hs=wavg("hs", "k") if k else None,
                   kpr=round(k / R_, 3), dpr=round(dd / R_, 3), apr=round(a_ / R_, 3),
                   fkpr=round(fk / R_, 3), fdpr=round(fd / R_, 3), fkpct=round(fk / (fk + fd), 3) if fk + fd else None,
                   k=k, d=dd, a=a_, fk=fk, fd=fd,
                   rt_atk=wavg("rt_t"), rt_def=wavg("rt_ct"), acs_atk=wavg("acs_t"), acs_def=wavg("acs_ct"),
                   p90=round(rts[int(0.9 * (len(rts) - 1))], 2) if rts else None,
                   sd=round(statistics.pstdev(rts), 3) if len(rts) > 2 else None,
                   rated=len(rated))
        return out

    # liquipedia players
    kinds = json.load(open(os.path.join(DATA, "lp_kinds.json"), encoding="utf8"))
    base_titles = kinds.get("player", []) + kinds.get("commentator", [])
    # many VCSA players have Liquipedia pages that are missing from its India category: look them up by name
    cand = set()
    for pp in P.values():
        if pp["flag"] == "in" and len(pp["rows"]) >= 5:
            nm = pp["name"].strip()
            if nm:
                t1 = nm[0].upper() + nm[1:]
                cand.update([t1, t1 + " (Indian player)"])
    lpw = lp.pages(sorted(set(base_titles) | cand))
    lp_by_vlr, lp_by_name = {}, {}
    for title, wt in lpw.items():
        ib = lp.infobox(wt, "player") or lp.infobox(wt, "commentator")
        if not ib:
            continue
        if title not in base_titles and ib.get("country", "").strip() != "India" and not ib.get("vlr"):
            continue
        rec = dict(title=title, name=re.sub(r"<[^>]+>", "", ib.get("romanized_name") or ib.get("name") or ""),
                   birth=ib.get("birth_date", ""), status=ib.get("status", ""), roles=(ib.get("roles") or ib.get("role") or "").lower(),
                   lp_id=ib.get("id", title), country=ib.get("country", ""), twitter=ib.get("twitter", ""),
                   twitch=ib.get("twitch", ""), youtube=ib.get("youtube", ""), instagram=ib.get("instagram", ""))
        if ib.get("vlr"):
            lp_by_vlr[ib["vlr"].strip()] = rec
        for nm in [ib.get("id", ""), title.split(" (")[0]] + [x.strip() for x in ib.get("ids", "").split(",")]:
            if nm:
                lp_by_name.setdefault(nm.lower(), rec)

    roster_of = {}
    for tid, tt in T.items():
        for r in tt["roster"]:
            roster_of.setdefault(r["pid"], []).append((tid, r))

    def is_foreign_team(tid):
        """True only for teams that are clearly outside South Asia (not just unclassified small Indian teams)."""
        if tid in T:
            return False
        if tid in region_of_team:
            return True
        t = teams_raw.get(str(tid), {})
        if t.get("flag") in SA:
            return False
        c = lineup.get(tid) or {}
        tot = sum(v for k, v in c.items() if k not in ("un", ""))
        if tot and sum(v for k, v in c.items() if k in SA) / tot >= 0.5:
            return False
        if tot:
            return True
        return t.get("flag", "") not in ("", "un") or tid in abroad_team_ids

    abroad_team_ids = {t["id"] for m in abroad_matches for t in m["teams"]}
    players_out = []
    for pid, pp in P.items():
        allrows = sorted(pp["rows"], key=lambda r: r["d"])
        gcrows = [r for r in allrows if r["tier"] == "gc"]
        is_gc = len(gcrows) * 2 >= len(allrows)
        rows = gcrows if is_gc else [r for r in allrows if r["tier"] != "gc"]
        if len(rows) < 5:
            continue
        indian_team_rows = [r for r in rows if r["tid"] in T and T[r["tid"]]["indian"]]
        if pp["flag"] != "in" and not indian_team_rows:
            continue
        last = rows[-1]
        cur_tid = last["tid"]
        # role from agents (last 365 days, else all)
        recent = [r for r in rows if (NOW - dt.datetime.strptime(r["d"], "%Y-%m-%d")).days < 365] or rows
        rc = collections.Counter(AGENT_ROLE.get(r["ag"], "?") for r in recent if r["ag"])
        ac = collections.Counter(r["ag"] for r in recent if r["ag"])
        tot = sum(rc.values())
        role, role_share = ("Flex", 0)
        if tot:
            top, cnt = rc.most_common(1)[0]
            role_share = cnt / tot
            role = top if role_share >= 0.55 else "Flex"
        lpr = lp_by_vlr.get(str(pid)) or lp_by_name.get(pp["name"].lower())
        if lpr and lpr["country"] and lpr["country"] != "India" and pp["flag"] == "in" and not lp_by_vlr.get(str(pid)):
            lpr = None
        age = None
        if lpr and re.match(r"\d{4}-\d{2}-\d{2}", lpr.get("birth", "")) and not lpr["birth"].endswith("-00-00"):
            try:
                b = dt.datetime.strptime(lpr["birth"][:10].replace("-00", "-01"), "%Y-%m-%d")
                age = (NOW - b).days // 365
            except Exception:
                pass
        staff = None
        real = ""
        for tid_, r in roster_of.get(pid, []):
            real = real or r["real"]
            if r["role"] not in ("player",) and "sub" not in r["role"]:
                staff = r["role"]
        teams_played = []
        for r in rows:
            if not teams_played or teams_played[-1][0] != r["tid"]:
                teams_played.append([r["tid"], r["d"], r["d"]])
            else:
                teams_played[-1][2] = r["d"]
        seasons = {}
        for yr in sorted({r["d"][:4] for r in rows}):
            seasons[yr] = agg([r for r in rows if r["d"][:4] == yr])
        def small(x):
            return {k: x[k] for k in ("maps", "wins", "rating", "acs", "kd")}
        bymap = {}
        for mp in {r["map"] for r in rows if r["map"]}:
            bymap[mp] = small(agg([r for r in rows if r["map"] == mp]))
        byag = {}
        for ag in {r["ag"] for r in rows if r["ag"]}:
            byag[ag] = small(agg([r for r in rows if r["ag"] == ag]))
        bytier = {}
        for tier in {r["tier"] for r in rows}:
            bytier[tier] = small(agg([r for r in rows if r["tier"] == tier]))
        last365 = agg(recent)
        best = sorted([r for r in rows if r["rt"] is not None], key=lambda r: -r["rt"])[:4]
        po = dict(id=pid, name=pp["name"], real=real or (lpr["name"] if lpr else ""), flag=pp["flag"],
                  team=cur_tid, last=last["d"], first=rows[0]["d"], active=(NOW - dt.datetime.strptime(last["d"], "%Y-%m-%d")).days <= 365,
                  role=role, role_share=round(role_share, 2), roles={k: v for k, v in rc.items()},
                  agents=[[k, v] for k, v in ac.most_common(6)], age=age, birth=(lpr or {}).get("birth", ""),
                  igl="igl" in ((lpr or {}).get("roles", "")), lp=(lpr or {}).get("title", ""),
                  status=(lpr or {}).get("status", ""), staff=staff,
                  social={k: (lpr or {}).get(k, "") for k in ("twitter", "twitch", "youtube", "instagram") if (lpr or {}).get(k)},
                  career=agg(rows), cur=last365, seasons=seasons, maps=bymap, ags=byag, tiers=bytier,
                  teams=teams_played[-12:],
                  best=[dict(d=r["d"], mid=r["mid"], map=r["map"], ag=r["ag"], rt=r["rt"], acs=r["acs"], k=_i(r["k"]), dth=_i(r["dth"]), a=_i(r["a"]), opp=r["opp"]) for r in best],
                  # last 30 maps for the form chart: [date, rating, acs, opp, match, map, agent, won, k, d, a]
                  recent=[[r["d"], r["rt"], _i(r["acs"]), r["opp"], r["mid"], r["map"], r["ag"], int(bool(r["won"])), _i(r["k"]), _i(r["dth"]), _i(r["a"])]
                          for r in rows[-30:]] if (NOW - dt.datetime.strptime(last["d"], "%Y-%m-%d")).days <= 365 else [],
                  indian_team=bool(indian_team_rows), gc=is_gc,
                  abroad=(dict(region=region_of_team.get(cur_tid) or (abroad_info.get(pid) or {}).get("region", "")
                               or teams_raw.get(str(cur_tid), {}).get("country", ""),
                               team_flag=(abroad_info.get(pid) or {}).get("team_flag", "") or teams_raw.get(str(cur_tid), {}).get("flag", ""))
                          if pp["flag"] == "in" and is_foreign_team(cur_tid) else None))
        players_out.append(po)

    # ---------- meta: agents & maps across Indian-team maps ----------
    agent_month = collections.defaultdict(collections.Counter)
    map_month = collections.defaultdict(collections.Counter)
    map_side = collections.defaultdict(lambda: [0, 0, 0])   # map -> [atk rounds won, def rounds won, maps]
    for m in matches:
        a, b = m["teams"][0]["id"], m["teams"][1]["id"]
        if not ((a in T and T[a]["indian"]) or (b in T and T[b]["indian"])):
            continue
        mon = m["date"][:7]
        for g in map_rows(m):
            map_month[mon][g.get("map")] += 1
            for p in g["players"][:10]:
                if p["agents"]:
                    agent_month[mon][p["agents"][0]] += 1
            for side_, n in g.get("halves", []):
                pass
            hv = g.get("halves", [])
            # halves listed: team1 [first-half side, n], [second-half side, n], team2 ... (+ot)
            for s_, n in hv:
                if s_ == "t":
                    map_side[g.get("map")][0] += int(n)
                elif s_ == "ct":
                    map_side[g.get("map")][1] += int(n)
            map_side[g.get("map")][2] += 1

    # ---------- events out ----------
    events_out = []
    for eid, e in evinfo.items():
        ds = sorted(first_dates.get(eid, []))
        tier = classify_event(e.get("title", ""))
        ind_res = []
        for tid, tt in T.items():
            for es in tt["events"]:
                if es["e"] == eid and tt["indian"]:
                    ind_res.append([tid, es["place"], es["w"], es["l"]])
        events_out.append(dict(id=eid, title=e.get("title", ""), series=e.get("series", []), logo=e.get("logo", ""),
                               dates=e.get("fields", {}).get("dates", ""), prize=e.get("fields", {}).get("prize", ""),
                               loc=e.get("fields", {}).get("location", "") or e.get("fields", {}).get("region", ""),
                               tier=tier, start=ds[0][:10] if ds else "", end=ds[-1][:10] if ds else "",
                               places=e.get("places", [])[:16], n=len(ds), ind=ind_res))
    events_out.sort(key=lambda x: x["start"], reverse=True)

    # ---------- write ----------
    team_list = []
    for tid, tt in T.items():
        tt.pop("y_", None)
        tt["y"] = {k: v for k, v in sorted(tt["y"].items())}
        if tt["series"][0] + tt["series"][1] == 0 and not tt["events"]:
            continue
        team_list.append(tt)
    used = set()
    for tt in team_list:
        used.add(tt["id"])
    opp_names = {}
    for m in matches:
        for t in m["teams"]:
            opp_names[t["id"]] = t["name"]
    used_abroad = {p["team"] for p in players_out} | {r[3] for p in players_out for r in p.get("recent", [])} | {b["opp"] for p in players_out for b in p["best"]}
    for m in abroad_matches:
        for t in m["teams"]:
            if t["id"] in used_abroad:
                opp_names.setdefault(t["id"], t["name"])
    abroad_logos = {v["team_id"]: v.get("team_logo", "") for v in abroad_info.values() if v.get("team_id")}
    out = dict(
        generated=NOW.strftime("%Y-%m-%d"),
        beta=beta,
        teams=team_list,
        players=players_out,
        events=events_out,
        matches=match_out,
        names={str(k): v for k, v in opp_names.items()},
        tlogos={str(k): teams_raw.get(str(k), {}).get("logo", "") or abroad_logos.get(k, "") for k in opp_names},
        agent_month={k: dict(v) for k, v in sorted(agent_month.items())},
        map_month={k: dict(v) for k, v in sorted(map_month.items())},
        map_side={k: v for k, v in map_side.items() if k},
        agent_role=AGENT_ROLE,
    )
    os.makedirs(os.path.join(ROOT, "site"), exist_ok=True)
    s = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    open(os.path.join(ROOT, "site", "data.js"), "w", encoding="utf8").write("window.IVI_DATA=" + s + ";")
    # cache-bust: point index.html at this exact data file so browsers don't keep last week's copy
    ix = os.path.join(ROOT, "site", "index.html")
    ver = hashlib.md5(s.encode("utf8")).hexdigest()[:10]
    html = open(ix, encoding="utf8").read()
    html2 = re.sub(r'src="data\.js(\?v=[0-9a-f]+)?"', f'src="data.js?v={ver}"', html)
    if html2 != html:
        open(ix, "w", encoding="utf8", newline="\n").write(html2)
    print("teams", len(team_list), "indian ranked", len(ranked), "players", len(players_out), "events", len(events_out),
          "matches", len(match_out), "bytes", len(s))


if __name__ == "__main__":
    main()
