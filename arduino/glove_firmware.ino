/*
  Silent Voice — Glove Firmware (Final: 3 Flex Sensors, 8 Gestures)

  Reads 3 flex sensors on analog pins A0-A2 (Index, Middle, Ring),
  classifies each as STRAIGHT (0) or BENT (1), combines them into a
  3-bit code, and sends that code as a string ("000".."111") over
  Serial whenever it changes.

  Wiring (see README.md for full diagram):
    Index sensor  -> A0
    Middle sensor -> A1
    Ring sensor   -> A2
    Each sensor: one leg to 5V, other leg to analog pin AND to a
    10k-ohm resistor to GND (voltage divider).

  Gesture table (bit order = Index, Middle, Ring):
    000 Open Hand        -> Hello
    100 Index Bent       -> I am thirsty.
    010 Middle Bent      -> I need food.
    001 Ring Bent        -> I need medicine.
    110 Index+Middle     -> Please help me.
    101 Index+Ring       -> Please call the doctor.
    011 Middle+Ring      -> I need my wheelchair.
    111 All Bent         -> Emergency! Call my caregiver immediately.
*/

const int PIN_INDEX  = A0;
const int PIN_MIDDLE = A1;
const int PIN_RING   = A2;

// Calibrate this threshold per sensor after wiring — flex sensors vary.
// Reading ABOVE this = straight (0). Reading AT or BELOW this = bent (1).
const int BEND_THRESHOLD = 650;

String lastCode = "";
unsigned long lastSendTime = 0;
const unsigned long DEBOUNCE_MS = 150;

void setup() {
  Serial.begin(9600);
}

int bitFor(int pin) {
  int val = analogRead(pin);
  return (val <= BEND_THRESHOLD) ? 1 : 0;
}

String readGestureCode() {
  int indexBit  = bitFor(PIN_INDEX);
  int middleBit = bitFor(PIN_MIDDLE);
  int ringBit   = bitFor(PIN_RING);

  String code = "";
  code += String(indexBit);
  code += String(middleBit);
  code += String(ringBit);
  return code;
}

void loop() {
  String code = readGestureCode();
  unsigned long now = millis();

  // Only send when the code changes, or every ~1s as a heartbeat.
  if (code != lastCode || (now - lastSendTime) > 1000) {
    Serial.println(code);
    lastCode = code;
    lastSendTime = now;
  }

  delay(DEBOUNCE_MS);
}
