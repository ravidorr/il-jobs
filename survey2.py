"""Deeper survey: follow 'open positions' links, record ATS hosts and job-list JSON responses. Dev tool."""
import asyncio, json, re, sys
from playwright.async_api import async_playwright

ATS = re.compile(r"(myworkdayjobs\.com|comeet\.(?:com|co)|greenhouse\.io|lever\.co|ashbyhq\.com|smartrecruiters\.com|workable\.com|icims\.com|taleo\.net|oraclecloud\.com|successfactors|jobvite\.com|teamtailor\.com|bamboohr\.com|recruitee\.com|personio\.|breezy\.hr|eightfold\.ai|phenompeople|avature\.net|hibob\.com|pinpointhq|join\.com|freshteam|teamme\.link|jobs\.cz|gem\.com|rippling\.com|ultipro|paylocity|dayforce|brassring)", re.I)
GO = re.compile(r"open positions|search jobs|view (all )?(jobs|positions|openings)|all jobs|see (all )?(openings|jobs|roles|positions)|explore (roles|jobs|positions)|find your (role|job|next)|current openings|browse jobs|job openings|apply now|join us", re.I)
NOISE = re.compile(r"google|facebook|doubleclick|segment|hotjar|cookie|gtm|analytics|linkedin|clarity|sentry|datadog|fullstory|onetrust|cloudflare|newrelic|nr-data|zoominfo|optimizely|6sense|demandbase|6si", re.I)


def joblists(obj, path="", depth=0):
    out = []
    if depth > 6:
        return out
    if isinstance(obj, list) and len(obj) >= 3 and all(isinstance(x, dict) for x in obj[:5]):
        keys = set().union(*[set(x.keys()) for x in obj[:5]])
        if any(re.search(r"title|jobtitle|name|text|position", k, re.I) for k in keys) and any(re.search(r"location|city|url|link|id|department|country", k, re.I) for k in keys):
            out.append((path, len(obj), sorted(keys)[:8]))
    if isinstance(obj, dict):
        for k, v in obj.items():
            out += joblists(v, f"{path}.{k}", depth + 1)
    elif isinstance(obj, list):
        for v in obj[:3]:
            out += joblists(v, path + "[]", depth + 1)
    return out


async def survey(ctx, co, sem):
    async with sem:
        res = dict(name=co["name"], ats=set(), lists=[], final="", title="", err="", steps=[])
        page = await ctx.new_page()
        tasks = []

        def on_req(r):
            if ATS.search(r.url) and not NOISE.search(r.url):
                res["ats"].add(re.sub(r"\?.*", "", r.url)[:110])

        async def on_resp(r):
            try:
                if r.request.resource_type in ("xhr", "fetch") and "json" in (r.headers.get("content-type") or "") and not NOISE.search(r.url):
                    d = await r.json()
                    for p, n, k in joblists(d):
                        res["lists"].append((re.sub(r"\?.*", "", r.url)[:100], p, n, k))
            except Exception:
                pass
        page.on("request", on_req)
        page.on("response", lambda r: tasks.append(asyncio.ensure_future(on_resp(r))))
        start = [co.get("careers_url")] if co.get("careers_url") else []
        start += [f"https://www.{co['domain']}/careers", f"https://{co['domain']}/careers", f"https://www.{co['domain']}/company/careers"]
        loaded = False
        for u in dict.fromkeys(start):
            try:
                r = await page.goto(u, timeout=40000, wait_until="domcontentloaded")
                if r and r.status < 400:
                    loaded = True
                    break
            except Exception as e:
                res["err"] = type(e).__name__
        if not loaded:
            res["err"] = res["err"] or "nopage"
        else:
            for hop in range(2):  # land, then follow one "open positions" style link
                try:
                    await page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                await page.wait_for_timeout(1000)
                res["steps"].append(page.url[:90])
                for f in page.frames:
                    if ATS.search(f.url) and not NOISE.search(f.url):
                        res["ats"].add("FRAME " + re.sub(r"\?.*", "", f.url)[:100])
                links = await page.eval_on_selector_all("a[href]", "e=>e.map(x=>[x.href,(x.innerText||x.getAttribute('aria-label')||'').trim().slice(0,60)])")
                for h, t in links:
                    if ATS.search(h) and not NOISE.search(h):
                        res["ats"].add("LINK " + re.sub(r"\?.*", "", h)[:100])
                if hop == 0 and not res["ats"] and not res["lists"]:
                    cand = [h for h, t in links if GO.search(t) and h.startswith("http") and "#" not in h.split("/")[-1][:1] and h.rstrip("/") != page.url.rstrip("/")]
                    if cand:
                        try:
                            await page.goto(cand[0], timeout=40000, wait_until="domcontentloaded")
                            continue
                        except Exception:
                            pass
                break
            res["final"] = page.url[:100]
            res["title"] = (await page.title())[:50]
        await asyncio.gather(*tasks, return_exceptions=True)
        await page.close()
        res["ats"] = sorted(res["ats"])[:5]
        res["lists"] = res["lists"][:4]
        print(f"{co['name']:16s} ats={len(res['ats'])} lists={len(res['lists'])} err={res['err']} | {res['title']}", flush=True)
        return res


async def main():
    names = set(sys.argv[1:])
    cos = [c for c in json.load(open("data/companies.json")) if (c["name"] in names if names else c["status"] != "ok")]
    sem = asyncio.Semaphore(4)
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/opt/pw-browsers/chromium", args=["--no-sandbox"])
        ctx = await b.new_context(user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36", locale="en-US")
        out = await asyncio.gather(*[survey(ctx, c, sem) for c in cos])
        await b.close()
    json.dump(out, open("data/survey2.json", "w"), indent=1, ensure_ascii=False)
    for r in out:
        if r["ats"] or r["lists"]:
            print("##", r["name"], "|", r["final"])
            for a in r["ats"]: print("   ATS ", a)
            for l in r["lists"]: print("   LIST", l[0], l[1], l[2], l[3])

asyncio.run(main())
