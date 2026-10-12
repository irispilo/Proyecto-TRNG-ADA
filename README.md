# TRNG con Arduino Uno — 160,000 números aleatorios desde sensores físicos

Proyecto 2 del curso Análisis y Diseño de Algoritmos: un generador de números aleatorios
verdaderos (TRNG) que obtiene su entropía del ruido eléctrico de sensores conectados a un
Arduino Uno.

## Idea

Toda lectura de un convertidor analógico-digital (ADC) trae ruido: térmico, de cuantización,
interferencia electromagnética de la red y variaciones de luz. Los bits altos de una
lectura siguen a la señal y son predecibles, pero el bit menos significativo (LSB) cambia
prácticamente al azar con ese ruido. El Arduino lee tres sensores (una fotoresistencia y dos
antenas), toma el LSB de cada lectura y los combina con XOR. Ese flujo de bits crudos se envía
por USB a Python, donde se evalúa y se acondiciona.

La arquitectura sigue el modelo de NIST SP 800-90B:

```
Sensores ─► ADC ─► LSB ⊕ ─► bits crudos ─► pruebas de salud ─► SHA-256 ─► números de 32 bits
```

- **Estimación de entropía.** Antes de generar se calibra la fuente con 200,000 bits crudos,
  usando los estimadores MCV y de Markov de SP 800-90B y quedándose con el mínimo.
- **Pruebas de salud continuas.** Repetition Count Test y Adaptive Proportion Test sobre cada
  bit crudo; detectan un sensor desconectado o una fuente que se quedó pegada.
- **Acondicionamiento.** Cada bloque de 256 bits de salida es `SHA-256(contador || bloque_crudo)`.
  El tamaño del bloque crudo se calcula para que contenga al menos 256 + 64 bits de entropía,
  como pide SP 800-90B.

## Circuito

| Pin | Sensor | Conexión |
|-----|--------|----------|
| A0 | Fotoresistencia (LDR) | 5V → LDR → A0 → resistencia 10 kΩ → GND |
| A1 | Antena 1 | cable de 15–20 cm en A1, el otro extremo libre |
| A2 | Antena 2 | cable jumper en A2, el otro extremo libre y separado de la antena 1 |

El diseño original contemplaba un micrófono KY-038 en A2; al no tenerlo, se reemplazó por una
segunda antena, sin cambios en el código. Un pin conectado solo a un cable suelto queda
flotante, y el cable capta el campo eléctrico de la instalación de la casa: la onda de 60 Hz
que se ve en `fig_00_senales_sensores.png`, con periodo de unos 16.7 ms. Esa onda es
predecible y por eso no se usa; lo que se aprovecha es el temblor del último bit encima de ella.

Como las dos antenas captan la misma onda de la red, sus lecturas completas están muy
correlacionadas (0.98 en `senales.csv`), pero sus bits menos significativos no lo están: la
correlación entre los LSB de A1 y A2 es prácticamente cero (|r| < 0.03). La fotoresistencia,
con la luz estable del cuarto, apenas oscila entre 316 y 321, pero su LSB también alterna entre
0 y 1. De todas formas la min-entropía se estima sobre el flujo ya combinado, así
que el tamaño de los bloques que se pasan a SHA-256 se ajusta a lo que realmente aportan los
tres sensores.

El ADC trabaja con prescaler 32 (unos 26 µs por lectura) y el puerto serial a 500,000 baudios.

## Estructura

```
proyecto_trng/
├── arduino/generador_entropia/generador_entropia.ino   sketch del Arduino
├── python/
│   ├── fuentes.py          lectura serial del Arduino (y una fuente simulada para pruebas)
│   ├── salud.py            estimación de entropía y pruebas de salud (SP 800-90B)
│   ├── generador.py        genera los 160,000 números (programa principal)
│   ├── senales.py          captura y grafica las señales de los sensores
│   ├── nist.py             9 pruebas de la batería NIST SP 800-22
│   ├── pruebas.py          pruebas clásicas, gráficas y reporte.html
│   ├── crateres.py         aplicación: Luna simulada con los números
│   ├── animacion_randu.py  GIF de los tríos de RANDU en 3D
│   └── salida/             resultados del lote generado con el Arduino
├── Verificador_TRNG.ipynb  notebook verificador del curso, con los resultados del lote
└── requirements.txt
```

## Resultados

El lote de `python/salida/` se generó el 11 de octubre de 2026 con el Arduino Uno, la
fotoresistencia y las dos antenas.

| Medida | Valor |
|--------|-------|
| Números generados | 160,000 enteros de 32 bits |
| Tiempo total | 727.8 s (unos 12 minutos), 219.8 números por segundo |
| Bits crudos capturados | 7,892,288 |
| Min-entropía de la fuente cruda | 0.842 bits por bit crudo |
| Bloques SHA-256 | 20,032, de 48 bytes crudos cada uno |
| Alarmas de las pruebas de salud | 0 (RCT y APT) |

### Pruebas estadísticas

`pruebas.py` aplica 17 pruebas a la salida del TRNG y, como comparación, a los bits crudos
sin acondicionar, a Mersenne Twister y a RANDU:

| Fuente | NIST SP 800-22 (9) | Pruebas clásicas (8) | Total |
|--------|:---:|:---:|:---:|
| **TRNG Arduino** | **9/9** | **8/8** | **17/17** |
| Bits crudos (sin SHA-256) | 1/9 | 1/8 | 2/17 |
| Mersenne Twister | 8/9 | 8/8 | 16/17 |
| RANDU | 0/9 | 7/8 | 7/17 |

Las pruebas clásicas son chi cuadrado de uniformidad, Kolmogorov–Smirnov, serial 2D y 3D,
rachas arriba/abajo, Ljung–Box, huecos y póker. Las de NIST se corren sobre 50 secuencias de
102,400 bits.

Los bits crudos fallan casi todo: tienen sesgo y dependencia entre bits consecutivos, que es
justo lo que corrige el acondicionamiento con SHA-256. RANDU pasa varias pruebas de
uniformidad, pero falla la serial 3D porque sus tríos caen en 15 planos. El fallo aislado de
Mersenne Twister (rango de matrices, proporción 0.94 contra un mínimo de 0.948) es el tipo de
falso positivo esperable con α = 0.01.

### Verificador del curso

[Verificador_TRNG.ipynb](Verificador_TRNG.ipynb), con el rango declarado [0, 2³² − 1]:

| Prueba | p-valor | Veredicto |
|--------|:---:|:---:|
| Chi cuadrado (uniformidad) | 0.3337 | PASA |
| Rachas (orden) | 0.2449 | PASA |
| Pares consecutivos | 0.8181 | PASA |

La imagen de 400 × 400 píxeles y el mapa de pares consecutivos se ven como ruido uniforme, sin
estructura, igual que la referencia.

### Aplicación: cráteres lunares

`crateres.py` usa los números para simular impactos sobre una Luna. De 53,333 tríos se aceptaron
41,939 impactos (78.6 %, contra el valor teórico π/4 = 78.5 %). En la comparación
(`fig_10_crateres_comparacion.png`), RANDU deja los cráteres alineados en diagonales, reflejo de
que sus tríos caen en planos, y los bits crudos producen una superficie mucho más saturada de
cráteres que la del TRNG.

### Archivos en `python/salida/`

| Archivo | Contenido |
|---------|-----------|
| `numeros.csv` | los 160,000 números (entero de 32 bits y su valor en [0, 1)) |
| `numeros.bin` | los mismos números en binario, uint32 little-endian |
| `crudo.bin` | todos los bits crudos recibidos del Arduino |
| `metadatos.json` | entropía medida, alarmas de salud, tiempo y tasa |
| `resultados.json` | p-valores de todas las pruebas |
| `senales.csv`, `fig_00` | señales de los sensores |
| `fig_01` … `fig_08` | gráficas de validación (histograma, mapa de bits, pares, tríos 3D, autocorrelación, caminata, Monte Carlo de π, NIST) |
| `fig_09` … `fig_11` | Luna simulada, comparación con bits crudos y RANDU, y curva de tamaños |
| `anim_randu_3d.gif` | animación de los tríos de RANDU en 3D |
| `reporte.html` | reporte completo con tablas y gráficas |

## Operación durante un año

Este proyecto funciona como piloto. Midió el rendimiento real del sistema y mostró sus puntos
débiles, y con esos datos se diseña la versión que operaría de forma continua durante un año.

### Lo que dejó el piloto

| Demostró | Reveló |
|----------|--------|
| 220 números por segundo con un Arduino | La protoboard es frágil: la fotoresistencia no funcionó hasta reubicar los cables de alimentación |
| Min-entropía de 0.842 bits por bit crudo | Con la luz estable de un cuarto, la fotoresistencia aporta poco |
| 0 alarmas de salud y 17/17 pruebas aprobadas | Las antenas dependen de la red eléctrica: sin ella desaparece la onda de 60 Hz |
| Costo de energía de unos Q0.01 por lote | Una laptop no es adecuada para operar 24/7 |

### Sistema

```
Sensores ─► Arduino ─USB─► Raspberry Pi (servicio 24/7) ─► archivos diarios + reportes
                                   │
                         UPS (respaldo de energía)
```

**Hardware.** Una Raspberry Pi reemplaza a la laptop: consume unos 5 W en lugar de unos 30 W y
puede quedar encendida todo el año. El circuito pasa de la protoboard a una placa perforada
soldada, dentro de una caja y con las antenas fijas, porque en el piloto mover un cable
cambiaba la señal. Un UPS evita que un corte de luz detenga el sistema, y se mantiene un
Arduino con sensores de repuesto.

**Software.** El código del piloto se mantiene, con cinco cambios de operación:

1. **Servicio automático:** arranca al encender la Raspberry Pi y se reinicia si falla.
2. **Alarmas con aviso:** las pruebas de salud ya descartan bloques defectuosos; si una alarma
   se repite, el sistema detiene la salida y envía una notificación.
3. **Entropía medida cada hora,** no solo al inicio, porque el ambiente cambia durante el año
   (día y noche, aparatos encendidos, cortes de luz).
4. **Validación diaria:** las 17 pruebas y el verificador del curso sobre una muestra diaria de
   160,000 números. A lo largo del año, los p-valores deberían distribuirse de forma uniforme.
5. **Salida en binario, un archivo por día;** el CSV ocupa ocho veces más espacio.

**Capacidad anual con un solo Arduino**

| Medida | Valor |
|--------|-------|
| Números generados | unos 6,930 millones (≈ 43,000 lotes como el del piloto) |
| Almacenamiento de los números en binario | 27.7 GB |
| Bits crudos, si se guardaran todos | 42.7 GB (se guardan solo muestras) |

**Si se necesitan más números** hay dos caminos. El lineal es conectar varios Arduinos a la
misma Raspberry Pi; cada uno suma unos 220 números por segundo. El recomendado es un esquema
híbrido: el TRNG produce semillas para un generador criptográfico determinista (DRBG, NIST
SP 800-90A), que entrega millones de números por segundo y se vuelve a sembrar de forma
continua. Es el mismo principio de `/dev/urandom` en Linux y de RDRAND en los procesadores
Intel; con él, el límite pasa a ser la CPU y no los sensores.

### Costos del primer año

Energía calculada con la tarifa no social de EEGSA para agosto–octubre de 2026, Q1.51 por kWh
([CNEE](https://cnee.gob.gt/wp-content/uploads/2026/07/Comunicado-CNEE-tarifas-trimestrales-agosto-a-octubre.pdf)).

| Concepto | A: piloto tal cual (laptop) | B: sistema propuesto |
|----------|-----------------------------|----------------------|
| Computadora | Q0 (equipo existente) | Raspberry Pi 5: ~Q1,000 – Q2,414* |
| Arduino y sensores | Q0 (equipo existente) | placa soldada y repuestos: Q150 – Q325 |
| UPS | — | ~Q500 – Q800* |
| Almacenamiento (128 GB) | — | ~Q150 – Q250* |
| Energía en un año | 30 W × 8,760 h = 263 kWh → **Q397** | 5 W × 8,760 h = 44 kWh → **Q66** |
| **Total del primer año** | **~Q400** (la laptop queda ocupada y se desgasta) | **~Q1,900 – Q3,900** |
| Costo por millón de números | ~Q0.06 | ~Q0.27 – Q0.56 |

\* Precios estimados. El de referencia es la Raspberry Pi 5 de 8 GB en Pacifiko (Q2,414); un
modelo de 2 o 4 GB es suficiente y más barato.

El costo principal es la inversión inicial; la operación cuesta unos Q66 al año de
electricidad. Con el esquema híbrido, el mismo hardware produce órdenes de magnitud más
números y el costo por número queda prácticamente en cero.

### Siguiente fase

Para operar un año, una fuente de ruido dedicada, como el ruido de avalancha de un transistor,
sería más estable que las antenas, porque no depende de la red eléctrica ni del ambiente. Sus
componentes son baratos, pero el circuito requiere un voltaje mayor (unos 12 V), por lo que
queda como la siguiente fase del piloto.

## Cómo reproducirlo

Requiere Python 3 y el sketch cargado en el Arduino Uno.

```bash
pip install -r requirements.txt
cd python
python senales.py   --puerto COM4 --segundos 5   # señales de los sensores
python generador.py --puerto COM4                # unos 12 minutos con 3 sensores
python pruebas.py   --entrada salida             # pruebas, figuras y reporte.html
python animacion_randu.py --entrada salida       # GIF de RANDU
```

`COM4` es el puerto en Windows; en Linux suele ser `/dev/ttyACM0` y en macOS
`/dev/cu.usbmodem…`. El Monitor Serie del Arduino IDE debe estar cerrado, porque ocupa el puerto.
`python generador.py --simulado` corre todo el flujo sin hardware, con una fuente simulada.
