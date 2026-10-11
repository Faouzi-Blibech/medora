"""Medora device simulator (owner: Hedi). Speaks docs/contracts/mqtt-topics.md v1.0.

Scaffold: publishes retained online status (with last-will) and normal vitals every few seconds.
Events, schedule subscription and scenarios are added on top of this.

    python sim.py --device bsu-001 --patient p-0001 --host localhost
"""

import argparse
import json
import os
import random
import time

import paho.mqtt.client as mqtt

FW_VERSION = "sim-0.1.0"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="bsu-001")
    ap.add_argument("--patient", default="p-0001")
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--interval", type=float, default=5.0)
    # broker login (mqtt-topics.md "Broker"): username = device id; the demo password is change-me-<device id>
    ap.add_argument("--username", default=os.environ.get("MQTT_USERNAME"), help="default: the device id")
    ap.add_argument("--password", default=os.environ.get("MQTT_PASSWORD"), help="default: change-me-<device id>")
    args = ap.parse_args()

    base = f"hospital/device/{args.device}"
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"ward-sim-{args.device}")
    client.username_pw_set(args.username or args.device, args.password or f"change-me-{args.device}")

    def on_connect(c, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"broker refused the login ({reason_code}); check --username/--password", flush=True)

    client.on_connect = on_connect
    client.will_set(f"{base}/status", json.dumps({"online": False, "fw_version": FW_VERSION}), qos=1, retain=True)
    client.connect(args.host, args.port)
    client.loop_start()
    client.publish(f"{base}/status", json.dumps({"online": True, "fw_version": FW_VERSION, "ip": "sim"}),
                   qos=1, retain=True)

    msg_id = 0
    try:
        while True:
            msg_id += 1
            vitals = {
                "msg_id": msg_id,
                "ts": int(time.time()),
                "patient_id": args.patient,
                "hr": random.randint(68, 88),
                "spo2": random.randint(96, 99),
                "temp": round(random.uniform(36.5, 37.3), 1),
            }
            client.publish(f"{base}/vitals", json.dumps(vitals), qos=1)
            print("vitals", vitals, flush=True)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        client.publish(f"{base}/status", json.dumps({"online": False, "fw_version": FW_VERSION}), qos=1,
                       retain=True)
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
