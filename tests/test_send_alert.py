import runpy
import sys
from typing import Any, ClassVar

import pytest

import send_alert

RUN_URL = "https://github.com/o/r/actions/runs/1"


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
def smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeSMTP.instances = []
    monkeypatch.setattr(send_alert.smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(sys, "argv", ["send_alert.py", RUN_URL])
    monkeypatch.setenv("GMAIL_USER", "me@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "pw")
    monkeypatch.delenv("DIGEST_TO", raising=False)


def test_sends_a_plain_alert_with_the_run_link(capsys: pytest.CaptureFixture[str]) -> None:
    send_alert.main()
    (server,) = FakeSMTP.instances
    assert server.args == ("smtp.gmail.com", 465, 60)
    assert server.login_args == ("me@example.com", "pw")
    msg = server.sent[0]
    assert msg["Subject"].startswith("Job crawl failed (")
    assert (msg["From"], msg["To"]) == ("me@example.com", "me@example.com")
    assert RUN_URL in msg.get_content()
    assert "sent: Job crawl failed" in capsys.readouterr().out


def test_digest_to_overrides_the_recipient(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGEST_TO", "other@example.com")
    send_alert.main()
    assert FakeSMTP.instances[0].sent[0]["To"] == "other@example.com"


def test_a_missing_link_is_said_so(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["send_alert.py"])
    send_alert.main()
    assert "no link to the run" in FakeSMTP.instances[0].sent[0].get_content()


def test_missing_credentials_fail_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GMAIL_APP_PASSWORD")
    with pytest.raises(KeyError):
        send_alert.main()
    assert FakeSMTP.instances == []


def test_as_a_script() -> None:
    runpy.run_module("send_alert", run_name="__main__")
    assert len(FakeSMTP.instances) == 1
