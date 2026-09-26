"""
telegram_worker.py — Lanza y supervisa el bot de Telegram (Node.js)
en un hilo aparte, retransmitiendo su salida a la UI.

Órdenes desde Telegram (/pc <orden>)
------------------------------------
El canal es el stdin/stdout del propio proceso del bot (sin red ni hub):

  · Al lanzarlo, si la función está activada (config telegram.ordenes_pc) Y hay
    apis.telegram_admin_id, se genera un token aleatorio (secrets.token_hex(16))
    que el bot recibe en la variable de entorno LUNE_ORDENES_TOKEN. Sin eso, el
    bot contesta a /pc que la función está apagada.
  · El bot pide una orden escribiendo en su stdout una línea
        @@LUNE_ORDEN <token> {"id": "...", "texto": "...", "chat_id": ...}
    El worker la reconoce (token correcto) y emite `orden_recibida(id, texto)`.
    Esas líneas NUNCA van al log de la UI (con token malo tampoco: se ignoran),
    y el token no aparece en el log aunque el bot lo imprimiera en otra línea.
  · `responder_orden(id, texto)` pone en una cola una línea JSON
    {"tipo": "orden:mensaje", "id", "texto"} que un hilo escritor («lune-tg-stdin»)
    escribe en el stdin del bot; el bot la manda al chat de esa orden. Así la
    llamada nunca bloquea el hilo de Qt aunque el bot no lea su stdin (tubería
    llena): con la cola llena, la respuesta se descarta con un aviso en el log.
    Es thread-safe y, si el proceso ya murió (o la tubería se rompió), devuelve
    False sin romper. `esperar_envios(tope_s)` espera a que la cola se vacíe.

Parar (`stop()`): marca la parada (si llega durante el primer `npm install`, el
bot ya no se lanza: dos bots con el mismo token darían 409), espera un momento a
que se escriba lo que quedaba en la cola y cierra el stdin; si el escritor se quedó
atascado, no lo cierra (se bloquearía) y termina el proceso.

Las líneas del canal van en ASCII (json con \\uXXXX), así no dependen de la
página de códigos de la consola. El stdout se lee como UTF-8.

Lanzamiento: `npm start` con shell en Windows. Comprobado en Windows 11: npm
hereda el stdio, así que el stdin llega a `node bot.js` (y la variable de
entorno también). Pero `terminate()` con shell solo mata cmd.exe y dejaba node
huérfano; por eso el bot, lanzado por Lune (LUNE_BOT_HIJO=1), se cierra solo
cuando se cierra su stdin, y `stop()` cierra el stdin antes de terminar.
"""
from __future__ import annotations

import json
import os
import queue
import re
import secrets
import subprocess
import threading
import time
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

# Sin ventana de consola en Windows: npm abría una terminal negra encima de la app.
SIN_CONSOLA = {}
if os.name == "nt":
    SIN_CONSOLA = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}

MARCA_ORDEN = "@@LUNE_ORDEN"
ENV_TOKEN = "LUNE_ORDENES_TOKEN"
ENV_HIJO = "LUNE_BOT_HIJO"          # el bot lo lanzó Lune: se cierra al cerrarse su stdin
TIPO_MENSAJE = "orden:mensaje"
MAX_ORDEN = 1000                    # caracteres de la orden que se aceptan
MAX_RESPUESTA = 3900                # un mensaje de Telegram admite 4096
COLA_RESPUESTAS = 256               # respuestas esperando al escritor del stdin (≤ ~1 MB)
ESPERA_COLA_AL_PARAR_S = 1.0        # stop(): lo que se espera a que se escriba lo pendiente
AVISO_COLA_LLENA = ("Telegram: el bot no está leyendo lo que le mando; descarto una respuesta "
                    "para no congelar Lune.")
_ID_VALIDO = re.compile(r"[A-Za-z0-9_\-]{1,40}")
_ADMIN_VALIDO = re.compile(r"\d{1,20}")

# Textos de las órdenes (piel web y nativa): burbuja en el chat y respuestas al bot.
PREFIJO_TELEGRAM = "📱 Telegram: "
PREFIJO_IA = "[Desde Telegram] "            # así el modelo sabe que no estás delante del PC
AVISO_TG_DESACTIVADAS = "Las órdenes desde Telegram están desactivadas en Lune."
AVISO_TG_OCUPADA = "Lune está ocupada, prueba en un momento."
AVISO_TG_DETENIDA = "Se detuvo la respuesta en el PC."
SIN_TEXTO = "(Lune no dijo nada)"


def admin_id() -> str:
    """apis.telegram_admin_id si tiene forma de ID de Telegram (solo dígitos); si no, ""."""
    try:
        from nucleo import datos
        tid = str(datos.telegram_admin_id() or "").strip()
    except Exception:
        return ""
    return tid if _ADMIN_VALIDO.fullmatch(tid) else ""


def admin_configurado() -> bool:
    """¿Hay un apis.telegram_admin_id con forma de ID de Telegram?"""
    return bool(admin_id())


def ordenes_activas(config) -> bool:
    """«Órdenes desde Telegram» encendido en la config y con tu ID de Telegram puesto."""
    try:
        activo = bool(config.get("telegram", "ordenes_pc", False))
    except Exception:
        return False
    return activo and admin_configurado()


class TelegramBotWorker(QThread):
    log_signal = pyqtSignal(str); stopped = pyqtSignal()
    orden_recibida = pyqtSignal(str, str)       # (id, texto) de una orden /pc
    BOT_DIR = Path(__file__).parent.parent / "telegram-bot-or"

    def __init__(self, ordenes: bool = False):
        """ordenes: True solo si `ordenes_activas(config)` (función encendida y admin)."""
        super().__init__(); self._process = None
        self._token = secrets.token_hex(16) if ordenes else ""
        self._lock = threading.Lock()           # _process y el escritor (UI, hilo del bot y stop())
        self._parar = threading.Event()         # stop() pedido: no lanzar el bot (o cerrarlo ya)
        self._cola = queue.Queue(maxsize=COLA_RESPUESTAS)   # (proceso, línea) para el stdin
        self._escritor = None                   # hilo «lune-tg-stdin»
        self._roto_de = None                    # proceso cuya tubería se rompió al escribir
        self._aviso_lleno = False               # ya se avisó de la cola llena (hasta que se vacíe)

    def _parado(self) -> bool:
        return self._parar.is_set() or self.isInterruptionRequested()

    @property
    def ordenes(self) -> bool:
        """¿Este bot se lanzó con el canal de órdenes abierto?"""
        return bool(self._token)

    def _entorno(self) -> dict:
        env = dict(os.environ)
        env.pop(ENV_TOKEN, None)                # nunca uno heredado de fuera
        env[ENV_HIJO] = "1"
        if self._token:
            env[ENV_TOKEN] = self._token
        return env

    def run(self):
        if not self.BOT_DIR.exists():
            self.log_signal.emit(f"No encontré la carpeta: {self.BOT_DIR}"); self.stopped.emit(); return
        if not (self.BOT_DIR / "node_modules").exists():
            self.log_signal.emit("Instalando dependencias (npm install)...")
            try: subprocess.run(["npm","install"], cwd=str(self.BOT_DIR), check=True, capture_output=True, shell=(os.name == "nt"), **SIN_CONSOLA)
            except Exception as e: self.log_signal.emit(f"npm install falló: {e}"); self.stopped.emit(); return
        # Te pidieron parar mientras instalaba (apagar el bot, cambiar de interfaz: la
        # ventana nueva lanza el suyo): no se lanza. Dos bots con el mismo token → 409.
        if self._parado():
            self.stopped.emit(); return
        self.log_signal.emit("Iniciando bot de Telegram...")
        try:
            p = subprocess.Popen(["npm","start"], cwd=str(self.BOT_DIR), stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                 encoding="utf-8", errors="replace", bufsize=1,
                                 shell=(os.name == "nt"), env=self._entorno(), **SIN_CONSOLA)
            with self._lock:
                self._process = p
            if self._parado():
                return                          # stop() llegó justo ahora: finally lo cierra
            for line in p.stdout:
                self.procesar_linea(line)
                if self.isInterruptionRequested(): break
        except Exception as e: self.log_signal.emit(self._sin_token(f"Error: {e}"))
        finally: self.stop(); self.stopped.emit()

    # ── Salida del bot ────────────────────────────────────────────────────────
    def _sin_token(self, texto: str) -> str:
        return texto.replace(self._token, "***") if self._token else texto

    def procesar_linea(self, linea: str) -> None:
        """Una línea del stdout del bot: una orden (señal, nunca al log) o log sin token."""
        linea = str(linea or "").rstrip("\r\n")
        if MARCA_ORDEN in linea:
            orden = self.leer_orden(linea[linea.index(MARCA_ORDEN):])
            if orden is not None:
                self.orden_recibida.emit(*orden)
            return
        self.log_signal.emit(self._sin_token(linea))

    def leer_orden(self, linea: str):
        """(id, texto) si la línea es una orden con el token de este bot; si no, None."""
        if not self._token:
            return None
        partes = str(linea or "").strip().split(" ", 2)
        if len(partes) != 3 or partes[0] != MARCA_ORDEN:
            return None
        if not secrets.compare_digest(partes[1].encode("utf-8", "replace"),
                                      self._token.encode("ascii")):
            return None
        try:
            orden = json.loads(partes[2])
        except ValueError:
            return None
        if not isinstance(orden, dict):
            return None
        oid, texto = orden.get("id"), orden.get("texto")
        if not isinstance(oid, str) or not _ID_VALIDO.fullmatch(oid) or not isinstance(texto, str):
            return None
        texto = texto.strip()[:MAX_ORDEN].strip()
        if not texto:
            return None
        # Defensa en profundidad: el bot ya exige tu ID, pero la orden tiene que venir
        # de TU chat privado (chat_id = tu ID). Sin ID configurado pasa y la app
        # contesta que las órdenes están desactivadas.
        admin = admin_id()
        if admin and str(orden.get("chat_id", "")).strip() != admin:
            self.log_signal.emit("Orden de Telegram ignorada: no viene de tu chat "
                                 "(si cambiaste tu ID, reinicia el bot).")
            return None
        return oid, texto

    # ── Respuestas hacia el bot (stdin) ───────────────────────────────────────
    def responder_orden(self, oid: str, texto: str) -> bool:
        """Manda `texto` al chat de la orden `oid`: lo deja en la cola del escritor y
        vuelve YA (nunca bloquea: la escritura la hace el hilo «lune-tg-stdin»). False
        si no se pudo (sin canal, id raro, texto vacío, el bot ya no está, su tubería
        se rompió o la cola está llena: entonces se descarta con un aviso en el log).
        Se puede llamar desde cualquier hilo."""
        if not self._token:
            return False
        oid = str(oid or "")
        texto = str(texto or "").strip()
        if not _ID_VALIDO.fullmatch(oid) or not texto:
            return False
        if len(texto) > MAX_RESPUESTA:
            texto = texto[:MAX_RESPUESTA - 1].rstrip() + "…"
        linea = json.dumps({"tipo": TIPO_MENSAJE, "id": oid, "texto": texto}) + "\n"
        with self._lock:
            p = self._process
            if p is None or p.stdin is None or p is self._roto_de:
                return False
            try:
                if p.poll() is not None:
                    return False
            except Exception:
                return False
            try:
                self._cola.put_nowait((p, linea))
                lleno = False
            except queue.Full:
                lleno = True
            else:
                self._asegurar_escritor()
        if lleno:
            if not self._aviso_lleno:
                self._aviso_lleno = True
                self.log_signal.emit(AVISO_COLA_LLENA)
            return False
        return True

    def _asegurar_escritor(self) -> None:
        """Arranca el hilo escritor si no está vivo (con self._lock tomado)."""
        h = self._escritor
        if h is None or not h.is_alive():
            h = threading.Thread(target=self._escribir, name="lune-tg-stdin", daemon=True)
            self._escritor = h
            h.start()

    def _escribir(self) -> None:
        """Hilo escritor: línea a línea de la cola al stdin del bot. Si el bot no lee y
        la tubería se llena, el que se queda esperando es este hilo, no la interfaz."""
        while True:
            item = self._cola.get()
            try:
                if item is None:
                    return                       # stop(): ya no hay nada más que escribir
                p, linea = item
                try:
                    p.stdin.write(linea)
                    p.stdin.flush()
                    self._aviso_lleno = False
                except (OSError, ValueError, AttributeError):   # tubería rota o cerrada
                    self._roto_de = p
            finally:
                self._cola.task_done()

    def esperar_envios(self, tope_s: float = 2.0) -> bool:
        """Espera (como mucho `tope_s`) a que el escritor vacíe la cola. True si se vació."""
        fin = time.monotonic() + max(0.0, float(tope_s))
        c = self._cola
        with c.all_tasks_done:
            while c.unfinished_tasks:
                quedan = fin - time.monotonic()
                if quedan <= 0:
                    return False
                c.all_tasks_done.wait(quedan)
        return True

    def stop(self):
        """Marca la parada (run() ya no lanza el bot), deja que se escriba lo que quedaba
        en la cola (ESPERA_COLA_AL_PARAR_S) y cierra el stdin (el bot lanzado por Lune se
        cierra solo al verlo); si sigue vivo, lo termina. Si el escritor se quedó atascado
        en una tubería llena, el stdin no se cierra (se bloquearía): se termina el proceso.
        Idempotente; se puede llamar desde la UI o el hilo."""
        self._parar.set()
        with self._lock:
            p = self._process
            self._process = None
            escritor = self._escritor
        if p is None:
            return
        vacia = self.esperar_envios(ESPERA_COLA_AL_PARAR_S)
        if vacia:
            if p.stdin is not None:
                try:
                    p.stdin.close()
                except (OSError, ValueError):
                    pass
            if escritor is not None and escritor.is_alive():
                try:
                    self._cola.put_nowait(None)  # el escritor termina
                except queue.Full:
                    pass
        try:
            p.wait(timeout=3)
            return
        except subprocess.TimeoutExpired:
            pass
        except Exception:
            return
        if p.poll() is None:
            p.terminate()
            try: p.wait(timeout=3)
            except subprocess.TimeoutExpired: p.kill()
