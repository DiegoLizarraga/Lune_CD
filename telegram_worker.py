"""
telegram_worker.py — Lanza y supervisa el bot de Telegram (Node.js)
en un hilo aparte, retransmitiendo su salida a la UI.
"""
import subprocess
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal


class TelegramBotWorker(QThread):
    log_signal = pyqtSignal(str); stopped = pyqtSignal()
    BOT_DIR = Path(__file__).parent / "telegram-bot-or"

    def __init__(self):
        super().__init__(); self._process = None

    def run(self):
        if not self.BOT_DIR.exists():
            self.log_signal.emit(f"No encontré la carpeta: {self.BOT_DIR}"); self.stopped.emit(); return
        if not (self.BOT_DIR / "node_modules").exists():
            self.log_signal.emit("Instalando dependencias (npm install)...")
            try: subprocess.run(["npm","install"], cwd=str(self.BOT_DIR), check=True, capture_output=True)
            except Exception as e: self.log_signal.emit(f"npm install falló: {e}"); self.stopped.emit(); return
        self.log_signal.emit("Iniciando bot de Telegram...")
        try:
            self._process = subprocess.Popen(["npm","start"], cwd=str(self.BOT_DIR), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            for line in self._process.stdout:
                self.log_signal.emit(line.rstrip())
                if self.isInterruptionRequested(): break
        except Exception as e: self.log_signal.emit(f"Error: {e}")
        finally: self.stop(); self.stopped.emit()

    def stop(self):
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try: self._process.wait(timeout=3)
            except subprocess.TimeoutExpired: self._process.kill()
            self._process = None
