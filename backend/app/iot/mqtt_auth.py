"""Broker login shared by the three server-side MQTT clients (worker, publisher, relay).
The account and its ACL live in infra/mosquitto (see docs/contracts/mqtt-topics.md, "Broker")."""

import logging

from app.config import Settings, get_settings

log = logging.getLogger("medora.mqtt")


def apply_credentials(client, settings: Settings | None = None) -> None:
    s = settings or get_settings()
    client.username_pw_set(s.mqtt_username, s.mqtt_password)


def connack_ok(reason_code, who: str) -> bool:
    """False (and one error line) when the broker refused the login, e.g. 'Not authorized'."""
    if getattr(reason_code, "is_failure", False):
        log.error("%s: broker refused the connection (%s); check MQTT_USERNAME / MQTT_PASSWORD "
                  "against MQTT_BACKEND_USERNAME / MQTT_BACKEND_PASSWORD", who, reason_code)
        return False
    return True
