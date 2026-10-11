"""MQTT ingestion worker (owner: Wali). Run with `python -m app.iot.worker`.

Subscribes to hospital/device/+/{vitals,events,status} (mqtt-topics.md), hands each message to
`ingest.handle` in its own transaction, commits, then relays the resulting frames on `ward/internal/ws`.
A bad message is logged and dropped; it never stops the loop.
"""

import json
import logging
import threading
import time

import paho.mqtt.client as mqtt
from sqlalchemy import inspect

from app.config import get_settings
from app.db import SessionLocal, engine
from app.iot import ingest, mqtt_auth, publisher
from app.services import radiology as radiology_jobs

log = logging.getLogger("ward.worker")
TOPICS = [("hospital/device/+/vitals", 1), ("hospital/device/+/events", 1), ("hospital/device/+/status", 1)]


def schema_ready(eng=engine) -> bool:
    """True once the api container's `alembic upgrade head` has created the tables we write to."""
    try:
        insp = inspect(eng)
        return all(insp.has_table(t) for t in ("ingested_messages", "vitals", "devices"))
    except Exception:
        return False


def parse_topic(topic: str) -> tuple[str, str] | None:
    parts = topic.split("/")
    if len(parts) == 4 and parts[0] == "hospital" and parts[1] == "device":
        return parts[2], parts[3]
    return None


def process(device_id: str, kind: str, raw: bytes) -> list[dict]:
    try:
        payload = json.loads(raw)
    except ValueError:  # includes UnicodeDecodeError
        log.warning("non-JSON %s from %s dropped", kind, device_id)
        return []
    with SessionLocal() as db:
        try:
            frames = ingest.handle(db, device_id, kind, payload)
            db.commit()
        except Exception:
            db.rollback()
            log.exception("ingest %s from %s failed", kind, device_id)
            return []
    for f in frames:
        publisher.publish_ws_frame(f)
    return frames


def on_connect(client, userdata, flags, reason_code, properties):
    if not mqtt_auth.connack_ok(reason_code, "ward-worker"):
        return  # paho retries; the error is already logged
    log.info("connected to broker (%s); subscribing", reason_code)
    client.subscribe(TOPICS)


def on_message(client, userdata, msg):
    parsed = parse_topic(msg.topic)
    if parsed:
        process(*parsed, msg.payload)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    s = get_settings()
    while not schema_ready():  # on a fresh volume, retained status would arrive before the migration
        log.info("waiting for the database schema (api runs the migrations)")
        time.sleep(2)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="ward-worker")
    mqtt_auth.apply_credentials(client, s)
    client.on_connect = on_connect
    client.on_message = on_message
    publisher.use(client)
    threading.Thread(target=radiology_jobs.run_forever, args=(threading.Event(),), daemon=True,
                     name="radiograph-jobs").start()
    while True:
        try:
            client.connect(s.mqtt_host, s.mqtt_port)
            break
        except OSError as e:
            log.warning("broker not reachable (%s), retrying in 2 s", e)
            time.sleep(2)
    client.loop_forever(retry_first_connection=True)


if __name__ == "__main__":
    main()
