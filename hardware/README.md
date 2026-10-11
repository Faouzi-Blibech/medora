# Hardware (owner: Wali)

Two devices:
1. **Smart Bedside Unit** (`bsu-001`…): the patient-side listener. It is built, in Wokwi.
2. **Nurse Wrist Pager** (`pgr-001`…): a smartwatch-style alert receiver for nurses. It is a proposal; see
   [Nurse Wrist Pager](#nurse-wrist-pager-proposal) below.

## Smart Bedside Unit

The bedside unit is a **listener**: it receives the medication schedule and commands over MQTT, shows them on an OLED,
and turns a servo to the dose's pill slot. It has **no vital-sign sensors**; vitals, nurse taps and call-nurse come
from `simulator/`. It is developed in **Wokwi** (`firmware/diagram.json`) and built on a real board last, if time allows.
The pin map lives in `firmware/PINMAP.md`.

### Bill of materials

| Part | Qty | Interface | Have? | Notes |
|---|---|---|---|---|
| ESP32 DevKit V1 | 1 (+1 spare) | — | ☐ | |
| 0.96" SSD1306 OLED 128×64 | 1 | I2C 0x3C | ☐ | |
| DS1307 RTC module + coin cell | 1 | I2C 0x68 | ☐ | a DS3231 also works (one-line firmware change) |
| SG90 micro servo | 1 | GPIO 13 (PWM) | ☐ | 5 V rail |
| Small pill holder (4 compartments on a disc or arc) | 1 | — | ☐ | cardboard / foam-board build on the servo horn |
| 5 V 1 A+ USB supply + cable | 1 | — | ☐ | |
| Breadboard, jumpers | — | — | ☐ | |

Wokwi needs none of these. Tick the boxes on Day 0 only if the real board is planned.

### Servo dispenser

- The servo horn carries a disc or arc with up to **4 pill compartments**.
- Slot angles: slot 0 = 0° (home), 1 = 45°, 2 = 90°, 3 = 135°, 4 = 180°. A fixed opening over the arc shows the active compartment.
- `rotate_home` sends it back to 0°. The firmware detaches the servo after each move to stop jitter.
- A dose with `slot: null` is reminder-only (no move).

---

## Nurse Wrist Pager (proposal)

> **Status:** proposal, not on the golden demo path yet. Build it only after the path works.
> Before writing firmware, bump `docs/contracts/mqtt-topics.md` to v1.2 with the `hospital/pager/` topics below, and
> add the firmware folder (`pager/`, proposed owner Wali).

### Why

At night a Tunisian ward often has one nurse for many beds and nobody at the nurse station. Alerts on the web
dashboard only help if someone is looking at a screen. The pager **vibrates on the nurse's wrist**, shows the bed and
the reason, and lets the nurse **accept the task on the screen**. Accepting is the same human confirmation as
`POST /alerts/{id}/ack`, so the human-in-the-loop rule also covers the pager.

### Design rules

1. **The touch screen is the only interface.** No buttons, no power switch: accepting a task, silencing the motor,
   quiet mode, brightness, power off and wake-up all happen on the screen.
2. **Smallest and lightest parts that still work:** no dev-board extras (headers, breadboard, separate charger
   module, perfboard); the few passives are 0402 SMD parts soldered directly on the XIAO's back pads.
3. **One small LiPo** powers everything; the XIAO charges it over USB-C.
4. **Target:** case ≤ 40 × 40 × 12 mm, total weight ≈ 25 g with the strap (a typical smartwatch is 30–50 g).

### Screen interactions

The CST816S touch controller detects taps, long presses and swipes in hardware and raises an interrupt, so the
firmware stays simple and the touch keeps working while the C3 sleeps.

| What the nurse wants | On the screen | Effect |
|---|---|---|
| Wake the watch | **Tap** anywhere | Backlight on, watch face or current alert |
| **Stop the vibration** | Tap **Silence** on the alert | Motor stops for this alert; it stays open on the watch and the dashboard |
| **Accept the task** ("I'm going") | **Hold Accept for 1 s** (a ring fills around the edge) | Sends `ack`: the alert gets `acked_by` = this nurse, the other pagers and the dashboard drop it. The hold prevents accidental accepts from a sleeve |
| See the other open alerts | **Swipe left / right** | Next / previous (up to 8 kept on the watch) |
| Back to the watch face | **Swipe down** | |
| Open settings | **Swipe up** on the watch face | Settings screen (below) |

**Settings screen** (one tap per item):

| Item | Effect |
|---|---|
| Quiet 15 min | Motor off for 15 min (breaks); alerts still appear. `critical` alerts still vibrate |
| Vibration strength | Low / medium / high (PWM duty) |
| Brightness | 3 levels; lower = longer battery |
| Info | Pager ID, assigned nurse, ward, Wi-Fi signal, battery %, firmware version |
| **Power off** (hold 3 s) | Display to sleep, backlight off, C3 into deep sleep. The pager publishes `status` `online:false` first |

**Power on:** hold the screen for 2 s; the touch interrupt wakes the C3 from deep sleep. Plugging in USB-C also
wakes it. This replaces the power switch.

- No patient data beyond the bed and first name on the wrist (privacy). It has no sensors and makes no medical claims.

### Bill of materials (size- and weight-optimised)

| # | Part | Reference | Size | Weight (≈) | Qty | Have? | What it does |
|---|---|---|---|---|---|---|---|
| 1 | Microcontroller | **Seeed Studio XIAO ESP32C3**, **no pin headers** (wires soldered to the castellated pads) | 21 × 17.5 × 3.5 mm | ~2 g | 1 (+1 spare) | ☐ | Wi-Fi + BLE, runs the firmware, **built-in LiPo charger** over USB-C |
| 2 | Round touch display (kept) | **Waveshare 1.28" Round Touch LCD**: GC9A01 (240×240 IPS, SPI) + CST816S (touch, I2C 0x15) | Ø ~37 mm, ~4 mm | ~6 g | 1 | ☐ | The watch face and the **only input** |
| 3 | Vibration motor | **0720 coin motor, 3 V** (Ø 7 × 2 mm). Stronger option: 0820 (Ø 8 × 2 mm) | Ø 7 mm | ~0.3 g | 1 | ☐ | Buzzes on the wrist |
| 4 | Motor switch | **SI2302** N-MOSFET, SOT-23 | 3 × 1.4 mm | < 0.1 g | 1 | ☐ | Switches the motor from a 3.3 V GPIO |
| 5 | Flyback diode | **1N4148WS**, SOD-323 | 1.7 × 1.3 mm | < 0.1 g | 1 | ☐ | Absorbs the motor's back-EMF spike |
| 6 | Resistors | 0402: 100 Ω (gate), 100 kΩ (gate pull-down), 2 × 220 kΩ (battery divider) | 1 × 0.5 mm | — | 4 | ☐ | Motor control and battery reading |
| 7 | Capacitors | 0402 100 nF (ADC filter) · 0805 47 µF (3V3 buffer for Wi-Fi + motor peaks) | ≤ 2 × 1.25 mm | — | 2 | ☐ | Stable readings, no brown-out resets |
| 8 | Battery | **LiPo 3.7 V 302530, ~250 mAh**, with protection (PCM), ≥ 1C | 30 × 25 × 3 mm | ~5 g | 1 | ☐ | Powers everything |
| 9 | Wiring | 30 AWG silicone wire, Kapton tape | — | ~0.5 g | — | ☐ | Short flexible links, insulation between layers |
| 10 | Case | 3D-printed round case, 1.2 mm walls, PETG, USB-C cut-out | 40 × 40 × 12 mm | ~5 g | 1 | ☐ | Holds the stack |
| 11 | Strap | 20 mm TPU or silicone strap (or printed TPU, integrated lugs) | — | ~5 g | 1 | ☐ | Wears it on the wrist |
| | **Total** | | | **~24 g** | | | Estimates: weigh the parts before quoting a number |

**Removed compared to v0.2 (smaller and lighter):** the power switch (now on-screen power off), the perfboard
(passives soldered on the XIAO's back pads), the pin headers, the 0603 parts (now 0402), the 0820 motor (now 0720).

**Check before ordering:**
- The XIAO ESP32C3's charge current: a 250 mAh cell should charge at ≤ 250 mA (1C). If it charges faster, use a
  bigger cell (402530, ~300 mAh).
- The 0720 motor is noticeable on the wrist but softer than the 0820. If nurses miss it during the test, switch to the
  0820 (same wiring, +1 mm).

### Battery: one small cell powers everything

The **3.7 V LiPo** feeds the XIAO, whose regulator makes 3.3 V for every part; its charger refills it over USB-C.

**What the cell must supply (all parts at 3.3 V):**

| Part | Typical | Peak |
|---|---|---|
| ESP32-C3 (Wi-Fi modem sleep / Wi-Fi transmit) | 20–30 mA | ~350 mA for a few ms |
| GC9A01 display + backlight | 15–25 mA | 30 mA (full brightness) |
| CST816S touch | < 1 mA | 2 mA |
| 0720 vibration motor | 0 (off) | 50–70 mA |
| **Total** | **~40–55 mA (screen on)** | **~450 mA (rare: Wi-Fi TX + motor + screen)** |
| Powered off (C3 deep sleep, display asleep, touch standby) | well under 1 mA | — |

**Cell choices that fit the case:**

| Cell | Size (mm) | Capacity | Peak at 2C | Runtime (estimate) | Verdict |
|---|---|---|---|---|---|
| 301230 | 30 × 12 × 3 | ~100 mAh | 200 mA | 3–4 h | ❌ too short, can't handle Wi-Fi peaks |
| 302030 | 30 × 20 × 3 | ~150 mAh | 300 mA | 4–6 h | ⚠️ borderline on peaks |
| **302530** | **30 × 25 × 3** | **~250 mAh** | **500 mA** | **7–10 h** | ✅ **recommended**: fits under the display, covers an 8 h shift |
| 402530 | 30 × 25 × 4 | ~300 mAh | 600 mA | 9–12 h | ✅ if the case can be 1 mm thicker |

**Rules for the cell:**
- Buy it **with a protection circuit (PCM)**: cut-off at over-charge, over-discharge and short circuit.
- Pick a cell rated **≥ 1C continuous, 2C peak**; a weak cell causes random resets on Wi-Fi peaks.
- **No coin cell (CR2032) or AAA:** a CR2032 collapses under Wi-Fi peaks; AAA cells are too big for a watch.
- Exact capacities vary by maker; check the seller's datasheet.

### Pin map (XIAO ESP32C3), draft v0.3

| Function | XIAO pin | GPIO | Dir | Notes |
|---|---|---|---|---|
| Battery sense | D0 | 2 | ADC1_CH2 | 220k/220k divider: reads V_bat / 2. ~2 V at boot keeps this strapping pin high |
| **Touch INT** | D1 | 3 | in | CST816S interrupt. GPIO 0–5 are the C3's **deep-sleep wake** pins, so this is how the screen powers the watch on |
| Vibration motor | D2 | 4 | out (LEDC PWM, 1 kHz) | MOSFET gate through 100 Ω, 100k pull-down to GND (motor off at boot) |
| LCD DC | D3 | 5 | out | data / command select |
| Touch SDA | D4 | 6 | I2C (400 kHz) | CST816S `0x15` |
| Touch SCL | D5 | 7 | I2C | |
| LCD CS | D6 | 21 | out | also UART TX: the boot log toggles it, which the display ignores before init |
| LCD backlight | D7 | 20 | out (LEDC PWM) | brightness levels; 0 = off |
| SPI SCK | D8 | 8 | out (SPI, 40–80 MHz) | strapping pin; SPI idles it high |
| *(free)* | D9 | 9 | — | BOOT strap: left free so flashing always works |
| SPI MOSI | D10 | 10 | out | the display is write-only, so no MISO |
| LCD RST + touch RST | — | — | — | tied to 3V3 through 10 kΩ with 100 nF to GND (power-on reset). The firmware uses the GC9A01 software reset (`0x01`); saves a GPIO |

### Wiring

```
 LiPo (+) ── XIAO BAT+ pad (back)      LiPo (−) ── XIAO BAT− pad      (no switch: power off is on the screen)

 Display module:  VCC → 3V3   GND → GND
                  SCL/CLK → D8   SDA/DIN → D10   CS → D6   DC → D3   BL → D7
                  TP_SDA → D4    TP_SCL → D5     TP_INT → D1
                  RST + TP_RST → 10k to 3V3, 100 nF to GND

 Battery sense:   BAT+ ── 220k ──┬── 220k ── GND
                                 ├── 100 nF ── GND
                                 └── D0

 Motor:           3V3 ──┬── motor (+)      motor (−) ──┬── drain (SI2302)
                        └── 1N4148WS cathode           └── 1N4148WS anode
                  D2 ── 100 Ω ── gate ── 100k ── GND     source ── GND

 3V3 buffer:      47 µF between 3V3 and GND, right at the XIAO pads
```

- The 0402 resistors, the MOSFET and the diode are soldered **directly on the XIAO's back pads** with short wire
  stubs, then covered with Kapton tape. No perfboard.
- The XIAO regulates the LiPo (3.4–4.2 V) down to 3.3 V. The firmware warns at 3.5 V and powers off cleanly at 3.4 V.
- Keep the motor wires away from the display flex to limit noise.

### Stack inside the case (side view)

```
   ┌──────────────────────────────┐  ← 1.28" round touch display (top, ~4 mm)
   ├──────────────────────────────┤  ← Kapton tape
   │ XIAO ESP32C3 (no headers)  ◯ │  ← middle (~3.5 mm); 0720 motor glued to the case wall
   ├──────────────────────────────┤  ← Kapton tape
   │        LiPo 302530           │  ← bottom (~3 mm)
   └──────────────────────────────┘  ← case back (1.2 mm) with USB-C cut-out for charging
          total ≈ 12 mm
```

### Vibration patterns

| Alert | Pattern | Repeats |
|---|---|---|
| `critical` | 3 × (400 ms on, 150 ms off) | every 10 s until accepted or silenced |
| `high` | 2 × (300 ms on, 200 ms off) | every 30 s until accepted or silenced |
| `medium` | 1 × 400 ms | once, again after 2 min if still open |
| `low` | 1 × 150 ms | once |
| `call_nurse` (any severity) | long-short-long (500 / 150 / 200 / 150 / 500 ms) | every 20 s until accepted or silenced |

"Silence" stops the repeats for that alert only. A new alert vibrates again.

### Screens (240×240 round)

```
     WATCH FACE                 ALERT                    SETTINGS
    .-''''''''-.              .-''''''''-.              .-''''''''-.
  .'  Wi-Fi 76% '.          .' CRITICAL 1/3'.          .' Quiet 15 min'.
 /                \        /   Bed C-12     \        /   Vibration ▮▮▯  \
|      03:42       |      |    Amira         |      |   Brightness ▮▯▯   |
|    Cardiology    |      |  SpO2 89% HR 128 |      |   Info             |
 \  0 open alerts /        \[Silence][Accept]/        \  Power off (hold)/
  '.  swipe up  .'          '. hold 1 s   .'          '.            .'
    '-........-'              '-........-'              '-........-'
```

- Alert colours by severity: red `critical`, orange `high`, yellow `medium`, grey `low`.
- After **Accept**: a green check with "On my way: Bed C-12" for 2 s, then the next alert or the watch face.
- Times are shown in Africa/Tunis (UTC+1). The pager takes its time from NTP when online; it has no RTC.
- The backlight turns off after 10 s without an open alert. A tap or a new alert wakes it.

### MQTT topics (proposed for mqtt-topics v1.2)

Prefix: `hospital/pager/{pager_id}/`. `pager_id` = `pgr-` + 3 digits (e.g. `pgr-001`), printed on the case back.
Client ID: `ward-pgr-{pager_id}`. The common rules of the MQTT contract apply (`msg_id`, epoch `ts`, max 1024 bytes,
unknown fields ignored). "Silence", quiet mode, brightness and vibration strength stay on the watch; only **Accept**
and the power state reach the server.

| Topic | Direction | QoS | Retained |
|---|---|---|---|
| `alert` | server → pager | 1 | no |
| `clear` | server → pager | 1 | no |
| `config` | server → pager | 1 | **yes** |
| `ack` | pager → server | 1 | no |
| `status` | pager → server (also last-will) | 1 | **yes** |

#### `alert` (server → pager)

```json
{ "alert_id": "al-0042", "kind": "news2", "severity": "critical", "bed": "C-12",
  "first_name": "Amira", "text": "SpO2 89%, HR 128", "news2": 7, "ts": 1759680000 }
```

- `text` is at most 40 characters (two lines on the round screen). The server truncates it.
- Only the first name and the bed are sent: no last name, ID number or phone number.
- If an alert with the same `alert_id` arrives twice, the pager keeps one copy.

#### `clear` (server → pager)

```json
{ "alert_id": "al-0042", "acked_by_name": "Salma" }
```

Sent to every pager of the ward when an alert is accepted anywhere (pager or web). The pager removes it and, if it was
on screen, shows "Taken by Salma" for 2 s.

#### `config` (server → pager, retained)

```json
{ "nurse_id": "u-0002", "nurse_name": "Salma", "ward": "Cardiology" }
```

`nurse_id: null` means the pager is unassigned: it shows "Not assigned" and ignores `alert`.

#### `ack` (pager → server)

```json
{ "msg_id": 2051, "ts": 1759680042, "alert_id": "al-0042" }
```

Sent when the nurse holds **Accept**. The backend worker applies it like `POST /alerts/{id}/ack` by the nurse in the
pager's `config`. That ack is idempotent: a second one keeps the first `acked_by`. The worker then publishes `clear` to
the ward's pagers and pushes the usual `alert` WS frame so the web dashboards drop the alert.

#### `status` (pager → server, retained, last-will)

```json
{ "online": true, "fw_version": "0.1.0", "battery_pct": 76, "rssi": -61 }
```

- On-screen **Power off** publishes `{"online": false, "reason": "power_off"}` before sleeping, so the server knows
  it was deliberate.
- Last-will: `{"online": false, "fw_version": "0.1.0"}`. When a pager bound to a nurse drops **without** a power-off
  (dead battery, out of range), the server raises a `device_offline` alert for the ward.

### Backend side (Wali, after the contract bump)

- Table `pagers` (`id`, `nurse_id`, `ward`, `online`, `battery_pct`, `last_seen`) + Alembic migration.
- `POST /pagers/{id}/assign` (admin, or a nurse for themselves) `{"nurse_id"}` → publishes the retained `config`.
  Needs an api.md bump too.
- Worker: subscribe to `hospital/pager/+/ack` and `hospital/pager/+/status`. On a new alert, publish `alert` to every
  online, assigned pager of the alert's ward.
- **Escalation (stretch):** if a `critical` alert is still open after 2 min, re-send it to all pagers of the ward.
- Tests in `backend/tests/` with a fake MQTT client: alert fan-out per ward, ack → `acked_by`, duplicate ack, clear
  fan-out, unassigned pager ignored, power-off vs last-will.

### Firmware structure (`pager/`, PlatformIO, Arduino framework)

```
pager/
├── platformio.ini        # envs: xiao_esp32c3 (real board), wokwi, native (logic tests)
├── wokwi.toml
├── diagram.json          # C3 + ILI9341 cap-touch stand-in + LED (motor) + pot (battery)
├── include/
│   └── secrets.h.example # WIFI_SSID, WIFI_PASS, MQTT_HOST, PAGER_ID (secrets.h is git-ignored)
├── src/
│   ├── main.cpp          # setup / loop, state machine
│   ├── net.cpp           # Wi-Fi + MQTT (PubSubClient), last-will, NTP, reconnect with backoff
│   ├── display.cpp       # GC9A01 driver (TFT_eSPI or LovyanGFX), backlight PWM, sleep in/out
│   ├── screens.cpp       # LVGL screens: watch face, alert, settings, info, power off
│   ├── touch.cpp         # CST816S over I2C: gestures, hold-to-accept, deep-sleep wake on INT
│   ├── haptic.cpp        # LEDC PWM, strength levels, non-blocking patterns, silence / quiet
│   └── power.cpp         # battery ADC + %, low-battery shutdown, deep sleep, settings in NVS
├── lib/
│   └── alerts/           # pure logic: alert queue (max 8), dedupe, sort by severity, silence state, pattern lookup
└── test/
    └── test_alerts/      # pio test -e native
```

State machine: `OFF (deep sleep) → BOOT → CONNECTING → IDLE ⇄ ALERTING → (Accept) → IDLE`, with `SETTINGS` reachable
from `IDLE`. `UNASSIGNED` while `config.nurse_id` is null; `LOW_BATTERY` overlays any state and leads to `OFF`.

**Wokwi:** Wokwi has no GC9A01 + CST816S. Use an ILI9341 with FT6206 capacitive touch as the stand-in, behind the same
`display.cpp` / `touch.cpp` interface, with an LED for the motor and a potentiometer for the battery. Board:
`board-xiao-esp32-c3` if your Wokwi version has it, otherwise `board-esp32-c3-devkitm-1` with the same GPIO numbers.

### Power budget (estimate, to measure on the real board)

| State | Current (approx.) |
|---|---|
| Wi-Fi connected, modem sleep, backlight off | 20–30 mA |
| Display on (backlight ~50 %) | +15–25 mA |
| Motor on | +50–70 mA (short bursts) |
| Powered off from the screen | well under 1 mA (days to weeks on a charge) |

With a 250 mAh cell and the screen mostly off, that is roughly **7–10 h**: enough for an 8 h shift. The pager charges at
the nurse station between shifts. These are estimates: measure with a USB power meter before quoting a number in the pitch.

### Build order

1. Contract: mqtt-topics v1.2 PR with the `hospital/pager/` topics; 👍 from Hedi and Faouzi.
2. Wokwi: the stand-in diagram; build the screens and gestures, driven by test messages from `mosquitto_pub`.
3. Backend: `pagers` table, fan-out and ack in the worker, tests.
4. Simulator (optional): a `--pager pgr-001` mode that prints alerts and acks after N seconds, for demos without the board.
5. Real board: test the XIAO and the display on the bench with flying leads, then solder the motor parts on the XIAO's
   back pads, check the deep-sleep wake from the touch screen, and fit the stack into the case.

### Demo moment

The simulator drops Amira's SpO2 → NEWS2 goes critical → **the presenter's wrist buzzes on stage** → they read
"Bed C-12" on the round screen, tap **Silence**, then hold **Accept** → the alert disappears from the web dashboard on
the projector, marked "acked by Salma".

### Pager changelog

- 0.3 (2026-10-10): screen-only interface (Accept, Silence, quiet, vibration strength, brightness, power off / on from
  the screen; no switch). Size and weight optimised: no headers, no perfboard, 0402 parts on the XIAO's back pads,
  0720 motor, 40 × 40 × 12 mm case, ~24 g. Pin map: touch INT moved to GPIO 3 (deep-sleep wake), backlight to GPIO 20,
  display/touch reset by RC + software reset. `status` gets `reason: "power_off"`; `config` drops `quiet`.
- 0.2 (2026-10-10): watch-sized parts: XIAO ESP32C3 with built-in charger, 1.28" round GC9A01 + CST816S touch display,
  coin motor, SOT-23 MOSFET and SMD passives, 302530 LiPo (battery sizing table). New pin map, gestures, case stack.
- 0.1 (2026-10-10): first proposal: BOM, pin map, wiring, vibration patterns, screens, MQTT topics, backend and
  firmware structure.
