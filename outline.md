# CYBERDECK NETRUNNER — Master Build Doc
**Base:** Women's M/L · Pi 3B+ arm-deck · Arduino Nano accessory zones · 1-month build
**Owner is EE** — bench-first workflow, all integration risk killed in week 1.

---

## 0. Concept
Working-class netrunner: black techwear base + MOLLE rig, **arm-mounted cyberdeck**
(Pi 3B+ + 3.5" touchscreen, visible wiring), dead Jetson Nano displayed as mil-spec
hardware on a back panel, minor cyberware (neck data ports, temple optic, spinal
implant, chest OLED biomon). Signature interactions: touchscreen deck OS, rotary
"frequency tune" during breaches, button emergency-blackout.

---

## 1. System Architecture

```
BANK A (UGREEN 20k/45W) ─USB-C─▶ LOGIC RAIL 5V/3A (direct)
   ├─ Pi 3B+ (arm deck)
   │    ├─ HDMI ────────── 3.5" touchscreen
   │    ├─ USB ─────────── touch controller + Nano comms (hub if >3 nodes)
   │    ├─ GPIO18 → AHCT125 ─▶ 8×8 matrix ─▶ sleeve strip   [LOCAL pixels]
   │    ├─ GPIO17/27 ───── rotary encoder
   │    ├─ GPIO22 ──────── push button
   │    └─ I2C ─────────── OLED chest biomon (≤50 cm, 100 kHz)
   └─ 40mm fan, EL inverter

BANK B (UGREEN 20k/45W) ─USB-C─▶ [PD trigger 12V] ─▶ XL4016 buck ─▶ LED RAIL 5V
   ├─ sleeve strip far-end injection
   └─ back panel 5V bus
        └─ NODE_BACK (Nano): spine pixels, Jetson glow, collar/neck-port LEDs

PI ──USB serial──▶ all Nanos:  "S <STATE>\n" broadcast, fire-and-forget
```

**Rules:**
- Never parallel the banks. Bank A = logic, Bank B = LED.
- Pixel power comes from the LED rail, never the Pi header.
- Common ground star point at the distro board.
- Nanos run local effects; Pi only broadcasts state changes.

---

## 2. Power System

| Item | Spec |
|---|---|
| Rails | LOGIC 5V/3A (Bank A direct) · LED 5V (Bank B via PD+buck) |
| Tier 1 fallback | Bank B plain 5V/3A, `BUDGET_MA=2800`, brightness caps in code |
| Tier 2 (recommended) | PD trigger → 12V → XL4016 buck → 5V/~6A, `BUDGET_MA=6000` |
| Runtime | Logic ~12–15 h · LED ~8–10 h · hot-swap banks in hip pouches |

**Distribution:**
- 2-pole latching master switch at distro board; polyfuse 3A on logic rail.
- Caps: 1000µF/25V buck input · 470µF buck output · 1000µF at arm deck · 470µF at 8×8 V+.
- **Wire gauge:** hip→arm 5V feed = **16 AWG** (3B+ peaks ~1.7 A; 18 AWG drops ~0.1 V — marginal).
- Panel-mount USB-C extensions for bank hot-swap; right-angle cables out of pouches.
- Verify Bank B's PDO list on the label day 1; use its C1/45W port.

---

## 3. I/O Map

### Pi 3B+ (arm deck)
| Peripheral | Interface | Pins |
|---|---|---|
| 3.5" touchscreen | HDMI + USB | HDMI0 / USB-A |
| 8×8 matrix + sleeve strip (one chain) | 1-wire | GPIO18 → AHCT125 |
| Rotary encoder A/B | GPIO | GPIO17 / GPIO27 |
| Push button | GPIO | GPIO22 (pull-up) |
| OLED biomon | I2C1 | GPIO2 / GPIO3, addr 0x3C |

### Nano nodes (accessories)
| Node | Loads | Comms |
|---|---|---|
| NODE_BACK | spine pixels, Jetson underglow, collar/neck-port LEDs | USB serial from Pi (or hub) |
| NODE_x (future) | boots, thigh ports, etc. | same protocol |
Nano power: local 5V rail → **5V pin** (bypass regulator) or USB.

---

## 4. Wiring Harness
| Run | Conductors | Notes |
|---|---|---|
| Hip Bank A → arm deck | 16 AWG 5V/GND | **coiled segment across elbow** (flex relief), strain ties at shoulder+wrist, connector at deck for removal |
| Hip Bank B → back panel | 16 AWG 5V/GND | LED rail bus; panel holds Nano + injection points |
| Back panel → collar | 22 AWG | tap off NODE_BACK outputs |
| Arm deck → sleeve strip | pixels chained from 8×8 | data leaves deck, power injected at far end from LED rail |
| Pi USB → back panel Nano | 1× USB-A | only long signal cable in the whole costume |

---

## 5. Firmware — Pi (`cyberdeck/`)

```
cyberdeck/
├── main.py            # init, event loop, events → FSM
├── config.py          # pins, LED counts, BUDGET_MA, colors, i2c addr, timeouts
├── fsm.py             # state machine
├── hw/
│   ├── pixels.py      # ONE rpi_ws281x chain: [0:64]=matrix, [64:]=strip;
│   │                  #   xy_to_index() serpentine map; effect generators;
│   │                  #   enforce_budget(); thread-owned
│   ├── encoder.py     # gpiozero RotaryEncoder → TICK(dir)
│   ├── button.py      # gpiozero Button → PRESS / LONG_PRESS(≥1.5s) / DOUBLE
│   ├── oled.py        # luma.oled, 2 Hz refresh thread, telemetry pages
│   ├── accessories.py # open /dev/serial/by-id/*Nano*; broadcast(state);
│   │                  #   heartbeat; flag dead nodes → SYS tile
│   └── telemetry.py   # vcgencmd temp, uptime, LED mA estimate, node health
├── ui/
│   ├── screens.py     # Boot, HomeDeck, Scan, Run, Alert, Cooldown, Blackout
│   ├── widgets.py     # terminal feed, netmap, gauges, ≥60px targets
│   └── glitch.py      # RGB-split / tear / noise overlays
└── services/
    ├── netmon.py      # background real `iw` scans → "nodes detected"
    └── loggen.py      # fake terminal traffic + real telemetry sprinkles
```

**Threads:** UI main (pygame) · pixels (sole owner of chain) · OLED 2 Hz · netmon.
FSM publishes state → pixel thread + `accessories.broadcast()`.

**State machine:**
| State | Enter via | Touchscreen | 8×8 | Strip | Nanos |
|---|---|---|---|---|---|
| BOOT | power | logo + log crawl | boot glyph | breathe | boot |
| IDLE | home | TERM/NETMAP/SYS + [SCAN][RUN] | radar blips | dim chase | idle |
| SCANNING | touch/encoder | sweep + real SSIDs | sweep+pings | outward sweep | scan |
| RUNNING | touch RUN | breach: align waveform | waveform | strobing | strobe |
| ALERT | fail/random | red glitch | hard strobe | red flash | red flash |
| COOLDOWN | resolve | "RUN COMPLETE" | fade | power-down | fade |
| BLACKOUT | button long | dim "LOCKED" | off | off | off |

**Controls:** encoder = cycle/tune/align, press = confirm · button short = confirm
(glove-friendly), long ≥1.5 s = **emergency blackout**, double = OLED page · touch = primary.

**EE details:** `enforce_budget()` clamps every frame to `BUDGET_MA`
(est = Σ(R+G+B)/765 × 60 mA/px) · BCM2710 hardware watchdog · every `hw/` init in
try/except (con-day repairability) · real numbers on OLED (temp, mA, uptime).

**Boot:** Bookworm desktop autologin → launch script; `xset s off`, `unclutter`,
touch calibration; render at panel native res (480×320 SPI-type / 854×480 HDMI).

---

## 6. Firmware — Nano nodes

Protocol: ASCII lines @ 115200, Pi→Nano broadcast only:
```
S IDLE|SCAN|RUN|ALERT|COOL|BLACKOUT\n
B <0-255>\n        # master brightness
```

Sketch outline (one sketch, `NODE_ID` define per node):
```
setup:  Serial.begin(115200); strip.begin(); read NODE_ID
loop:
  parse serial lines → set state / brightness
  run current effect (millis-based, non-blocking)
  enforce per-node mA cap (LED count × brightness ceiling in config)
  NO comms for 30 s → autonomous IDLE effect (Pi-crash resilience)
effects mirror Pi states: idle breathe / scan sweep / run strobe /
alert red flash / cooldown fade / blackout off
```

---

## 7. 3D Prints (existing files)
| Part | File |
|---|---|
| Deck enclosure (Pi-sized) | Triskel_mk1 cyberdeck — https://www.thingiverse.com/thing:7010296 |
| Bracer/arm shell options | https://www.printables.com/tag/gauntlet |
| More deck shapes | https://www.printables.com/tag/cyberdeck |
| Neck data ports | https://www.printables.com/model/627815-cyberpunk-data-shard-ports/ |
| Data shards (prop) | https://makerworld.com/en/models/757818-cyberpunk-shard |
| Spinal implant | Wearable Spine (thoracic section only, sew-on) — https://www.thingiverse.com/thing:4982223 |
| Small surface implants | https://cults3d.com/en/3d-model/fashion/cyberpunk-cyberware |
| Visor (optional) | https://www.thingiverse.com/thing:6314899 (TPU LED) or https://www.printables.com/model/1816044-cyberpunk-hex-visor/ |

Jetson prop: strip RF shields (weight), Dremel around SoC, EL/heatsink over die.

---

## 8. BOM
**Owned:** Pi 3B+ · dead Jetson Nano · 2× UGREEN 20k/45W · Arduino Nanos · 3.5" touch · encoder · button · OLED · 8×8 matrix.

**Buy (fast-ship only — Adafruit same-day, Amazon Prime, Digi-Key next-day; nothing overseas):**
| Item | Source |
|---|---|
| NeoPixel strip 60/m ×2 m + silicone diffuser | Adafruit |
| AHCT125 level shifter, polyfuse 3A, caps (1000µF/25V, 470µF/10V) | Adafruit/Digi-Key |
| USB-C panel-mount extensions ×2 + right-angle 100W cables ×2 | Amazon Prime |
| PD trigger board 45W w/ display (Tier 2) | Amazon Prime |
| XL4016/HW-623 10A buck + heatsink (Tier 2) | Amazon Prime |
| 2-pole latching switch, terminal blocks, 16/18/22 AWG silicone wire | Amazon/Digi-Key |
| EL wire 3 m + **5V** USB inverter · 40 mm 5V fan | Amazon |
| MOLLE vest + 2 hip pouches + elastic straps/buckles | Amazon Prime |
| USB hub (only if >3 Nanos) · JST-SM connectors | Amazon |
| Techflex sleeving, heat shrink | Amazon |

---

## 9. Schedule
| Week | Milestones |
|---|---|
| 1 | Order day 1. Bench: kiosk UI, encoder, button, OLED, both pixel segments, limiter, Nano flash + serial broadcast. Verify Bank B PDOs. |
| 2 | Print queue (deck, ports, spine, implants). Build power harness + distro board. Sleeve pixel segments. |
| 3 | Assemble arm deck (strap mount, screen angle, elbow coil). Mount back panel, spine, ports. Route harness. |
| 4 | Integration + sleeving. 3-hour wear test: thermals, drop test on cable joints, bank swap drill. |

---

## 10. Acceptance Tests (end of week 1)
- [ ] UI boots to kiosk unattended; watchdog reboots on hang
- [ ] Encoder cycles tiles; press selects; long-press = blackout
- [ ] 8×8 radar sweep + strip chase simultaneously, limiter clamps full-white
- [ ] OLED shows real temp/mA/uptime at 2 Hz
- [ ] `S ALERT` → every Nano flashes red within 100 ms
- [ ] Unplug Pi serial → Nanos fall back to autonomous idle
- [ ] Arm cable: 1.7 A load, ≥4.8 V measured at deck