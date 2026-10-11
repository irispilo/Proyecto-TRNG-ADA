"""
Animación para el video: el cubo de tríos gira hasta quedar "de canto"
y revela los 15 planos de RANDU; al lado, el TRNG no muestra estructura.

Uso:
    python animacion_randu.py --entrada salida
Genera salida/anim_randu_3d.gif (≈ 8 s). Para MP4 instala ffmpeg y usa --mp4.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FFMpegWriter, FuncAnimation, PillowWriter

from pruebas import COL, randu


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", default="salida")
    ap.add_argument("--mp4", action="store_true")
    args = ap.parse_args()
    carpeta = Path(args.entrada)

    n_trios = 20_000
    trng = np.fromfile(carpeta / "numeros.bin", dtype="<u4")[: n_trios * 3]
    datos = {"TRNG Arduino": trng, "RANDU": randu(n_trios * 3)}

    fig = plt.figure(figsize=(11, 5.4), facecolor="#fcfcfb")
    ejes = []
    for i, (nombre, x) in enumerate(datos.items()):
        t = (x.astype(np.float64) / 2**32).reshape(-1, 3)
        ax = fig.add_subplot(1, 2, i + 1, projection="3d")
        ax.scatter(t[:, 0], t[:, 1], t[:, 2], s=0.4, color=COL[nombre], alpha=0.5, linewidths=0)
        ax.set_title(nombre, fontsize=13, loc="center")
        ax.set_xticklabels([]); ax.set_yticklabels([]); ax.set_zticklabels([])
        ax.set_facecolor("#fcfcfb")
        ejes.append(ax)

    azim_final = math.degrees(math.atan2(-9, -6))     # vista de canto de los planos
    cuadros = 120
    azims = np.concatenate([np.linspace(azim_final + 140, azim_final, 90), np.full(30, azim_final)])
    elevs = np.concatenate([np.linspace(30, 0, 90), np.zeros(30)])

    def actualizar(k):
        for ax in ejes:
            ax.view_init(elev=elevs[k], azim=azims[k])
        return []

    anim = FuncAnimation(fig, actualizar, frames=cuadros, interval=66)
    if args.mp4:
        destino = carpeta / "anim_randu_3d.mp4"
        anim.save(destino, writer=FFMpegWriter(fps=15), dpi=120)
    else:
        destino = carpeta / "anim_randu_3d.gif"
        anim.save(destino, writer=PillowWriter(fps=15), dpi=90)
    print(f"Animación guardada en {destino.resolve()}")


if __name__ == "__main__":
    main()
