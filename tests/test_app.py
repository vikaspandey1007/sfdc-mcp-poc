"""Smoke tests for app/app.py, the Gate 5 Streamlit thin UI.

Per docs/gate-0-plan.md's own note ("Streamlit apps are hard to unit test
meaningfully -- note this as a known limitation rather than
over-engineering test coverage here"), this stays a light smoke-test tier:
does the app render, does the access-code gate actually gate, does asking
a question show the answer/evidence, does a failure show a friendly error,
and -- the assertions worth being thorough about -- are DEMO_API_KEY and
UI_ACCESS_CODE ever rendered on screen. Uses streamlit.testing.v1.AppTest,
which actually executes the script; requests.post is mocked so nothing
here makes a real network call.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from streamlit.testing.v1 import AppTest

_APP_PATH = str(Path(__file__).parent.parent / "app" / "app.py")
_TEST_API_KEY = "unit-test-demo-key-should-never-render"
_TEST_ACCESS_CODE = "unit-test-access-code-should-never-render"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_API_KEY", _TEST_API_KEY)
    monkeypatch.setenv("UI_ACCESS_CODE", _TEST_ACCESS_CODE)
    monkeypatch.setenv("AGENT_API_URL", "https://example-agent.onrender.com")


def _unlocked(at: AppTest) -> AppTest:
    """Runs the app fresh and enters the correct access code, landing on
    the question box -- the starting point most tests below actually care
    about testing."""
    at.run()
    at.text_input[0].input(_TEST_ACCESS_CODE).run()
    at.button[0].click().run()
    return at


def _all_rendered_text(at: AppTest) -> str:
    """Concatenates every piece of text the app rendered, across every
    element type this app actually uses, for the blanket
    "never appears anywhere" assertions."""
    pieces: list[str] = []
    pieces.extend(t.value for t in at.title)
    pieces.extend(c.value for c in at.caption)
    pieces.extend(m.value for m in at.markdown)
    pieces.extend(e.value for e in at.error)
    pieces.extend(ex.label for ex in at.expander)
    return "\n".join(pieces)


# -- access-code gate --


def test_app_refuses_to_render_when_access_code_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UI_ACCESS_CODE", raising=False)
    at = AppTest.from_file(_APP_PATH)
    at.run()

    assert not at.exception
    assert any("UI_ACCESS_CODE is not configured" in e.value for e in at.error)
    assert len(at.text_input) == 0  # nothing rendered, not even the code prompt


def test_app_shows_access_code_prompt_before_anything_else() -> None:
    at = AppTest.from_file(_APP_PATH)
    at.run()

    assert not at.exception
    assert len(at.text_input) == 1  # the access-code field, not the question box
    assert len(at.caption) == 0  # "Talking to <url>" only appears after unlock


def test_wrong_access_code_is_rejected_and_stays_locked() -> None:
    at = AppTest.from_file(_APP_PATH)
    at.run()
    at.text_input[0].input("totally-wrong-code").run()
    at.button[0].click().run()

    assert not at.exception
    assert any("Incorrect access code" in e.value for e in at.error)
    # Still locked: no question box appeared.
    assert len(at.text_input) == 1  # still just the access-code field


def test_correct_access_code_unlocks_the_question_box() -> None:
    at = _unlocked(AppTest.from_file(_APP_PATH))

    assert not at.exception
    assert len(at.text_input) == 1  # now the question box, not the code field
    assert len(at.button) == 1
    assert at.button[0].disabled  # nothing typed yet


def test_access_code_is_never_rendered_anywhere_on_screen() -> None:
    at = AppTest.from_file(_APP_PATH)
    at.run()
    at.text_input[0].input("totally-wrong-code").run()
    at.button[0].click().run()

    assert _TEST_ACCESS_CODE not in _all_rendered_text(at)


# -- the question/answer flow, once unlocked --


def test_ask_button_enabled_once_question_is_typed() -> None:
    at = _unlocked(AppTest.from_file(_APP_PATH))

    at.text_input[0].input("Show me open opportunities worth more than $250k.").run()
    assert not at.button[0].disabled


def test_asking_shows_the_answer_and_tool_calls() -> None:
    fake_response = MagicMock(status_code=200)
    fake_response.json.return_value = {
        "answer": "Here are the opportunities.",
        "tool_calls": ["getObjectSchema", "soqlQuery"],
    }

    with patch("requests.post", return_value=fake_response) as mock_post:
        at = _unlocked(AppTest.from_file(_APP_PATH))
        at.text_input[0].input("Show me open opportunities worth more than $250k.").run()
        at.button[0].click().run()

    assert not at.exception
    rendered = _all_rendered_text(at)
    assert "Here are the opportunities." in rendered
    assert "getObjectSchema" in rendered
    assert "soqlQuery" in rendered

    # The request itself must carry the key as a header, never in the body/URL.
    args, kwargs = mock_post.call_args
    assert kwargs["headers"]["X-Demo-Api-Key"] == _TEST_API_KEY
    assert _TEST_API_KEY not in str(kwargs.get("json", ""))
    assert _TEST_API_KEY not in args[0]  # requests.post's first positional arg is the URL


def test_asking_with_no_tool_calls_shows_that_clearly() -> None:
    fake_response = MagicMock(status_code=200)
    fake_response.json.return_value = {"answer": "I cannot help with that.", "tool_calls": []}

    with patch("requests.post", return_value=fake_response):
        at = _unlocked(AppTest.from_file(_APP_PATH))
        at.text_input[0].input("Update something to Closed Won.").run()
        at.button[0].click().run()

    rendered = _all_rendered_text(at)
    assert "No tools were called" in rendered


def test_api_failure_shows_a_friendly_error_not_a_crash() -> None:
    fake_response = MagicMock(status_code=503)
    fake_response.headers = {"content-type": "application/json"}
    fake_response.json.return_value = {"error": "The agent is temporarily unavailable. Please retry shortly."}

    with patch("requests.post", return_value=fake_response):
        at = _unlocked(AppTest.from_file(_APP_PATH))
        at.text_input[0].input("hi").run()
        at.button[0].click().run()

    assert not at.exception
    assert any("temporarily unavailable" in e.value for e in at.error)


def test_missing_demo_api_key_shows_a_clear_error_after_unlock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEMO_API_KEY", raising=False)
    at = _unlocked(AppTest.from_file(_APP_PATH))

    assert not at.exception
    assert any("DEMO_API_KEY is not configured" in e.value for e in at.error)
    assert len(at.text_input) == 0  # question box isn't shown without it


def test_demo_api_key_is_never_rendered_anywhere_on_screen() -> None:
    fake_response = MagicMock(status_code=200)
    fake_response.json.return_value = {"answer": "answer text", "tool_calls": ["soqlQuery"]}

    with patch("requests.post", return_value=fake_response):
        at = _unlocked(AppTest.from_file(_APP_PATH))
        at.text_input[0].input("Show me opportunities.").run()
        at.button[0].click().run()

    assert _TEST_API_KEY not in _all_rendered_text(at)
