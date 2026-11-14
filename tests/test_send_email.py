import runpy
import sqlite3
import sys
from typing import Any, ClassVar

import pytest

import send_email
from tests.conftest import add_crawls, add_job


class FakeSMTP:
    instances: ClassVar[list["FakeSMTP"]] = []

    def __init__(self, host: str, port: int, timeout: int) -> None:
        self.args = (host, port, timeout)
        self.login_args: tuple[str, str] | None = None
        self.sent: list[Any] = []
        FakeSMTP.instances.append(self)

    def __enter__(self) -> "FakeSMTP":
        return self

    def __exit__(self, *_a: object) -> None:
        return None

    def login(self, user: str, pw: str) -> None:
        self.login_args = (user, pw)

    def send_message(self, msg: Any) -> None:
        self.sent.append(msg)


@pytest.fixture(autouse=True)
def smtp(monkeypatch: pytest.MonkeyPatch) -> type[FakeSMTP]:
    FakeSMTP.instances = []
    monkeypatch.setattr(send_email.smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(sys, "argv", ["send_email.py"])
    monkeypatch.setenv("GMAIL_USER", "me@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "pw")
    monkeypatch.delenv("DIGEST_TO", raising=False)
    return FakeSMTP


def test_nothing_to_send(db: sqlite3.Connection, capsys: pytest.CaptureFixture[str]) -> None:
    send_email.main()
    assert "nothing sent" in capsys.readouterr().out
    assert FakeSMTP.instances == []


def test_dry_run(db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    add_job(db, "A", "1", "Product Manager")
    monkeypatch.setattr(sys, "argv", ["send_email.py", "--dry-run"])
    send_email.main()
    assert "[dry-run] would send" in capsys.readouterr().out
    assert FakeSMTP.instances == []
    assert db.execute("SELECT reported FROM jobs").fetchone()[0] == 0


def test_send_marks_reported(db: sqlite3.Connection, capsys: pytest.CaptureFixture[str]) -> None:
    add_job(db, "A", "1", "Product Manager")
    send_email.main()
    (server,) = FakeSMTP.instances
    assert server.args == ("smtp.gmail.com", 465, 60)
    assert server.login_args == ("me@example.com", "pw")
    assert server.sent[0]["To"] == "me@example.com"
    assert server.sent[0]["From"] == "me@example.com"
    assert "sent: New Israel jobs: 1" in capsys.readouterr().out
    assert db.execute("SELECT reported FROM jobs").fetchone()[0] == 1


def test_digest_to_override_via_main_entrypoint(db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch) -> None:
    add_job(db, "A", "1", "Product Manager")
    monkeypatch.setenv("DIGEST_TO", "other@example.com")
    runpy.run_module("send_email", run_name="__main__")
    assert FakeSMTP.instances[0].sent[0]["To"] == "other@example.com"


def test_a_new_coverage_gap_is_worth_an_email_without_any_new_jobs(
    db: sqlite3.Connection, capsys: pytest.CaptureFixture[str]
) -> None:
    add_crawls(db, "Blocked", [(1, ""), (0, "HTTP 403"), (0, "HTTP 403")])
    send_email.main()
    (server,) = FakeSMTP.instances
    assert server.sent[0]["Subject"].startswith("Job crawl alert: 1 new (")
    assert "Blocked" in server.sent[0].get_payload()[1].get_content()
    assert "sent: Job crawl alert" in capsys.readouterr().out


def test_an_old_coverage_gap_alone_sends_nothing(db: sqlite3.Connection, capsys: pytest.CaptureFixture[str]) -> None:
    add_crawls(db, "Blocked", [(0, "HTTP 403")] * 4)
    send_email.main()
    assert "nothing sent" in capsys.readouterr().out
    assert FakeSMTP.instances == []


def test_jobs_and_gaps_go_in_one_email(db: sqlite3.Connection) -> None:
    add_job(db, "A", "1", "Product Manager")
    add_crawls(db, "Blocked", [(0, "HTTP 403")] * 4)
    send_email.main()
    (server,) = FakeSMTP.instances
    assert server.sent[0]["Subject"].startswith("New Israel jobs: 1 (")
    assert "Not crawled properly (1)" in server.sent[0].get_payload()[1].get_content()


def test_dry_run_reports_a_gap_alert_without_sending(
    db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    add_crawls(db, "Held", [(0, "sharp drop: got 0, 20 open before")])
    monkeypatch.setattr(sys, "argv", ["send_email.py", "--dry-run"])
    send_email.main()
    assert "[dry-run] would send: Job crawl alert: 1 new" in capsys.readouterr().out
    assert FakeSMTP.instances == []
