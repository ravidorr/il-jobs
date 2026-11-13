"""Tier 3: generic crawler for career pages without a public ATS API. Real browser (Playwright).
Extracts JSON-LD JobPosting, else job-looking links. Returns list of jobs, or None if blocked/failed."""
import asyncio, json, os, re
from playwright.async_api import async_playwright

JOBLINK = re.compile(r"/(jobs?|positions?|careers?|openings?|vacanc\w+|job-?post\w*)/[^/?#]{4,}", re.I)
NOT_JOB = re.compile(r"/(department|departments|category|team|teams|locations?|working-at|life-at|benefits|students?|early-careers?|login|search|saved|talent-network)\b|#", re.I)
NEXT_SELS = ['a[title="Next" i]', 'a.link-next', 'a[aria-label="Next page" i]', 'button[title="Next" i]', 'body a[rel="next"]', 'a[aria-label="Next" i]', 'button[aria-label="Next" i]', 'li.next a',
             '.pagination-next', 'a:text-is("Next")', 'button:text-is("Next")', 'a:text-is("Next >")']
MORE = re.compile(r"load more|show more|see more|view more|more jobs|more positions", re.I)
LANGS = {"english", "español", "français", "português", "deutsch", "italiano", "日本語", "한국어", "中文", "русский", "עברית", "polski", "nederlands"}
BLOCKED = re.compile(r"just a moment|attention required|security checkpoint|access denied|error 429|verify you are human", re.I)
EXE = os.environ.get("PW_CHROMIUM") or ("/opt/pw-browsers/chromium" if os.path.exists("/opt/pw-browsers/chromium") else None)
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"


def _job(job_id, title, location, url, team=""):
    return dict(job_id=job_id, title=title, location=location, url=url, team=team, posted="")


async def crawl_one(ctx, url, sem):
    async with sem:
        page = await ctx.new_page()
        captured = []

        async def on_resp(resp):  # HiBob career boards load every job in one JSON response
            try:
                if "/api/job-ad" in resp.url and resp.request.resource_type in ("xhr", "fetch") and resp.status == 200:
                    d = await resp.json()
                    if isinstance(d, dict) and isinstance(d.get("jobAdDetails"), list):
                        origin = re.match(r"https?://[^/]+", resp.url).group(0)
                        for j in d["jobAdDetails"]:
                            loc = ", ".join(x for x in (j.get("site"), j.get("country")) if x)
                            captured.append(_job(j["id"], j.get("title", ""), loc, f"{origin}/jobs/{j['id']}", team=j.get("department") or ""))
            except Exception:
                pass
        page.on("response", lambda r: asyncio.ensure_future(on_resp(r)))
        try:
            r = await page.goto(url, timeout=45000, wait_until="domcontentloaded")
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            if (r and r.status >= 400) or BLOCKED.search(await page.title()):
                return None
            prev = -1
            await page.wait_for_timeout(1000)
            if captured:
                return captured
            for _ in range(25):  # lazy-loaded / paginated lists: scroll and press "load more" until the count stops growing
                await page.mouse.wheel(0, 6000)
                await page.wait_for_timeout(700)
                try:
                    btn = page.get_by_role("button", name=MORE).first
                    if await btn.is_visible(timeout=300):
                        await btn.click(timeout=2000)
                        await page.wait_for_timeout(900)
                except Exception:
                    pass
                n = await page.eval_on_selector_all("a[href]", "e=>e.length")
                if n == prev:
                    break
                prev = n
            out, seen = [], set()
            # 1. JSON-LD JobPosting
            for raw in await page.eval_on_selector_all('script[type="application/ld+json"]', "e=>e.map(x=>x.textContent)"):
                try:
                    data = json.loads(raw)
                except ValueError:
                    continue
                for d in (data if isinstance(data, list) else data.get("@graph", [data])):
                    if isinstance(d, dict) and d.get("@type") == "JobPosting" and d.get("url"):
                        loc = d.get("jobLocation") or {}
                        loc = (loc[0] if isinstance(loc, list) and loc else loc)
                        addr = (loc.get("address") or {}) if isinstance(loc, dict) else {}
                        L = ", ".join(x for x in (addr.get("addressLocality"), addr.get("addressCountry")) if isinstance(x, str))
                        if d["url"] not in seen:
                            seen.add(d["url"]); out.append(_job(d["url"], d.get("title", ""), L, d["url"]))
            # 2. job-looking links, across paginated result pages
            async def collect():
                found = 0
                links = await page.eval_on_selector_all("a[href]", "els=>els.map(e=>[e.href,(e.innerText||'').trim()])")
                for href, text in links:
                    key = href.split("?")[0].rstrip("/")
                    if not text or key in seen or not JOBLINK.search(href) or NOT_JOB.search(href):
                        continue
                    lines = [l.strip() for l in text.split("\n") if l.strip() and l.strip().lower() not in ("location", "location:", "department", "apply", "apply now")]
                    if not lines:
                        continue
                    title = lines[0][:140]
                    if title.lower() in LANGS:
                        continue
                    if len(title) < 4 or title.lower() in ("apply now", "apply", "view job", "read more", "see open positions", "see careers", "skip to main content"):
                        if len(lines) > 1:
                            title = lines[1][:140]
                        else:
                            continue
                    seen.add(key)
                    found += 1
                    loc = " | ".join(lines[1:3])[:100]
                    m = re.search(r"myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?[^/]+/job/([^/]+)/", href)
                    if m:  # Workday puts the location in the URL path
                        loc = m.group(1).replace("-", " ")
                    out.append(_job(key, title, loc, href))
                return found
            await collect()
            for _ in range(60):  # pagination: stop when "next" is missing/disabled or yields nothing new
                nxt = None
                for sel in NEXT_SELS:  # first *visible* match (a <link rel=next> in <head> is not clickable)
                    loc = page.locator("body " + sel if not sel.startswith("body") else sel).locator("visible=true")
                    if await loc.count():
                        nxt = loc.first
                        break
                if nxt is None:
                    break
                try:
                    cls = (await nxt.get_attribute("class") or "") + " " + (await nxt.get_attribute("aria-disabled") or "")
                    if re.search(r"disabled|true", cls, re.I) or await nxt.is_disabled():
                        break
                    await nxt.click(timeout=3000)
                except Exception:
                    break
                await page.wait_for_timeout(1500)
                if not await collect():
                    break
            return out
        except Exception:
            return None
        finally:
            await page.close()


async def _run(urls):
    sem = asyncio.Semaphore(3)
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=EXE, args=["--no-sandbox"]) if EXE else await p.chromium.launch(args=["--no-sandbox"])
        ctx = await b.new_context(user_agent=UA, locale="en-US")
        res = await asyncio.gather(*[crawl_one(ctx, u, sem) for u in urls])
        await b.close()
    return dict(zip(urls, res))


def crawl_many(urls):
    return asyncio.run(_run(list(urls)))
