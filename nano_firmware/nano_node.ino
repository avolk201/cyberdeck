#include <Adafruit_NeoPixel.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

#define NODE_ID 1
#define PIN_LEDS 6
#define NUM_LEDS 12
#define MAX_MA 500
#define MA_PER_PX 60

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

Adafruit_NeoPixel strip(NUM_LEDS, PIN_LEDS, NEO_GRB + NEO_KHZ800);

String currentState = "BOOT";
int masterBrightness = 255;
unsigned long lastComms = 0;

void setup() {
  Serial.begin(115200);
  
  strip.begin();
  strip.show();

  if(!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println(F("SSD1306 allocation failed"));
  }
  display.clearDisplay();
  display.setTextSize(2);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println("BOOTING...");
  display.display();
}

void updateOLED() {
  display.clearDisplay();
  
  // Header
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.print("CYBERDECK OS v1.0");
  display.drawLine(0, 10, 128, 10, SSD1306_WHITE);

  // Status
  display.setTextSize(2);
  display.setCursor(0, 20);
  
  if (currentState == "IDLE") {
    display.println("SECURE");
  } else if (currentState == "ALERT") {
    display.println("!! ALERT !!");
  } else if (currentState == "SCANNING") {
    display.println("SCANNING...");
  } else if (currentState == "RUNNING") {
    display.println("EXEC RUN");
  } else if (currentState == "BLACKOUT") {
    display.println("BLACKOUT");
  } else {
    display.println(currentState);
  }

  // Footer (Uptime or connection status)
  display.setTextSize(1);
  display.setCursor(0, 50);
  if (millis() - lastComms > 30000) {
    display.print("SYS: OFFLINE");
  } else {
    display.print("SYS: ONLINE");
  }

  display.display();
}

void loop() {
  bool stateChanged = false;

  if (Serial.available() > 0) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.startsWith("S ")) {
      String newState = line.substring(2);
      if (newState != currentState) {
        currentState = newState;
        stateChanged = true;
      }
      lastComms = millis();
    } else if (line.startsWith("B ")) {
      masterBrightness = line.substring(2).toInt();
    }
  }

  if (millis() - lastComms > 30000 && currentState != "IDLE") {
    currentState = "IDLE"; // Autonomous fallback
    stateChanged = true;
  }

  // Update OLED if state changed (or periodically if we wanted)
  static unsigned long lastDisplayUpdate = 0;
  if (stateChanged || millis() - lastDisplayUpdate > 1000) {
    updateOLED();
    lastDisplayUpdate = millis();
  }

  // Very basic LED effects
  if (currentState == "BOOT") {
    strip.fill(strip.Color(0, 50, 0));
  } else if (currentState == "IDLE") {
    strip.fill(strip.Color(0, 10, 0));
  } else if (currentState == "ALERT") {
    if ((millis() / 100) % 2 == 0) {
      strip.fill(strip.Color(255, 0, 0));
    } else {
      strip.fill(strip.Color(0, 0, 0));
    }
  } else if (currentState == "BLACKOUT") {
    strip.fill(strip.Color(0, 0, 0));
  } else {
    strip.fill(strip.Color(0, 20, 20));
  }

  strip.setBrightness(masterBrightness);
  strip.show();
  delay(20);
}
