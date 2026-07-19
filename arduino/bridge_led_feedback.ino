/*
  Silent Voice — Bridge/RPC ambient LED feedback (Arduino UNO Q)

  The MPU-side Python script (main_camera.py or main_npu.py) writes the
  current expression label into a shared Bridge key called "expression"
  whenever it changes.  This MCU sketch reads that key every 100 ms and
  drives an LED at a brightness that reflects the detected emotion:

      HAPPY    → bright white pulse  (200 / 255)
      SURPRISE → medium-bright       (150 / 255)
      NEUTRAL  → dim ambient         ( 60 / 255)
      SAD      → very dim            ( 20 / 255)
      (any unknown value)            → dim ambient (60)

  This gives judges a visible at-a-glance cue that the system is live
  and reacting — independent of the spoken TTS output.

  To drive the key from Python, add one call in main_camera.py /
  main_npu.py wherever current_expression is updated, e.g.:

      import subprocess
      subprocess.Popen(["bridge-client", "put", "expression", expression])

  Or use any Bridge RPC library that exposes Bridge.put() on the MPU side.

  IMPORTANT: The Arduino UNO Q Bridge API is new hardware.  Verify the
  exact header name and method signatures against the official UNO Q SDK
  documentation at the venue.  The Bridge.begin() / Bridge.get() pattern
  below matches the classic Arduino Yún Bridge library — UNO Q's API is
  expected to be compatible but may differ in minor ways.

  Wiring: one LED (with a ~220 Ω resistor in series) from pin 9 to GND.
  Pin 9 is PWM-capable on most Arduino boards.
*/

#include <Bridge.h>   // Verify header name against the UNO Q SDK

const int LED_PIN          = 9;    // PWM-capable pin
const int POLL_INTERVAL_MS = 100;  // how often to read the Bridge key (ms)

// Brightness values per expression label (0–255 for analogWrite)
const int BRIGHTNESS_HAPPY    = 200;
const int BRIGHTNESS_SURPRISE = 150;
const int BRIGHTNESS_NEUTRAL  =  60;
const int BRIGHTNESS_SAD      =  20;
const int BRIGHTNESS_DEFAULT  =  60;  // fallback for unknown / empty key

void setup() {
  Bridge.begin();           // initialise the Bridge — blocks until ready
  pinMode(LED_PIN, OUTPUT);
  analogWrite(LED_PIN, BRIGHTNESS_DEFAULT);
}

void loop() {
  // Read the "expression" key written by the Python side.
  // Bridge.get() returns an empty String if the key has not been set yet.
  String expression = Bridge.get("expression");

  int brightness = BRIGHTNESS_DEFAULT;

  if (expression == "HAPPY") {
    brightness = BRIGHTNESS_HAPPY;
  } else if (expression == "SURPRISE") {
    brightness = BRIGHTNESS_SURPRISE;
  } else if (expression == "NEUTRAL") {
    brightness = BRIGHTNESS_NEUTRAL;
  } else if (expression == "SAD") {
    brightness = BRIGHTNESS_SAD;
  }
  // Any other value (empty string on first boot, unknown label) → default

  analogWrite(LED_PIN, constrain(brightness, 0, 255));
  delay(POLL_INTERVAL_MS);
}
