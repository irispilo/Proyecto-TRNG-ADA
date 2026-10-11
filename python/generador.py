"""
Generador de números aleatorios verdaderos (TRNG) con Arduino Uno.

Arquitectura (modelo NIST SP 800-90B):

    Sensores ─► ADC ─► LSB ⊕ ─► [bits crudos] ─► Pruebas de salud ─►
    ─► Acondicionamiento SHA-256 ─► [bits de entropía completa] ─► números

Uso:
    python generador.py --puerto COM3          (Windows)
    python generador.py --puerto /dev/ttyACM0  (Linux)
    python generador.py --puerto /dev/cu.usbmodem1101  (macOS)
    python generador.py --simulado             (sin hardware, solo pruebas)

Salida (carpeta ./salida):
    numeros.csv      160,000 números: entero de 32 bits y uniforme en [0,1)
    numeros.bin      los mismos números en binario (uint32 little-endian)
    crudo.bin        todos los bits crudos capturados (para analizarlos)
    metadatos.json   entropía estimada, pruebas de salud, tiempos, tasa
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from fuentes import FuenteArduino, FuenteSimulada
from salud import PruebasSalud, estimar_entropia

BITS_SALIDA_BLOQUE = 256      # SHA-256
MARGEN_ENTROPIA = 64          # SP 800-90B: entrada >= salida + 64 bits de entropía
BYTES_CALIBRACION = 25_000    # 200,000 bits crudos (~16 s en el Arduino)


def barra(actual: int, total: int, t0: float, extra: str = "") -> None:
    frac = actual / total
    llenos = int(30 * frac)
    trans = time.time() - t0
    eta = trans / frac - trans if frac > 0 else 0
    sys.stdout.write(
        f"\r  [{'█' * llenos}{'·' * (30 - llenos)}] {frac:6.1%}  "
        f"{actual:,}/{total:,}  ETA {eta:5.0f}s {extra}   "
    )
    sys.stdout.flush()


def generar(fuente, cantidad: int, carpeta: Path) -> dict:
    carpeta.mkdir(parents=True, exist_ok=True)
    crudo_f = open(carpeta / "crudo.bin", "wb")
    t_inicio = time.time()

    # ---------- 1. Calibración: ¿cuánta entropía tiene cada bit crudo? ----------
    print(f"\n[1/3] Calibrando fuente: {fuente.nombre}")
    print(f"      {fuente.info}")
    cal = fuente.leer_bytes(BYTES_CALIBRACION)
    crudo_f.write(cal)
    bits_cal = np.unpackbits(np.frombuffer(cal, dtype=np.uint8))
    ent = estimar_entropia(bits_cal)
    h = ent["h_min"]
    print(f"      Proporción de unos: {ent['proporcion_unos']:.4f}")
    print(f"      Min-entropía MCV:    {ent['h_mcv']:.4f} bits/bit")
    print(f"      Min-entropía Markov: {ent['h_markov']:.4f} bits/bit")
    print(f"      → Se usa H = {h:.4f} bits de entropía por bit crudo")
    if h < 0.1:
        raise RuntimeError(
            "La fuente casi no tiene entropía (H < 0.1). Revisa las conexiones "
            "de los sensores: un pin sin conectar a nada o un cable suelto."
        )

    # ---------- 2. Parámetros del acondicionador ----------
    bits_entrada = math.ceil((BITS_SALIDA_BLOQUE + MARGEN_ENTROPIA) / h)
    bytes_entrada = math.ceil(bits_entrada / 8)
    bytes_salida_total = cantidad * 4
    bloques = math.ceil(bytes_salida_total / (BITS_SALIDA_BLOQUE // 8))
    print(f"\n[2/3] Acondicionamiento SHA-256: {bytes_entrada} bytes crudos "
          f"({bytes_entrada * 8} bits) → 32 bytes de salida por bloque")
    print(f"      Bloques necesarios: {bloques:,}  "
          f"(≈ {bloques * bytes_entrada * 8 / 1e6:.2f} M bits crudos)")

    salud = PruebasSalud(h)
    salida = bytearray()
    contador = 0
    descartados = 0
    LOTE = 64  # bloques SHA por lectura
    print(f"\n[3/3] Generando {cantidad:,} números de 32 bits")
    t_gen = time.time()
    while len(salida) < bytes_salida_total:
        crudo = fuente.leer_bytes(bytes_entrada * LOTE)
        crudo_f.write(crudo)
        bits = np.unpackbits(np.frombuffer(crudo, dtype=np.uint8))
        if not salud.revisar(bits):
            descartados += LOTE          # lote sospechoso: se descarta completo
            if salud.fallos_rct + salud.fallos_apt > 50:
                raise RuntimeError("Demasiadas alarmas de salud: la fuente parece dañada.")
            continue
        for i in range(LOTE):
            trozo = crudo[i * bytes_entrada:(i + 1) * bytes_entrada]
            salida.extend(hashlib.sha256(struct.pack("<Q", contador) + trozo).digest())
            contador += 1
        barra(min(len(salida) // 4, cantidad), cantidad, t_gen)
    print()
    crudo_f.close()

    numeros = np.frombuffer(bytes(salida[:bytes_salida_total]), dtype="<u4")
    t_total = time.time() - t_inicio

    # ---------- Guardado ----------
    numeros.tofile(carpeta / "numeros.bin")
    with open(carpeta / "numeros.csv", "w", encoding="utf-8") as f:
        f.write("indice,entero_32b,uniforme_0_1\n")
        for i, x in enumerate(numeros.tolist()):
            f.write(f"{i},{x},{x / 2**32:.10f}\n")

    bytes_crudos = (carpeta / "crudo.bin").stat().st_size
    meta = {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "fuente": fuente.nombre,
        "info_fuente": fuente.info,
        "cantidad_numeros": int(cantidad),
        "bits_por_numero": 32,
        "entropia_calibracion": ent,
        "acondicionador": {
            "algoritmo": "SHA-256(contador || bloque_crudo)",
            "bytes_crudos_por_bloque": bytes_entrada,
            "bits_salida_por_bloque": BITS_SALIDA_BLOQUE,
            "bloques_generados": contador,
            "bloques_descartados_por_salud": descartados,
        },
        "pruebas_salud": salud.resumen(),
        "bits_crudos_totales": bytes_crudos * 8,
        "tiempo_total_s": round(t_total, 2),
        "tasa_numeros_por_s": round(cantidad / t_total, 1),
        "eficiencia_bits_salida_por_bit_crudo": round(cantidad * 32 / (bytes_crudos * 8), 4),
    }
    with open(carpeta / "metadatos.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    print(f"\n✔ Listo: {cantidad:,} números en {t_total:.1f} s "
          f"({meta['tasa_numeros_por_s']:,} números/s)")
    print(f"  Alarmas de salud: RCT={salud.fallos_rct}  APT={salud.fallos_apt}")
    print(f"  Archivos en: {carpeta.resolve()}")
    return meta


def main() -> None:
    ap = argparse.ArgumentParser(description="TRNG con sensores de Arduino Uno")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--puerto", help="puerto serial del Arduino (COM3, /dev/ttyACM0, ...)")
    g.add_argument("--simulado", action="store_true", help="usar la simulación (sin hardware)")
    ap.add_argument("--cantidad", type=int, default=160_000)
    ap.add_argument("--salida", default="salida")
    args = ap.parse_args()

    fuente = FuenteSimulada() if args.simulado else FuenteArduino(args.puerto)
    try:
        generar(fuente, args.cantidad, Path(args.salida))
    finally:
        fuente.cerrar()


if __name__ == "__main__":
    main()
