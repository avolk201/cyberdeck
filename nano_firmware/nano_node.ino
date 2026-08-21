#include <Adafruit_NeoPixel.h>

#define NODE_ID 1
#define PIN_LEDS 6
#define NUM_LEDS 12
#define MAX_MA 500
#define MA_PER_PX 60

Adafruit_NeoPixel strip(NUM_LEDS, PIN_LEDS, NEO_GRB + NEO_KHZ800);

String currentState = "BOOT";
int masterBrightness = 255;
unsigned long lastComms = 0;

void setup() {
  Serial.begin(115200);
  strip.begin();
  strip.show();
}

void loop() {
  if (Serial.available() > 0) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.startsWith("S ")) {
      currentState = line.substring(2);
      lastComms = millis();
    } else if (line.startsWith("B ")) {
      masterBrightness = line.substring(2).toInt();
    }
  }

  if (millis() - lastComms > 30000) {
    currentState = "IDLE"; // Autonomous fallback
  }

  // Very basic effects
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
