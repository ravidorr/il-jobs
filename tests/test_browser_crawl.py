import asyncio
import json
from typing import Any

import pytest

import browser_crawl
from browser_crawl import WHY, crawl_one
from tests.fakes import FakeCtx, FakeEl, FakeLoc, FakePage, FakePlaywright, FakeResp, Status

URL = "https://x.test/careers"
SCROLL_CAP = 25
TWO = 2


@pytest.fixture(autouse=True)
def clear_why() -> None:
    WHY.clear()


async def run(page: FakePage) -> list[dict[str, Any]] | None:
    result = await crawl_one(FakeCtx(page), URL, asyncio.Semaphore(1))
    assert page.closed
    return result


def link(path: str, text: str, card: str = "") -> list[str]:
    return [f"https://x.test{path}", text, card]


async def test_http_error_recorded() -> None:
    assert await run(FakePage(goto_result=Status(404), idle_error=True)) is None
    assert WHY[URL].startswith("HTTP 404")


async def test_blocked_title_recorded() -> None:
    assert await run(FakePage(goto_result=None, title="Just a moment...")) is None
    assert WHY[URL].startswith("blocked page")


async def test_goto_exception_recorded() -> None:
    assert await run(FakePage(goto_error=RuntimeError("boom\nsecond line"))) is None
    assert WHY[URL] == "RuntimeError: boom"
    assert await run(FakePage(goto_error=RuntimeError())) is None
    assert WHY[URL] == "RuntimeError: "


async def test_hibob_json_response_short_circuits() -> None:
    api = "https://acme.hibob.com/api/job-ad"
    ads = {
        "jobAdDetails": [
            {"id": "1", "title": "PM", "site": "Tel Aviv", "country": "IL", "department": "P"},
            {"id": "2"},
        ]
    }
    responses = [
        FakeResp("https://acme.hibob.com/other", data=ads),
        FakeResp(api, data=ads, resource_type="document"),
        FakeResp(api, data=ads, status=500),
        FakeResp(api, data=["not a dict"]),
        FakeResp(api, data={"jobAdDetails": "nope"}),
        FakeResp(api, error=True),
        FakeResp(api, data=ads),
    ]
    jobs = await run(FakePage(responses=responses))
    assert jobs == [
        {
            "job_id": "1",
            "title": "PM",
            "location": "Tel Aviv, IL",
            "url": "https://acme.hibob.com/jobs/1",
            "team": "P",
            "posted": "",
        },
        {"job_id": "2", "title": "", "location": "", "url": "https://acme.hibob.com/jobs/2", "team": "", "posted": ""},
    ]


def ld(*items: Any) -> list[str]:
    return [json.dumps(i) if not isinstance(i, str) else i for i in items]


async def test_json_ld_variants() -> None:
    def posting(url: str, **kw: Any) -> dict[str, Any]:
        return {"@type": "JobPosting", "url": url, "title": "T", **kw}

    addr = {"address": {"addressLocality": "Haifa", "addressCountry": "IL"}}
    raws = ld(
        "{not json",
        [posting("u1", jobLocation=[addr]), posting("u1"), "str", {"@type": "Other", "url": "x"}, posting("")],
        {"@graph": [posting("u2", jobLocation=addr), posting("u3", jobLocation=[]), posting("u4", jobLocation="x")]},
        posting("u5", jobLocation={"address": {"addressLocality": 3, "addressCountry": "IL"}}),
    )
    jobs = await run(FakePage(ld=raws))
    assert jobs is not None
    assert [(j["job_id"], j["location"]) for j in jobs] == [
        ("u1", "Haifa, IL"),
        ("u2", "Haifa, IL"),
        ("u3", ""),
        ("u4", ""),
        ("u5", "IL"),
    ]
    assert WHY == {}


async def test_scroll_loop_load_more_and_growth() -> None:
    btn = FakeEl()
    page = FakePage(btn=btn, count_fn=lambda i: i)
    await run(page)
    assert btn.clicks == SCROLL_CAP
    assert WHY[URL].startswith("no jobs found")
    # a failing load-more click is swallowed, and an unchanged count stops the loop
    bad = FakeEl(click_error=True)
    page = FakePage(btn=bad, count_fn=lambda _i: 3)
    assert await run(page) == []


async def test_collect_link_filters_and_titles() -> None:
    wd = "https://acme.myworkdayjobs.com/en-US/ext/job/Tel-Aviv-Israel/Product-Manager_R1/apply"
    links = [
        link("/jobs/dup-title", "Seen Job\nTel Aviv"),
        link("/jobs/dup-title/", "Seen Job again"),
        link("/jobs/", ""),
        link("/about/us-page", "Not a job link"),
        link("/team/ceo-profile", "Team page with long name"),
        link("/jobs/only-junk", "Apply\nlocation"),
        link("/jobs/lang-link", "English"),
        link("/jobs/card-job", "Card Job", "Card Job\nSave job\nHaifa\nFull time\nExtra"),
        link("/jobs/long-card", "Long Card", "x" * 300),
        link("/jobs/empty-card", "Empty Card", ""),
        link("/jobs/short-title", "PM\nHerzliya\nIL"),
        link("/jobs/short-alone", "PM"),
        link("/jobs/junk-title", "Read more\nSecond Title\nJerusalem"),
        [wd, "Workday Job\nElsewhere", ""],
    ]
    page = FakePage(link_fn=lambda i: links if i == 1 else [], ld=ld({"@type": "JobPosting", "url": "u0"}))
    jobs = await run(page)
    assert jobs is not None
    got = {j["title"]: j["location"] for j in jobs}
    assert got == {
        "": "",
        "Seen Job": "Tel Aviv",
        "Card Job": "Haifa | Full time",
        "Long Card": "",
        "Empty Card": "",
        "Herzliya": "Herzliya | IL",
        "Second Title": "Second Title | Jerusalem",
        "Workday Job": "Tel Aviv Israel",
    }


async def test_pagination_no_next() -> None:
    page = FakePage(link_fn=lambda i: [link("/jobs/job-one", "Job One")] if i == 1 else [])
    jobs = await run(page)
    assert jobs is not None
    assert len(jobs) == 1


def next_page(first: FakeEl, key: str = 'body a[rel="next"]') -> FakePage:
    return FakePage(
        link_fn=lambda i: [link(f"/jobs/job-{i}", f"Job {i}")],
        locators={key: FakeLoc(1, first)},
    )


async def test_pagination_stops_when_disabled() -> None:
    for el in (FakeEl(attrs={"class": "btn disabled"}), FakeEl(attrs={"aria-disabled": "true"}), FakeEl(disabled=True)):
        jobs = await run(next_page(el))
        assert jobs is not None
        assert len(jobs) == 1
        assert el.clicks == 0


async def test_pagination_click_error_stops() -> None:
    jobs = await run(next_page(FakeEl(click_error=True), key="body a.link-next"))
    assert jobs is not None
    assert len(jobs) == 1


async def test_pagination_stops_when_nothing_new() -> None:
    el = FakeEl()
    page = FakePage(
        link_fn=lambda i: [link("/jobs/job-one", "Job One")] if i <= TWO else [],
        locators={'body a[rel="next"]': FakeLoc(1, el)},
    )
    jobs = await run(page)
    assert jobs is not None
    assert len(jobs) == 1
    assert el.clicks == 1


async def test_pagination_runs_to_the_cap() -> None:
    el = FakeEl()
    jobs = await run(next_page(el))
    assert jobs is not None
    cap = 61
    assert len(jobs) == cap
    assert el.clicks == cap - 1


async def test_pagination_waits_until_the_page_changes() -> None:
    el = FakeEl()
    changes_after = 3  # the page only changes on the third poll after the click
    page = FakePage(
        link_fn=lambda i: [link(f"/jobs/job-{i}", f"Job {i}")] if i <= TWO else [],
        sig_fn=lambda i: ["/same"] if i < changes_after else [f"/new-{i}"],
        locators={'body a[rel="next"]': FakeLoc(1, el)},
    )
    jobs = await run(page)
    assert jobs is not None
    assert len(jobs) == TWO
    # click 1: read before, poll (same), poll (changed) = 3 reads; click 2: read before, poll (changed) = 2 reads
    assert page.sig_calls == changes_after + 2


async def test_pagination_gives_up_waiting_for_a_change() -> None:
    el = FakeEl()
    page = FakePage(
        link_fn=lambda i: [link(f"/jobs/job-{i}", f"Job {i}")] if i <= TWO else [],
        sig_fn=lambda _i: ["/same"],
        locators={'body a[rel="next"]': FakeLoc(1, el)},
    )
    jobs = await run(page)
    assert jobs is not None
    assert len(jobs) == TWO
    assert page.sig_calls == 2 * (browser_crawl.SETTLE_POLLS + 1)  # two clicks, each: one read before and every poll


@pytest.mark.parametrize("exe", ["/bin/chromium", None])
def test_crawl_many(monkeypatch: pytest.MonkeyPatch, exe: str | None) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_crawl(_ctx: object, url: str, _sem: asyncio.Semaphore) -> list[dict[str, Any]] | None:
        return [] if url == "a" else None

    monkeypatch.setattr(browser_crawl, "async_playwright", lambda: FakePlaywright(calls))
    monkeypatch.setattr(browser_crawl, "crawl_one", fake_crawl)
    monkeypatch.setattr(browser_crawl, "EXE", exe)
    assert browser_crawl.crawl_many(iter(["a", "b"])) == {"a": [], "b": None}
    assert ("executable_path" in calls[0]) == bool(exe)
