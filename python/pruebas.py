"""
Validación técnica: pruebas estadísticas + análisis visual + reporte HTML.

Compara 4 generadores con exactamente la misma cantidad de números:
  1. TRNG Arduino   – nuestro sistema (sensores + SHA-256)
  2. Bits crudos    – los bits del Arduino SIN acondicionar
  3. Mersenne Twister – PRNG estándar (referencia "buena")
  4. RANDU          – LCG de IBM de los 60s (referencia "mala", famosa)

Uso:
    python pruebas.py --entrada salida
Genera en la misma carpeta: fig_*.png (incluye la Luna simulada), resultados.json y reporte.html
"""

from __future__ import annotations

import argparse
import base64
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker
import numpy as np
from scipy import stats

import nist

# ------------------------------------------------------------------ estilo
COL = {"TRNG Arduino": "#2a78d6", "Bits crudos": "#eb6834",
       "Mersenne Twister": "#1baf7a", "RANDU": "#e34948"}
TINTA, TINTA2, REJILLA = "#0b0b0b", "#52514e", "#e4e3df"
plt.rcParams.update({
    "font.size": 10, "axes.edgecolor": TINTA2, "axes.labelcolor": TINTA2,
    "xtick.color": TINTA2, "ytick.color": TINTA2, "axes.titlecolor": TINTA,
    "axes.titlesize": 11, "axes.titlelocation": "left", "axes.grid": True,
    "grid.color": REJILLA, "grid.linewidth": 0.6, "axes.spines.top": False,
    "axes.spines.right": False, "figure.facecolor": "#fcfcfb",
    "axes.facecolor": "#fcfcfb", "savefig.facecolor": "#fcfcfb",
    "legend.frameon": False,
})


# ------------------------------------------------------------------ generadores
def randu(n: int, semilla: int = 1) -> np.ndarray:
    x = semilla
    out = np.empty(n, dtype=np.uint32)
    for i in range(n):
        x = (65539 * x) % 2**31
        out[i] = x << 1          # 31 bits -> palabra de 32 bits (LSB siempre 0)
    return out


def cargar_generadores(carpeta: Path) -> dict[str, np.ndarray]:
    trng = np.fromfile(carpeta / "numeros.bin", dtype="<u4")
    n = trng.size
    crudo = np.fromfile(carpeta / "crudo.bin", dtype="<u4")[:n]
    mt = np.random.RandomState(20261011).randint(0, 2**32, size=n, dtype=np.uint64).astype(np.uint32)
    return {"TRNG Arduino": trng, "Bits crudos": crudo,
            "Mersenne Twister": mt, "RANDU": randu(n)}


def a_bits(x: np.ndarray) -> np.ndarray:
    return np.unpackbits(x.astype(">u4").view(np.uint8))


# ------------------------------------------------------------------ pruebas clásicas
def pruebas_clasicas(x: np.ndarray) -> dict:
    u = x.astype(np.float64) / 2**32
    n = u.size
    r = {}

    # 1. Chi-cuadrado de uniformidad (100 clases)
    obs, _ = np.histogram(u, bins=100, range=(0, 1))
    chi, p = stats.chisquare(obs)
    r["Chi-cuadrado uniformidad (100 clases)"] = (chi, p)

    # 2. Kolmogorov–Smirnov contra U(0,1)
    d, p = stats.kstest(u, "uniform")
    r["Kolmogorov–Smirnov"] = (d, p)

    # 3. Serial 2D: pares no traslapados en rejilla 20×20
    pares = u[: n // 2 * 2].reshape(-1, 2)
    h2, _, _ = np.histogram2d(pares[:, 0], pares[:, 1], bins=20, range=[[0, 1], [0, 1]])
    chi, p = stats.chisquare(h2.ravel())
    r["Serial 2D (pares, 20×20)"] = (chi, p)

    # 4. Serial 3D: tríos no traslapados en rejilla 10×10×10
    trios = u[: n // 3 * 3].reshape(-1, 3)
    h3, _ = np.histogramdd(trios, bins=10, range=[[0, 1]] * 3)
    chi, p = stats.chisquare(h3.ravel())
    r["Serial 3D (tríos, 10×10×10)"] = (chi, p)

    # 5. Rachas ascendentes/descendentes (Wald–Wolfowitz)
    signos = np.sign(np.diff(u))
    signos = signos[signos != 0]
    R = 1 + np.count_nonzero(signos[1:] != signos[:-1])
    mu = (2 * n - 1) / 3
    var = (16 * n - 29) / 90
    z = (R - mu) / math.sqrt(var)
    r["Rachas arriba/abajo"] = (z, 2 * stats.norm.sf(abs(z)))

    # 6. Ljung–Box: autocorrelación conjunta de los rezagos 1..20
    ac = autocorrelacion(u, 20)
    Q = n * (n + 2) * np.sum(ac**2 / (n - np.arange(1, 21)))
    r["Ljung–Box (rezagos 1–20)"] = (Q, stats.chi2.sf(Q, 20))

    # 7. Prueba de huecos (gap test) en [0, 0.1)
    idx = np.flatnonzero(u < 0.1)
    huecos = np.diff(idx) - 1
    k = 15
    obs = np.bincount(np.minimum(huecos, k), minlength=k + 1)
    pr = np.array([0.1 * 0.9**j for j in range(k)] + [0.9**k])
    chi, p = stats.chisquare(obs, pr * obs.sum())
    r["Huecos (gap test)"] = (chi, p)

    # 8. Póker (5 dígitos decimales por número → patrones)
    dig = (u * 10).astype(int)
    manos = dig[: n // 5 * 5].reshape(-1, 5)
    distintos = np.array([len(set(m)) for m in manos.tolist()])
    obs = np.bincount(distintos, minlength=6)[1:]
    # probabilidades de 1..5 valores distintos con d=10, k=5 (Stirling 2ª especie)
    S = [1, 15, 25, 10, 1]
    pr = np.array([S[i - 1] * math.perm(10, i) / 10**5 for i in range(1, 6)])
    obs_c = np.array([obs[0] + obs[1], obs[2], obs[3], obs[4]])
    pr_c = np.array([pr[0] + pr[1], pr[2], pr[3], pr[4]])
    chi, p = stats.chisquare(obs_c, pr_c * obs_c.sum())
    r["Póker (5 dígitos)"] = (chi, p)

    return {k: {"estadistico": float(v[0]), "p_value": float(v[1]), "pasa": bool(v[1] >= 0.01)}
            for k, v in r.items()}


def autocorrelacion(u: np.ndarray, max_lag: int) -> np.ndarray:
    c = u - u.mean()
    var = np.dot(c, c)
    return np.array([np.dot(c[:-k], c[k:]) / var for k in range(1, max_lag + 1)])


# ------------------------------------------------------------------ figuras
def guardar(fig, carpeta: Path, nombre: str) -> str:
    ruta = carpeta / nombre
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)
    return nombre


def figuras(gens: dict, carpeta: Path) -> list[tuple[str, str, str]]:
    figs = []
    trng = gens["TRNG Arduino"].astype(np.float64) / 2**32
    n = trng.size

    # 1. Histograma
    fig, ejes = plt.subplots(1, 2, figsize=(12, 3.8), sharey=True)
    for ax, nombre in zip(ejes, ["TRNG Arduino", "Bits crudos"]):
        u = gens[nombre].astype(np.float64) / 2**32
        ax.hist(u, bins=50, color=COL[nombre], edgecolor="#fcfcfb", linewidth=1)
        esperado = n / 50
        banda = 3 * math.sqrt(esperado)
        ax.axhline(esperado, color=TINTA, lw=1, ls="--")
        ax.axhspan(esperado - banda, esperado + banda, color=TINTA2, alpha=0.08)
        ax.set_title(f"{nombre} — 160,000 números en 50 clases")
        ax.set_xlabel("valor normalizado en [0, 1)")
    ejes[0].set_ylabel("frecuencia")
    tope = max(np.histogram(gens[g].astype(np.float64) / 2**32, bins=50, range=(0, 1))[0].max()
               for g in ["TRNG Arduino", "Bits crudos"])
    ejes[0].set_ylim(0, max(tope, n / 50) * 1.1)
    figs.append((guardar(fig, carpeta, "fig_01_histograma.png"),
                 "Histograma de frecuencias",
                 "Línea punteada = frecuencia esperada (3,200 por clase); franja gris = ±3σ. "
                 "Si la distribución es uniforme, todas las barras quedan dentro de la franja gris (±3σ). "
                 "Los bits crudos pueden inclinarse porque el ADC tiene sesgo; tras SHA-256 desaparece."))

    # 2. Mapas de bits
    fig, ejes = plt.subplots(1, 3, figsize=(12, 4.4))
    lado = 256
    for ax, nombre in zip(ejes, ["TRNG Arduino", "Bits crudos", "RANDU"]):
        x = gens[nombre]
        if nombre == "RANDU":
            bajo = ((x[: lado * lado // 8] >> 1) & 0xFF).astype(np.uint8)
            bits = np.unpackbits(bajo)                # 8 bits más bajos de RANDU
            titulo = "RANDU — sus 8 bits más bajos"
        else:
            bits = a_bits(x)[: lado * lado]
            titulo = f"{nombre} — primeros 65,536 bits"
        ax.imshow(bits.reshape(lado, lado), cmap="gray", interpolation="nearest")
        ax.set_title(titulo, fontsize=10)
        ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
    figs.append((guardar(fig, carpeta, "fig_02_mapa_bits.png"),
                 "Mapa de bits",
                 "Cada píxel es un bit (blanco = 1, negro = 0). Una buena fuente se ve como estática de TV "
                 "sin patrones. Los bits bajos de RANDU tienen periodos muy cortos (el último siempre vale 1) "
                 "y dibujan franjas regulares."))

    # 3. Pares consecutivos
    fig, ejes = plt.subplots(1, 2, figsize=(10, 5))
    for ax, nombre in zip(ejes, ["TRNG Arduino", "RANDU"]):
        u = gens[nombre].astype(np.float64) / 2**32
        ax.scatter(u[:-1:2][:20000], u[1::2][:20000], s=0.6, color=COL[nombre], alpha=0.6, linewidths=0)
        ax.set_aspect("equal"); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        ax.set_title(f"{nombre} — 20,000 pares (xᵢ, xᵢ₊₁)")
        ax.set_xlabel("xᵢ"); ax.set_ylabel("xᵢ₊₁")
    figs.append((guardar(fig, carpeta, "fig_03_pares.png"),
                 "Dispersión de pares consecutivos",
                 "En 2 dimensiones ambos llenan el cuadrado de forma uniforme: a simple vista RANDU parece "
                 "bueno. Por eso hace falta mirar en 3D."))

    # 4. Tríos en 3D: RANDU cae en 15 planos
    fig = plt.figure(figsize=(12, 5.6))
    for i, nombre in enumerate(["TRNG Arduino", "RANDU"]):
        u = gens[nombre].astype(np.float64) / 2**32
        t = u[: 30000 * 3].reshape(-1, 3)
        ax = fig.add_subplot(1, 2, i + 1, projection="3d")
        ax.scatter(t[:, 0], t[:, 1], t[:, 2], s=0.4, color=COL[nombre], alpha=0.5, linewidths=0)
        # vista "de canto" respecto a los planos 9x − 6y + z = k de RANDU
        ax.view_init(elev=0, azim=math.degrees(math.atan2(-9, -6)))
        ax.set_title(f"{nombre} — 30,000 tríos (xᵢ, xᵢ₊₁, xᵢ₊₂)", fontsize=10)
        ax.set_xticklabels([]); ax.set_yticklabels([]); ax.set_zticklabels([])
    figs.append((guardar(fig, carpeta, "fig_04_trios_3d.png"),
                 "Tríos consecutivos en 3D",
                 "Vistos desde el ángulo correcto, los tríos de RANDU caen en solo 15 planos paralelos "
                 "(xᵢ₊₂ = 6xᵢ₊₁ − 9xᵢ mód 1). Nuestro TRNG llena el cubo sin estructura."))

    # 5. Autocorrelación
    fig, ax = plt.subplots(figsize=(12, 3.8))
    lags = np.arange(1, 51)
    for nombre, desplaz in [("TRNG Arduino", -0.18), ("Bits crudos", 0.18)]:
        u = gens[nombre].astype(np.float64) / 2**32
        ac = autocorrelacion(u, 50)
        ax.vlines(lags + desplaz, 0, ac, color=COL[nombre], lw=2, label=nombre)
        ax.plot(lags + desplaz, ac, "o", color=COL[nombre], ms=3)
    lim = 1.96 / math.sqrt(n)
    ax.axhspan(-lim, lim, color=TINTA2, alpha=0.1)
    ax.axhline(0, color=TINTA2, lw=0.8)
    ax.text(50.5, lim, " ±1.96/√n", va="bottom", color=TINTA2, fontsize=9)
    ax.set_xlabel("rezago k"); ax.set_ylabel("autocorrelación r(k)")
    ax.set_title("Autocorrelación de la secuencia para rezagos 1 a 50")
    ax.legend(loc="upper right", ncol=2)
    figs.append((guardar(fig, carpeta, "fig_05_autocorrelacion.png"),
                 "Autocorrelación",
                 "Mide si un número “recuerda” a los anteriores. Para una secuencia independiente, ~95 % "
                 "de las barras caen en la franja gris."))

    # 6. Caminata aleatoria
    fig, ax = plt.subplots(figsize=(12, 4.2))
    pasos = 1_000_000
    for nombre in ["TRNG Arduino", "Bits crudos", "Mersenne Twister"]:
        b = a_bits(gens[nombre])[:pasos].astype(np.int8)
        cam = np.cumsum(2 * b - 1, dtype=np.int64)
        ax.plot(np.arange(pasos)[::200], cam[::200], color=COL[nombre], lw=1.4, label=nombre)
    k = np.arange(1, pasos)
    ax.fill_between(k[::200], -3 * np.sqrt(k[::200]), 3 * np.sqrt(k[::200]), color=TINTA2, alpha=0.08)
    ax.set_xlabel("número de bits"); ax.set_ylabel("posición (+1 por cada 1, −1 por cada 0)")
    ax.set_title("Caminata aleatoria con el primer millón de bits")
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.legend(loc="upper left")
    figs.append((guardar(fig, carpeta, "fig_06_caminata.png"),
                 "Caminata aleatoria",
                 "Cada 1 sube y cada 0 baja. Con bits justos la caminata se mantiene dentro de ±3√n "
                 "(zona gris). Un sesgo pequeño en los bits crudos hace que la caminata se escape."))

    # 7. Montecarlo π
    fig, ax = plt.subplots(figsize=(12, 3.8))
    for nombre in ["TRNG Arduino", "Mersenne Twister", "RANDU"]:
        u = gens[nombre].astype(np.float64) / 2**32
        xy = u[: n // 2 * 2].reshape(-1, 2)
        dentro = (xy ** 2).sum(axis=1) <= 1
        est = 4 * np.cumsum(dentro) / np.arange(1, dentro.size + 1)
        ax.plot(np.arange(1, dentro.size + 1), est, color=COL[nombre], lw=1.4, label=nombre)
    ax.axhline(math.pi, color=TINTA, lw=1, ls="--")
    ax.text(n // 2, math.pi, "π ", ha="right", va="bottom", color=TINTA)
    ax.set_xscale("log"); ax.set_ylim(2.9, 3.4); ax.set_xlim(100, n // 2 * 1.3)
    ax.set_xlabel("puntos usados (escala log)"); ax.set_ylabel("estimación de π")
    ax.set_title("Aplicación: estimar π con el método de Montecarlo (80,000 puntos)")
    ax.legend(loc="upper right")
    figs.append((guardar(fig, carpeta, "fig_07_montecarlo_pi.png"),
                 "Aplicación: Montecarlo",
                 "Lanzamos puntos al azar en un cuadrado y contamos cuántos caen en el cuarto de círculo. "
                 "Con buenos números aleatorios, la estimación converge a π."))
    return figs


def figura_nist(res_nist: dict, carpeta: Path) -> tuple[str, str, str]:
    nombres = list(nist.PRUEBAS)
    pruebas = [p for p, _ in nombres]
    fig, ax = plt.subplots(figsize=(12, 4.6))
    y = np.arange(len(pruebas))
    desplaz = {"TRNG Arduino": -0.27, "Bits crudos": -0.09, "Mersenne Twister": 0.09, "RANDU": 0.27}
    for gen, r in res_nist.items():
        props = [r["pruebas"][p]["proporcion"] for p in pruebas]
        ax.scatter(props, y + desplaz[gen], color=COL[gen], s=40, label=gen, zorder=3,
                   edgecolors="#fcfcfb", linewidths=1)
    minimo = next(iter(res_nist.values()))["proporcion_minima"]
    ax.axvline(minimo, color=TINTA, lw=1, ls="--")
    ax.text(minimo, len(pruebas) - 0.4, f" mínimo aceptable {minimo:.3f}", color=TINTA, fontsize=9)
    ax.set_yticks(y); ax.set_yticklabels(pruebas); ax.invert_yaxis()
    ax.set_xlim(-0.03, 1.03)
    ax.set_xlabel("proporción de las 50 secuencias que pasan (p ≥ 0.01)")
    ax.set_title("Batería NIST SP 800-22 — proporción de secuencias aprobadas")
    ax.legend(loc="lower left", ncol=4, bbox_to_anchor=(0, -0.32))
    return (guardar(fig, carpeta, "fig_08_nist.png"), "Batería NIST SP 800-22",
            "Cada punto es la proporción de secuencias que aprueba una prueba. A la derecha de la línea "
            "punteada se aprueba la prueba.")


# ------------------------------------------------------------------ reporte HTML
def img64(ruta: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(ruta.read_bytes()).decode()


def reporte(carpeta: Path, meta: dict, res: dict, figs: list) -> None:
    gens = list(res)
    def marca(ok): return '<span class="ok">✔ pasa</span>' if ok else '<span class="no">✘ falla</span>'

    filas_nist = ""
    for prueba, _ in nist.PRUEBAS:
        celdas = "".join(
            f"<td>{res[g]['nist']['pruebas'][prueba]['proporcion']:.2f} "
            f"{marca(res[g]['nist']['pruebas'][prueba]['pasa'])}</td>" for g in gens)
        filas_nist += f"<tr><th>{prueba}</th>{celdas}</tr>"
    filas_cl = ""
    for prueba in res[gens[0]]["clasicas"]:
        celdas = "".join(
            f"<td>p = {res[g]['clasicas'][prueba]['p_value']:.4f} "
            f"{marca(res[g]['clasicas'][prueba]['pasa'])}</td>" for g in gens)
        filas_cl += f"<tr><th>{prueba}</th>{celdas}</tr>"
    resumen = "".join(
        f"<div class='tile'><div class='lbl'><i style='background:{COL[g]}'></i>{g}</div>"
        f"<div class='big'>{res[g]['aprobadas']}/{res[g]['total']}</div>"
        f"<div class='lbl'>pruebas aprobadas</div></div>" for g in gens)
    bloques_fig = "".join(
        f"<figure><h3>{t}</h3><img src='{img64(carpeta / f)}' alt='{t}'><figcaption>{c}</figcaption></figure>"
        for f, t, c in figs)
    ent = meta["entropia_calibracion"]
    sim = "Simulación" in meta["fuente"]
    aviso = ("<p class='aviso'>⚠ Estos datos vienen de la <b>simulación</b>, no del Arduino. "
             "Sirven para probar el software; para la entrega ejecuta el generador con el Arduino conectado.</p>"
             if sim else "")

    html = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Reporte de validación TRNG</title>
<style>
:root{{--bg:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--line:#e4e3df;--ok:#008300;--no:#c62828}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}}
main{{max-width:1100px;margin:0 auto;padding:32px 16px 64px}}
h1{{font-size:28px;margin:0 0 4px}} h2{{margin-top:44px;font-size:20px;border-bottom:1px solid var(--line);padding-bottom:6px}}
h3{{font-size:16px;margin:0 0 8px}} .sub{{color:var(--ink2);margin:0}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-top:20px}}
.tile{{border:1px solid var(--line);border-radius:10px;padding:14px 16px}}
.tile .big{{font-size:30px;font-weight:650;font-variant-numeric:tabular-nums}}
.lbl{{color:var(--ink2);font-size:13px}} .lbl i{{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px}}
.wrap{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;font-size:13.5px;font-variant-numeric:tabular-nums}}
td,th{{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}} thead th{{color:var(--ink2);font-weight:600}}
.ok{{color:var(--ok);font-weight:600}} .no{{color:var(--no);font-weight:600}}
figure{{margin:32px 0}} figure img{{width:100%;height:auto;border:1px solid var(--line);border-radius:8px}}
figcaption{{color:var(--ink2);font-size:14px;margin-top:6px}}
dl{{display:grid;grid-template-columns:max-content 1fr;gap:4px 16px}} dt{{color:var(--ink2)}} dd{{margin:0;font-variant-numeric:tabular-nums}}
.aviso{{background:#fff4d6;border:1px solid #eda100;border-radius:8px;padding:10px 14px}}
</style></head><body><main>
<h1>Reporte de validación del TRNG</h1>
<p class="sub">{meta['cantidad_numeros']:,} números de 32 bits · fuente: {meta['fuente']} · {meta['fecha']}</p>
{aviso}
<div class="tiles">{resumen}</div>

<h2>Fuente de entropía</h2>
<dl>
<dt>Bits crudos analizados</dt><dd>{ent['bits_analizados']:,}</dd>
<dt>Proporción de unos (crudo)</dt><dd>{ent['proporcion_unos']:.4f}</dd>
<dt>Min-entropía MCV</dt><dd>{ent['h_mcv']:.4f} bits/bit</dd>
<dt>Min-entropía Markov</dt><dd>{ent['h_markov']:.4f} bits/bit</dd>
<dt>Bits crudos por bloque SHA-256</dt><dd>{meta['acondicionador']['bytes_crudos_por_bloque'] * 8} → 256 bits de salida</dd>
<dt>Alarmas de salud (RCT / APT)</dt><dd>{meta['pruebas_salud']['fallos_rct']} / {meta['pruebas_salud']['fallos_apt']}</dd>
<dt>Tiempo total</dt><dd>{meta['tiempo_total_s']:,} s ({meta['tasa_numeros_por_s']:,} números/s)</dd>
</dl>

<h2>Batería NIST SP 800-22</h2>
<p class="sub">50 secuencias de {res[gens[0]]['nist']['bits_por_secuencia']:,} bits. Valor = proporción de secuencias con p ≥ 0.01; se aprueba si es ≥ {res[gens[0]]['nist']['proporcion_minima']:.3f}.</p>
<div class="wrap"><table><thead><tr><th>Prueba</th>{''.join(f'<th>{g}</th>' for g in gens)}</tr></thead><tbody>{filas_nist}</tbody></table></div>

<h2>Pruebas clásicas sobre los números</h2>
<p class="sub">Se aprueba si p ≥ 0.01.</p>
<div class="wrap"><table><thead><tr><th>Prueba</th>{''.join(f'<th>{g}</th>' for g in gens)}</tr></thead><tbody>{filas_cl}</tbody></table></div>

<p class="sub" style="margin-top:14px"><b>Cómo leer un “falla” aislado:</b> con α = 0.01, incluso un generador perfecto
falla cada prueba el 1 % de las veces por puro azar; con 17 pruebas, la probabilidad de ver al menos un fallo aislado ronda el 15 %.
Lo que delata a un mal generador es fallar <i>muchas</i> pruebas o con p-values extremos (p &lt; 10⁻⁶), como los bits crudos y RANDU.</p>

<h2>Análisis visual</h2>
{bloques_fig}
</main></body></html>"""
    (carpeta / "reporte.html").write_text(html, encoding="utf-8")


# ------------------------------------------------------------------ main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", default="salida")
    args = ap.parse_args()
    carpeta = Path(args.entrada)
    meta = json.loads((carpeta / "metadatos.json").read_text(encoding="utf-8"))
    gens = cargar_generadores(carpeta)

    res = {}
    for nombre, x in gens.items():
        print(f"Probando {nombre}…")
        r_nist = nist.bateria(a_bits(x))
        r_cl = pruebas_clasicas(x)
        aprob = sum(v["pasa"] for v in r_nist["pruebas"].values()) + sum(v["pasa"] for v in r_cl.values())
        res[nombre] = {"nist": r_nist, "clasicas": r_cl, "aprobadas": aprob,
                       "total": len(r_nist["pruebas"]) + len(r_cl)}
        print(f"  {aprob}/{res[nombre]['total']} pruebas aprobadas")

    print("Generando figuras…")
    figs = []
    if (carpeta / "fig_00_senales_sensores.png").exists():
        figs.append(("fig_00_senales_sensores.png", "Señales de los sensores",
                     "Izquierda: la lectura del ADC (10 bits) parece estable. Derecha: su bit menos "
                     "significativo cambia de forma impredecible por el ruido; de ahí sale la entropía."))
    figs += figuras(gens, carpeta)
    figs.append(figura_nist({g: res[g]["nist"] for g in res}, carpeta))

    print("Simulando cráteres lunares…")
    import crateres                      # aplicación: la Luna simulada (fig_09–fig_11)
    figs += crateres.generar_figuras(carpeta)

    (carpeta / "resultados.json").write_text(
        json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    reporte(carpeta, meta, res, figs)
    print(f"Reporte: {(carpeta / 'reporte.html').resolve()}")


if __name__ == "__main__":
    main()
