

const uint8_t PINES[] = {A0, A1, A2};   // fotoresistencia, antena 1, antena 2
const uint8_t NUM_PINES = sizeof(PINES) / sizeof(PINES[0]);
const long    BAUDIOS = 500000;
const uint8_t TAM_BUFFER = 32;           // bytes que se envían en bloque

enum Modo { DETENIDO, BITS, SENALES };
Modo modo = DETENIDO;

uint8_t buffer[TAM_BUFFER];
uint8_t posBuffer = 0;
uint8_t byteActual = 0;
uint8_t bitsEnByte = 0;

void setup() {
  Serial.begin(BAUDIOS);

  // Prescaler del ADC = 32  ->  reloj ADC de 500 kHz (~26 µs por lectura).
  // Por defecto es 128 (~112 µs). Más rápido = más lecturas por segundo
  // y, además, el LSB queda todavía más dominado por el ruido.
  ADCSRA = (ADCSRA & 0xF8) | 0x05;

  // Las entradas analógicas no usan pull-up (deben quedar "flotantes")
  for (uint8_t i = 0; i < NUM_PINES; i++) pinMode(PINES[i], INPUT);
}

// Un bit crudo = XOR de los LSB de una lectura de cada sensor.
inline uint8_t bitCrudo() {
  uint8_t b = 0;
  for (uint8_t i = 0; i < NUM_PINES; i++) {
    b ^= (uint8_t)(analogRead(PINES[i]) & 0x01);
  }
  return b;
}

void atenderComandos() {
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == 'B') { modo = BITS; posBuffer = 0; bitsEnByte = 0; byteActual = 0; }
    else if (c == 'S') { modo = SENALES; }
    else if (c == 'X') { modo = DETENIDO; Serial.flush(); }
    else if (c == 'I') {
      modo = DETENIDO;
      Serial.print(F("TRNG-ARDUINO v1 | sensores="));
      Serial.print(NUM_PINES);
      Serial.print(F(" | baudios="));
      Serial.print(BAUDIOS);
      Serial.println(F(" | prescaler ADC=32"));
    }
  }
}

void loop() {
  atenderComandos();

  if (modo == BITS) {
    // Generamos un bloque completo antes de volver a revisar comandos
    for (uint16_t k = 0; k < TAM_BUFFER * 8; k++) {
      byteActual = (byteActual << 1) | bitCrudo();
      if (++bitsEnByte == 8) {
        buffer[posBuffer++] = byteActual;
        bitsEnByte = 0;
        byteActual = 0;
      }
    }
    Serial.write(buffer, TAM_BUFFER);
    posBuffer = 0;
  }
  else if (modo == SENALES) {
    // Señales completas (10 bits) para graficar lo que "ve" cada sensor
    Serial.print(micros());
    for (uint8_t i = 0; i < NUM_PINES; i++) {
      Serial.print(',');
      Serial.print(analogRead(PINES[i]));
    }
    Serial.println();
    delayMicroseconds(500);   // ~1500 muestras por segundo
  }
}
