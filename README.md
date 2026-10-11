# TRNG con Arduino Uno — 160,000 números aleatorios desde sensores físicos

Proyecto del curso de Diseño y Análisis de Algoritmos.

```
proyecto_trng/
├── arduino/generador_entropia/generador_entropia.ino   ← se carga en el Arduino
├── python/
│   ├── fuentes.py      lectura serial del Arduino (+ simulación para pruebas)
│   ├── salud.py        estimación de entropía y pruebas de salud (NIST SP 800-90B)
│   ├── generador.py    genera los 160,000 números  ← PROGRAMA PRINCIPAL
│   ├── senales.py      captura/grafica las señales de los sensores (para el video)
│   ├── nist.py         9 pruebas de la batería NIST SP 800-22
│   ├── pruebas.py      pruebas clásicas + gráficas + reporte.html
│   ├── crateres.py     aplicación: Luna simulada con los números (lo llama pruebas.py)
│   └── animacion_randu.py  GIF del cubo 3D girando (escena 8 del video)
├── requirements.txt
└── salida_simulada/    ejemplo de resultados con la SIMULACIÓN (no usar para entregar)
```

## 1. Armar el circuito (≈10 minutos)

| Pin | Sensor | Conexión |
|-----|--------|----------|
| A0 | Fotoresistencia (LDR) | 5V → LDR → A0 → resistencia 10 kΩ → GND |
| A1 | Antena | cable de 15–20 cm en A1, el otro extremo libre |
| A2 | Micrófono KY-038 (opcional) | AO → A2, + → 5V, G → GND |

Si no tienes el micrófono, en el sketch cambia `{A0, A1, A2}` por `{A0, A1}`.

## 2. Cargar el sketch

1. Abre `arduino/generador_entropia/generador_entropia.ino` en el Arduino IDE.
2. Placa: **Arduino Uno**. Puerto: el que aparezca (COM3, /dev/ttyACM0…).
3. Subir. **Cierra el Monitor Serie** después (si queda abierto, Python no puede usar el puerto).

## 3. Instalar Python y dependencias

```bash
cd proyecto_trng
pip install -r requirements.txt
```

## 4. Ejecutar

```bash
cd python
python senales.py   --puerto COM3 --segundos 5     # gráfica de los sensores (opcional, para el video)
python generador.py --puerto COM3                  # ~12–15 min con 3 sensores
python pruebas.py   --entrada salida               # ~30 s (incluye la Luna); abre salida/reporte.html
python animacion_randu.py --entrada salida         # ~1 min; GIF para el video
```

En macOS el puerto se ve como `/dev/cu.usbmodem1101`; en Linux `/dev/ttyACM0`
(si da "permission denied": `sudo usermod -aG dialout $USER` y reinicia sesión).

Para probar el software sin el Arduino: `python generador.py --simulado`.

## Resultados que se generan en `salida/`

| Archivo | Contenido |
|---------|-----------|
| `numeros.csv` | los 160,000 números (entero de 32 bits y su valor en [0,1)) |
| `numeros.bin` | los mismos en binario, uint32 little-endian |
| `crudo.bin` | todos los bits crudos del Arduino |
| `metadatos.json` | entropía medida, alarmas de salud, tiempo y tasa |
| `resultados.json` | p-values de todas las pruebas |
| `fig_00…fig_08.png` | gráficas de validación para el video y el documento |
| `fig_09…fig_11.png` | la Luna simulada, la comparación con RANDU y la curva de tamaños |
| `reporte.html` | reporte completo con tablas y gráficas |

## Problemas comunes

- **"could not open port"**: cierra el Monitor Serie del Arduino IDE.
- **"La fuente casi no tiene entropía"**: un sensor está mal conectado; revisa con `senales.py`.
- **Muchas alarmas de salud**: un cable se soltó durante la captura.
- **Una prueba aislada "falla"**: ver la nota del reporte; con α = 0.01 es esperable de vez en cuando.
  Si quieres confirmarlo, vuelve a generar y a probar.
