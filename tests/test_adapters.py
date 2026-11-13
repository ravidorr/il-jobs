from typing import Any

import pytest

import adapters
from tests.fakes import FakeHttpResponse


def fake_get(monkeypatch: pytest.MonkeyPatch, *responses: FakeHttpResponse | None) -> list[str]:
    urls: list[str] = []
    queue = list(responses)

    def _get(url: str, **_kw: Any) -> FakeHttpResponse | None:
        urls.append(url)
        return queue.pop(0) if len(queue) > 1 else queue[0]

    monkeypatch.setattr(adapters, "get", _get)
    return urls


def test_job_normalises() -> None:
    assert adapters._job(5, None, " x ", "u") == {
        "job_id": "5",
        "title": "",
        "location": "x",
        "url": "u",
        "team": "",
        "posted": "",
    }


@pytest.mark.parametrize("name", ["greenhouse", "lever", "ashby", "workable", "comeet", "greenhouse_url"])
@pytest.mark.parametrize("resp", [None, FakeHttpResponse(status_code=500)])
def test_failure_returns_none(monkeypatch: pytest.MonkeyPatch, name: str, resp: FakeHttpResponse | None) -> None:
    fake_get(monkeypatch, resp)
    assert adapters.ADAPTERS[name]("slug") is None


def test_greenhouse(monkeypatch: pytest.MonkeyPatch) -> None:
    data = {
        "jobs": [
            {"id": 1, "title": "A", "location": {"name": "Tel Aviv"}, "absolute_url": "u1", "updated_at": "t"},
            {"id": 2, "title": "B", "location": None, "absolute_url": "u2"},
        ]
    }
    fake_get(monkeypatch, FakeHttpResponse(data=data))
    jobs = adapters.greenhouse("acme")
    assert jobs is not None
    assert [(j["job_id"], j["location"], j["posted"]) for j in jobs] == [("1", "Tel Aviv", "t"), ("2", "", "")]


def test_lever_eu_and_categories(monkeypatch: pytest.MonkeyPatch) -> None:
    data = [
        {"id": "a", "text": "T1", "hostedUrl": "h1", "categories": {"location": "Haifa", "team": "R"}, "createdAt": 7},
        {"id": "b", "text": "T2", "hostedUrl": "h2", "categories": {"allLocations": ["X", "Y"]}},
        {"id": "c", "text": "T3", "hostedUrl": "h3", "categories": None},
    ]
    urls = fake_get(monkeypatch, FakeHttpResponse(data=data))
    jobs = adapters.lever("eu:acme")
    assert urls == ["https://api.eu.lever.co/v0/postings/acme?mode=json"]
    assert jobs is not None
    assert [j["location"] for j in jobs] == ["Haifa", "X, Y", ""]
    assert jobs[0]["team"] == "R"
    assert jobs[0]["posted"] == "7"
    urls = fake_get(monkeypatch, FakeHttpResponse(data=[]))
    assert adapters.lever("acme") == []
    assert urls == ["https://api.lever.co/v0/postings/acme?mode=json"]


def test_ashby_skips_unlisted(monkeypatch: pytest.MonkeyPatch) -> None:
    data = {
        "jobs": [
            {"id": "1", "title": "A", "location": "L", "jobUrl": "u", "team": "T", "publishedAt": "p"},
            {"id": "2", "title": "B", "isListed": False},
        ]
    }
    fake_get(monkeypatch, FakeHttpResponse(data=data))
    jobs = adapters.ashby("acme")
    assert jobs is not None
    assert [j["job_id"] for j in jobs] == ["1"]


def test_workable(monkeypatch: pytest.MonkeyPatch) -> None:
    data = {
        "jobs": [
            {"shortcode": "s1", "title": "A", "city": "TLV", "country": "IL", "url": "u1", "department": "D"},
            {"shortcode": "s2", "title": "B", "application_url": "u2"},
        ]
    }
    fake_get(monkeypatch, FakeHttpResponse(data=data))
    jobs = adapters.workable("acme")
    assert jobs is not None
    assert [(j["location"], j["url"]) for j in jobs] == [("TLV, IL", "u1"), ("", "u2")]


def posting(i: str) -> dict[str, Any]:
    return {
        "id": i,
        "name": f"N{i}",
        "location": {"city": "C", "country": "IL"},
        "department": {"label": "D"},
        "releasedDate": "r",
    }


def test_smartrecruiters_paginates(monkeypatch: pytest.MonkeyPatch) -> None:
    page1 = FakeHttpResponse(data={"content": [posting("1")], "totalFound": 150})
    page2 = FakeHttpResponse(data={"content": [{"id": "2", "name": "N2"}], "totalFound": 150})
    urls = fake_get(monkeypatch, page1, page2)
    jobs = adapters.smartrecruiters("acme")
    assert jobs is not None
    assert [j["job_id"] for j in jobs] == ["1", "2"]
    assert jobs[0]["url"] == "https://jobs.smartrecruiters.com/acme/1"
    assert jobs[0]["team"] == "D"
    assert urls[1].endswith("offset=100")


def test_smartrecruiters_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_get(monkeypatch, None)
    assert adapters.smartrecruiters("acme") is None
    page1 = FakeHttpResponse(data={"content": [posting("1")], "totalFound": 150})
    fake_get(monkeypatch, page1, FakeHttpResponse(status_code=429))
    jobs = adapters.smartrecruiters("acme")
    assert jobs is not None
    assert len(jobs) == 1
    fake_get(monkeypatch, FakeHttpResponse(data={}))
    assert adapters.smartrecruiters("acme") == []


def test_comeet(monkeypatch: pytest.MonkeyPatch) -> None:
    text = (
        'var COMPANY_POSITIONS_DATA = [{"uid": "u1", "name": "A", "location": {"city": "TLV", "country": "IL"},'
        ' "url_active_page": "a", "department": "D", "time_updated": "t"},'
        ' {"uid": "u2", "name": "B", "url_comeet_hosted_page": "b"}];'
    )
    fake_get(monkeypatch, FakeHttpResponse(text=text))
    jobs = adapters.comeet("n/uid")
    assert jobs is not None
    assert [(j["job_id"], j["location"], j["url"]) for j in jobs] == [("u1", "TLV, IL", "a"), ("u2", "", "b")]


@pytest.mark.parametrize(
    "text", ["nothing here", "COMPANY_POSITIONS_DATA but no array", "COMPANY_POSITIONS_DATA = [not json];"]
)
def test_comeet_unparseable(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    fake_get(monkeypatch, FakeHttpResponse(text=text))
    assert adapters.comeet("n/uid") is None


def test_greenhouse_url(monkeypatch: pytest.MonkeyPatch) -> None:
    data = {"jobs": [{"id": 1, "title": "A", "location": {"name": "L"}, "absolute_url": "u"}]}
    fake_get(monkeypatch, FakeHttpResponse(data=data))
    jobs = adapters.greenhouse_url("https://x.test/jobs.json")
    assert jobs is not None
    assert jobs[0]["location"] == "L"
    fake_get(monkeypatch, FakeHttpResponse(json_error=True))
    assert adapters.greenhouse_url("https://x.test/jobs.json") is None
