/*
 * ================================================================
 *  Generador de entropía física — Arduino Uno
 *  Proyecto: Sistema de generación de números aleatorios (TRNG)
 *  Curso: Diseño y Análisis de Algoritmos
 * ================================================================
 *
 *  IDEA
 *  ----
 *  Todo convertidor analógico-digital (ADC) tiene ruido: térmico,
 *  de cuantización, interferencia electromagnética (60 Hz de la red),
 *  fluctuaciones de luz, sonido ambiente... Los bits MÁS ALTOS de una
 *  lectura son predecibles (dependen de la señal), pero el BIT MENOS
 *  SIGNIFICATIVO (LSB) cambia casi al azar con ese ruido.
 *
 *  Este sketch lee varios sensores externos, toma el LSB de cada
 *  lectura y los combina con XOR. El resultado es un flujo de bits
 *  "crudos" que se envía por USB a Python, donde se evalúa su calidad
 *  (pruebas de salud) y se acondiciona criptográficamente (SHA-256).
 *
 *  CONEXIONES
 *  ----------
 *   A0  Fotoresistencia (LDR) en divisor de voltaje:
 *         5V ── LDR ──┬── 10 kΩ ── GND
 *                     └── A0
 *   A1  Antena 1: un cable de 15–20 cm conectado a A1 y libre en el
 *       otro extremo (capta ruido electromagnético del ambiente).
 *   A2  Antena 2: otro cable suelto en A2, separado del de A1.
 *
 *  PROTOCOLO SERIAL (500000 baudios)
 *  ---------------------------------
 *   'B' -> inicia flujo binario de bits crudos (8 bits por byte)
 *   'S' -> inicia flujo de señales en texto: "t_us,a0,a1,a2\n"
 *   'X' -> detiene cualquier flujo
 *   'I' -> imprime información de configuración
 * ================================================================
 */

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
