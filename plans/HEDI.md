# Hedi (HW-A) — Implementation Plan (v2, reduced hardware)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **v2 (2026-10-05):** the hardware scope changed. The bedside unit is now **ESP32 + 0.96" SSD1306 OLED + one servo + DS1307 RTC clock**:
> no vital-sign sensors, no RFID, no touch screen, no stepper, no IR. It is a **listener**. It receives the schedule and
> commands from the backend, shows them, turns the servo and sends acks back. It is developed in **Wokwi** (a virtual
> ESP32) and built **last**. The Python simulator becomes the source of all patient-side traffic (vitals, call-nurse,
> nurse taps, dose taken).

**Goal:**
1. The Python simulator that produces every device→server message the demo needs. It is the main deliverable, and it unblocks Wali and Faouzi.
2. The no-show model.
3. Last, the ESP32 listener (OLED + servo), developed in Wokwi and then flashed to the real board if time allows.

**Architecture:**
- **Simulator** (`simulator/`): pure payload builders (unit-tested with pytest) plus a CLI with scenarios. It runs in two modes:
  - standalone: it *is* the device
  - `--companion`: runs next to the ESP on the same `device_id` and fills in the messages the ESP can't produce
- **Firmware** (`firmware/`): hardware-free logic (schedule parsing, next dose, dose state machine) lives in `firmware/lib/` and is tested with `pio test -e native`. Thin modules live in `firmware/src/`: `net`, `ui` (OLED), `servo`, `schedule`, `clock`. `main.cpp` runs a cooperative loop.
- **Wokwi:** `firmware/diagram.json` (the virtual circuit) and `firmware/wokwi.toml` (points at the PlatformIO build output). The same code runs on the real board.

**Tech stack:**
- Python 3.12 + paho-mqtt 2 + pytest (simulator)
- ESP32 DevKit V1 with PlatformIO (Arduino), plus these libraries:

  | Library | Used for |
  |---|---|
  | Adafruit SSD1306 + Adafruit GFX | OLED |
  | ESP32Servo | Servo |
  | RTClib | DS1307 real-time clock |
  | PubSubClient | MQTT |
  | ArduinoJson 7 | JSON |
  | Preferences (NVS) | Storage that survives reboots |

- Wokwi for VS Code (the ESP32 simulator)
- scikit-learn offline only (no-show training)

**Read first:** `CLAUDE.md`, `docs/contracts/mqtt-topics.md` v1.1 (**your** contract; you are its device-side owner), `docs/architecture.md` §5, `firmware/PINMAP.md`.

**You are:** Hedi, HW-A, **Patient role owner**. In the demo:
- The schedule appears on the bedside OLED seconds after the doctor prescribes.
- At dose time, the OLED shows the reminder and the servo turns to the pill slot.
- The dose is marked taken, and the doctor view updates.
- Alerts and messages from the backend appear on the OLED.

## Global Constraints

- **The MQTT contract v1.0 stays frozen.** Topics, payload shapes, retained flags and QoS are unchanged.
  - The ESP and the simulator together must produce exactly what the contract describes.
  - The only proposed change is the `msg_id` rule (see below), and it needs Wali's 👍 before you rely on it.
- Payloads are JSON ≤ 1024 bytes; `ts` = epoch seconds UTC.
- Topics: `hospital/device/{device_id}/{vitals,events,status,schedule,command}`. `schedule` and `status` are retained.
- **Schedule times are local** (Africa/Tunis, UTC+1, no DST). The DS1307 keeps **UTC**; the ESP adds 60 minutes for display and dose matching.
- **Reminders must not depend on the server** (locked rule):
  - The schedule is stored in NVS, so a reboot or a broker outage keeps it.
  - Time comes from the **DS1307 RTC**, so a reboot with no Wi-Fi still knows the time.
  - NTP is only used to *set* the RTC: at boot, if Wi-Fi is up, sync NTP and write UTC to the RTC.
  - If the RTC isn't running (new module, dead coin cell) and there's no NTP, the clock is invalid: show "Syncing time…" and fire no doses.
- You own `firmware/` (PINMAP co-owned with Wali), `simulator/` and `backend/app/ai/no_show/`.
- No AI attribution in commits/PRs. Branches: `hedi/<feature>`. Conventional Commits.

## Who sends what (ESP + simulator split)

| Message | Standalone sim (no ESP) | ESP listener | Sim `--companion` (next to ESP) |
|---|---|---|---|
| `status` (retained, last-will) | ✅ | ✅ | ❌ (would overwrite the ESP's) |
| `vitals` | ✅ | ❌ | ✅ |
| `events/call_nurse`, `nurse_tap` | ✅ | ❌ | ✅ |
| `events/schedule_ack` | ✅ | ✅ | ❌ |
| `events/dose_dispensed` | ✅ (`dose_flow`) | ✅ (servo turned) | ❌ |
| `events/dose_taken {method:"button"}` | ✅ | ❌ (no button) | ✅, 5 s after it sees the ESP's `dose_dispensed` |
| `events/dose_missed` | ✅ (`dose_flow --miss`) | ✅ (30 min with no `dose_taken` seen) | ❌ |

To see `dose_taken`, the ESP **subscribes to its own `events` topic**.

## Contract change to propose: `msg_id` (mqtt-topics v1.1)

**Problem 1:** the server deduplicates on `(device_id, msg_id)`.
- In companion mode, the ESP and the simulator publish on the same `device_id` with separate counters, so their IDs collide and messages get dropped.
- A simulator restarted at `msg_id = 1` is also dropped as duplicates. That already happens with today's `sim.py`.

**Problem 2:** Wokwi wipes flash on every run, so "persist `msg_id` in NVS" doesn't survive restarts there.

**Proposal** (PR on `docs/contracts/mqtt-topics.md`, bump to 1.1, wait for Wali's 👍):
- `msg_id` must be **unique and increasing per publisher** instead of "+1, persisted in NVS".
- ESP: base = RTC epoch seconds at boot, +1 per message.
- Simulator: base = `2_000_000_000 + (now_epoch − 1_700_000_000)`, +1 per message.
- Both stay unique across restarts as long as each sends less than 1 message per second on average, which the ESP and the 5-s simulator do. The two ranges never meet before 2030, and both fit in `uint32`.

Until the 👍 arrives, run the simulator and the ESP on **different** `device_id`s (`bsu-001` ESP, `bsu-002` sim). Wali's seed must map both to a patient.

## Interfaces you PROVIDE

- **To Wali and Faouzi:** MQTT traffic per `mqtt-topics.md`. The simulator CLI is a contract with your teammates; keep the flags stable:

```
python simulator/sim.py --device bsu-001 --patient p-0001 [--host localhost] [--interval 5]
                        [--scenario normal|abnormal|call_nurse|nurse_tap|dose_flow|offline_replay]
                        [--companion] [--miss]
```

  - `normal`: normal vitals every `--interval` s
  - `abnormal`: after 3 normal readings, SpO2 88 / HR 130 / temp 38.6 (NEWS2 ≥ 7)
  - `call_nurse`: one `call_nurse` event, then normal vitals
  - `nurse_tap`: `nurse_tap {rfid_uid:"04A1B2C3"}`, then one vitals message with `nurse_rfid:"04A1B2C3"`, then normal vitals
  - `dose_flow`:
    - Obeys the received schedule plus `dispense_now`: `dose_dispensed`, then after 5 s `dose_taken {method:"button"}`.
    - With `--miss`, it sends `dose_missed` instead.
    - With `--companion`, it skips `dose_dispensed` and answers the ESP's `dose_dispensed`.
  - `offline_replay`: publishes 20 buffered vitals with past `ts` and increasing `msg_id`, then live data. It also sends 3 of the 20 twice, to exercise deduplication.
  - Without `--companion`, the simulator publishes retained `status` and replies `schedule_ack` to a new schedule. In every mode it prints any `command`.

- **To Faouzi/Wali (Day 1–2):** `backend/app/ai/no_show/` exposes

```python
def predict_no_show(features: dict) -> float          # 0..1; falls back to 0.20 on any error
def rank_backfill(candidates: list[dict]) -> list[dict]
    # candidates: {"appointment_id", "urgency": int, "no_show_prob": float, "created_at": str}
    # sort: urgency desc, no_show_prob asc, created_at asc
```

## Interfaces you CONSUME

- **From Wali:** the retained `schedule` and the `command` messages (from Day 2). Until then, publish them by hand with `mosquitto_pub`; see the mocks table below.
- **From Wali:** a seed where `bsu-001` (and `bsu-002` until the `msg_id` change lands) are assigned to a patient, plus nurse `u-0002` with RFID UID `04A1B2C3`.

## Mocks to use until the real thing is ready

| You need | Until | Use |
|---|---|---|
| Server schedule | Day 2 | `mosquitto_pub -h <laptop> -r -t hospital/device/bsu-001/schedule -f simulator/scenarios/schedule_example.json` |
| Commands | Day 2 | `mosquitto_pub -t hospital/device/bsu-001/command -m '{"type":"dispense_now","dose_id":"d-000123"}'` |
| See what you publish | always | `mosquitto_sub -h <laptop> -t 'hospital/#' -v` |

---

## Day 0 — Mon 10-05 (afternoon): Simulator v1 (unblocks the team today)

### Task 1: Pure payload builders + tests

**Files:**
- Create: `simulator/payloads.py`, `simulator/test_payloads.py`, `simulator/scenarios/schedule_example.json`
- Modify: `simulator/requirements.txt` (add `pytest`)

- [ ] **Step 1: Failing tests**

```python
# simulator/test_payloads.py
from payloads import vitals, event, MsgCounter, sim_msg_id_base, is_newer_schedule

def test_vitals_shape():
    c = MsgCounter(0)
    v = vitals(c, "p-0001", hr=80, spo2=98, temp=36.9)
    assert set(v) == {"msg_id", "ts", "patient_id", "hr", "spo2", "temp"}
    assert v["msg_id"] == 1 and isinstance(v["ts"], int)

def test_vitals_nurse_optional():
    v = vitals(MsgCounter(0), "p-0001", 80, 98, 36.9, nurse_rfid="04A1B2C3")
    assert v["nurse_rfid"] == "04A1B2C3"

def test_event_dose_taken():
    e = event(MsgCounter(0), "dose_taken", dose_id="d-000123", method="button")
    assert e["type"] == "dose_taken" and e["dose_id"] == "d-000123" and e["method"] == "button"

def test_msg_ids_increase():
    c = MsgCounter(0); a = vitals(c, "p", 1, 1, 1.0); b = event(c, "call_nurse")
    assert b["msg_id"] == a["msg_id"] + 1

def test_sim_base_is_above_esp_range_and_fits_uint32():
    base = sim_msg_id_base(now=1_759_680_000)
    assert base > 2_000_000_000 and base < 2**32

def test_schedule_version_filter():
    assert is_newer_schedule({"schedule_version": 3}, stored=2)
    assert not is_newer_schedule({"schedule_version": 3}, stored=3)
    assert not is_newer_schedule({"schedule_version": 1}, stored=3)
```

Run: `cd simulator && pip install -r requirements.txt && pytest -q`. Expected: FAIL (no module `payloads`).

- [ ] **Step 2: Implement `payloads.py`**

```python
# simulator/payloads.py
import time

class MsgCounter:
    def __init__(self, start: int):
        self.n = start
    def next(self) -> int:
        self.n += 1
        return self.n

def sim_msg_id_base(now: float | None = None) -> int:
    """Unique across restarts and disjoint from the ESP's epoch-based range (mqtt-topics v1.1 proposal)."""
    return 2_000_000_000 + int((now if now is not None else time.time()) - 1_700_000_000)

def vitals(c: MsgCounter, patient_id, hr, spo2, temp, nurse_rfid=None, ts=None) -> dict:
    p = {"msg_id": c.next(), "ts": int(ts if ts is not None else time.time()), "patient_id": patient_id,
         "hr": hr, "spo2": spo2, "temp": temp}
    if nurse_rfid:
        p["nurse_rfid"] = nurse_rfid
    return p

def event(c: MsgCounter, type_: str, ts=None, **extra) -> dict:
    return {"msg_id": c.next(), "ts": int(ts if ts is not None else time.time()), "type": type_, **extra}

def is_newer_schedule(schedule: dict, stored: int) -> bool:
    return int(schedule.get("schedule_version", 0)) > stored
```

- [ ] **Step 3:** `scenarios/schedule_example.json` is an exact copy of the `schedule` example in the contract. Tests pass. Commit `feat(simulator): payload builders`.

### Task 2: Scenarios, subscriptions, companion mode

**Files:** Modify `simulator/sim.py`

- [ ] Add `--scenario`, `--companion` and `--miss` per the CLI above. Start `MsgCounter(sim_msg_id_base())`.
- [ ] Subscribe to `{base}/schedule`, `{base}/command` and, in companion mode, `{base}/events`.
- [ ] On a schedule where `is_newer_schedule` is true, store it in memory. Unless in companion mode, also publish `schedule_ack`.
- [ ] `dispense_now` in `dose_flow` (standalone): publish `dose_dispensed`, wait 5 s (non-blocking, using a `threading.Timer`), then publish `dose_taken {method:"button"}`, or `dose_missed` with `--miss`.
- [ ] Companion mode:
  - On an ESP `dose_dispensed` event, wait 5 s, then publish `dose_taken {method:"button", dose_id}`. Skip it with `--miss`; the ESP then sends `dose_missed` after 30 min.
  - Ignore your own events (they carry a `msg_id` ≥ 2e9).
- [ ] `alert` / `message` commands: print them.
- [ ] Run each scenario against the compose broker and check with `mosquitto_sub -t 'hospital/#' -v`. Commit `feat(simulator): scenarios, schedule ack, dose flow, companion mode`.

**Day 0 done when:** Wali and Faouzi can run `python simulator/sim.py --scenario abnormal` and see the traffic. Then open the `msg_id` v1.1 contract PR and post it in the team chat.

---

## Day 1 — Tue 10-06: No-show model (moved earlier; the hardware lane is now small)

### Task 3: No-show model

**Files:**
- Create: `backend/app/ai/no_show/{__init__,model,train}.py`, `backend/app/ai/no_show/model.json`
- Test: `backend/tests/test_no_show.py`

- [ ] **Step 1:** Download the Kaggle "Medical Appointment No Shows" CSV (`KaggleV2-May-2016.csv`) to `backend/app/ai/no_show/data/`.
  - Add `backend/app/ai/no_show/data/` to `.gitignore`; the dataset licence forbids redistributing it.
- [ ] **Step 2:** `train.py` (offline; needs `pip install scikit-learn pandas`) trains a `LogisticRegression(max_iter=1000)`.
  - Features: `age`, `is_female`, `scholarship`, `hypertension`, `diabetes`, `alcoholism`, `handicap>0`, `sms_received`, `lead_days`, `weekday_0..6` (one-hot).
  - Print the ROC-AUC on a 20 % holdout. Expect about 0.6–0.7, and say so honestly.
  - Export `{"features": [...], "coef": [...], "intercept": x, "auc": y}` to `model.json`. **No scikit-learn at runtime.**
- [ ] **Step 3: Failing tests, then implement**

```python
# backend/tests/test_no_show.py
from app.ai.no_show import predict_no_show, rank_backfill

def test_predict_in_range():
    p = predict_no_show({"age": 30, "is_female": 1, "lead_days": 20, "sms_received": 1, "weekday": 0})
    assert 0.0 <= p <= 1.0

def test_predict_fallback_on_garbage():
    assert predict_no_show({"age": "abc"}) == 0.20

def test_rank_backfill():
    c = [{"appointment_id": "a-1", "urgency": 3, "no_show_prob": 0.1, "created_at": "2026-10-01T00:00:00Z"},
         {"appointment_id": "a-2", "urgency": 5, "no_show_prob": 0.4, "created_at": "2026-10-02T00:00:00Z"},
         {"appointment_id": "a-3", "urgency": 5, "no_show_prob": 0.2, "created_at": "2026-10-03T00:00:00Z"}]
    assert [x["appointment_id"] for x in rank_backfill(c)] == ["a-3", "a-2", "a-1"]
```

  - `model.py` loads `model.json` once and computes a sigmoid over the dot product.
  - Missing features default to 0. Any exception returns `0.20`.
- [ ] **Step 4:** Tell Faouzi it's ready. He calls `predict_no_show` in `POST /appointments/{id}/confirm` and `rank_backfill` in W2. Commit `feat(ai): no-show logistic model + backfill ranking`.

### Task 4: Wokwi setup + pure firmware logic (afternoon)

**Files:**
- Modify: `firmware/platformio.ini`
- Create: `firmware/diagram.json`, `firmware/wokwi.toml`, `firmware/lib/ward_schedule/ward_schedule.{h,cpp}`, `firmware/test/test_schedule/test_main.cpp`

- [ ] **`platformio.ini`:** replace the dropped libraries (MAX3010x, MLX90614, MFRC522, AccelStepper, TFT_eSPI, LVGL) with the ones below. Keep `adafruit/RTClib@^2.1`.
  - `adafruit/Adafruit SSD1306@^2.5`
  - `adafruit/Adafruit GFX Library@^1.11`
  - `madhephaestus/ESP32Servo@^3`

  Keep PubSubClient, ArduinoJson and the `native` env. Add `-DWOKWI=1` to a separate `[env:wokwi]` that extends `esp32dev`.
- [ ] **`diagram.json`:**
  - `board-esp32-devkit-c-v4`
  - `board-ssd1306` on I2C SDA 21 / SCL 22, address `0x3C`
  - `wokwi-servo` signal on GPIO 13, powered from 5 V
  - `wokwi-ds1307` on the same I2C bus (SDA 21 / SCL 22), address `0x68`

  `wokwi.toml` points `firmware`/`elf` at `.pio/build/wokwi/firmware.{bin,elf}`.
- [ ] **Networking in Wokwi:**
  - The virtual ESP joins Wi-Fi `Wokwi-GUEST` (open, no password).
  - To reach Mosquitto on your laptop, enable the Wokwi **private IoT gateway** and use MQTT host `host.wokwi.internal`.
  - **Verify this on Day 1.** If the gateway isn't available on your Wokwi licence, bridge to a public test broker for development only, and tell Wali.
- [ ] **Schedule logic, failing native tests first.** Keep the v1 API; it still fits:

```cpp
// firmware/test/test_schedule/test_main.cpp
#include <unity.h>
#include "ward_schedule.h"

static const char* J = R"({"schedule_version":3,"patient_id":"p-0001","patient_first_name":"Amira",
 "doses":[{"dose_id":"d-1","time":"08:00","meds":["Paracetamol 500mg"],"slot":1},
          {"dose_id":"d-2","time":"14:00","meds":["Amoxicillin 1g"],"slot":null}]})";

void test_parse() {
  Schedule s; TEST_ASSERT_TRUE(parse_schedule(J, s));
  TEST_ASSERT_EQUAL(3, s.version); TEST_ASSERT_EQUAL(2, s.n_doses);
  TEST_ASSERT_EQUAL(480, s.doses[0].minute_of_day); TEST_ASSERT_EQUAL(1, s.doses[0].slot);
  TEST_ASSERT_EQUAL(0, s.doses[1].slot);                       // null slot → 0 (no servo move)
  TEST_ASSERT_EQUAL_STRING("Amira", s.first_name);
}

void test_ignores_older_version() {
  Schedule s; parse_schedule(J, s);
  TEST_ASSERT_FALSE(should_accept(s, 3));
  TEST_ASSERT_FALSE(should_accept(s, 5));
  TEST_ASSERT_TRUE(should_accept(s, 2));
}

void test_next_dose_same_day() {
  Schedule s; parse_schedule(J, s);
  TEST_ASSERT_EQUAL(1, next_dose_index(s, 9 * 60));
}

void test_next_dose_wraps_midnight() {
  Schedule s; parse_schedule(J, s);
  TEST_ASSERT_EQUAL(0, next_dose_index(s, 23 * 60 + 50));
}

void test_unassigned() {
  Schedule s;
  TEST_ASSERT_TRUE(parse_schedule(R"({"schedule_version":4,"patient_id":null,"patient_first_name":"","doses":[]})", s));
  TEST_ASSERT_EQUAL(-1, next_dose_index(s, 600));
  TEST_ASSERT_FALSE(s.assigned);
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_parse); RUN_TEST(test_ignores_older_version); RUN_TEST(test_next_dose_same_day);
  RUN_TEST(test_next_dose_wraps_midnight); RUN_TEST(test_unassigned);
  return UNITY_END();
}
```

```cpp
// firmware/lib/ward_schedule/ward_schedule.h
#pragma once
#include <stdint.h>
constexpr int MAX_DOSES = 8;
struct Dose { char dose_id[16]; int minute_of_day; char meds[96]; int slot; };  // slot 0 = none
struct Schedule {
  int version = 0; bool assigned = false;
  char patient_id[16] = ""; char first_name[32] = "";
  Dose doses[MAX_DOSES]; int n_doses = 0;
};
bool parse_schedule(const char* json, Schedule& out);     // meds joined with ", "; null slot → 0
bool should_accept(const Schedule& incoming, int stored_version);  // incoming.version > stored
int  next_dose_index(const Schedule& s, int now_minute_local);     // -1 if none; >= now, else first (wrap)
```

- [ ] Run `pio test -e native -f test_schedule` (fail first, then green). Commit `feat(firmware): wokwi project + schedule logic`.

**Day 1 done when:** the no-show tests pass, Faouzi has the functions, a blank sketch boots in Wokwi with the OLED showing "Medora", and `pio test -e native` is green.

---

## Day 2 — Wed 10-07: ESP listener in Wokwi (built last, after the simulator and model)

### Task 5: Dose state machine (pure logic)

**Files:** Create `firmware/lib/ward_dose/ward_dose.{h,cpp}`, `firmware/test/test_dose/test_main.cpp`

- [ ] **Step 1: Failing native tests**

```cpp
// firmware/test/test_dose/test_main.cpp
#include <unity.h>
#include "ward_dose.h"

void test_dispense_then_taken() {
  DoseFsm f; f.start("d-1", /*now*/1000, /*slot*/1);
  TEST_ASSERT_EQUAL(DoseOut::Dispensed, f.tick(1000));      // caller turns the servo
  TEST_ASSERT_EQUAL(DoseOut::None,      f.tick(1010));
  TEST_ASSERT_EQUAL(DoseOut::Taken,     f.on_taken("d-1", 1015));
  TEST_ASSERT_FALSE(f.active());
}

void test_no_slot_reminds_without_dispense() {
  DoseFsm f; f.start("d-1", 1000, 0);
  TEST_ASSERT_EQUAL(DoseOut::None,  f.tick(1000));          // reminder only, no dose_dispensed
  TEST_ASSERT_EQUAL(DoseOut::Taken, f.on_taken("d-1", 1005));
}

void test_taken_for_other_dose_ignored() {
  DoseFsm f; f.start("d-1", 1000, 1); f.tick(1000);
  TEST_ASSERT_EQUAL(DoseOut::None, f.on_taken("d-9", 1005));
  TEST_ASSERT_TRUE(f.active());
}

void test_missed_after_30_min() {
  DoseFsm f; f.start("d-1", 1000, 1); f.tick(1000);
  TEST_ASSERT_EQUAL(DoseOut::None,   f.tick(1000 + 1799));
  TEST_ASSERT_EQUAL(DoseOut::Missed, f.tick(1000 + 1800));
  TEST_ASSERT_FALSE(f.active());
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_dispense_then_taken); RUN_TEST(test_no_slot_reminds_without_dispense);
  RUN_TEST(test_taken_for_other_dose_ignored); RUN_TEST(test_missed_after_30_min);
  return UNITY_END();
}
```

- [ ] **Step 2: Implement `DoseFsm`.**
  - States: `Idle → Reminding → Done`.
  - With `slot > 0`, the first `tick` returns `Dispensed`.
  - `on_taken(dose_id, now)` returns `Taken` only for the active dose.
  - `now - start >= 1800` → `Missed`.
  - Expose `const char* dose_id()`, `int slot()` and `bool active()`. Tests green → commit `feat(firmware): dose state machine`.

### Task 6: Device modules + main loop

**Files:** Create `firmware/src/{net,ui,servo,schedule,clock}.{h,cpp}`; modify `firmware/src/main.cpp`, `firmware/include/secrets.h.example`

- [ ] **`clock.cpp`:**
  - `clock_init()`:
    - start `RTC_DS1307` (RTClib)
    - if Wi-Fi is up, `configTime(0, 0, "pool.ntp.org")`; once synced, `rtc.adjust()` with the UTC time
  - API: `bool clock_valid()` (RTC running, year ≥ 2026), `uint32_t clock_utc()` (from the RTC), `int clock_local_minute()` (= (UTC + 60 min) mod 1440).
  - Until the clock is valid, show "Syncing time…" and fire no doses.
  - **Verify on Day 1:** what time the Wokwi DS1307 starts with (it may start at the host's time, which is local, not UTC). If it isn't UTC, rely on the NTP write.
- [ ] **`net.cpp`:** Wi-Fi with reconnect backoff, PubSubClient with `setBufferSize(1280)`, client ID `ward-dev-{device_id}`.
  - Last-will: `status` = `{"online":false,"fw_version":...}`, retained, QoS 1.
  - On connect:
    1. publish the retained `status` online with `ip`
    2. subscribe to `schedule`, `command` and the device's own `events`
  - `net_publish(kind, doc)` adds `msg_id` (epoch base, per the v1.1 proposal) and `ts`. If offline, it keeps up to **8 pending events** in a small RAM queue and sends them on reconnect. The ESP sends few messages, so the 128-entry buffer is no longer needed.
  - API:

```cpp
void net_init();                     // uses secrets.h
void net_loop();                     // call every loop
bool net_online();
void net_publish(const char* kind, JsonDocument& doc); // adds msg_id + ts; queues (max 8) when offline
void net_on_schedule(void (*cb)(const char* json));
void net_on_command(void (*cb)(const char* json));
void net_on_event(void (*cb)(const char* json));      // own events topic, used to see dose_taken
```

- [ ] **`schedule.cpp`:**
  - When `should_accept` is true: save the raw JSON to NVS (namespace `ward`, key `sched`) and the version to key `sver`, then publish `schedule_ack`.
  - Also store `acked_ver`. If the ack couldn't be sent, re-send it on the next connect, even though the retained re-delivery has the same version.
  - Load the schedule from NVS on boot.
- [ ] **`ui.cpp`** (SSD1306 128×64, Adafruit GFX):

```cpp
void ui_init();
void ui_tick();                                              // call every loop (toast/banner timeouts)
void ui_show_home(const char* first_name, const char* clock_hhmm, const char* next_dose, bool online);
void ui_show_dose(const char* meds, const char* time_hhmm);  // big "TAKE NOW" + meds, blinking
void ui_show_status(const char* text);                       // e.g. "Syncing time…", "Not assigned"
void ui_toast(const char* text, uint32_t ms);                // command type=message
void ui_banner_alert(const char* text, uint32_t ms);         // command type=alert, inverted screen
```

  128×64 is small: text size 2 for the clock and "TAKE NOW", size 1 elsewhere. Long meds text scrolls.
- [ ] **`servo.cpp`:**
  - `servo_go_to(int slot)` with `SLOT_ANGLES[] = {0, 45, 90, 135, 180}` (slot 0 = home, slots 1–4).
  - `servo_home()`.
  - Detach after each move to stop jitter. Slots > 4 → no move, reminder only.
- [ ] **`main.cpp` wiring:**
  - **Every loop:** `net_loop()`, `ui_tick()`, then the FSM `tick(clock_utc())`.
  - **Every minute:** if `next_dose_index` matches `clock_local_minute()` and the FSM is idle:
    - call `start()` and `ui_show_dose`
    - on `Dispensed`, call `servo_go_to(slot)` and publish `dose_dispensed`
  - **Own `events` topic:** a `dose_taken` message calls `fsm.on_taken`. On `Taken`, call `servo_home()` and show the home screen.
  - **On `Missed`:** publish `dose_missed` and call `servo_home()`.
  - **Commands:**

    | Command | Action |
    |---|---|
    | `dispense_now {dose_id}` | Start the FSM now with that dose's slot |
    | `rotate_home` | `servo_home()` |
    | `alert` | `ui_banner_alert(text, 5000)` |
    | `message` | `ui_toast(text, 4000)` |
- [ ] **Wokwi check:**
  - Run the ESP in Wokwi (`bsu-001`) and `python simulator/sim.py --device bsu-001 --scenario dose_flow --companion`.
  - Publish the example schedule and then `dispense_now`. Expect: the OLED shows the dose, the servo turns to slot 1, `dose_dispensed` arrives, then the sim's `dose_taken`, the servo returns home, and the home screen comes back.
  - Commit `feat(firmware): oled listener, servo dispense, mqtt acks`.

**Day 2 done when:** CP2 passes using Wokwi.
- Faouzi prescribes in the doctor view.
- The Wokwi OLED shows the schedule within 5 s and `schedule_ack` arrives.
- `dispense_now` turns the servo, `dose_taken` comes back, and the doctor view updates.
- An `alert` command shows the banner.

---

## Day 3 — Thu 10-08 (integration)

### Task 7: Golden path as the Patient owner

- [ ] Run the patient part of the golden path (Wokwi ESP + companion simulator) twice by 13:00 (CP3), and fix only blockers.
- [ ] Nurse segment support: `--scenario nurse_tap` and `--scenario abnormal` drive Wali's alert flow. Rehearse the timing with him.
- [ ] **Offline reboot check:** load a schedule, reboot the ESP with the broker unreachable, and wait for a dose minute. The RTC still knows the time. The reminder and the servo still fire. `dose_dispensed` / `dose_missed` are queued and sent on reconnect.

### Task 8: Real board (only if the path is green)

- [ ] Flash the same code to the real ESP32 (`pio run -e esp32dev -t upload`) with a real SSD1306, a servo (SG90 on 5 V, shared ground; signal GPIO 13) and an RTC module on I2C. A DS1307 or a DS3231 both work with RTClib; for a DS3231, swap `RTC_DS1307` for `RTC_DS3231`.
- [ ] Update `firmware/PINMAP.md` to v1.0 for the new parts, signed with Wali.
- [ ] If the real board fails, the demo uses the Wokwi device on the projector. The events are identical.

## Day 4 — Fri 10-09 (polish)

- [ ] OLED polish: a greeting ("Sbah el khir, Amira"), clearer icons for online, offline and time not synced.
- [ ] A 30-minute soak test (Wokwi or real) with MQTT; no reboot.
- [ ] Record the device (or the Wokwi screen) for the backup video.
- [ ] Rehearse your demo segment (Care, ~60 s) three times.

## Docs updated for v2 (same PR as this plan)

`CLAUDE.md`, `README.md`, `TEAM_PLAN.md`, `docs/architecture.md`, `docs/contracts/mqtt-topics.md` (v1.1),
`firmware/PINMAP.md` (v0.2), `hardware/README.md`, `plans/WALI.md` and an amendment note on the foundation spec.
Most of these are owned by Faouzi or Wali: **tag them on the PR**, and get Wali's 👍 on the contract.

Not touched, because they have unmerged edits on Faouzi's branches (avoid conflicts; tell Faouzi):
- `docs/contracts/data-model.md`: `med_doses.slot` comment "carousel slot" → "servo slot 1..4".
- `docs/contracts/api.md`: the `dose_event.method` enum keeps `ir|button` (still valid).
- `plans/FAOUZI.md`: the pitch "honesty slide" should say vitals are simulated.

## Self-review checklist (run before each PR)

- [ ] Every published payload matches `docs/contracts/mqtt-topics.md`, compared field by field against `mosquitto_sub` output.
- [ ] `pytest -q` in `simulator/` and `backend/` green; `pio test -e native` green; `pio run` builds without warnings in your modules.
- [ ] `secrets.h` is not committed.
