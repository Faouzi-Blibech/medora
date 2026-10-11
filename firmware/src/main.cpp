// Medora bedside unit — scaffold. Modules (sensors, net, schedule, ui, carousel, rfid) are added one per file.
#include <Arduino.h>

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.printf("Medora bedside unit fw %s booting\n", WARD_FW_VERSION);
}

void loop() {
  delay(1000);
}
