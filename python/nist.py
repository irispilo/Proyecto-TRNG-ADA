"""
Pruebas estadísticas de NIST SP 800-22 rev. 1a (implementación propia con numpy).

Cada función recibe un arreglo de bits (0/1) y devuelve uno o más p-values.
Una secuencia "pasa" una prueba si p >= 0.01.

Pruebas incluidas (9 de las 15 de la batería, las más usadas en cursos):
  1. Frecuencia (monobit)          5. Rango de matrices binarias
  2. Frecuencia por bloques        6. Espectral (DFT)
  3. Rachas (runs)                 7. Serial (2 p-values)
  4. Racha más larga de unos       8. Entropía aproximada
                                   9. Sumas acumuladas (ida y vuelta)
"""

from __future__ import annotations

import math

import numpy as np
from scipy.special import erfc, gammaincc
from scipy.stats import norm


def frecuencia(b):
    n = b.size
    s = np.sum(2 * b.astype(np.int64) - 1)
    return [float(erfc(abs(s) / math.sqrt(2 * n)))]


def frecuencia_bloques(b, M=1280):
    N = b.size // M
    pi = b[: N * M].reshape(N, M).mean(axis=1)
    chi = 4 * M * np.sum((pi - 0.5) ** 2)
    return [float(gammaincc(N / 2, chi / 2))]


def rachas(b):
    n = b.size
    pi = b.mean()
    if abs(pi - 0.5) >= 2 / math.sqrt(n):
        return [0.0]
    V = 1 + np.count_nonzero(b[1:] != b[:-1])
    num = abs(V - 2 * n * pi * (1 - pi))
    den = 2 * math.sqrt(2 * n) * pi * (1 - pi)
    return [float(erfc(num / den))]


def racha_mas_larga(b, M=128):
    N = b.size // M
    bloques = b[: N * M].reshape(N, M)
    v = np.zeros(6)
    for fila in bloques:
        p = np.concatenate(([0], fila, [0]))
        d = np.diff(p)
        largos = np.flatnonzero(d == -1) - np.flatnonzero(d == 1)
        L = largos.max() if largos.size else 0
        v[min(max(L, 4), 9) - 4] += 1
    pis = np.array([0.1174, 0.2430, 0.2493, 0.1752, 0.1027, 0.1124])
    chi = np.sum((v - N * pis) ** 2 / (N * pis))
    return [float(gammaincc(5 / 2, chi / 2))]


def _rango_gf2(filas):
    filas = list(filas)
    rango = 0
    for bit in range(31, -1, -1):
        mascara = 1 << bit
        piv = next((i for i in range(rango, len(filas)) if filas[i] & mascara), None)
        if piv is None:
            continue
        filas[rango], filas[piv] = filas[piv], filas[rango]
        for i in range(len(filas)):
            if i != rango and filas[i] & mascara:
                filas[i] ^= filas[rango]
        rango += 1
    return rango


def rango_matrices(b, Q=32):
    N = b.size // (Q * Q)
    pesos = (1 << np.arange(Q - 1, -1, -1)).astype(np.uint64)
    F = np.zeros(3)
    for k in range(N):
        mat = b[k * Q * Q:(k + 1) * Q * Q].reshape(Q, Q).astype(np.uint64)
        filas = (mat * pesos).sum(axis=1).tolist()
        r = _rango_gf2(int(x) for x in filas)
        F[0 if r == Q else 1 if r == Q - 1 else 2] += 1
    p = np.array([0.2888, 0.5776, 0.1336])
    chi = np.sum((F - N * p) ** 2 / (N * p))
    return [float(math.exp(-chi / 2))]


def espectral(b):
    n = b.size
    X = 2 * b.astype(np.float64) - 1
    mod = np.abs(np.fft.fft(X))[: n // 2]
    T = math.sqrt(math.log(1 / 0.05) * n)
    N0 = 0.95 * n / 2
    N1 = np.count_nonzero(mod < T)
    d = (N1 - N0) / math.sqrt(n * 0.95 * 0.05 / 4)
    return [float(erfc(abs(d) / math.sqrt(2)))]


def _conteo_patrones(b, m):
    if m == 0:
        return np.array([b.size])
    ext = np.concatenate((b, b[: m - 1])).astype(np.int64)
    n = b.size
    val = np.zeros(n, dtype=np.int64)
    for j in range(m):
        val = (val << 1) | ext[j:j + n]
    return np.bincount(val, minlength=2 ** m)


def serial(b, m=10):
    n = b.size

    def psi2(mm):
        if mm <= 0:
            return 0.0
        v = _conteo_patrones(b, mm)
        return (2 ** mm / n) * np.sum(v.astype(np.float64) ** 2) - n

    p0, p1, p2 = psi2(m), psi2(m - 1), psi2(m - 2)
    d1 = p0 - p1
    d2 = p0 - 2 * p1 + p2
    return [float(gammaincc(2 ** (m - 2), d1 / 2)), float(gammaincc(2 ** (m - 3), d2 / 2))]


def entropia_aproximada(b, m=10):
    n = b.size

    def phi(mm):
        c = _conteo_patrones(b, mm) / n
        c = c[c > 0]
        return np.sum(c * np.log(c))

    apen = phi(m) - phi(m + 1)
    chi = 2 * n * (math.log(2) - apen)
    return [float(gammaincc(2 ** (m - 1), chi / 2))]


def sumas_acumuladas(b):
    n = b.size
    X = 2 * b.astype(np.int64) - 1
    res = []
    for seq in (X, X[::-1]):
        z = np.max(np.abs(np.cumsum(seq)))
        sq = math.sqrt(n)
        k1 = np.arange(int((-n / z + 1) // 4), int((n / z - 1) // 4) + 1)
        s1 = np.sum(norm.cdf((4 * k1 + 1) * z / sq) - norm.cdf((4 * k1 - 1) * z / sq))
        k2 = np.arange(int((-n / z - 3) // 4), int((n / z - 1) // 4) + 1)
        s2 = np.sum(norm.cdf((4 * k2 + 3) * z / sq) - norm.cdf((4 * k2 + 1) * z / sq))
        res.append(float(1 - s1 + s2))
    return res


PRUEBAS = [
    ("Frecuencia (monobit)", frecuencia),
    ("Frecuencia por bloques", frecuencia_bloques),
    ("Rachas", rachas),
    ("Racha más larga de unos", racha_mas_larga),
    ("Rango de matrices binarias", rango_matrices),
    ("Espectral (DFT)", espectral),
    ("Serial", serial),
    ("Entropía aproximada", entropia_aproximada),
    ("Sumas acumuladas", sumas_acumuladas),
]


def bateria(bits: np.ndarray, n_secuencias: int = 50, alfa: float = 0.01) -> dict:
    """
    Metodología NIST: se divide el flujo en `n_secuencias` secuencias y se
    aplica cada prueba a cada una. Se reporta la PROPORCIÓN de secuencias
    que pasan y se compara con el mínimo aceptable:
        p̂ - 3·sqrt(p̂(1-p̂)/m),  con p̂ = 1 - alfa.
    """
    largo = bits.size // n_secuencias
    secs = bits[: largo * n_secuencias].reshape(n_secuencias, largo)
    p_hat = 1 - alfa
    minimo = p_hat - 3 * math.sqrt(p_hat * (1 - p_hat) / n_secuencias)
    resultados = {}
    for nombre, f in PRUEBAS:
        pvals = np.array([f(s) for s in secs])          # (m, k)
        prop = (pvals >= alfa).mean(axis=0)            # por sub-prueba
        resultados[nombre] = {
            "proporcion": float(prop.min()),
            "pasa": bool(prop.min() >= minimo),
            "p_values": pvals.min(axis=1).round(6).tolist(),
        }
    return {
        "n_secuencias": n_secuencias,
        "bits_por_secuencia": int(largo),
        "proporcion_minima": minimo,
        "pruebas": resultados,
    }
