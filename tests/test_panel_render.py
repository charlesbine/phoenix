"""Tests for the pure-Python Pillow dashboard panel renderer and new optional panel fields."""

from __future__ import annotations

from PIL import Image

from phoenix.panel_render import (
    parse_hex_color,
    render_panel_frames,
    render_panel_to_files,
)
from phoenix.preprocessors.dashboard_panel import _build_panel_data


def _has_non_black_pixels(img: Image.Image) -> bool:
    return any(px != (0, 0, 0) for px in img.get_flattened_data())


class TestPanelRendererLayouts:
    def test_big_number_legacy_and_enhanced(self, tmp_path):
        # Legacy minimal config (backwards compatibility)
        legacy = {"layout": "big_number", "title": "REVENUE", "value": "$4.8k"}
        frames, durations = render_panel_frames(legacy)
        assert len(frames) == 1
        assert durations == [1000]
        assert frames[0].size == (64, 64)
        assert _has_non_black_pixels(frames[0])

        # Enhanced config with unit, delta pill, and progress bar
        enhanced = {
            "layout": "big_number",
            "title": "ACTIVE USERS",
            "value": "12.4",
            "unit": "k",
            "delta": "+18.6%",
            "progress": 78,
            "color": "#FFF2CF",
            "accent_color": "#FF8E3C",
        }
        out = tmp_path / "kpi.webp"
        out_large = tmp_path / "kpi.large.webp"
        render_panel_to_files(enhanced, out, out_large, magnification=8)
        assert out.exists() and out_large.exists()
        with Image.open(out) as im_small, Image.open(out_large) as im_large:
            assert im_small.size == (64, 64)
            assert im_large.size == (512, 512)

    def test_sparkline_positive_negative_and_empty(self):
        # Positive series with delta, subtitle, and shaded fill
        frames, _ = render_panel_frames(
            {
                "layout": "sparkline",
                "title": "API P95",
                "value": "42ms",
                "delta": "-14%",
                "delta_color": "#2EE58D",
                "subtitle": "24H",
                "color": "#5BCEFA",
                "fill": True,
                "points": [64, 58, 61, 55, 49, 52, 47, 42],
            }
        )
        assert len(frames) == 1
        assert frames[0].size == (64, 64)
        assert _has_non_black_pixels(frames[0])

        # Series crossing below zero + single-point series
        neg_frames, _ = render_panel_frames(
            {"layout": "sparkline", "title": "DELTA", "points": [-5, -2, 0, 3, -1]}
        )
        assert neg_frames[0].size == (64, 64)

        single_frames, _ = render_panel_frames(
            {"layout": "sparkline", "points": [42.0], "fill": False, "show_minmax": False}
        )
        assert single_frames[0].size == (64, 64)

        # Empty points falls back gracefully to error card
        empty_frames, _ = render_panel_frames({"layout": "sparkline", "points": []})
        assert empty_frames[0].size == (64, 64)
        assert _has_non_black_pixels(empty_frames[0])

    def test_multi_stat_1_to_4_tiles_and_empty(self):
        for count in (1, 2, 3, 4):
            stats = [{"label": f"S{i}", "value": f"{i * 15}%"} for i in range(1, count + 1)]
            frames, _ = render_panel_frames({"layout": "multi_stat", "title": "HOMELAB", "stats": stats})
            assert len(frames) == 1
            assert frames[0].size == (64, 64)
            assert _has_non_black_pixels(frames[0])

        empty_frames, _ = render_panel_frames({"layout": "multi_stat", "stats": []})
        assert empty_frames[0].size == (64, 64)

    def test_key_value_banded_rows_with_and_without_colors(self):
        frames, _ = render_panel_frames(
            {
                "layout": "key_value",
                "title": "CLIMATE",
                "items": [
                    {"key": "Living", "value": "22° 44%", "color": "#2EE58D"},
                    {"key": "Office", "value": "23° 41%", "color": "#5BCEFA"},
                    {"key": "Bedrm", "value": "19° 48%"},
                    {"key": "Studio", "value": "21° 45%"},
                    {"key": "Garage", "value": "15° 52%"},
                ],
            }
        )
        assert len(frames) == 1
        assert frames[0].size == (64, 64)
        assert _has_non_black_pixels(frames[0])

    def test_marquee_static_vs_animated_scrolling(self, tmp_path):
        # Short message renders as single static frame
        short_frames, short_durs = render_panel_frames(
            {"layout": "marquee", "title": "STATUS", "text": "OK", "color": "#2EE58D"}
        )
        assert len(short_frames) == 1
        assert len(short_durs) == 1

        # Long message renders as multi-frame animated WebP
        long_data = {
            "layout": "marquee",
            "title": "DEPLOY FEED",
            "text": "v2.4.1 LIVE · ALL REGIONS GREEN",
            "subtitle": "PROD CLUSTER",
            "color": "#FFD98A",
        }
        long_frames, long_durs = render_panel_frames(long_data)
        assert len(long_frames) > 5
        assert len(long_frames) == len(long_durs)

        out = tmp_path / "marquee.webp"
        out_large = tmp_path / "marquee.large.webp"
        render_panel_to_files(long_data, out, out_large, magnification=4)
        with Image.open(out) as im_small, Image.open(out_large) as im_large:
            assert getattr(im_small, "is_animated", False) is True
            assert getattr(im_large, "is_animated", False) is True
            assert im_small.size == (64, 64)
            assert im_large.size == (256, 256)

    def test_malformed_inputs_and_unknown_layout_never_crash(self):
        assert parse_hex_color("not-a-color", (1, 2, 3)) == (1, 2, 3)
        assert parse_hex_color("#0f8", (0, 0, 0)) == (0, 255, 136)

        frames, _ = render_panel_frames({"layout": "unknown_xyz", "color": "bad"})
        assert frames[0].size == (64, 64)

        long_frames, _ = render_panel_frames(
            {
                "layout": "big_number",
                "title": "VERY LONG TITLE THAT EXCEEDS WIDTH",
                "value": "123456789012345",
                "progress": "not-a-number",
            }
        )
        assert long_frames[0].size == (64, 64)


class TestBuildPanelDataBackwardsCompatAndNewFields:
    def test_big_number_extracts_optional_delta_subtitle_and_progress(self):
        panel = {
            "layout": "big_number",
            "title": "ACTIVE USERS",
            "config": {"unit": "k", "accent_color": "#FF8E3C"},
            "data_source": {
                "type": "http",
                "mappings": {
                    "value": "metrics.users",
                    "transform": "/ 1000 | round 1",
                    "delta": "metrics.delta",
                    "subtitle": "metrics.window",
                    "progress": "metrics.goal_pct",
                },
            },
        }
        fetched = {"metrics": {"users": 12400, "delta": "+18.6%", "window": "TODAY", "goal_pct": 78}}
        data = _build_panel_data(panel, fetched)
        assert data["value"] == "12.4"
        assert data["unit"] == "k"
        assert data["delta"] == "+18.6%"
        assert data["subtitle"] == "TODAY"
        assert data["progress"] == 78.0
        assert data["accent_color"] == "#FF8E3C"

    def test_sparkline_and_key_value_preserve_legacy_and_pass_new_options(self):
        spark_panel = {
            "layout": "sparkline",
            "title": "API P95",
            "config": {"unit": "ms", "subtitle": "24H", "delta": "-14%", "show_minmax": False},
            "data_source": {
                "type": "http",
                "mappings": {"points": "series", "value": "current"},
            },
        }
        spark_data = _build_panel_data(spark_panel, {"series": [50, 45, 42], "current": 42})
        assert spark_data["points"] == [50.0, 45.0, 42.0]
        assert spark_data["value"] == "42"
        assert spark_data["unit"] == "ms"
        assert spark_data["delta"] == "-14%"
        assert spark_data["subtitle"] == "24H"
        assert spark_data["show_minmax"] is False

        kv_panel = {
            "layout": "key_value",
            "title": "CLIMATE",
            "config": {},
            "data_source": {
                "type": "http",
                "mappings": {
                    "items": [{"key": "Living", "value_path": "temp", "unit": "°", "color": "#2EE58D"}]
                },
            },
        }
        kv_data = _build_panel_data(kv_panel, {"temp": 22})
        assert kv_data["items"] == [{"key": "Living", "value": "22°", "color": "#2EE58D"}]

    def test_preview_endpoint_renders_webp_without_pixlet(self, tmp_path, monkeypatch):
        from fastapi.testclient import TestClient

        from phoenix import paths
        from phoenix.server import dashboard

        monkeypatch.setattr(paths, "DATA_DIR", tmp_path / "data")
        monkeypatch.setattr(paths, "OUTPUTS_DIR", tmp_path / "data" / "output")
        monkeypatch.setattr(paths, "DB_PATH", tmp_path / "phoenix.db")
        monkeypatch.setenv("PHOENIX_DB_PATH", str(tmp_path / "phoenix.db"))

        # Make sure paths inside render/dashboard point to tmp_path
        import phoenix.db as db_mod

        monkeypatch.setattr(db_mod, "DB_PATH", tmp_path / "phoenix.db")

        app = dashboard.create_app()
        client = TestClient(app)
        res = client.post(
            "/api/panels/preview",
            json={
                "layout": "sparkline",
                "title": "API P95",
                "config": {"points": [60, 52, 48, 42], "value": "42ms", "delta": "-14%"},
                "data_source": {"type": "static"},
            },
        )
        assert res.status_code == 200
        body = res.json()
        assert "preview_url" in body
        assert body["preview_url"].startswith("/static/outputs/panel__preview.large.webp?t=")
        rendered = paths.output_path_large("panel__preview")
        assert rendered.exists()
        with Image.open(rendered) as im:
            assert im.size[0] >= 64 and im.size[1] >= 64
