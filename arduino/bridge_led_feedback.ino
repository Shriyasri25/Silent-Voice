/*
  Silent Voice — Bridge/RPC ambient LED feedback (Arduino UNO Q)

  IMPORTANT: The Arduino UNO Q's dual MCU (STM32) + MPU (QRB2210) Bridge RPC
  API is new hardware — verify the exact function names against the official
  Arduino UNO Q Bridge documentation at the venue before relying on this.
  The pattern below (Bridge.begin() + a shared variable the MPU-side Python
  can read/write) matches the classic Arduino Bridge library pattern used on
  Yun-style boards; UNO Q's exact API may differ slightly.

  Concept: the AI PC or MPU-side Python script calls into the MCU to set an
  LED brightness value (0-255) reflecting detected expression/urgency —
  a visible "the system is alive and reacting" cue for judges standing at
  your table, independent of the spoken output.

  Wiring: one LED (with a ~220ohm resistor) from a PWM-capable pin to GND.
*/

#include <Bridge.h>   // Verify this header name against UNO Q's actual SDK

const int LED_PIN = 9;  // any PWM-capable pin

void setup() {
  Bridge.begin();
  pinMode(LED_PIN, OUTPUT);
}

void loop() {
  // Read a brightness value the Python/MPU side has written via Bridge,
  // e.g. bridge.call("set_brightness", value) on the Linux side, or
  // Bridge.get("brightness") depending on the confirmed UNO Q API.
  int brightness = 40;  // placeholder default while API is being confirmed

  // Example if UNO Q exposes a key-value bridge store:
  // String val = Bridge.get("brightness");
  // if (val.length() > 0) brightness = val.toInt();

  analogWrite(LED_PIN, constrain(brightness, 0, 255));
  delay(100);
}
