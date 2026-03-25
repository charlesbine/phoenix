import json

from phoenix.models import AppStatus
from phoenix.paths import DATA_DIR, ensure_dirs
from phoenix.preprocessors import get_preprocessor
from phoenix.settings import Settings


def test_get_existing_preprocessor():
    fn = get_preprocessor("programming_excuses")
    assert fn is not None
    assert callable(fn)


def test_get_nonexistent_preprocessor():
    assert get_preprocessor("nonexistent_app_xyz") is None


def test_programming_excuses_returns_result(tmp_path, monkeypatch):
    ensure_dirs()
    settings = Settings()
    fn = get_preprocessor("programming_excuses")
    result = fn(settings)
    assert result.status == AppStatus.NORMAL
    assert isinstance(result.data, str)
    assert len(result.data) > 0


def test_programming_excuses_writes_json():
    ensure_dirs()
    settings = Settings()
    fn = get_preprocessor("programming_excuses")
    fn(settings)
    data_file = DATA_DIR / "programming_excuses.json"
    assert data_file.exists()
    data = json.loads(data_file.read_text())
    assert "excuse" in data


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
    fn = get_preprocessor("spotify")
    result = fn(settings)
    assert result.status == AppStatus.SKIP
