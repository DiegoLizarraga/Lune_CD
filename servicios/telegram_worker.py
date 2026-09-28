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
    False sin romper. `esperar_envios(tope_s)` espera a que la cola se vacíe. El
    escritor se va solo cuando ya no hay bot y no le queda nada que escribir.

Parar (`stop()`): marca la parada (si llega durante la primera instalación, mata
el árbol de npm y el bot ya no se lanza: dos bots con el mismo token darían 409),
espera un momento a que se escriba lo que quedaba en la cola y cierra el stdin; si
el escritor se quedó atascado, no lo cierra (se bloquearía). Si el bot no se va
solo, se mata su árbol (node y lo que hubiera lanzado).

Las líneas del canal van en ASCII (json con \\uXXXX), así no dependen de la
página de códigos de la consola. El stdout se lee como UTF-8.

Instalación (la primera vez, sin node_modules/grammy): el mismo endurecimiento que
el bot de Minecraft (lune_core/minecraft_proceso.py): `npm ci --omit=optional
--ignore-scripts --no-audit --no-fund` con el package-lock.json del repo
(versiones exactas e integridad sha512, sin scripts de instalación de terceros).
npm va como `node <npm-cli.js>` SIN shell (o el npm del PATH si no viene junto a
node), sin ventana y con tope de 10 min. El Popen se guarda: stop() mata su árbol.

Lanzamiento: `node bot.js` SIN shell (antes `npm start` con shell en Windows:
`terminate()` solo mataba cmd.exe y dejaba node huérfano). El entorno del hijo no
hereda NODE_OPTIONS ni ninguna LUNE_* de fuera. El bot, lanzado por Lune
(LUNE_BOT_HIJO=1), se cierra solo cuando se cierra su stdin, y `stop()` cierra el
stdin antes de matarlo.
"""
from __future__ import annotations

import json
import os
import queue
import re
import secrets
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional

from PyQt6.QtCore import QThread, pyqtSignal

# Sin ventana de consola en Windows: npm abría una terminal negra encima de la app.
SIN_CONSOLA = {}
if os.name == "nt":
    SIN_CONSOLA = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
# Fuera de Windows, npm y el bot en su propio grupo: matar_arbol los mata con sus hijos.
_GRUPO = {} if os.name == "nt" else {"start_new_session": True}

TIMEOUT_INSTALAR_S = 600
ARGS_NPM_CI = ("ci", "--omit=optional", "--ignore-scripts", "--no-audit", "--no-fund")
AVISO_SIN_NODE = "Hace falta Node.js 18 o más nuevo (nodejs.org) para el bot de Telegram."

MARCA_ORDEN = "@@LUNE_ORDEN"
ENV_TOKEN = "LUNE_ORDENES_TOKEN"
ENV_HIJO = "LUNE_BOT_HIJO"          # el bot lo lanzó Lune: se cierra al cerrarse su stdin
TIPO_MENSAJE = "orden:mensaje"
MAX_ORDEN = 1000                    # caracteres de la orden que se aceptan
MAX_RESPUESTA = 3900                # un mensaje de Telegram admite 4096
COLA_RESPUESTAS = 256               # respuestas esperando al escritor del stdin (≤ ~1 MB)
ESPERA_COLA_AL_PARAR_S = 1.0        # stop(): lo que se espera a que se escriba lo pendiente
ESPERA_ESCRITOR_S = 1.0             # el escritor sin trabajo mira cada tanto si ya no hay bot
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


# ── npm y procesos ─────────────────────────────────────────────────────────────
def comando_npm(node: Optional[str], which: Callable[[str], Optional[str]] = shutil.which) -> Optional[List[str]]:
    """npm sin shell: `node <npm-cli.js>` si viene junto a node; si no, el npm del PATH."""
    if node:
        try:
            cli = Path(node).resolve().parent / "node_modules" / "npm" / "bin" / "npm-cli.js"
            if cli.is_file():
                return [str(node), str(cli)]
        except OSError:
            pass
    w = which("npm")
    return [w] if w else None


def _paquete_completo(carpeta: Path) -> bool:
    """¿Está el paquete de node_modules con su package.json y el archivo de su «main»?"""
    try:
        pkg = json.loads((carpeta / "package.json").read_text("utf-8"))
    except (OSError, ValueError):
        return False
    main = pkg.get("main") if isinstance(pkg, dict) else None
    if not isinstance(main, str) or not main.strip():
        return True                             # sin «main» (solo tipos o «exports»)
    m = carpeta / main.strip()
    return any(p.is_file() for p in (m, m.with_name(m.name + ".js"), m / "index.js",
                                     m.with_name(m.name + ".json")))


def matar_arbol(p, espera_s: float = 3.0) -> None:
    """Mata el proceso `p` y sus hijos (npm lanza node; el bot, edge-tts…). Nunca lanza."""
    try:
        if p is None or p.poll() is not None:
            return
    except Exception:
        return
    pid = getattr(p, "pid", None)
    if isinstance(pid, int) and pid > 0:
        if os.name == "nt":
            try:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], stdin=subprocess.DEVNULL,
                               capture_output=True, timeout=10, **SIN_CONSOLA)
            except Exception:
                pass
        else:
            try:
                os.killpg(pid, signal.SIGKILL)          # su propio grupo (_GRUPO)
            except Exception:
                pass
    try:
        if p.poll() is None:
            p.terminate()
            p.wait(timeout=espera_s)
    except subprocess.TimeoutExpired:
        try:
            p.kill()
        except Exception:
            pass
    except Exception:
        pass


class TelegramBotWorker(QThread):
    log_signal = pyqtSignal(str); stopped = pyqtSignal()
    orden_recibida = pyqtSignal(str, str)       # (id, texto) de una orden /pc
    BOT_DIR = Path(__file__).parent.parent / "telegram-bot-or"

    def __init__(self, ordenes: bool = False):
        """ordenes: True solo si `ordenes_activas(config)` (función encendida y admin)."""
        super().__init__(); self._process = None
        self._token = secrets.token_hex(16) if ordenes else ""
        self._lock = threading.Lock()           # _process, _instalador y el escritor (UI, hilo del bot y stop())
        self._parar = threading.Event()         # stop() pedido: no lanzar el bot (o cerrarlo ya)
        self._cola = queue.Queue(maxsize=COLA_RESPUESTAS)   # (proceso, línea) para el stdin
        self._escritor = None                   # hilo «lune-tg-stdin»
        self._roto_de = None                    # proceso cuya tubería se rompió al escribir
        self._aviso_lleno = False               # ya se avisó de la cola llena (hasta que se vacíe)
        self._node: Optional[str] = None        # ruta de node (None = la del PATH)
        self._instalador = None                 # Popen de `npm ci` mientras instala (stop() lo mata)

    def _parado(self) -> bool:
        return self._parar.is_set() or self.isInterruptionRequested()

    @property
    def ordenes(self) -> bool:
        """¿Este bot se lanzó con el canal de órdenes abierto?"""
        return bool(self._token)

    def _entorno(self, hijo: bool = True) -> dict:
        """Entorno del hijo SIN NODE_OPTIONS ni LUNE_* de fuera (nunca un token heredado;
        NODE_OPTIONS haría cargar código ajeno a npm o al bot). `hijo`: el bot (con
        LUNE_BOT_HIJO y, con órdenes, su token); False para npm."""
        env = {k: v for k, v in os.environ.items()
               if not k.upper().startswith("LUNE_") and k.upper() != "NODE_OPTIONS"}
        if hijo:
            env[ENV_HIJO] = "1"
            if self._token:
                env[ENV_TOKEN] = self._token
        return env

    # ── Instalar (la primera vez) ─────────────────────────────────────────────
    def _ruta_node(self) -> Optional[str]:
        return self._node or shutil.which("node")

    def instalado(self) -> bool:
        """grammy y cada paquete del lockfile en node_modules CON su «main». Una copia a
        medias (p. ej. copiada sin las carpetas lib/ o dist/: node-fetch sin lib/index.js)
        no cuenta: el bot no arrancaría, así que se reinstala con npm ci."""
        nm = self.BOT_DIR / "node_modules"
        if not (nm / "grammy" / "package.json").is_file():
            return False
        try:
            lock = json.loads((self.BOT_DIR / "package-lock.json").read_text("utf-8"))
            paquetes = [k for k, v in (lock.get("packages") or {}).items()
                        if k.startswith("node_modules/") and isinstance(v, dict)
                        and not any(v.get(c) for c in ("optional", "dev", "devOptional", "peer"))]
        except (OSError, ValueError, AttributeError):
            return True                         # sin lockfile legible no hay con qué comparar
        return all(_paquete_completo(self.BOT_DIR / k) for k in paquetes)

    def _instalar(self, node: str) -> bool:
        """`npm ci --omit=optional --ignore-scripts --no-audit --no-fund` con el lockfile
        del repo, sin shell ni ventana, con tope. True si quedó instalado. Bloquea (va
        en el hilo del bot); stop() lo corta matando el árbol de npm."""
        npm = comando_npm(node)
        if not npm:
            self.log_signal.emit("No encuentro npm (viene con Node.js)."); return False
        if not (self.BOT_DIR / "package-lock.json").is_file():
            self.log_signal.emit("Falta telegram-bot-or/package-lock.json: no instalo sin versiones fijas.")
            return False
        self.log_signal.emit("Instalando dependencias (npm ci)...")
        with self._lock:
            if self._parado():
                return False
            try:
                p = subprocess.Popen(npm + list(ARGS_NPM_CI), cwd=str(self.BOT_DIR),
                                     stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                     errors="replace", env=self._entorno(hijo=False),
                                     **SIN_CONSOLA, **_GRUPO)
            except Exception as e:
                self.log_signal.emit(f"No pude lanzar npm: {e}"[:300]); return False
            self._instalador = p
        try:
            salida, _ = p.communicate(timeout=TIMEOUT_INSTALAR_S)
        except subprocess.TimeoutExpired:
            matar_arbol(p)
            try:
                p.communicate(timeout=5)             # recoge lo que quedaba y cierra la tubería
            except Exception:
                pass
            self.log_signal.emit("npm tardó más de 10 minutos: lo corté. Prueba otra vez con mejor conexión.")
            return False
        except Exception as e:
            matar_arbol(p)
            self.log_signal.emit(f"npm ci falló: {e}"[:300]); return False
        finally:
            with self._lock:
                if self._instalador is p:
                    self._instalador = None
        if self._parado():
            return False
        if p.returncode == 0 and self.instalado():
            return True
        ultimas = " · ".join(l.strip() for l in str(salida or "").splitlines()[-4:] if l.strip())
        self.log_signal.emit(f"npm ci falló (código {p.returncode}): {ultimas}"[:400])
        return False

    def run(self):
        if not self.BOT_DIR.exists():
            self.log_signal.emit(f"No encontré la carpeta: {self.BOT_DIR}"); self.stopped.emit(); return
        node = self._ruta_node()
        if not node:
            self.log_signal.emit(AVISO_SIN_NODE); self.stopped.emit(); return
        if not self.instalado() and not self._instalar(node):
            self.stopped.emit(); return
        # Te pidieron parar mientras instalaba (apagar el bot, cambiar de interfaz: la
        # ventana nueva lanza el suyo): no se lanza. Dos bots con el mismo token → 409.
        if self._parado():
            self.stopped.emit(); return
        self.log_signal.emit("Iniciando bot de Telegram...")
        try:
            p = subprocess.Popen([node, "bot.js"], cwd=str(self.BOT_DIR), stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                 encoding="utf-8", errors="replace", bufsize=1,
                                 env=self._entorno(), **SIN_CONSOLA, **_GRUPO)
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
        yo = threading.current_thread()
        while True:
            try:
                item = self._cola.get(timeout=ESPERA_ESCRITOR_S)
            except queue.Empty:
                # Sin bot (parado o nunca lanzado) y nada que escribir: el hilo se va (el
                # siguiente responder_orden arranca otro). Con el candado: nadie encola a medias.
                with self._lock:
                    if self._process is None and self._cola.empty():
                        if self._escritor is yo:
                            self._escritor = None
                        return
                continue
            try:
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
        """Marca la parada (run() ya no lanza el bot; un `npm ci` en marcha se mata con su
        árbol), deja que se escriba lo que quedaba en la cola (ESPERA_COLA_AL_PARAR_S) y
        cierra el stdin (el bot lanzado por Lune se cierra solo al verlo); si sigue vivo,
        mata su árbol. Si el escritor se quedó atascado en una tubería llena, el stdin no
        se cierra (se bloquearía): se mata el proceso.
        Idempotente; se puede llamar desde la UI o el hilo."""
        self._parar.set()
        with self._lock:
            instalador = self._instalador
            p = self._process
            self._process = None             # sin bot: el escritor, ya sin trabajo, se va solo
        if instalador is not None:
            matar_arbol(instalador)          # run() sale de communicate() y no lanza el bot
        if p is None:
            return
        if self.esperar_envios(ESPERA_COLA_AL_PARAR_S) and p.stdin is not None:
            try:
                p.stdin.close()
            except (OSError, ValueError):
                pass
        try:
            p.wait(timeout=3)
            return
        except subprocess.TimeoutExpired:
            pass
        except Exception:
            return
        matar_arbol(p)
