"""
Fuentes de entropía cruda.

- FuenteArduino: lee el flujo de bits crudos que envía el sketch
  `generador_entropia.ino` por el puerto serial (USB).
- FuenteSimulada: SOLO PARA PRUEBAS sin hardware. Modela lo que hace el
  Arduino (ADC de 10 bits con señal + ruido + interferencia de 60 Hz, se
  toma el LSB y se hace XOR de 3 sensores) para poder ejecutar y depurar
  todo el sistema. No debe usarse para la entrega final: el requisito del
  proyecto es que la aleatoriedad provenga de sensores externos reales.
"""

from __future__ import annotations

import os
import time

import numpy as np


class FuenteArduino:
    """Lee bits crudos del Arduino Uno por puerto serial."""

    def __init__(self, puerto: str, baudios: int = 500_000, timeout: float = 2.0):
        import serial  # pyserial

        self.nombre = f"Arduino Uno ({puerto})"
        self.ser = serial.Serial(puerto, baudios, timeout=timeout)
        time.sleep(2.0)                 # el Uno se reinicia al abrir el puerto
        self.ser.reset_input_buffer()
        self.ser.write(b"I")
        time.sleep(0.2)
        self.info = self.ser.readline().decode(errors="replace").strip()
        self.ser.reset_input_buffer()
        self.ser.write(b"B")            # iniciar flujo binario de bits crudos

    def leer_bytes(self, n: int) -> bytes:
        datos = bytearray()
        while len(datos) < n:
            trozo = self.ser.read(n - len(datos))
            if not trozo:
                raise TimeoutError(
                    "El Arduino dejó de enviar datos. Revisa el cable USB, "
                    "el puerto y que el sketch esté cargado."
                )
            datos.extend(trozo)
        return bytes(datos)

    def cerrar(self) -> None:
        try:
            self.ser.write(b"X")
        finally:
            self.ser.close()


class FuenteSimulada:
    """
    Simulación física del Arduino (solo para pruebas sin hardware).

    Cada "lectura" de un sensor es:
        señal lenta (deriva de luz) + 60 Hz (red eléctrica) + ruido gaussiano
    cuantizada a 10 bits. El ruido gaussiano sale de un generador de numpy sembrado con os.urandom, de modo
    que la simulación tiene imperfecciones realistas (sesgo, correlación)
    pero sí contiene entropía.
    """

    TASA_BITS = 12_500  # bits/s aproximados del Arduino real con 3 sensores

    def __init__(self, sensores: int = 3, sigma_ruido: float = 0.3):
        self.nombre = "Simulación (sin hardware)"
        self.info = f"SIMULADO | sensores={sensores} | sigma={sigma_ruido} LSB"
        self.sensores = sensores
        self.sigma = sigma_ruido
        self.rng = np.random.default_rng(int.from_bytes(os.urandom(16), "little"))
        self.t = 0.0
        self.dt = 1.0 / self.TASA_BITS

    def _lecturas(self, n: int) -> np.ndarray:
        t = self.t + np.arange(n) * self.dt
        self.t = float(t[-1] + self.dt)
        bits = np.zeros(n, dtype=np.uint8)
        for s in range(self.sensores):
            base = 400 + 150 * s
            senal = (
                base
                + 30 * np.sin(2 * np.pi * 0.05 * t + s)      # deriva lenta
                + 2.2 * np.sin(2 * np.pi * 60 * t + 0.7 * s)  # interferencia 60 Hz
            )
            ruido = self.rng.normal(0, self.sigma, n)
            # pequeña correlación temporal (filtro RC del ADC)
            ruido[1:] = 0.8 * ruido[1:] + 0.2 * ruido[:-1]
            adc = np.clip(np.round(senal + ruido), 0, 1023).astype(np.int32)
            bits ^= (adc & 1).astype(np.uint8)
        return bits

    def leer_bytes(self, n: int) -> bytes:
        return np.packbits(self._lecturas(n * 8)).tobytes()

    def cerrar(self) -> None:
        pass
