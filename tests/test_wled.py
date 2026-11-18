"""WLED DNRGB transport — verified against a local UDP loopback (fake panel)."""

import socket
import threading

from phoenix.display.wled import (
    DNRGB_PROTOCOL,
    MAX_LEDS_PER_PACKET,
    TOTAL_LEDS,
    send_dnrgb,
)


def _gradient_frame() -> bytes:
    """Deterministic 64x64 RGB frame where every pixel byte is distinct-ish."""
    return bytes((i * 7 + c * 53) % 256 for i in range(TOTAL_LEDS) for c in range(3))


def test_send_dnrgb_reassembles_full_frame() -> None:
    frame = _gradient_frame()
    assert len(frame) == TOTAL_LEDS * 3 == 12288

    recv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    recv.bind(("127.0.0.1", 0))
    recv.settimeout(3.0)
    port = recv.getsockname()[1]

    expected_packets = (TOTAL_LEDS + MAX_LEDS_PER_PACKET - 1) // MAX_LEDS_PER_PACKET
    buf = bytearray(TOTAL_LEDS * 3)
    got = {"packets": 0}

    def receiver() -> None:
        for _ in range(expected_packets):
            data, _ = recv.recvfrom(2048)
            assert data[0] == DNRGB_PROTOCOL
            offset = (data[2] << 8) | data[3]  # LED index this packet starts at
            payload = data[4:]
            buf[offset * 3 : offset * 3 + len(payload)] = payload
            got["packets"] += 1

    t = threading.Thread(target=receiver)
    t.start()

    send = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    send_dnrgb(send, "127.0.0.1", port, frame)
    t.join(timeout=4.0)

    assert expected_packets == 9  # 4096 LEDs / 480 per packet
    assert got["packets"] == expected_packets
    assert bytes(buf) == frame  # every pixel reassembled in the right place

    send.close()
    recv.close()


def test_backend_satisfies_frame_sink_protocol() -> None:
    from phoenix.display.sink import FrameSink
    from phoenix.display.wled import WLEDDisplayBackend

    # Same seam as SerialDisplayBackend / MatrixDisplayBackend — a FrameSink.
    for method in ("send_frame", "set_brightness", "clear", "close"):
        assert callable(getattr(WLEDDisplayBackend, method, None)), method
    # WLED is lossy → asks the player to re-send stills.
    assert WLEDDisplayBackend.still_refresh > 0
    assert issubclass(WLEDDisplayBackend, FrameSink)


def test_managed_wled_repairs_scheduled_brightness_after_panel_restart(tmp_path, monkeypatch):
    from unittest.mock import Mock

    import phoenix.db as db_module
    from phoenix.display import wled
    from phoenix.models import BrightnessSchedule

    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "devices.sqlite")
    db = db_module.DeviceDatabase()
    db.create("panel", "Panel", "wled")
    get = Mock(return_value=Mock(json=Mock(return_value={"on": True, "bri": 64})))
    post = Mock()
    monkeypatch.setattr(wled.httpx, "get", get)
    monkeypatch.setattr(wled.httpx, "post", post)
    clock = Mock(return_value=100.0)
    monkeypatch.setattr(wled.time, "monotonic", clock)

    backend = wled.WLEDDisplayBackend(device_id="panel", ip="127.0.0.1")
    try:
        backend.set_brightness(16)
        backend.set_brightness(16)
        assert post.call_count == 1
        get.assert_not_called()

        clock.return_value += wled.BRIGHTNESS_CHECK_INTERVAL
        backend.set_brightness(16)
        get.assert_called_once()
        assert post.call_count == 2
        assert post.call_args.kwargs["json"] == {"on": True, "bri": 16}

        db.set_brightness_schedule("panel", BrightnessSchedule(enabled=False))
        clock.return_value += wled.BRIGHTNESS_CHECK_INTERVAL
        backend.set_brightness(16)
        assert get.call_count == 1
        assert post.call_count == 2
    finally:
        backend.close()
