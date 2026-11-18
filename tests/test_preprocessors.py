import json

import httpx

from phoenix.models import AppStatus
from phoenix.paths import DATA_DIR, ensure_dirs
from phoenix.preprocessors import get_preprocessor
from phoenix.preprocessors import programming_excuses as excuses
from phoenix.settings import Settings


def test_get_existing_preprocessor():
    fn = get_preprocessor("programming_excuses")
    assert fn is not None
    assert callable(fn)


def test_get_nonexistent_preprocessor():
    assert get_preprocessor("nonexistent_app_xyz") is None


def test_programming_excuses_returns_result(tmp_path, monkeypatch):
    monkeypatch.setattr(excuses, "data_path", lambda name: tmp_path / f"{name}.json")
    monkeypatch.setattr(excuses, "_fetch_quote", lambda: None)
    settings = Settings()
    fn = get_preprocessor("programming_excuses")
    result = fn(settings)
    assert result.status == AppStatus.NORMAL
    assert isinstance(result.data, str)
    assert len(result.data) > 0


def test_programming_excuses_learns_and_keeps_the_pool_offline(tmp_path, monkeypatch):
    monkeypatch.setattr(excuses, "data_path", lambda name: tmp_path / f"{name}.json")
    monkeypatch.setattr(excuses, "choice", lambda values: values[-1])
    now = 1000
    monkeypatch.setattr(excuses, "time", lambda: now)
    quote = "The test harness ate my merge."
    replies = iter([quote, quote, None])
    calls = []

    def fetch():
        calls.append(now)
        return next(replies)

    monkeypatch.setattr(excuses, "_fetch_quote", fetch)
    settings = Settings()
    assert excuses.run(settings).data == quote
    now += 30
    assert excuses.run(settings).data == quote
    assert len(calls) == 1

    now += excuses.REFRESH_SECONDS
    assert excuses.run(settings).data == quote
    now += excuses.REFRESH_SECONDS
    assert excuses.run(settings).data == quote  # upstream outage
    assert excuses.run(settings).data == quote
    assert len(calls) == 3  # failed requests also respect the interval
    pool = json.loads((tmp_path / "programming_excuses_pool.json").read_text())
    assert pool["quotes"] == [quote]
    assert json.loads((tmp_path / "programming_excuses.json").read_text()) == {"excuse": quote}


def test_programming_excuses_parses_only_the_source_anchor(monkeypatch):
    parsed_pages = iter([
        '<a href="other.html">Navigation</a><a href="/" rel="nofollow">A &amp; B <b>failed.</b></a>',
        '<a href="/">No advice here</a>',
    ])
    transport = httpx.MockTransport(lambda request: httpx.Response(
        200, text=next(parsed_pages), headers={"content-type": "text/html; charset=UTF-8"},
    ))
    with httpx.Client(transport=transport) as client:
        monkeypatch.setattr(excuses.httpx, "stream", client.stream)
        assert excuses._fetch_quote() == "A & B failed."
        assert excuses._fetch_quote() is None


def test_programming_excuses_uses_cache_while_another_refresh_owns_the_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(excuses, "data_path", lambda name: tmp_path / f"{name}.json")
    monkeypatch.setattr(excuses, "choice", lambda values: values[-1])
    quote = "The cache kept it."
    (tmp_path / "programming_excuses_pool.json").write_text(json.dumps({"quotes": [quote]}))

    def unexpected_fetch():
        raise AssertionError("One process at a time may refresh the pool")

    monkeypatch.setattr(excuses, "_fetch_quote", unexpected_fetch)
    with (tmp_path / "programming_excuses_pool.lock").open("a") as lock:
        excuses.flock(lock, excuses.LOCK_EX)
        assert excuses.run(Settings()).data == quote


def test_pixel_planet_returns_result():
    ensure_dirs()
    settings = Settings()
    fn = get_preprocessor("pixel_planet")
    result = fn(settings)
    assert result.status == AppStatus.NORMAL
    assert isinstance(result.data, str)


def test_pixel_planet_writes_json():
    ensure_dirs()
    settings = Settings()
    fn = get_preprocessor("pixel_planet")
    fn(settings)
    data_file = DATA_DIR / "pixel_planet.json"
    assert data_file.exists()
    data = json.loads(data_file.read_text())
    assert "image" in data


def test_spotify_skips_without_credentials():
    settings = Settings(spotify_client_id="", spotify_client_secret="")
    fn = get_preprocessor("spotify_now_playing")
    result = fn(settings)
    assert result.status == AppStatus.SKIP
