"""
Evaluación de la fuente cruda (basado en NIST SP 800-90B).

1. Estimación de min-entropía por bit crudo:
   - Estimador MCV (valor más común, sección 6.3.1).
   - Estimador de Markov (sección 6.3.3): detecta dependencia entre bits
     consecutivos, que es el defecto típico de un ADC.
   Se usa el MÍNIMO de ambos (criterio conservador).

2. Pruebas de salud continuas (sección 4.4), que detectan si un sensor
   falla (p. ej. un cable desconectado que deja el pin en un valor fijo):
   - Repetition Count Test (RCT): demasiados bits iguales seguidos.
   - Adaptive Proportion Test (APT): un valor aparece demasiado en una
     ventana de 1024 bits.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.stats import binom


def entropia_mcv(bits: np.ndarray) -> float:
    n = bits.size
    p = max(bits.mean(), 1 - bits.mean())
    p_u = min(1.0, p + 2.576 * math.sqrt(p * (1 - p) / (n - 1)))  # cota sup. 99 %
    return -math.log2(p_u)


def entropia_markov(bits: np.ndarray) -> float:
    b = bits.astype(np.int8)
    n = b.size
    p1 = b.mean()
    p0 = 1 - p1
    a, c = b[:-1], b[1:]
    n0 = np.count_nonzero(a == 0)
    n1 = n - 1 - n0
    p00 = np.count_nonzero((a == 0) & (c == 0)) / max(n0, 1)
    p01 = 1 - p00
    p11 = np.count_nonzero((a == 1) & (c == 1)) / max(n1, 1)
    p10 = 1 - p11
    L = 128
    candidatos = [
        p0 * p00 ** (L - 1),
        p0 * p01 ** (L // 2) * p10 ** (L // 2 - 1),
        p0 * p01 * p11 ** (L - 2),
        p1 * p10 * p00 ** (L - 2),
        p1 * p10 ** (L // 2) * p01 ** (L // 2 - 1),
        p1 * p11 ** (L - 1),
    ]
    p_max = max(candidatos)
    return min(-math.log2(p_max) / L, 1.0)


def estimar_entropia(bits: np.ndarray) -> dict:
    h_mcv = entropia_mcv(bits)
    h_markov = entropia_markov(bits)
    return {
        "bits_analizados": int(bits.size),
        "proporcion_unos": float(bits.mean()),
        "h_mcv": h_mcv,
        "h_markov": h_markov,
        "h_min": min(h_mcv, h_markov),
    }


class PruebasSalud:
    """Pruebas continuas RCT y APT sobre el flujo de bits crudos."""

    VENTANA_APT = 1024

    def __init__(self, h_min: float, alfa_exp: int = 30):
        h = max(h_min, 0.05)
        self.corte_rct = 1 + math.ceil(alfa_exp / h)
        self.corte_apt = int(binom.ppf(1 - 2.0 ** -alfa_exp, self.VENTANA_APT, 2.0 ** -h)) + 1
        self.fallos_rct = 0
        self.fallos_apt = 0
        self.bits_revisados = 0
        self._ultimo = None
        self._racha = 0

    def revisar(self, bits: np.ndarray) -> bool:
        """Devuelve True si el bloque pasa; False si hay alarma."""
        ok = True
        # --- RCT: racha máxima (continuando la racha del bloque anterior)
        cambios = np.flatnonzero(np.diff(bits)) + 1
        bordes = np.concatenate(([0], cambios, [bits.size]))
        longitudes = np.diff(bordes)
        if self._ultimo is not None and bits[0] == self._ultimo:
            longitudes[0] += self._racha
        if longitudes.max() >= self.corte_rct:
            self.fallos_rct += 1
            ok = False
        self._ultimo = int(bits[-1])
        self._racha = int(longitudes[-1])

        # --- APT: proporción del primer valor de cada ventana
        W = self.VENTANA_APT
        for i in range(0, bits.size - W + 1, W):
            ventana = bits[i:i + W]
            if np.count_nonzero(ventana == ventana[0]) >= self.corte_apt:
                self.fallos_apt += 1
                ok = False
        self.bits_revisados += bits.size
        return ok

    def resumen(self) -> dict:
        return {
            "corte_rct": self.corte_rct,
            "corte_apt": self.corte_apt,
            "ventana_apt": self.VENTANA_APT,
            "bits_revisados": self.bits_revisados,
            "fallos_rct": self.fallos_rct,
            "fallos_apt": self.fallos_apt,
        }
