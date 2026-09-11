#include <WiFi.h>
#include <AsyncUDP.h>
#include <Wire.h>
#include <U8g2lib.h>
#include <Adafruit_NeoPixel.h>

enum VisorState : uint8_t {
  ST_BOOT, ST_IDLE, ST_SCANNING, ST_RUNNING,
  ST_ALERT, ST_COOLDOWN, ST_BLACKOUT, ST_TARGET_LOCK,
  ST_BOLD_TEXT, ST_VIDEO_STREAM
};

const char* ssid = "VISOR_LINK";
const char* password = "cyberdeck";

AsyncUDP udp;
const int udpPort = 1337;

// --- Maelstrom visor LEDs ---------------------------------------------------
// A couple of NeoPixels on the visor that ONLY ever show red (Maelstrom look).
// Wire the data line to PIN_VISOR_LEDS; change these two defines to match your
// wiring / LED count.
#define PIN_VISOR_LEDS 4
#define NUM_VISOR_LEDS 2
Adafruit_NeoPixel visorLeds(NUM_VISOR_LEDS, PIN_VISOR_LEDS, NEO_GRB + NEO_KHZ800);

// ESP32 has two hardware I2C buses: Wire (I2C0) and Wire1 (I2C1).
// This allows you to connect two IDENTICAL OLED screens without changing their addresses!
// Left Eye: GPIO 21 (SDA), GPIO 22 (SCL) on Wire.
U8G2_SSD1306_128X64_NONAME_1_HW_I2C u8g2_left(U8G2_R0, U8X8_PIN_NONE, 22, 21);

// Right Eye: GPIO 17 (SDA), GPIO 16 (SCL) on Wire1.
// U8g2's built-in 2ND_HW_I2C class needs WIRE_INTERFACES_COUNT, which the
// ESP32 core does not define, so it silently no-ops here. Mirror the
// library's own hardware-I2C byte callback (U8x8lib.cpp) but against Wire1.
extern "C" uint8_t u8x8_byte_esp32_wire1_i2c(u8x8_t *u8x8, uint8_t msg, uint8_t arg_int, void *arg_ptr)
{
  switch(msg)
  {
    case U8X8_MSG_BYTE_SEND:
      Wire1.write((uint8_t *)arg_ptr, (int)arg_int);
      break;
    case U8X8_MSG_BYTE_INIT:
      if ( u8x8->bus_clock == 0 )
        u8x8->bus_clock = u8x8->display_info->i2c_bus_clock_100kHz * 100000UL;
      if ( u8x8->pins[U8X8_PIN_I2C_CLOCK] != U8X8_PIN_NONE && u8x8->pins[U8X8_PIN_I2C_DATA] != U8X8_PIN_NONE )
      {
        Wire1.begin((int)u8x8->pins[U8X8_PIN_I2C_DATA], u8x8->pins[U8X8_PIN_I2C_CLOCK]);
      }
      else
      {
        Wire1.begin();
      }
      break;
    case U8X8_MSG_BYTE_SET_DC:
      break;
    case U8X8_MSG_BYTE_START_TRANSFER:
      Wire1.setClock(u8x8->bus_clock);
      Wire1.beginTransmission(u8x8_GetI2CAddress(u8x8)>>1);
      break;
    case U8X8_MSG_BYTE_END_TRANSFER:
      Wire1.endTransmission();
      break;
    default:
      return 0;
  }
  return 1;
}

class U8G2_SSD1306_128X64_NONAME_1_WIRE1 : public U8G2 {
  public: U8G2_SSD1306_128X64_NONAME_1_WIRE1(const u8g2_cb_t *rotation, uint8_t reset = U8X8_PIN_NONE, uint8_t clock = U8X8_PIN_NONE, uint8_t data = U8X8_PIN_NONE) : U8G2() {
    u8g2_Setup_ssd1306_i2c_128x64_noname_1(&u8g2, rotation, u8x8_byte_esp32_wire1_i2c, u8x8_gpio_and_delay_arduino);
    u8x8_SetPin_HW_I2C(getU8x8(), reset, clock, data);
  }
};

// Constructor signature: (rotation, reset, clock, data)
U8G2_SSD1306_128X64_NONAME_1_WIRE1 u8g2_right(U8G2_R0, U8X8_PIN_NONE, 16, 17);

VisorState currentState = ST_BOOT;
IPAddress piIP;
bool hasPiIP = false;
uint16_t estimatedVisorMA = 160;

VisorState parseState(const char* s) {
  if (strcmp(s, "IDLE") == 0)        return ST_IDLE;
  if (strcmp(s, "SCANNING") == 0)    return ST_SCANNING;
  if (strcmp(s, "RUNNING") == 0)     return ST_RUNNING;
  if (strcmp(s, "ALERT") == 0)       return ST_ALERT;
  if (strcmp(s, "COOLDOWN") == 0)    return ST_COOLDOWN;
  if (strcmp(s, "BLACKOUT") == 0)    return ST_BLACKOUT;
  if (strcmp(s, "TARGET_LOCK") == 0) return ST_TARGET_LOCK;
  return ST_IDLE;
}

const char* stateToStr(VisorState st) {
  switch(st) {
    case ST_BOOT: return "BOOT";
    case ST_IDLE: return "IDLE";
    case ST_SCANNING: return "SCANNING";
    case ST_RUNNING: return "RUNNING";
    case ST_ALERT: return "ALERT";
    case ST_COOLDOWN: return "COOLDOWN";
    case ST_BLACKOUT: return "BLACKOUT";
    case ST_TARGET_LOCK: return "TARGET_LOCK";
    case ST_BOLD_TEXT: return "BOLD_TEXT";
    case ST_VIDEO_STREAM: return "VIDEO_STREAM";
  }
  return "UNKNOWN";
}

unsigned long lastHeartbeat = 0;
String leftWord = "CYBER";
String rightWord = "DECK";

// Video buffers
uint8_t leftBuffer[1024] = {0};
uint8_t rightBuffer[1024] = {0};
bool newLeftFrame = false;
bool newRightFrame = false;

void setup() {
  Serial.begin(115200);

  // Maelstrom LEDs: moderate brightness since they sit near the wearer's eyes
  // behind the visor; raise VISOR_LED_BRIGHTNESS if they read too dim.
  visorLeds.begin();
  visorLeds.setBrightness(70);
  visorLeds.show();

  // SSD1306 supports 400 kHz fast mode; the default 100 kHz takes ~90 ms
  // per full 1024-byte frame. setBusClock() is the knob that sticks: the
  // U8g2 HAL re-applies bus_clock via Wire.setClock() on every transfer.
  u8g2_left.setBusClock(400000);
  u8g2_left.begin();
  u8g2_left.setI2CAddress(0x3C * 2);

  u8g2_right.setBusClock(400000);
  u8g2_right.begin();
  u8g2_right.setI2CAddress(0x3C * 2);

  // Force Access Point mode explicitly
  WiFi.persistent(false);
  WiFi.mode(WIFI_AP);

  // Modem sleep must be off in SoftAP mode: with it on, the radio dozes
  // between beacons and drops auth/assoc frames from picky clients
  // (the Raspberry Pi), so association times out or never completes.
  WiFi.setSleep(false);

  // Host our own WiFi network (SoftAP).
  // Channel 1 explicitly: some core/region combos default to 12/13, which
  // regulatory-locked clients (US Raspberry Pis) are not allowed to see.
  bool apOk = WiFi.softAP(ssid, password, 1, 0, 4);
  if (!apOk) {
    delay(100);
    apOk = WiFi.softAP(ssid, password, 1, 0, 4);
  }

  // Pin the subnet so the SoftAP DHCP server always comes up.
  WiFi.softAPConfig(IPAddress(192, 168, 4, 1), IPAddress(192, 168, 4, 1), IPAddress(255, 255, 255, 0));

  Serial.print("Hosting WiFi Network: ");
  Serial.println(ssid);
  Serial.print("SoftAP started: ");
  Serial.println(apOk ? "OK" : "FAILED");
  Serial.print("ESP32 IP Address: ");
  Serial.println(WiFi.softAPIP());

  if (udp.listen(udpPort)) {
    Serial.println("UDP Listening on port " + String(udpPort));
    
    udp.onPacket([](AsyncUDPPacket packet) {
      piIP = packet.remoteIP();
      hasPiIP = true;
      uint8_t* data = packet.data();
      size_t len = packet.length();
      
      // Video Frame Format: 'V', ' ', ('L' or 'R'), ' ', <1024 bytes binary>
      if (len >= 1028 && data[0] == 'V' && data[1] == ' ' && data[3] == ' ') {
        char eye = data[2];
        if (eye == 'L') {
          memcpy(leftBuffer, data + 4, 1024);
          newLeftFrame = true;
        } else if (eye == 'R') {
          memcpy(rightBuffer, data + 4, 1024);
          newRightFrame = true;
        }
        lastHeartbeat = millis();
        currentState = ST_VIDEO_STREAM;
      } else {
        // Safe string parsing for standard text commands
        size_t msgLen = 0;
        char msg[128];
        for (size_t i = 0; i < len && i < sizeof(msg) - 1; i++) {
          if (data[i] == 0 || data[i] == '\n') break;
          msg[msgLen++] = (char)data[i];
        }
        msg[msgLen] = '\0';
        
        if (strncmp(msg, "TXT ", 4) == 0 || strncmp(msg, "TEXT ", 5) == 0 || strncmp(msg, "WORDS ", 6) == 0) {
          char* first_sp = strchr(msg, ' ');
          if (first_sp) {
            char* rest = first_sp + 1;
            char* second_sp = strchr(rest, ' ');
            if (second_sp) {
              *second_sp = '\0';
              leftWord = String(rest);
              rightWord = String(second_sp + 1);
              rightWord.trim();
            } else {
              leftWord = String(rest);
              rightWord = String(rest);
            }
          }
          currentState = ST_BOLD_TEXT;
          lastHeartbeat = millis();
          Serial.println("Bold text set - L: " + leftWord + " | R: " + rightWord);
        } else if (strncmp(msg, "S ", 2) == 0) {
          if (msgLen > 2) {
            currentState = parseState(msg + 2);
            lastHeartbeat = millis();
            Serial.print("State updated: ");
            Serial.println(msg + 2);
          }
        } else if (msg[0] == 'H') {
          lastHeartbeat = millis();
        }
      }
    });
  }
}

void drawCenteredBoldText(U8G2 &display, const String &word) {
  // Use large bold font (18pt Helvetica Bold, with fallbacks for long words)
  display.setFont(u8g2_font_helvB18_tr);
  int text_w = display.getStrWidth(word.c_str());
  if (text_w > 120) {
    display.setFont(u8g2_font_helvB14_tr);
    text_w = display.getStrWidth(word.c_str());
  }
  if (text_w > 120) {
    display.setFont(u8g2_font_8x13B_tr);
    text_w = display.getStrWidth(word.c_str());
  }
  int x = max(0, (128 - text_w) / 2);
  int y = 42; // Vertically centered baseline for ~18px font on 64px display

  // Cyberpunk corner HUD reticle brackets
  display.drawLine(2, 2, 10, 2);
  display.drawLine(2, 2, 2, 10);
  display.drawLine(125, 2, 117, 2);
  display.drawLine(125, 2, 125, 10);
  display.drawLine(2, 61, 10, 61);
  display.drawLine(2, 61, 2, 53);
  display.drawLine(125, 61, 117, 61);
  display.drawLine(125, 61, 125, 53);

  display.drawStr(x, y, word.c_str());
}

void drawLeftEye() {
  if (currentState == ST_VIDEO_STREAM) {
    if (newLeftFrame) {
      u8g2_left.firstPage();
      do {
        u8g2_left.drawXBM(0, 0, 128, 64, leftBuffer);
      } while (u8g2_left.nextPage());
      newLeftFrame = false;
    }
    return;
  }

  if (currentState == ST_BOLD_TEXT) {
    u8g2_left.firstPage();
    do {
      drawCenteredBoldText(u8g2_left, leftWord);
    } while (u8g2_left.nextPage());
    return;
  }

  u8g2_left.firstPage();
  do {
    u8g2_left.setFont(u8g2_font_8x13B_tr);
    u8g2_left.drawStr(0, 15, "L-OPTIK v1");
    
    if (millis() - lastHeartbeat > 5000) {
      u8g2_left.drawStr(0, 35, "LINK LOST");
    } else {
      u8g2_left.drawStr(0, 35, stateToStr(currentState));
    }
  } while (u8g2_left.nextPage());
}

void drawRightEye() {
  if (currentState == ST_VIDEO_STREAM) {
    if (newRightFrame) {
      u8g2_right.firstPage();
      do {
        u8g2_right.drawXBM(0, 0, 128, 64, rightBuffer);
      } while (u8g2_right.nextPage());
      newRightFrame = false;
    }
    return;
  }

  if (currentState == ST_BOLD_TEXT) {
    u8g2_right.firstPage();
    do {
      drawCenteredBoldText(u8g2_right, rightWord);
    } while (u8g2_right.nextPage());
    return;
  }

  u8g2_right.firstPage();
  do {
    u8g2_right.setFont(u8g2_font_8x13B_tr);
    u8g2_right.drawStr(0, 15, "R-OPTIK v1");
    
    if (millis() - lastHeartbeat > 5000) {
      u8g2_right.drawStr(0, 35, "NO SIGNAL");
    } else {
      // Example of drawing something different on the right eye based on state
      if (currentState == ST_TARGET_LOCK) {
        u8g2_right.drawCircle(64, 32, 20);
        u8g2_right.drawLine(64, 0, 64, 64);
        u8g2_right.drawLine(0, 32, 128, 32);
      } else {
        u8g2_right.drawStr(0, 35, "SYS NORMAL");
      }
    }
  } while (u8g2_right.nextPage());
}

unsigned long lastTextDraw = 0;
unsigned long lastVisorLedUpdate = 0;

// Maelstrom visor LEDs. They only ever emit red; the state changes how the red
// behaves (breathing glow, fast alert blink, off for blackout/stealth).
void updateVisorLEDs() {
  unsigned long t = millis();
  int r;
  if (currentState == ST_BLACKOUT) {
    r = 0;                                      // stealth / blackout: dark
    estimatedVisorMA = 40;                      // low-power idle draw
  } else if (currentState == ST_ALERT || currentState == ST_TARGET_LOCK) {
    r = ((t / 90) % 2 == 0) ? 230 : 0;          // aggressive fast blink
    uint16_t ledMA = (uint16_t)((NUM_VISOR_LEDS * (uint32_t)r * 20UL) / 255UL);
    estimatedVisorMA = 160 + ledMA;
  } else if (t - lastHeartbeat > 5000) {
    r = 50;                                     // link lost: dim steady ember
    uint16_t ledMA = (uint16_t)((NUM_VISOR_LEDS * (uint32_t)r * 20UL) / 255UL);
    estimatedVisorMA = 160 + ledMA;
  } else {
    r = 40 + (int)(90 + 90 * sin(t / 600.0));   // breathing menace ~40..220
    uint16_t ledMA = (uint16_t)((NUM_VISOR_LEDS * (uint32_t)r * 20UL) / 255UL);
    estimatedVisorMA = 160 + ledMA;
  }
  for (int i = 0; i < NUM_VISOR_LEDS; i++) {
    visorLeds.setPixelColor(i, visorLeds.Color(r, 0, 0));   // red only, always
  }
  visorLeds.show();
}

void loop() {
  // Throttled LED refresh so the glow animates smoothly in every mode.
  if (millis() - lastVisorLedUpdate >= 20) {
    lastVisorLedUpdate = millis();
    updateVisorLEDs();
  }

  // Periodic Power Telemetry report to Pi over UDP (1 Hz)
  static unsigned long lastPowerReport = 0;
  if (millis() - lastPowerReport >= 1000) {
    lastPowerReport = millis();
    char pwrMsg[32];
    snprintf(pwrMsg, sizeof(pwrMsg), "PWR %u\n", estimatedVisorMA);
    if (hasPiIP) {
      udp.writeTo((const uint8_t*)pwrMsg, strlen(pwrMsg), piIP, udpPort);
    } else {
      udp.broadcastTo(pwrMsg, udpPort);
    }
  }

  if (currentState == ST_VIDEO_STREAM) {
    // Draw fresh frames as soon as they arrive; the draw calls early-return
    // when there is no new buffer, so this loop can run hot.
    drawLeftEye();
    drawRightEye();
    delay(2);
  } else {
    // Text mode only changes on state updates / heartbeat timeout, so
    // throttle redraws instead of hammering I2C 500 times a second.
    if (millis() - lastTextDraw > 250) {
      lastTextDraw = millis();
      drawLeftEye();
      drawRightEye();
    }
    delay(10);
  }
}
