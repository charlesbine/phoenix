from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess

import pytest

from phoenix import shop


def test_catalog_retries_failed_clone_and_only_clones_once_for_concurrent_reads(tmp_path, monkeypatch):
    calls = []
    catalog = tmp_path / "community"

    def git(command, **kwargs):
        calls.append(command[:2])
        if command[1] == "clone":
            checkout = Path(command[-1])
            (checkout / ".git").mkdir(parents=True)
            if len(calls) == 1:
                raise subprocess.CalledProcessError(1, command)
            app = checkout / "apps" / "clock"
            app.mkdir(parents=True)
            (app / "manifest.yaml").write_text("id: clock\ncategory: time\n")

    monkeypatch.setattr(shop.subprocess, "run", git)
    with pytest.raises(subprocess.CalledProcessError):
        shop.ensure_repo(catalog, refresh=False)
    assert not catalog.exists()
    assert list(tmp_path.iterdir()) == []

    with ThreadPoolExecutor(max_workers=2) as workers:
        list(workers.map(lambda _: shop.ensure_repo(catalog, refresh=False), range(2)))
    assert calls == [["git", "clone"], ["git", "clone"]]
    assert [app.name for app in shop.search_apps(catalog)] == ["clock"]
    assert shop.list_categories(catalog) == ["time"]

    shop.ensure_repo(catalog, refresh=True)
    assert calls[-1] == ["git", "pull"]
