"""MQTT client — persistent connection to broker, stores last messages, handles notifications.

Runs as a background task inside the dashboard process. Two purposes:
1. phoenix/notify topic → notification queue → display interrupt
2. Arbitrary topic subscriptions → mqtt_messages table → panel data source
"""

import json
import logging
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Iterator

import paho.mqtt.client as mqtt

from phoenix.paths import PACKAGE_DIR
from phoenix.settings import Settings

logger = logging.getLogger(__name__)

MQTT_DB = PACKAGE_DIR / "phoenix.db"  # share the main DB

_MQTT_SCHEMA = """
CREATE TABLE IF NOT EXISTS mqtt_messages (
    topic TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    received_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    color TEXT NOT NULL DEFAULT '#FFFFFF',
    duration INTEGER NOT NULL DEFAULT 10,
    layout TEXT NOT NULL DEFAULT 'marquee',
    created_at REAL NOT NULL,
    displayed INTEGER NOT NULL DEFAULT 0
);
"""

_schema_initialized = False


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    global _schema_initialized
    conn = sqlite3.connect(str(MQTT_DB), timeout=10)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.row_factory = sqlite3.Row
        if not _schema_initialized:
            conn.executescript(_MQTT_SCHEMA)
            _schema_initialized = True
        yield conn
    finally:
        conn.close()


def store_message(topic: str, payload: str) -> None:
    """Store the last message for a topic."""
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO mqtt_messages (topic, payload, received_at) VALUES (?, ?, ?)",
            (topic, payload, time.time()),
        )
        conn.commit()


def get_message(topic: str) -> dict | None:
    """Get the last message for a topic. Returns parsed JSON or {"_raw": string}."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT payload, received_at FROM mqtt_messages WHERE topic = ?", (topic,)
        ).fetchone()
    if row is None:
        return None
    try:
        return json.loads(row["payload"])
    except (json.JSONDecodeError, TypeError):
        return {"_raw": row["payload"]}


def push_notification(text: str, color: str = "#FFFFFF", duration: int = 20, layout: str = "marquee") -> None:
    """Queue a notification for display."""
    with _connect() as conn:
        conn.execute(
            "INSERT INTO notifications (text, color, duration, layout, created_at) VALUES (?, ?, ?, ?, ?)",
            (text, color, duration, layout, time.time()),
        )
        conn.commit()
    logger.info("[notify] Queued: %s", text[:80])


def pop_notification() -> dict | None:
    """Get the next undisplayed notification, mark it as displayed."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM notifications WHERE displayed = 0 ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        conn.execute("UPDATE notifications SET displayed = 1 WHERE id = ?", (row["id"],))
        conn.commit()
        return {
            "id": row["id"],
            "text": row["text"],
            "color": row["color"],
            "duration": row["duration"],
            "layout": row["layout"],
        }


def list_notifications(limit: int = 20) -> list[dict]:
    """Get recent notifications for the dashboard."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM notifications ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [
            {
                "id": r["id"],
                "text": r["text"],
                "color": r["color"],
                "duration": r["duration"],
                "layout": r["layout"],
                "created_at": r["created_at"],
                "displayed": bool(r["displayed"]),
            }
            for r in rows
        ]


class MQTTClient:
    """Manages the persistent MQTT connection and topic subscriptions."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client: mqtt.Client | None = None
        self._subscribed_topics: set[str] = set()
        self._lock = threading.Lock()

    @property
    def connected(self) -> bool:
        return self._client is not None and self._client.is_connected()

    def start(self) -> None:
        """Start the MQTT client in a background thread."""
        if not self._settings.mqtt_broker:
            logger.info("[mqtt] No broker configured, MQTT disabled")
            return

        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect

        if self._settings.mqtt_tls:
            import ssl
            self._client.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS_CLIENT)

        if self._settings.mqtt_username:
            self._client.username_pw_set(
                self._settings.mqtt_username,
                self._settings.mqtt_password,
            )

        try:
            self._client.connect(
                self._settings.mqtt_broker,
                self._settings.mqtt_port,
            )
            self._client.loop_start()
            logger.info("[mqtt] Connecting to %s:%d", self._settings.mqtt_broker, self._settings.mqtt_port)
        except Exception:
            logger.exception("[mqtt] Failed to connect")

    def stop(self) -> None:
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()

    def subscribe(self, topic: str) -> None:
        """Subscribe to an additional topic (for panel data sources)."""
        with self._lock:
            if topic in self._subscribed_topics:
                return
            self._subscribed_topics.add(topic)
        if self._client and self._client.is_connected():
            self._client.subscribe(topic)
            logger.info("[mqtt] Subscribed to %s", topic)

    def _on_connect(self, client: mqtt.Client, userdata: object, flags: object, rc: object, properties: object = None) -> None:
        logger.info("[mqtt] Connected to broker")
        # Subscribe to notify topic
        notify_topic = self._settings.mqtt_notify_topic
        client.subscribe(notify_topic)
        self._subscribed_topics.add(notify_topic)
        logger.info("[mqtt] Subscribed to %s", notify_topic)

        # Re-subscribe to any panel topics
        with self._lock:
            for topic in self._subscribed_topics:
                client.subscribe(topic)

    def _on_message(self, client: mqtt.Client, userdata: object, msg: mqtt.MQTTMessage) -> None:
        payload = msg.payload.decode("utf-8", errors="replace")
        logger.debug("[mqtt] %s: %s", msg.topic, payload[:200])

        # Store last message for all topics
        store_message(msg.topic, payload)

        # Handle notifications
        if msg.topic == self._settings.mqtt_notify_topic:
            self._handle_notification(payload)

    def _on_disconnect(self, client: mqtt.Client, userdata: object, flags: object, rc: object, properties: object = None) -> None:
        if rc != 0:
            logger.warning("[mqtt] Unexpected disconnect (rc=%s), will reconnect", rc)

    def _handle_notification(self, payload: str) -> None:
        """Parse notification payload and queue it."""
        try:
            data = json.loads(payload)
            if isinstance(data, dict):
                push_notification(
                    text=data.get("text", payload),
                    color=data.get("color", "#FFFFFF"),
                    duration=data.get("duration", 10),
                    layout=data.get("layout", "marquee"),
                )
                return
        except json.JSONDecodeError:
            pass
        # Plain string message
        push_notification(text=payload)


# Singleton
_mqtt_client: MQTTClient | None = None


def get_mqtt_client(settings: Settings | None = None) -> MQTTClient:
    global _mqtt_client
    if _mqtt_client is None:
        _mqtt_client = MQTTClient(settings or Settings())
    return _mqtt_client
