"""
Aplicación: simulación de cráteres lunares con los números del TRNG.

Cada impacto de meteorito consume 3 números aleatorios:
    u1, u2 -> posición (x, y)
    u3     -> radio del cráter

Dos algoritmos clásicos de simulación:

1. MUESTREO POR RECHAZO (posición).
   Se elige un punto uniforme en el cuadrado [-1, 1] x [-1, 1] y se acepta
   solo si cae dentro del disco x² + y² <= 1. Así los impactos quedan
   uniformes sobre la cara de la Luna. Se acepta ~π/4 ≈ 78.5 % de los tríos.

2. TRANSFORMADA INVERSA (tamaño).
   En la Luna los cráteres pequeños son muchísimo más comunes que los grandes:
   el número de cráteres con radio mayor que r decae aproximadamente como r^-2
   (ley de potencia). Si u es uniforme en [0, 1), la fórmula

       r = r_min · (1 − u · (1 − (r_min / r_max)^α))^(−1/α)

   produce radios con exactamente esa distribución (Pareto truncada, α = 2).

Después se "estampa" cada cráter en un mapa de alturas (un cuenco hundido con
un borde elevado) y se ilumina con luz rasante desde la izquierda para que se
vea como una fotografía.

Uso:
    python crateres.py --entrada salida
Genera:
    fig_09_crateres_luna.png        la Luna simulada con el TRNG
    fig_10_crateres_comparacion.png TRNG vs bits crudos vs RANDU
    fig_11_tamanos_crateres.png     validación de la ley de potencia
"""

from __future__ import annotations

import argparse
import math
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from pruebas import COL, TINTA, TINTA2, randu

LADO = 1000          # píxeles del mapa
R_MIN = 0.8          # radio mínimo (píxeles)
R_MAX = 70.0         # radio máximo (píxeles)
ALFA = 2.0           # exponente de la ley de potencia acumulada


# ------------------------------------------------------------------ algoritmos
def impactos(numeros: np.ndarray) -> dict:
    """Convierte enteros de 32 bits en impactos (x, y, r) dentro del disco."""
    u = numeros.astype(np.float64) / 2**32
    trios = u[: u.size // 3 * 3].reshape(-1, 3)

    # 1. Muestreo por rechazo
    x = 2 * trios[:, 0] - 1
    y = 2 * trios[:, 1] - 1
    dentro = x**2 + y**2 <= 1

    # 2. Transformada inversa
    k = 1 - (R_MIN / R_MAX) ** ALFA
    r = R_MIN * (1 - trios[:, 2] * k) ** (-1 / ALFA)

    return {"x": x[dentro], "y": y[dentro], "r": r[dentro], "numeros": int(numeros.size),
            "intentos": len(trios), "aceptados": int(dentro.sum())}


def mapa_alturas(imp: dict) -> np.ndarray:
    """Estampa cada cráter: cuenco parabólico + borde elevado + eyecta."""
    h = np.zeros((LADO, LADO), dtype=np.float32)
    centro = LADO / 2
    radio_disco = LADO / 2 - 4
    cx = centro + imp["x"] * radio_disco
    cy = centro + imp["y"] * radio_disco
    for x0, y0, r in zip(cx, cy, imp["r"]):
        R = int(math.ceil(2.2 * r)) + 1
        i0, i1 = max(int(y0) - R, 0), min(int(y0) + R + 1, LADO)
        j0, j1 = max(int(x0) - R, 0), min(int(x0) + R + 1, LADO)
        if i0 >= i1 or j0 >= j1:
            continue
        yy, xx = np.mgrid[i0:i1, j0:j1]
        d = np.hypot(xx - x0, yy - y0) / r
        prof = 0.35 * r
        perfil = np.where(
            d < 1,
            prof * (d**2 - 1) + 0.12 * r,                     # cuenco
            0.12 * r * np.exp(-((d - 1) / 0.35) ** 2)          # borde y eyecta
        ).astype(np.float32)
        perfil[d > 2.2] = 0
        zona = h[i0:i1, j0:j1]
        # el cráter nuevo "borra" lo que había dentro de su cuenco
        h[i0:i1, j0:j1] = np.where(d < 1, zona * d**2 + perfil, zona + perfil)
    return h


def iluminar(h: np.ndarray) -> np.ndarray:
    """Sombreado de relieve con luz rasante desde la izquierda."""
    gy, gx = np.gradient(h)
    luz = np.array([-0.75, -0.25, 0.6])
    luz /= np.linalg.norm(luz)
    n = np.stack([-gx, -gy, np.ones_like(h)])
    n /= np.linalg.norm(n, axis=0)
    brillo = np.clip(np.tensordot(luz, n, axes=1), 0, 1)
    yy, xx = np.mgrid[0:LADO, 0:LADO]
    rho = np.hypot(xx - LADO / 2, yy - LADO / 2) / (LADO / 2 - 4)
    limbo = np.sqrt(np.clip(1 - rho**2, 0, 1)) ** 0.35       # oscurece el borde
    img = (0.25 + 0.85 * brillo) * (0.55 + 0.45 * limbo)
    img[rho > 1] = 0
    return np.clip(img, 0, 1)


def simular(numeros: np.ndarray) -> tuple[np.ndarray, dict]:
    imp = impactos(numeros)
    return iluminar(mapa_alturas(imp)), imp


# ------------------------------------------------------------------ figuras
FONDO = "#0e0e0d"


def fig_luna(img, imp, carpeta: Path, segundos: float) -> None:
    fig, ax = plt.subplots(figsize=(8, 8.6), facecolor=FONDO)
    ax.imshow(img, cmap="gray", vmin=0, vmax=1, interpolation="lanczos")
    ax.set_axis_off()
    fig.text(0.5, 0.955, "Una Luna hecha con números aleatorios verdaderos",
             ha="center", color="#f0efec", fontsize=15, weight="bold")
    fig.text(0.5, 0.925,
             f"{imp['aceptados']:,} impactos simulados con {imp['numeros']:,} números del TRNG Arduino",
             ha="center", color="#c3c2b7", fontsize=10.5)
    fig.subplots_adjust(left=0.02, right=0.98, bottom=0.02, top=0.9)
    fig.savefig(carpeta / "fig_09_crateres_luna.png", dpi=150, facecolor=FONDO)
    plt.close(fig)


def fig_comparacion(imagenes: dict, carpeta: Path) -> None:
    fig, ejes = plt.subplots(1, len(imagenes), figsize=(15, 5.8), facecolor=FONDO)
    for ax, (nombre, img) in zip(ejes, imagenes.items()):
        ax.imshow(img, cmap="gray", vmin=0, vmax=1, interpolation="lanczos")
        ax.set_axis_off()
        ax.set_title(nombre, color="#f0efec", fontsize=13, pad=10)
    fig.subplots_adjust(left=0.01, right=0.99, bottom=0.02, top=0.9, wspace=0.04)
    fig.savefig(carpeta / "fig_10_crateres_comparacion.png", dpi=130, facecolor=FONDO)
    plt.close(fig)


def fig_tamanos(imp, carpeta: Path) -> None:
    r = np.sort(imp["r"])[::-1]
    acumulado = np.arange(1, r.size + 1)                 # N(radio >= r)
    malla = np.geomspace(R_MIN, R_MAX, 200)
    k = 1 - (R_MIN / R_MAX) ** ALFA
    teorico = r.size * ((R_MIN / malla) ** ALFA - (R_MIN / R_MAX) ** ALFA) / k

    fig, ax = plt.subplots(figsize=(10, 4.4))
    ax.loglog(r, acumulado, color=COL["TRNG Arduino"], lw=2.2, label="simulación con el TRNG")
    ax.loglog(malla, teorico, color=TINTA, lw=1, ls="--", label="ley teórica  N(>r) ∝ r⁻²")
    ax.set_ylim(0.7, r.size * 2)
    ax.set_xlabel("radio del cráter r (píxeles, escala log)")
    ax.set_ylabel("cráteres con radio ≥ r (escala log)")
    ax.set_title("Los tamaños siguen la ley de potencia: muchos cráteres pequeños, pocos grandes")
    ax.legend(loc="lower left")
    ax.text(R_MIN * 1.1, 2, f"{(imp['r'] >= 10).sum():,} cráteres con r ≥ 10 px   ·   "
            f"{(imp['r'] < 2).sum():,} con r < 2 px", color=TINTA2, fontsize=9.5)
    fig.tight_layout()
    fig.savefig(carpeta / "fig_11_tamanos_crateres.png", dpi=150)
    plt.close(fig)


# ------------------------------------------------------------------ main
def generar_figuras(carpeta: Path, comparacion: bool = True) -> list[tuple[str, str, str]]:
    """Genera las figuras 09–11 y devuelve (archivo, título, pie) para el reporte."""
    trng = np.fromfile(carpeta / "numeros.bin", dtype="<u4")
    t0 = time.time()
    print("Simulando la Luna con el TRNG…")
    img, imp = simular(trng)
    seg = time.time() - t0
    print(f"  {imp['intentos']:,} tríos → {imp['aceptados']:,} impactos aceptados "
          f"({imp['aceptados'] / imp['intentos']:.1%}, teórico π/4 = 78.5 %) en {seg:.1f} s")
    fig_luna(img, imp, carpeta, seg)
    fig_tamanos(imp, carpeta)
    figs = [
        ("fig_09_crateres_luna.png", "Aplicación: una Luna simulada con el TRNG",
         f"Cada impacto usa 3 números: dos para la posición (muestreo por rechazo dentro del disco; "
         f"se aceptaron {imp['aceptados']:,} de {imp['intentos']:,} tríos, {imp['aceptados'] / imp['intentos']:.1%} "
         f"frente al π/4 = 78.5 % teórico) y uno para el radio (transformada inversa de una ley de potencia)."),
        ("fig_11_tamanos_crateres.png", "Validación de la transformada inversa",
         "La distribución de radios simulada coincide con la ley teórica N(>r) ∝ r⁻², como en la Luna real: "
         "muchísimos cráteres pequeños y muy pocos grandes."),
    ]
    if comparacion:
        imagenes = {"TRNG Arduino": img}
        crudo_f = carpeta / "crudo.bin"
        if crudo_f.exists():
            print("Simulando con los bits crudos…")
            crudo = np.fromfile(crudo_f, dtype="<u4")[: trng.size]
            imagenes["Bits crudos (sin SHA-256)"] = simular(crudo)[0]
        print("Simulando con RANDU…")
        imagenes["RANDU"] = simular(randu(trng.size))[0]
        fig_comparacion(imagenes, carpeta)
        figs.insert(1, (
            "fig_10_crateres_comparacion.png", "La misma Luna con otros generadores",
            "Con RANDU los cráteres se alinean en franjas diagonales: sus tríos (x, y, radio) caen en 15 planos, "
            "así que para cada tamaño solo son posibles ciertas posiciones. Con los bits crudos el sesgo cambia "
            "la proporción de tamaños y la superficie se ve distinta."))
    return figs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", default="salida")
    ap.add_argument("--sin-comparacion", action="store_true",
                    help="solo la Luna del TRNG (más rápido)")
    args = ap.parse_args()
    carpeta = Path(args.entrada)
    generar_figuras(carpeta, not args.sin_comparacion)
    print(f"Figuras guardadas en {carpeta.resolve()}")


if __name__ == "__main__":
    main()
