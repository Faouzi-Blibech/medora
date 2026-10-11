"""API side of the worker → API relay: subscribe to `ward/internal/ws` and hand frames to the hub."""

import json
import logging
import os

import paho.mqtt.client as mqtt

from app.config import get_settings
from app.iot import mqtt_auth
from app.iot.publisher import WS_TOPIC
from app.ws.hub import hub

log = logging.getLogger("medora.relay")


def start():
    s = get_settings()
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"ward-api-relay-{os.getpid()}")

    def on_connect(client, userdata, flags, reason_code, properties):
        if not mqtt_auth.connack_ok(reason_code, "ward-api-relay"):
            return
        client.subscribe(WS_TOPIC, qos=0)

    def on_message(client, userdata, msg):
        try:
            hub.broadcast(json.loads(msg.payload))
        except Exception as e:
            log.warning("bad relay frame: %s", e)

    mqtt_auth.apply_credentials(c, s)
    c.on_connect = on_connect
    c.on_message = on_message
    c.connect_async(s.mqtt_host, s.mqtt_port)
    c.loop_start()  # paho reconnects by itself if the broker isn't up yet
    return c
