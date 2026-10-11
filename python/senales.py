"""
Captura y grafica lo que "ve" cada sensor (señal completa de 10 bits).
Sirve para el video: muestra que la señal es casi constante a simple vista,
pero el bit menos significativo (LSB) fluctúa al azar.

Uso:
    python senales.py --puerto COM3 --segundos 5
    python senales.py --simulado
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

NOMBRES = ["A0 · Fotoresistencia", "A1 · Antena (pin flotante)", "A2 · Micrófono"]
COLORES = ["#2a78d6", "#d6602a", "#2aa876"]


def capturar_arduino(puerto: str, segundos: float) -> np.ndarray:
    import serial
    ser = serial.Serial(puerto, 500_000, timeout=1)
    time.sleep(2.0)
    ser.reset_input_buffer()
    ser.write(b"S")
    filas, t0 = [], time.time()
    while time.time() - t0 < segundos:
        linea = ser.readline().decode(errors="ignore").strip()
        partes = linea.split(",")
        if len(partes) >= 2 and all(p.isdigit() for p in partes):
            filas.append([int(p) for p in partes])
    ser.write(b"X")
    ser.close()
    datos = np.array(filas, dtype=float)
    datos[:, 0] = (datos[:, 0] - datos[0, 0]) / 1e6   # micros -> segundos
    return datos


def capturar_simulado(segundos: float) -> np.ndarray:
    rng = np.random.default_rng()
    t = np.arange(0, segundos, 1 / 1500)
    cols = [t]
    for s in range(3):
        senal = 400 + 150 * s + 30 * np.sin(2 * np.pi * 0.05 * t + s) \
            + 2.2 * np.sin(2 * np.pi * 60 * t + 0.7 * s)
        cols.append(np.clip(np.round(senal + rng.normal(0, 0.55, t.size)), 0, 1023))
    return np.column_stack(cols)


def graficar(datos: np.ndarray, destino: Path) -> None:
    t = datos[:, 0]
    n_sens = datos.shape[1] - 1
    fig, ejes = plt.subplots(n_sens, 2, figsize=(13, 2.6 * n_sens), squeeze=False)
    ventana = t < min(t[-1], 0.1)   # primeros 100 ms para ver detalle
    for i in range(n_sens):
        y = datos[:, i + 1]
        ax = ejes[i, 0]
        ax.plot(t[ventana] * 1000, y[ventana], color=COLORES[i], lw=1.2)
        ax.set_title(f"{NOMBRES[i]} — lectura ADC (10 bits)", fontsize=10, loc="left")
        ax.set_xlabel("tiempo (ms)")
        ax.set_ylabel("valor ADC")
        ax = ejes[i, 1]
        lsb = y[ventana].astype(int) & 1
        ax.step(t[ventana] * 1000, lsb, where="post", color=COLORES[i], lw=1)
        ax.set_ylim(-0.3, 1.3)
        ax.set_yticks([0, 1])
        ax.set_title("bit menos significativo (LSB) → fuente de entropía", fontsize=10, loc="left")
        ax.set_xlabel("tiempo (ms)")
    for ax in ejes.flat:
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(destino, dpi=150)
    print(f"Gráfica guardada en {destino.resolve()}")


def main() -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--puerto")
    g.add_argument("--simulado", action="store_true")
    ap.add_argument("--segundos", type=float, default=5)
    ap.add_argument("--salida", default="salida")
    args = ap.parse_args()
    carpeta = Path(args.salida)
    carpeta.mkdir(parents=True, exist_ok=True)
    datos = capturar_simulado(args.segundos) if args.simulado \
        else capturar_arduino(args.puerto, args.segundos)
    np.savetxt(carpeta / "senales.csv", datos, delimiter=",",
               header="t_s," + ",".join(f"sensor{i}" for i in range(datos.shape[1] - 1)),
               comments="")
    graficar(datos, carpeta / "fig_00_senales_sensores.png")


if __name__ == "__main__":
    main()
