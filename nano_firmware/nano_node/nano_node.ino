#include <Adafruit_NeoPixel.h>
#include <Wire.h>
#include <U8g2lib.h>

#define NODE_ID 1
#define PIN_LEDS_STRIP 6
#define NUM_LEDS_STRIP 120

#define PIN_LEDS_MATRIX 7
#define NUM_LEDS_MATRIX 64

#define PIN_SWITCH 12
#define PIN_HR_SENSOR A0

#define MAX_MA 500
#define MA_PER_PX 60

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64

// Page buffer mode (1): Uses only 128 bytes of RAM!
U8G2_SSD1306_128X64_NONAME_1_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE);

Adafruit_NeoPixel strip(NUM_LEDS_STRIP, PIN_LEDS_STRIP, NEO_GRB + NEO_KHZ800);
Adafruit_NeoPixel matrix(NUM_LEDS_MATRIX, PIN_LEDS_MATRIX, NEO_GRB + NEO_KHZ800);

char currentState[24] = "BOOT";
int masterBrightness = 255;
unsigned long lastComms = 0;

bool customMatrixGlitch = false;
byte customMatrixBuffer[8] = {0};
bool oledConnected = false;

int hrBpm = 0;
unsigned long lastHrUpdate = 0;

// 8x8 matrix bitmaps. Byte k = row k; bit j of byte k = pixel (row k, col j),
// LSB = leftmost column, matching the custom-draw buffer layout. Generated from
// ASCII art and round-trip verified (see tests/nano_fx_math.cpp).
const uint8_t MAT_CYBER_SKULL[8] = { 0x7E, 0xFF, 0xBD, 0xBD, 0xE7, 0x7E, 0x24, 0x3C };
const uint8_t MAT_HEART_PULSE[8] = { 0x66, 0xFF, 0xFF, 0xFF, 0x7E, 0x3C, 0x18, 0x00 };
const uint8_t MAT_CROSSHAIR[8]   = { 0x18, 0x18, 0x00, 0xC3, 0xC3, 0x00, 0x18, 0x18 };
const uint8_t MAT_DIAMOND_HUD[8] = { 0x18, 0x3C, 0x7E, 0xFF, 0xFF, 0x7E, 0x3C, 0x18 };
const uint8_t MAT_BIOHAZARD[8]   = { 0x66, 0xDB, 0x3C, 0x7E, 0x66, 0x24, 0x42, 0x00 };

void setup() {
  Serial.begin(115200);

  pinMode(PIN_SWITCH, INPUT);
  pinMode(PIN_HR_SENSOR, INPUT);

  // Configure I2C address and bus clock BEFORE begin
  u8g2.setI2CAddress(0x3C * 2); // 8-bit address: 0x3C << 1 = 0x78
  u8g2.setBusClock(400000);
  u8g2.begin();
  
  oledConnected = true;
  u8g2.firstPage();
  do {
    u8g2.setFont(u8g2_font_5x7_tr);
    u8g2.drawStr(10, 30, "BOOTING...");
  } while ( u8g2.nextPage() );

  strip.begin();
  strip.show();
  
  matrix.begin();
  matrix.show();
}

void drawCustomEffect(const char* fx) {
  u8g2.setFont(u8g2_font_5x7_tr);
  unsigned long t = millis();
  
  if (strstr(fx, "NETRUNNER_HUD")) {
    u8g2.setCursor(4, 10); u8g2.print(F("NETRUNNER HUD"));
    u8g2.drawLine(0, 14, 128, 14);
    u8g2.setCursor(80, 26); u8g2.print(F("LINK: 85%"));
    u8g2.setCursor(80, 38); u8g2.print(F("LAT: 12ms"));
    int cpu = (t / 400) % 30 + 10;
    u8g2.setCursor(80, 50); u8g2.print(F("CPU: ")); u8g2.print(cpu); u8g2.print(F("%"));
    int actX = (t / 20) % 128;
    u8g2.drawLine(0, 60, 128, 60);
    u8g2.drawBox(actX, 58, 8, 5);
    
  } else if (strstr(fx, "SYSTEM_VITALS")) {
    u8g2.setCursor(4, 10); u8g2.print(F("HR: ")); u8g2.print(hrBpm > 0 ? hrBpm : 138); u8g2.print(F(" BPM"));
    u8g2.setCursor(4, 22); u8g2.print(F("SURGE: 88%"));
    u8g2.drawFrame(100, 0, 28, 64);
    u8g2.setCursor(104, 30); u8g2.print(F("BPM"));
    for (int x = 0; x < 90; x += 2) {
      int y = 52 + (int)(sin((t / 80.0) + (x / 6.0)) * 8.0 * (sin(x / 20.0) > 0 ? 1 : 0));
      u8g2.drawPixel(x, y);
    }
    
  } else if (strstr(fx, "DIAGNOSTICS")) {
    u8g2.setCursor(4, 10); u8g2.print(F("SYS DIAGNOSTICS // V1"));
    u8g2.drawLine(0, 12, 128, 12);
    const char* mods[] = {"NEURAL", "OPTICS", "SANDY", "ICE"};
    int vals[] = {98, 100, 92, 85};
    for(int i=0; i<4; i++) {
      int y = 24 + i*11;
      u8g2.setCursor(4, y); u8g2.print(mods[i]);
      u8g2.drawFrame(54, y-6, 50, 7);
      u8g2.drawBox(54, y-6, vals[i]/2, 7);
    }
    
  } else if (strstr(fx, "FREQ_TUNER")) {
    u8g2.setCursor(10, 10); u8g2.print(F("RF SPECTRAL TUNER"));
    for(int i=0; i<16; i++) {
      int h = (int)(abs(sin((t / 300.0) + i*0.5)) * 32.0);
      u8g2.drawBox(8 + i*7, 60 - h, 5, h);
    }
    
  } else if (strstr(fx, "NEURAL_MESH")) {
    u8g2.setCursor(4, 10); u8g2.print(F("NEURAL MESH // ACTIVE"));
    // 8 nodes drifting on Lissajous orbits around a 4x2 grid of anchors, joined
    // into a mesh. Float math + clamping keeps every node on the 128x64 canvas;
    // the old `int` version overflowed 16-bit on the AVR (seed*i*17 wraps
    // negative) and drew off-screen, so the effect looked dead.
    const int NODES = 8;
    int nx[NODES], ny[NODES];
    for (int i = 0; i < NODES; i++) {
      float phase = (t / 900.0) + i * 0.7854;      // 2*PI / 8 spacing
      float cx = 18.0 + (i % 4) * 31.0;            // 4 anchor columns
      float cy = 28.0 + (i / 4) * 20.0;            // 2 anchor rows
      int x = (int)(cx + cos(phase) * 10.0);
      int y = (int)(cy + sin(phase * 1.4) * 8.0);
      if (x < 2) x = 2; else if (x > 125) x = 125;
      if (y < 18) y = 18; else if (y > 61) y = 61;
      nx[i] = x; ny[i] = y;
    }
    // Ring of links plus a few cross-links for a mesh look.
    for (int i = 0; i < NODES; i++) {
      u8g2.drawLine(nx[i], ny[i], nx[(i + 1) % NODES], ny[(i + 1) % NODES]);
      if (i % 2 == 0) u8g2.drawLine(nx[i], ny[i], nx[(i + 3) % NODES], ny[(i + 3) % NODES]);
    }
    // Nodes drawn last so they sit on top of the links.
    for (int i = 0; i < NODES; i++) u8g2.drawDisc(nx[i], ny[i], 2);
    
  } else if (strstr(fx, "DATA_STREAM")) {
    u8g2.setCursor(4, 10); u8g2.print(F("HEX DUMP // BUFFER"));
    int seed = (t / 150) % 255;
    for(int i=0; i<4; i++) {
      u8g2.setCursor(4, 24 + i*10);
      u8g2.print(F("0x")); u8g2.print(1000 + i*16 + seed, HEX);
      u8g2.print(F(" ")); u8g2.print((seed * 11 + i) & 0xFF, HEX);
      u8g2.print(F(" ")); u8g2.print((seed * 17 + i) & 0xFF, HEX);
      u8g2.print(F(" ")); u8g2.print((seed * 23 + i) & 0xFF, HEX);
    }
    
  } else if (strstr(fx, "SECURITY_ICE")) {
    u8g2.setCursor(4, 10); u8g2.print(F("BREACH PROTOCOL"));
    int actRow = (t / 400) % 4;
    int actCol = (t / 200) % 6;
    for(int r=0; r<4; r++) {
      for(int c=0; c<6; c++) {
        if (r == actRow && c == actCol) {
          u8g2.drawBox(10 + c*18, 20 + r*11 - 7, 14, 9);
          u8g2.setDrawColor(0);
          u8g2.setCursor(11 + c*18, 20 + r*11); u8g2.print(F("FF"));
          u8g2.setDrawColor(1);
        } else {
          u8g2.setCursor(11 + c*18, 20 + r*11);
          u8g2.print(((r*6+c) % 2 == 0) ? F("1C") : F("55"));
        }
      }
    }
    
  } else if (strstr(fx, "BATTERY_GAUGE")) {
    u8g2.setCursor(6, 10); u8g2.print(F("20Ah BATTERY TELEMETRY"));
    u8g2.drawFrame(6, 16, 116, 18);
    u8g2.drawBox(8, 18, 112 * 0.85, 14);
    u8g2.setCursor(6, 46); u8g2.print(F("DRAW: ~11W"));
    u8g2.setCursor(72, 46); u8g2.print(F("CUR: 2.2A"));
    u8g2.setCursor(6, 58); u8g2.print(F("REM: ~6H 30M"));
    
  } else if (strstr(fx, "OFFLINE_STATE")) {
    u8g2.setCursor(10, 15); u8g2.print(F("SYS OFFLINE // NO CARRIER"));
    u8g2.drawLine(0, 32, 128, 32);
    if ((t / 500) % 2 == 0) {
      u8g2.setCursor(45, 50); u8g2.print(F("REBOOT?"));
    }
    
  } else if (strstr(fx, "COMBAT_BIOMON")) {
    u8g2.setCursor(4, 10); u8g2.print(F("TARGET LOCK // BIOMON"));
    u8g2.drawCircle(64, 40, 16);
    u8g2.drawLine(64, 20, 64, 60);
    u8g2.drawLine(44, 40, 84, 40);
    u8g2.setCursor(90, 35); u8g2.print(F("HR: ")); u8g2.print(hrBpm > 0 ? hrBpm : 120);
    u8g2.setCursor(90, 45); u8g2.print(F("ADR: 90%"));
    
  } else if (strstr(fx, "RF_SCANNER")) {
    u8g2.setCursor(10, 10); u8g2.print(F("RF SWEEP // 2.4GHz"));
    u8g2.drawCircle(64, 40, 20);
    float angle = (t / 500.0);
    int ex = 64 + (int)(cos(angle) * 20);
    int ey = 40 + (int)(sin(angle) * 20);
    u8g2.drawLine(64, 40, ex, ey);
    
  } else if (strstr(fx, "RAM_ALLOCATOR")) {
    u8g2.setCursor(4, 10); u8g2.print(F("KERNEL MEMORY MATRIX"));
    // Bounded seed: the old `(t / 250)` grew without limit and would overflow a
    // 16-bit int after ~9 hours of uptime.
    int seed = (int)((t / 250) % 256);
    for(int y=0; y<4; y++) {
      for(int x=0; x<16; x++) {
        if ((seed + x*y) % 3 == 0) {
          u8g2.drawBox(4 + x*7, 20 + y*9, 6, 7);
        } else {
          u8g2.drawFrame(4 + x*7, 20 + y*9, 6, 7);
        }
      }
    }
    
  } else if (strstr(fx, "OPTICS_CAMO")) {
    u8g2.setCursor(4, 10); u8g2.print(F("OPTICAL CAMO // ACTIVE"));
    // Shimmering particle field. Unsigned 32-bit hashing stays in bounds; the
    // old `int` version overflowed 16-bit and drew off-screen.
    unsigned long s = (t / 120);
    for (int i = 0; i < 120; i++) {
      unsigned long h = (s * 31UL) + (unsigned long)i * 1013UL;
      h ^= (h << 3);
      int px = (int)(h % 128UL);
      int py = 18 + (int)((h / 128UL) % 44UL);
      u8g2.drawPixel(px, py);
    }
    
  } else if (strstr(fx, "CYBERWARE_LINK")) {
    u8g2.setCursor(4, 10); u8g2.print(F("CYBERWARE NEURAL BUS"));
    u8g2.drawLine(0, 12, 128, 12);
    u8g2.setCursor(4, 24); u8g2.print(F("SYNAPTIC   SYNCED"));
    u8g2.setCursor(4, 38); u8g2.print(F("SANDEVISTAN NOMINAL"));
    u8g2.setCursor(4, 52); u8g2.print(F("BIOMON     100% OK"));
    
  } else if (strstr(fx, "BLACKWALL_LOG")) {
    u8g2.setCursor(4, 10); u8g2.print(F(">> BLACKWALL LOG <<"));
    const char* logs[] = {"0x88F: VOID_BREACH", "0x91C: MEM_CORRUPT", "0xA04: ICE_INTRUSION", "0xBF2: TRACE_ACTIVE"};
    int glitchRow = (t / 300) % 4;
    for(int i=0; i<4; i++) {
      u8g2.setCursor(4, 22 + i*10);
      if (i == glitchRow) {
        u8g2.print(F("0x???: #######!@"));
      } else {
        u8g2.print(logs[i]);
      }
    }
    
  } else if (strncmp(fx, "SUIT_", 5) == 0) {
    u8g2.setCursor(0, 26);
    const char* s = fx + 5;
    for (int i = 0; s[i] != '\0'; i++) {
      if (s[i] == '_') u8g2.print(' ');
      else u8g2.print(s[i]);
    }
    u8g2.setCursor(0, 38); u8g2.print(F("SANDEVISTAN // SYNCED"));
    int sweep = (t / 20) % 128;
    u8g2.drawLine(sweep, 42, sweep, 50);
  } else {
    // Fallback if missing
    u8g2.setCursor(0, 26);
    const char* s = strncmp(fx, "MC_", 3) == 0 ? fx + 3 : fx;
    for (int i = 0; s[i] != '\0'; i++) {
      if (s[i] == '_') u8g2.print(' ');
      else u8g2.print(s[i]);
    }
  }
}

void updateOLED() {
  if (!oledConnected) return;

  u8g2.firstPage();
  do {
    if (strncmp(currentState, "MC_", 3) == 0 || strncmp(currentState, "SUIT_", 5) == 0) {
      // Custom effects own the full 128x64 canvas
      drawCustomEffect(currentState);
    } else {
      // Standard System Status Screens (with Header & Footer)
      u8g2.setFont(u8g2_font_5x7_tr);
      u8g2.drawStr(0, 10, "CYBERDECK OS v1.0");
      u8g2.drawLine(0, 12, 128, 12);
    
      if (strcmp(currentState, "IDLE") == 0) {
        u8g2.drawStr(0, 32, "BIOMON: OK");
        if (hrBpm > 0) {
          u8g2.setCursor(0, 48);
          u8g2.print(hrBpm);
          u8g2.print(F(" BPM"));
          int r = (millis() / 250) % 4 + 2;
          u8g2.drawDisc(108, 38, r);
        } else {
          u8g2.drawStr(0, 48, "STANDBY");
          int r = (millis() / 200) % 5 + 2;
          u8g2.drawDisc(108, 38, r);
        }
      } else if (strcmp(currentState, "ALERT") == 0) {
        u8g2.drawStr(0, 35, "!! ALERT !!");
        if ((millis() / 150) % 2 == 0) {
          u8g2.drawBox(0, 45, 128, 5);
        }
      } else if (strcmp(currentState, "TARGET_LOCK") == 0) {
        u8g2.drawStr(0, 32, "TARGET LOCK");
        u8g2.drawCircle(100, 35, 12);
        u8g2.drawLine(100, 20, 100, 50);
        u8g2.drawLine(85, 35, 115, 35);
      } else if (strcmp(currentState, "COOLDOWN") == 0) {
        u8g2.drawStr(0, 35, "PURGE ICE");
        int fill_w = (millis() / 50) % 120;
        u8g2.drawFrame(0, 45, 120, 6);
        u8g2.drawBox(2, 47, fill_w, 2);
      } else if (strcmp(currentState, "SCANNING") == 0) {
        u8g2.drawStr(0, 35, "SCANNING RF");
        int offset = (millis() / 10) % 128;
        u8g2.drawLine(offset, 15, offset, 45);
      } else if (strcmp(currentState, "RUNNING") == 0) {
        u8g2.drawStr(0, 35, "EXEC RUN");
        for(int i=0; i<5; i++) {
          int h = (millis() / 50 + i*10) % 20;
          u8g2.drawBox(90 + i*6, 45 - h, 4, h);
        }
      } else if (strcmp(currentState, "BLACKOUT") == 0 || masterBrightness == 0) {
        // Blank display for blackout & stealth power saving
        u8g2.setFont(u8g2_font_5x7_tr);
        u8g2.drawStr(20, 35, "[ STEALTH / CAMO ]");
      } else if (strncmp(currentState, "MATRIX_", 7) == 0) {
        // Friendly label for the 8x8 patterns instead of the raw state string.
        u8g2.drawStr(0, 28, "LED MATRIX:");
        u8g2.setCursor(0, 42);
        const char* s = currentState + 7;
        for (int i = 0; s[i] != '\0'; i++) u8g2.print(s[i] == '_' ? ' ' : s[i]);
      } else {
        u8g2.drawStr(0, 35, currentState);
      }
    
      // Footer
      u8g2.setFont(u8g2_font_5x7_tr);
      if (millis() - lastComms > 30000) {
        u8g2.drawStr(0, 60, "SYS: OFFLINE");
      } else {
        u8g2.drawStr(0, 60, "SYS: ONLINE");
      }
    }
  } while ( u8g2.nextPage() );
}

// ---------------------------------------------------------------------------
// 8x8 LED-matrix pattern renderers.
// Every helper keeps all math bounded (no 16-bit overflow) so coordinates can
// never run off the 64-pixel panel. Index = row*8 + col (row-major).
// ---------------------------------------------------------------------------

void drawMatrixBitmap(const uint8_t* bmp, uint8_t r, uint8_t g, uint8_t b) {
  for (int i = 0; i < 64; i++) {
    if (bmp[i / 8] & (1 << (i % 8))) matrix.setPixelColor(i, matrix.Color(r, g, b));
    else matrix.setPixelColor(i, matrix.Color(0, 0, 0));
  }
}

void drawMatrixBitmapPulse(const uint8_t* bmp, unsigned long t, uint8_t r, uint8_t g, uint8_t b) {
  float f = 0.55 + 0.45 * (0.5 + 0.5 * sin(t / 450.0));   // gentle 0.55..1.0 pulse
  drawMatrixBitmap(bmp, (uint8_t)(r * f), (uint8_t)(g * f), (uint8_t)(b * f));
}

void matRadarSweep(unsigned long t) {
  matrix.fill(matrix.Color(0, 8, 0));
  int col = (int)((t / 90) % 8);
  for (int r = 0; r < 8; r++) matrix.setPixelColor(r * 8 + col, matrix.Color(0, 255, 120));
  for (int k = 1; k <= 3; k++) {                          // fading trail behind the sweep
    int c = (col - k + 8) % 8;
    for (int r = 0; r < 8; r++) matrix.setPixelColor(r * 8 + c, matrix.Color(0, 70 - k * 20, 30 - k * 8));
  }
}

void matRainCascade(unsigned long t) {
  matrix.fill(matrix.Color(0, 0, 0));
  for (int c = 0; c < 8; c++) {
    unsigned long speed = 60 + (c % 4) * 25;              // per-column fall speed
    int head = (int)(((t / speed) + c * 3) % 8);
    for (int k = 0; k < 4; k++) {                         // head + short tail
      int r = (head - k + 8) % 8;
      matrix.setPixelColor(r * 8 + c, matrix.Color(0, 200 - k * 55, k == 0 ? 60 : 0));
    }
  }
}

void matSignalBars(unsigned long t) {
  matrix.fill(matrix.Color(0, 0, 0));
  for (int c = 0; c < 8; c++) {
    int h = 1 + (int)(abs(sin((t / 300.0) + c * 0.7)) * 7);   // 1..8
    if (h > 8) h = 8;
    for (int r = 0; r < h; r++) matrix.setPixelColor((7 - r) * 8 + c, matrix.Color(0, 180, 40));
  }
}

void matFirewallIce(unsigned long t) {
  matrix.fill(matrix.Color(0, 0, 0));
  for (int c = 0; c < 8; c++) {
    int h = 3 + (int)(((unsigned long)c * 37 + (t / 200)) % 5);   // 3..7
    for (int r = 0; r < h; r++) matrix.setPixelColor((7 - r) * 8 + c, matrix.Color(0, 120, 200));
    if (((t / 100) + c) % 3 == 0) {                               // flickering cap block
      int row = 7 - h;
      if (row >= 0) matrix.setPixelColor(row * 8 + c, matrix.Color(0, 255, 255));
    }
  }
}

void matHexDump(unsigned long t) {
  matrix.fill(matrix.Color(0, 0, 0));
  unsigned long s = (t / 150);
  for (int i = 0; i < 24; i++) {
    unsigned long h = (s * 31UL) + (unsigned long)i * 1013UL;
    h ^= (h << 3);
    int c = (int)(h % 8UL);
    int r = (int)((h / 8UL) % 8UL);
    matrix.setPixelColor(r * 8 + c, matrix.Color(0, 200, 60));
  }
}

void matSandevistan(unsigned long t) {
  matrix.fill(matrix.Color(4, 0, 0));
  for (int r = 0; r < 8; r++) {
    unsigned long speed = 20 + (r % 3) * 12;
    int col = (int)(((t / speed) + r * 5) % 8);
    for (int k = 0; k < 4; k++) {                          // fast horizontal streaks
      int c = (col - k + 8) % 8;
      matrix.setPixelColor(r * 8 + c, matrix.Color(255 - k * 60, 0, k == 0 ? 40 : 0));
    }
  }
}

void matLightning(unsigned long t) {
  matrix.fill(matrix.Color(0, 0, 4));
  unsigned long s = (t / 70);
  int x = 3 + (int)(s % 3);                               // wobbling bolt column
  for (int r = 0; r < 8; r++) {
    matrix.setPixelColor(r * 8 + x, matrix.Color(120, 160, 255));
    if ((s + r) % 2 == 0) x = (x + 1) % 8;
  }
  if ((t / 300) % 5 == 0) {                               // occasional bright sparks
    for (int i = 0; i < 10; i++) {
      unsigned long h = (s * 17UL) + (unsigned long)i * 999UL;
      h ^= (h << 5);
      matrix.setPixelColor((int)(h % 64UL), matrix.Color(200, 220, 255));
    }
  }
}

void matSonarRing(unsigned long t) {
  matrix.fill(matrix.Color(0, 0, 0));
  int radius = (int)((t / 120) % 5);                       // Chebyshev dist max is 4
  for (int r = 0; r < 8; r++) {
    for (int c = 0; c < 8; c++) {
      int dx = abs(c - 3), dy = abs(r - 3);
      int dist = (dx > dy) ? dx : dy;
      if (dist == radius) matrix.setPixelColor(r * 8 + c, matrix.Color(0, 220, 220));
      else if (dist == ((radius + 4) % 5)) matrix.setPixelColor(r * 8 + c, matrix.Color(0, 60, 60));
    }
  }
}

void matEqualizer(unsigned long t) {
  matrix.fill(matrix.Color(0, 0, 0));
  for (int c = 0; c < 8; c++) {
    int phase = (int)(((t / 60) + c * 3) % 14);            // triangle-wave bounce
    int h = (phase < 7 ? phase : 14 - phase) + 1;          // 1..8
    for (int r = 0; r < h; r++) matrix.setPixelColor((7 - r) * 8 + c, matrix.Color(0, 100 + r * 18, 180));
  }
}

void matHeartPulse(unsigned long t) {
  bool beat = ((t / 400) % 2) == 0;
  drawMatrixBitmap(MAT_HEART_PULSE, beat ? 255 : 90, 0, 20);
}

// Dispatch a named MATRIX_* pattern. Returns false for unknown names so the
// caller can fall back. MATRIX_CUSTOM_DRAW is handled separately (it uses the
// user-drawn buffer).
bool renderMatrixFx(unsigned long t) {
  if (strcmp(currentState, "MATRIX_CYBER_SKULL") == 0)   drawMatrixBitmapPulse(MAT_CYBER_SKULL, t, 0, 255, 60);
  else if (strcmp(currentState, "MATRIX_HEART_PULSE") == 0) matHeartPulse(t);
  else if (strcmp(currentState, "MATRIX_CROSSHAIR") == 0)   drawMatrixBitmapPulse(MAT_CROSSHAIR, t, 0, 255, 255);
  else if (strcmp(currentState, "MATRIX_DIAMOND_HUD") == 0) drawMatrixBitmapPulse(MAT_DIAMOND_HUD, t, 255, 200, 0);
  else if (strcmp(currentState, "MATRIX_BIOHAZARD") == 0)   drawMatrixBitmapPulse(MAT_BIOHAZARD, t, 140, 255, 0);
  else if (strcmp(currentState, "MATRIX_RADAR_SWEEP") == 0) matRadarSweep(t);
  else if (strcmp(currentState, "MATRIX_RAIN_CASCADE") == 0) matRainCascade(t);
  else if (strcmp(currentState, "MATRIX_SIGNAL_BARS") == 0) matSignalBars(t);
  else if (strcmp(currentState, "MATRIX_FIREWALL_ICE") == 0) matFirewallIce(t);
  else if (strcmp(currentState, "MATRIX_HEX_DUMP") == 0)    matHexDump(t);
  else if (strcmp(currentState, "MATRIX_SANDEVISTAN") == 0) matSandevistan(t);
  else if (strcmp(currentState, "MATRIX_LIGHTNING") == 0)   matLightning(t);
  else if (strcmp(currentState, "MATRIX_SONAR_RING") == 0)  matSonarRing(t);
  else if (strcmp(currentState, "MATRIX_EQUALIZER") == 0)   matEqualizer(t);
  else return false;
  return true;
}

// Estimate total mA draw across both strips and scale brightness if over budget.
// Formula from outline: est = Σ(R+G+B)/765 × MA_PER_PX per pixel.
uint16_t estimatedMA = 0;

void enforceBudget() {
  uint32_t totalDraw = 0;
  for (int i = 0; i < NUM_LEDS_STRIP; i++) {
    uint32_t c = strip.getPixelColor(i);
    totalDraw += ((c >> 16) & 0xFF) + ((c >> 8) & 0xFF) + (c & 0xFF);
  }
  for (int i = 0; i < NUM_LEDS_MATRIX; i++) {
    uint32_t c = matrix.getPixelColor(i);
    totalDraw += ((c >> 16) & 0xFF) + ((c >> 8) & 0xFF) + (c & 0xFF);
  }
  // mA = totalDraw / 765 * MA_PER_PX, but avoid float:
  uint16_t estMA = (uint16_t)((totalDraw * (uint32_t)MA_PER_PX) / 765UL);
  estimatedMA = estMA;

  if (estMA > MAX_MA) {
    // Scale brightness proportionally to stay within budget
    uint8_t scale = (uint8_t)((uint32_t)MAX_MA * 255 / estMA);
    strip.setBrightness(min(masterBrightness, (int)scale));
    matrix.setBrightness(min(masterBrightness, (int)scale));
  } else {
    strip.setBrightness(masterBrightness);
    matrix.setBrightness(masterBrightness);
  }
}

void updateLEDs() {
  if (strcmp(currentState, "BOOT") == 0) {
    int b = (millis() / 10) % 80;
    strip.fill(strip.Color(0, b, 0));
    matrix.fill(matrix.Color(0, b, 0));
  } else if (strcmp(currentState, "IDLE") == 0) {
    strip.fill(strip.Color(0, 15, 0));
    matrix.fill(matrix.Color(0, 15, 0));
  } else if (strcmp(currentState, "SCANNING") == 0) {
    int pos = (millis() / 20) % NUM_LEDS_STRIP;
    strip.fill(strip.Color(0, 5, 0));
    strip.setPixelColor(pos, strip.Color(0, 255, 120));
    matrix.fill(matrix.Color(0, 20, 40));
  } else if (strcmp(currentState, "RUNNING") == 0) {
    if ((millis() / 60) % 2 == 0) {
      strip.fill(strip.Color(0, 200, 255));
      matrix.fill(matrix.Color(0, 255, 100));
    } else {
      strip.fill(strip.Color(0, 30, 60));
      matrix.fill(matrix.Color(0, 40, 10));
    }
  } else if (strcmp(currentState, "TARGET_LOCK") == 0) {
    if ((millis() / 120) % 2 == 0) {
      strip.fill(strip.Color(255, 0, 0));
      matrix.fill(matrix.Color(255, 0, 0));
    } else {
      strip.fill(strip.Color(0, 255, 255));
      matrix.fill(matrix.Color(0, 255, 255));
    }
  } else if (strcmp(currentState, "COOLDOWN") == 0) {
    int fade = max(5, 80 - (int)((millis() / 50) % 80));
    strip.fill(strip.Color(0, fade / 2, fade));
    matrix.fill(matrix.Color(0, fade / 2, fade));
  } else if (strcmp(currentState, "ALERT") == 0) {
    if ((millis() / 100) % 2 == 0) {
      strip.fill(strip.Color(255, 0, 0));
      matrix.fill(matrix.Color(255, 0, 0));
    } else {
      strip.fill(strip.Color(0, 0, 0));
      matrix.fill(matrix.Color(0, 0, 0));
    }
  } else if (strcmp(currentState, "BLACKOUT") == 0) {
    strip.fill(strip.Color(0, 0, 0));
    matrix.fill(matrix.Color(0, 0, 0));
  } else if (strcmp(currentState, "MATRIX_CUSTOM_DRAW") == 0) {
    for (int px = 0; px < 64; px++) {
      if (customMatrixBuffer[px / 8] & (1 << (px % 8))) {
        matrix.setPixelColor(px, matrix.Color(0, 255, 0));
      } else {
        matrix.setPixelColor(px, matrix.Color(0, 0, 0));
      }
    }
    if (customMatrixGlitch) {
      if (random(100) < 30) {
        int p1 = random(64);
        int p2 = random(64);
        matrix.setPixelColor(p1, matrix.Color(255, 0, 0));
        matrix.setPixelColor(p2, matrix.Color(0, 255, 255));
      }
    }
    strip.fill(strip.Color(0, 20, 20));
  } else if (strncmp(currentState, "MATRIX_", 7) == 0) {
    // Named 8x8 patterns (skull, radar, rain, ...). The sleeve strip holds a dim
    // ambient glow while the matrix shows the pattern.
    renderMatrixFx(millis());
    strip.fill(strip.Color(0, 20, 20));
  } else {
    strip.fill(strip.Color(0, 20, 20));
    matrix.fill(matrix.Color(0, 20, 20));
  }
}

void processCommandLine(const char* line, bool& stateChanged) {
  lastComms = millis(); // Refresh comms heartbeat on ANY valid command from Pi
  
  if (strncmp(line, "S ", 2) == 0) {
    const char* newState = line + 2;
    while (*newState == ' ') newState++;
    if (strcmp(currentState, newState) != 0) {
      strncpy(currentState, newState, sizeof(currentState) - 1);
      currentState[sizeof(currentState) - 1] = '\0';
      stateChanged = true;
    }
  } else if (strncmp(line, "B ", 2) == 0) {
    masterBrightness = atoi(line + 2);
  } else if (strncmp(line, "M ", 2) == 0) {
    const char* hexStr = line + 2;
    while (*hexStr == ' ') hexStr++;
    int len = strlen(hexStr);
    if (len >= 16) {
      for (int chunk = 0; chunk < 16; chunk++) {
        char c = hexStr[chunk];
        int val = 0;
        if (c >= '0' && c <= '9') val = c - '0';
        else if (c >= 'A' && c <= 'F') val = c - 'A' + 10;
        else if (c >= 'a' && c <= 'f') val = c - 'a' + 10;
        
        for (int bit = 0; bit < 4; bit++) {
          int px = chunk * 4 + bit;
          if (val & (1 << (3 - bit))) {
            customMatrixBuffer[px / 8] |= (1 << (px % 8));
          } else {
            customMatrixBuffer[px / 8] &= ~(1 << (px % 8));
          }
        }
      }
    }
  } else if (strncmp(line, "G ", 2) == 0) {
    customMatrixGlitch = (line[2] == '1');
  } else if (strncmp(line, "W ", 2) == 0) {
    hrBpm = atoi(line + 2);
    lastHrUpdate = millis();
  }
}

void loop() {
  bool stateChanged = false;

  static char serialBuffer[64];
  static int serialPos = 0;

  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (serialPos > 0) {
        serialBuffer[serialPos] = '\0';
        processCommandLine(serialBuffer, stateChanged);
        serialPos = 0;
      }
    } else if (serialPos < (int)sizeof(serialBuffer) - 1) {
      serialBuffer[serialPos++] = c;
    }
  }

  // Autonomous fallback only if totally disconnected for > 30 seconds
  if (millis() - lastComms > 30000 && strcmp(currentState, "IDLE") != 0) {
    strcpy(currentState, "IDLE");
    stateChanged = true;
  }

  // OLED Refresh (~30 FPS for active animations, 2 Hz for static status)
  static unsigned long lastDisplayUpdate = 0;
  bool isCustomFx = (strncmp(currentState, "MC_", 3) == 0 || strncmp(currentState, "SUIT_", 5) == 0);
  bool isFastSystem = (strcmp(currentState, "COOLDOWN") == 0 || strcmp(currentState, "RUNNING") == 0 || strcmp(currentState, "SCANNING") == 0);
  unsigned long refreshRate = (isCustomFx || isFastSystem) ? 33 : 500;
  
  if (stateChanged || millis() - lastDisplayUpdate >= refreshRate) {
    updateOLED();
    lastDisplayUpdate = millis();
  }

  // Sensor Reporting (20 Hz)
  static unsigned long lastSensorUpdate = 0;
  if (millis() - lastSensorUpdate >= 50) {
    int hrVal = analogRead(PIN_HR_SENSOR);
    int swVal = digitalRead(PIN_SWITCH);
    Serial.print(F("HR ")); Serial.println(hrVal);
    Serial.print(F("SW ")); Serial.println(swVal);
    Serial.print(F("MA ")); Serial.println(estimatedMA);
    lastSensorUpdate = millis();
  }

  // Dynamic Reactive LED Effects (Throttled to prevent AVR UART interrupt starvation)
  static unsigned long lastLedUpdate = 0;
  bool isLedAnimated = (strcmp(currentState, "BOOT") == 0 || strcmp(currentState, "SCANNING") == 0 || 
                        strcmp(currentState, "RUNNING") == 0 || strcmp(currentState, "TARGET_LOCK") == 0 || 
                        strcmp(currentState, "COOLDOWN") == 0 || strcmp(currentState, "ALERT") == 0 || 
                        strncmp(currentState, "MATRIX_", 7) == 0 ||
                        (strcmp(currentState, "MATRIX_CUSTOM_DRAW") == 0 && customMatrixGlitch));
  
  if (stateChanged || (isLedAnimated && millis() - lastLedUpdate >= 50)) {
    updateLEDs();
    enforceBudget();
    strip.show();
    matrix.show();
    lastLedUpdate = millis();
  }
}
