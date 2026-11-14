"""Tier 3: generic crawler for career pages without a public ATS API. Real browser (Playwright).
Extracts JSON-LD JobPosting, else job-looking links. Returns list of jobs, or None if blocked/failed."""

import asyncio
import contextlib
import json
import os
import re
from typing import Any, cast

from playwright.async_api import async_playwright

from discover import ISRAEL

JOBLINK = re.compile(r"/(jobs?|positions?|careers?|openings?|vacanc\w+|job-?post\w*)/[^/?#]{4,}", re.I)
NOT_JOB = re.compile(
    r"/(department|departments|category|team|teams|locations?|working-at|life-at|benefits|students?|early-careers?|login|search|saved|talent-network)\b|#",
    re.I,
)
NEXT_SELS = [
    'a[title="Next" i]',
    "a.link-next",
    'a[aria-label="Next page" i]',
    'button[title="Next" i]',
    'body a[rel="next"]',
    'a[aria-label="Next" i]',
    'button[aria-label="Next" i]',
    "li.next a",
    ".pagination-next",
    'a:text-is("Next")',
    'button:text-is("Next")',
    'a:text-is("Next >")',
]
EF_SEARCH = "/api/pcsx/search"  # Eightfold career sites: the page's own search request
EF_NEXT = 'button[aria-label="Next jobs" i]'
EF_MAX_PAGES = 60  # ten jobs a page
SETTLE_POLLS = 32  # at 250 ms: wait up to 8 s for a pagination click to show new job links
MORE = re.compile(r"load more|show more|see more|view more|more jobs|more positions", re.I)
LANGS = {
    "english",
    "español",
    "français",
    "português",
    "deutsch",
    "italiano",
    "日本語",
    "한국어",
    "中文",
    "русский",
    "עברית",
    "polski",
    "nederlands",
}
BLOCKED = re.compile(
    r"just a moment|attention required|security checkpoint|access denied|error 429|verify you are human", re.I
)
EXE = os.environ.get("PW_CHROMIUM") or (
    "/opt/pw-browsers/chromium" if os.path.exists("/opt/pw-browsers/chromium") else None
)
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"


HTTP_OK = 200
HTTP_ERROR = 400
CARD_MAX = 250
MIN_TITLE = 4

WHY: dict[str, str] = {}  # url -> reason, filled for failed or empty crawls, printed by run.py


def _job(job_id: Any, title: Any, location: Any, url: Any, team: Any = "") -> dict[str, Any]:
    return {"job_id": job_id, "title": title, "location": location, "url": url, "team": team, "posted": ""}


def _eightfold_jobs(resp_url: str, body: dict[str, Any]) -> list[dict[str, Any]]:
    origin = cast("re.Match[str]", re.match(r"https?://[^/]+", resp_url))[0]
    return [
        _job(
            str(p["id"]),
            p.get("name", ""),
            "; ".join(p.get("locations") or []),
            origin + p["positionUrl"],
            team=p.get("department") or "",
        )
        for p in body["data"]["positions"]
    ]


async def _eightfold_pages(page: Any, ef_jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Eightfold boards: use the page's own search results and press "Next jobs" for the rest.

    The click is dispatched as an event because cookie banners often cover the button. Results come sorted by
    distance from the searched place, so a page after the first with no Israel job ends the list."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def drain() -> list[dict[str, Any]]:
        fresh = [j for j in ef_jobs if j["job_id"] not in seen]
        seen.update(j["job_id"] for j in fresh)
        out.extend(fresh)
        return fresh

    batch = drain()
    for n in range(EF_MAX_PAGES - 1):
        if n and not any(ISRAEL.search(j["location"]) for j in batch):
            break
        nxt = page.locator(EF_NEXT)
        if not await nxt.count():
            break
        el = nxt.first
        if await el.is_disabled() or await el.get_attribute("aria-disabled") == "true":
            break
        await el.dispatch_event("click")
        batch = []
        for _poll in range(SETTLE_POLLS):
            await page.wait_for_timeout(250)
            batch = drain()
            if batch:
                break
        if not batch:
            break
    return out


async def crawl_one(ctx: Any, url: str, sem: asyncio.Semaphore) -> list[dict[str, Any]] | None:  # noqa: PLR0912, PLR0915
    async with sem:
        page = await ctx.new_page()
        captured: list[dict[str, Any]] = []
        ef_jobs: list[dict[str, Any]] = []
        link_count = 0

        async def on_resp(resp: Any) -> None:  # HiBob career boards load every job in one JSON response
            with contextlib.suppress(Exception):
                if (
                    "/api/job-ad" in resp.url
                    and resp.request.resource_type in ("xhr", "fetch")
                    and resp.status == HTTP_OK
                ):
                    d = await resp.json()
                    if isinstance(d, dict) and isinstance(d.get("jobAdDetails"), list):
                        origin = cast("re.Match[str]", re.match(r"https?://[^/]+", resp.url))[0]
                        for j in d["jobAdDetails"]:
                            loc = ", ".join(x for x in (j.get("site"), j.get("country")) if x)
                            captured.append(
                                _job(
                                    j["id"],
                                    j.get("title", ""),
                                    loc,
                                    f"{origin}/jobs/{j['id']}",
                                    team=j.get("department") or "",
                                )
                            )

        async def on_search(resp: Any) -> None:  # Eightfold: every search page, first load and each "Next jobs"
            with contextlib.suppress(Exception):
                if EF_SEARCH in resp.url and resp.request.resource_type in ("xhr", "fetch") and resp.status == HTTP_OK:
                    ef_jobs.extend(_eightfold_jobs(resp.url, await resp.json()))

        page.on("response", lambda r: asyncio.ensure_future(on_resp(r)))
        page.on("response", lambda r: asyncio.ensure_future(on_search(r)))
        try:
            r = await page.goto(url, timeout=45000, wait_until="domcontentloaded")
            with contextlib.suppress(Exception):
                await page.wait_for_load_state("networkidle", timeout=15000)
            title = (await page.title())[:80]
            if r and r.status >= HTTP_ERROR:
                WHY[url] = f"HTTP {r.status}, title={title!r}, final={page.url[:80]}"
                return None
            if BLOCKED.search(title):
                WHY[url] = f"blocked page, title={title!r}, final={page.url[:80]}"
                return None
            prev = -1
            await page.wait_for_timeout(1000)
            if captured:
                return captured
            if ef_jobs:
                return await _eightfold_pages(page, ef_jobs)
            for _ in range(
                25
            ):  # lazy-loaded / paginated lists: scroll and press "load more" until the count stops growing
                await page.mouse.wheel(0, 6000)
                await page.wait_for_timeout(700)
                with contextlib.suppress(Exception):
                    btn = page.get_by_role("button", name=MORE).first
                    if await btn.is_visible(timeout=300):
                        await btn.click(timeout=2000)
                        await page.wait_for_timeout(900)
                n = await page.eval_on_selector_all("a[href]", "e=>e.length")
                if n == prev:
                    break
                prev = n
            out: list[dict[str, Any]] = []
            seen: set[str] = set()
            # 1. JSON-LD JobPosting
            for raw in await page.eval_on_selector_all(
                'script[type="application/ld+json"]', "e=>e.map(x=>x.textContent)"
            ):
                try:
                    data = json.loads(raw)
                except ValueError:
                    continue
                for d in data if isinstance(data, list) else data.get("@graph", [data]):
                    if isinstance(d, dict) and d.get("@type") == "JobPosting" and d.get("url"):
                        loc = d.get("jobLocation") or {}
                        loc = loc[0] if isinstance(loc, list) and loc else loc
                        addr = (loc.get("address") or {}) if isinstance(loc, dict) else {}
                        L = ", ".join(
                            x for x in (addr.get("addressLocality"), addr.get("addressCountry")) if isinstance(x, str)
                        )
                        if d["url"] not in seen:
                            seen.add(d["url"])
                            out.append(_job(d["url"], d.get("title", ""), L, d["url"]))

            # 2. job-looking links, across paginated result pages
            async def collect() -> int:
                nonlocal link_count
                found = 0
                links = await page.eval_on_selector_all(
                    "a[href]",
                    """els=>els.map(e=>{let n=e; for(let i=0;i<2&&n.parentElement;i++) n=n.parentElement;
                    return [e.href,(e.innerText||'').trim(),(n.innerText||'').trim().slice(0,300)]})""",
                )
                link_count = len(links)
                for href, text, card in links:
                    key = href.split("?")[0].rstrip("/")
                    if not text or key in seen or not JOBLINK.search(href) or NOT_JOB.search(href):
                        continue
                    lines = [
                        ln.strip()
                        for ln in text.split("\n")
                        if ln.strip()
                        and ln.strip().lower() not in ("location", "location:", "department", "apply", "apply now")
                    ]
                    if not lines:
                        continue
                    title = lines[0][:140]
                    if title.lower() in LANGS:
                        continue
                    if (
                        len(lines) == 1 and 0 < len(card) < CARD_MAX
                    ):  # bare title link: location sits in the surrounding card
                        cl = [
                            ln.strip()
                            for ln in card.split("\n")
                            if ln.strip()
                            and ln.strip().lower() not in ("save job", "share job", "apply", "apply now", title.lower())
                        ]
                        lines = [title, *cl[:2]]
                    if len(title) < MIN_TITLE or title.lower() in (
                        "apply now",
                        "apply",
                        "view job",
                        "read more",
                        "see open positions",
                        "see careers",
                        "skip to main content",
                    ):
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
                    cand = page.locator("body " + sel if not sel.startswith("body") else sel).locator("visible=true")
                    if await cand.count():
                        nxt = cand.first
                        break
                if nxt is None:
                    break
                try:
                    cls = (
                        (await nxt.get_attribute("class") or "")
                        + " "
                        + (await nxt.get_attribute("aria-disabled") or "")
                    )
                    if re.search(r"disabled|true", cls, re.I) or await nxt.is_disabled():
                        break
                    await nxt.click(timeout=3000)
                except Exception:
                    break
                found = 0
                for _poll in range(SETTLE_POLLS):  # wait for new job links; a pager may clear the list first
                    await page.wait_for_timeout(250)
                    found = await collect()
                    if found:
                        break
                if not found:
                    break
            if not out:
                WHY[url] = f"no jobs found, title={title!r}, final={page.url[:80]}, links={link_count}"
            return out
        except Exception as e:
            WHY[url] = f"{type(e).__name__}: {str(e).splitlines()[0][:140] if str(e) else ''}"
            return None
        finally:
            await page.close()


async def _run(urls: list[str]) -> dict[str, list[dict[str, Any]] | None]:
    sem = asyncio.Semaphore(3)
    async with async_playwright() as p:
        b = (
            await p.chromium.launch(executable_path=EXE, args=["--no-sandbox"])
            if EXE
            else await p.chromium.launch(args=["--no-sandbox"])
        )
        ctx = await b.new_context(user_agent=UA, locale="en-US")
        res = await asyncio.gather(*[crawl_one(ctx, u, sem) for u in urls])
        await b.close()
    return dict(zip(urls, res, strict=True))


def crawl_many(urls: Any) -> dict[str, list[dict[str, Any]] | None]:
    return asyncio.run(_run(list(urls)))
