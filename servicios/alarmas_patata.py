"""
servicios/alarmas_patata.py — Alarmas y temporizadores en el modo patata (terminal).

`AlarmasTerminal` hace en la terminal lo que ControlAlarmasQt en la app:

- Un hilo con un tic por segundo. Solo programa si es dueño del mutex
  `Local\\Lune_CD_Alarmas` (se reintenta cada 10 s): con la app y patata abiertas
  a la vez, suena UNA vez (y el reclamo atómico de alarmas.json es la segunda red).
- La app es la dueña PREFERENTE (tiene `Local\\Lune_CD_Alarmas_app` mientras sus
  alarmas están en marcha): patata no coge el mutex si la ve, y si ya lo tenía
  se lo cede en cuanto no suene nada (una alarma sonando no se corta: se espera a
  que se apague). La app recupera lo que pase entre medias desde `visto_hasta`.
- Al sonar: banner ANSI encima del prompt (`consola.aviso`), `\\a` y parpadeo
  en la barra de tareas (`consola.parpadear`), la capa de título «⏰ texto»
  (`consola.titulo_capa("alarma", …, 60)` si existe; si no, `titulo`) y un
  reclamo de la consola con el prompt «⏰ Enter apaga · p pospone»: la próxima
  línea no va al chat. El reclamo va con prioridad MAYOR que el de una aprobación
  pendiente («¿Lo hago? [s/N]»): el Enter o la «p» son de la alarma, no un «no».
    · Enter (o «a», «/apagar») apaga tras el bloqueo de 5 s; antes consume la
      línea y dice «(espera N s)».
    · «p» (o «/posponer») pospone `alarmas.posponer_min`.
    · Cualquier otra cosa: si ya se puede, apaga y la línea sigue al chat.
- Sonido por el Mezclador (canal «alarma», en bucle), como en la app. En modo
  juego también suena (D3).
- `comando(linea)`: /alarma HH:MM [lmxjvsd|todos] [texto], /alarma probar,
  /alarmas [on|off], /borrar_alarma <id|n>, /timer 10m [texto], /timers,
  /apagar, /posponer. None si la línea no es suya.
- `registrar_herramientas(tools)`: las cuatro herramientas del catálogo sobre
  el mismo almacén.

En la terminal no hay pantalla grande: la alarma es el banner, el sonido y el título.
"""
from __future__ import annotations

import logging
import math
import re
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from nucleo import alarmas as al
from nucleo.alarmas import Almacen, Disparo, Programador, texto_visible
from servicios.alarmas_aviso import SONIDOS, ControlAviso

_log = logging.getLogger("lune.alarmas")

REINTENTO_MUTEX_S = 10.0
PRIORIDAD_TITULO = 60
PRIORIDAD_RECLAMO = 10          # > 0 (aprobación de patata) > -10 (baile): el Enter es de la alarma
_APAGAR = frozenset({"", "a", "apagar", "/apagar", "ok", "vale", "ya", "stop"})
_POSPONER = frozenset({"p", "posponer", "/posponer", "pospon", "pospón"})
_COLORES = ("cyan", "yellow", "dim", "bold", "red", "reset")


class AlarmasTerminal:
    """Programador + aviso de las alarmas para patata (sin Qt)."""

    def __init__(self, consola: Any, config: Any, *, voice: Any = None, colores: Optional[Dict[str, str]] = None,
                 almacen: Optional[Almacen] = None, mezclador: Any = None, mutex: Any = None,
                 reloj: Callable[[], float] = time.monotonic, ahora: Optional[Callable[[], datetime]] = None,
                 epoch: Optional[Callable[[], float]] = None, aviso: Optional[ControlAviso] = None,
                 intervalo_s: float = 1.0, lanzar_sonido: Optional[Callable[[Callable[[], None]], Any]] = None,
                 mutex_app: Any = None):
        self.consola = consola
        self.config = config
        self.voice = voice
        c = dict(colores or {})
        self.c = {k: str(c.get(k, "") or "") for k in _COLORES}
        self._reloj = reloj
        self._ahora = ahora or datetime.now
        self._epoch = epoch or time.time
        self.intervalo_s = max(0.05, float(intervalo_s))
        self.almacen = almacen if almacen is not None else Almacen(al.RUTA)
        self.programador = Programador(self.almacen, recuperar_min=self._cfg("recuperar_min", al.RECUPERAR_MIN))
        if aviso is None:
            aviso = ControlAviso(mezclador=mezclador, almacen=self.almacen, reloj=reloj, epoch=self._epoch,
                                 lanzar=lanzar_sonido)
        self.aviso = aviso
        aviso.on_mostrar = self._on_mostrar
        aviso.on_ocultar = self._on_ocultar
        aviso.on_voz = self._on_voz
        self._mutex = mutex
        # ¿Está la app abierta? (su mutex `…_app`). Con un mutex de dueño inyectado (tests)
        # y sin `mutex_app`, no se mira: nada de mutex reales en los tests.
        self._mutex_app = mutex_app
        self._mutex_app_auto = mutex_app is None and mutex is None
        self._ultimo_mirar_app: Optional[float] = None
        self._fallo_tic = ""
        self._lock = threading.RLock()
        self._hilo: Optional[threading.Thread] = None
        self._parar = threading.Event()
        self._dueno = False
        self._recien_dueno = False
        self._ultimo_intento: Optional[float] = None
        self._activo_prev: Optional[bool] = None
        self._reclamo: Optional[dict] = None      # {"cancelar": fn, "prompt": str}

    # ── Config ─────────────────────────────────────────────────────────────────
    def _cfg(self, clave: str, defecto: Any = None, seccion: str = "alarmas") -> Any:
        try:
            v = self.config.get(seccion, clave, defecto) if self.config is not None else defecto
        except Exception:
            return defecto
        return defecto if v is None else v

    def _num(self, clave: str, defecto: float, lo: float, hi: float) -> float:
        try:
            v = float(self._cfg(clave, defecto))
        except (TypeError, ValueError):
            return defecto
        return min(max(v, lo), hi)

    def _activo(self) -> bool:
        return bool(self._cfg("activo", True))

    def recargar_config(self) -> None:
        self.programador.recuperar_min = self._num("recuperar_min", al.RECUPERAR_MIN, 0, 24 * 60)
        a = self.aviso
        a.bloqueo_s = self._num("bloqueo_s", 5, 0, 60)
        a.volumen = self._num("volumen", 0.8, 0, 1)
        a.posponer_min = self._num("posponer_min", 5, 1, 120)
        sonido = str(self._cfg("sonido", "azar") or "azar")
        a.sonido = sonido if sonido in SONIDOS else "azar"
        disp = self._cfg("dispositivo_salida", None, seccion="voz")
        a.dispositivo = str(disp) if disp is not None else None
        activo = self._activo()
        previo, self._activo_prev = self._activo_prev, activo
        if previo is False and activo:
            try:
                self.almacen.marcar_visto(self._epoch())
            except Exception:
                _log.exception("alarmas: no pude marcar visto_hasta")
            self.programador.reiniciar()
        elif previo and not activo:
            d = a.sonando
            pendientes = ([d] if d is not None else []) + list(a.cola)
            a.detener()
            for x in pendientes:
                try:
                    self.almacen.quitar_sonando(x)
                except Exception:
                    pass
            if d is not None:
                self._on_ocultar(d)

    # ── Ciclo de vida ──────────────────────────────────────────────────────────
    def iniciar(self) -> None:
        with self._lock:
            if self._hilo is not None and self._hilo.is_alive():
                return
            self._parar.clear()
            self.recargar_config()
            self._hilo = threading.Thread(target=self._bucle, name="LuneAlarmasPatata", daemon=True)
            self._hilo.start()

    def detener(self) -> None:
        """Para el hilo y calla. Lo que sonaba queda en alarmas.json para la próxima vez."""
        self._parar.set()
        hilo, self._hilo = self._hilo, None
        if hilo is not None and hilo is not threading.current_thread():
            hilo.join(timeout=2.0)
        try:
            self.aviso.detener()
        except Exception:
            pass
        self._soltar_reclamo()
        self._titulo(None)
        if self._mutex is not None and self._dueno:
            try:
                self._mutex.liberar()
            except Exception:
                pass
        self._dueno = False
        self._recien_dueno = False
        self._ultimo_intento = None
        self.programador.reiniciar()

    def _bucle(self) -> None:
        while not self._parar.wait(self.intervalo_s):
            self.tic()

    # ── Mutex del dueño ────────────────────────────────────────────────────────
    def _mutex_real(self):
        if self._mutex is None:
            from servicios.mutex_win import MutexNombrado
            self._mutex = MutexNombrado(al.nombre_mutex_dueno(self.almacen.ruta))
        return self._mutex

    def _asegurar_dueno(self) -> bool:
        m = self._mutex_real()
        if self._dueno:
            if bool(getattr(m, "es_dueno", True)):
                return not self._ceder_a_la_app()
            self._dueno = False
            self._ultimo_intento = None
        ahora = self._reloj()
        if self._ultimo_intento is not None and ahora - self._ultimo_intento < REINTENTO_MUTEX_S:
            return False
        self._ultimo_intento = ahora
        if self._app_presente():
            return False                          # la app está abierta: programa ella
        try:
            ok = bool(m.adquirir())
        except Exception:
            ok = False
        if ok:
            self._dueno = True
            self._recien_dueno = True
        return ok

    def _mutex_app_real(self):
        if self._mutex_app is None and self._mutex_app_auto:
            from servicios.mutex_win import MutexNombrado
            self._mutex_app = MutexNombrado(al.nombre_mutex_app(self.almacen.ruta))
        return self._mutex_app

    def _app_presente(self) -> bool:
        """¿Tiene alguien (la app) el mutex `…_app`? Se prueba a cogerlo: si se puede, no
        hay app y se suelta al momento."""
        m = self._mutex_app_real()
        if m is None:
            return False
        try:
            if m.adquirir():
                m.liberar()
                return False
            return True
        except Exception:
            return False

    def _ceder_a_la_app(self) -> bool:
        """Siendo dueña: si la app está abierta y aquí no suena nada, le pasa las alarmas
        (suelta el mutex; la app lo coge en su próximo reintento y recupera desde
        `visto_hasta`). Mira como mucho cada 10 s. True si cedió."""
        if self.aviso.sonando is not None or self.aviso.cola:
            return False                          # una alarma sonando no se corta
        ahora = self._reloj()
        if self._ultimo_mirar_app is not None and ahora - self._ultimo_mirar_app < REINTENTO_MUTEX_S:
            return False
        self._ultimo_mirar_app = ahora
        if not self._app_presente():
            return False
        try:
            self._mutex_real().liberar()
        except Exception:
            pass
        self._dueno = False
        self._recien_dueno = False
        self._ultimo_intento = ahora
        self.programador.reiniciar()
        _log.info("alarmas (patata): la app está abierta; le cedo las alarmas")
        self._imprimir(f"{self.c['dim']}⏰ La app de Lune está abierta: ella se encarga ahora de las alarmas."
                       f"{self.c['reset']}")
        return True

    @property
    def dueno(self) -> bool:
        return self._dueno

    # ── Tic ────────────────────────────────────────────────────────────────────
    def tic(self) -> None:
        """Un paso (el hilo lo llama cada segundo; los tests, a mano)."""
        try:
            self.recargar_config()           # barato; /alarmas off o la app pueden cambiarla
            activo = bool(self._activo_prev)
            if activo and self._asegurar_dueno():
                epoch = self._epoch()
                if self._recien_dueno:
                    self._recien_dueno = False
                    self.programador.reiniciar()
                    for d in self.programador.recuperar_sonando(epoch):
                        self._disparar(d)
                disparos, perdidas = self.programador.tick(self._ahora(), epoch)
                for d in disparos:
                    self._disparar(d)
                ahora = self._ahora()
                for p in perdidas:
                    self._imprimir(f"{self.c['dim']}⏰ {al.texto_perdida(p, ahora)}.{self.c['reset']}")
            self.aviso.tick()
            self._actualizar_prompt()
        except Exception as e:
            fallo = f"{type(e).__name__}: {e}"
            if fallo != self._fallo_tic:          # una traza y silencio mientras falle igual
                self._fallo_tic = fallo
                _log.exception("alarmas (patata): el tic falló (no se repite mientras falle igual)")
            return
        self._fallo_tic = ""

    def _disparar(self, d: Disparo) -> None:
        """Suena ya o, si otra está sonando, se avisa de que espera su turno."""
        if not self.aviso.disparar(d) and d in self.aviso.cola:
            self._imprimir(f"{self.c['dim']}⏰ En espera: {texto_visible(d)}{self.c['reset']}")

    # ── Salida ─────────────────────────────────────────────────────────────────
    def _imprimir(self, texto: str) -> None:
        try:
            self.consola.aviso(texto)
        except Exception:
            try:
                self.consola.imprimir(texto)
            except Exception:
                pass

    def _titulo(self, texto: Optional[str]) -> None:
        capa = getattr(self.consola, "titulo_capa", None)
        try:
            if callable(capa):
                capa("alarma", texto, PRIORIDAD_TITULO)
            elif texto:
                self.consola.titulo(f"Lune {texto}")
        except Exception:
            pass

    def banner(self, d: Disparo) -> str:
        c = self.c
        titulo = {"temporizador": "⏲ TEMPORIZADOR", "pospuesta": "⏲ POSPUESTA",
                  "prueba": "⏰ PRUEBA"}.get(d.tipo, "⏰ ALARMA")
        hora = f" {c['bold']}{d.programado}{c['reset']}" if d.programado else ""
        cola = len(self.aviso.cola)
        extra = f"  {c['dim']}(+{cola} en espera){c['reset']}" if cola else ""
        mins = int(round(float(getattr(self.aviso, "posponer_min", 5))))
        return (f"{c['red']}{c['bold']}{titulo}{c['reset']}{hora}  {c['bold']}{texto_visible(d)}{c['reset']}{extra}\n"
                f"{c['dim']}   Enter apaga · p pospone {mins} min{c['reset']}")

    def _prompt(self) -> str:
        falta = self.aviso.restante_bloqueo()
        if falta > 0:
            return f"⏰ espera {int(math.ceil(falta))} s… > "
        return "⏰ Enter apaga · p pospone > "

    # ── Callbacks de ControlAviso ──────────────────────────────────────────────
    def _on_mostrar(self, d: Disparo) -> None:
        self._imprimir(self.banner(d))
        try:
            self.consola.parpadear(veces=5, hasta_foco=True, campana=True)
        except TypeError:
            try:
                self.consola.parpadear()
            except Exception:
                pass
        except Exception:
            pass
        self._titulo(f"⏰ {texto_visible(d)}")
        self._reclamar()

    def _on_ocultar(self, d: Disparo) -> None:
        self._soltar_reclamo()
        self._titulo(None)
        motivo = getattr(self.aviso, "motivo_fin", "")
        if motivo == "cortada":
            self._imprimir(f"{self.c['dim']}⏰ «{texto_visible(d)}» se apagó sola tras "
                           f"{int(self.aviso.max_sonando_s // 60)} min.{self.c['reset']}")

    def _on_voz(self, d: Disparo) -> None:
        if self.voice is None or not self._cfg("decir_texto", True) or not d.texto:
            return
        try:
            self.voice.speak(d.texto)
        except Exception:
            pass

    # ── Reclamo de la consola («Enter apaga») ─────────────────────────────────
    def _reclamar(self) -> None:
        with self._lock:
            if self._reclamo is not None:
                return
            tok: dict = {"prompt": self._prompt()}

            def fn(linea: str, tok=tok):
                return self._atender(linea, tok)
            try:
                try:
                    tok["cancelar"] = self.consola.reclamar(fn, prompt=tok["prompt"], prioridad=PRIORIDAD_RECLAMO)
                except TypeError:                 # una consola sin prioridades
                    tok["cancelar"] = self.consola.reclamar(fn, prompt=tok["prompt"])
            except Exception:
                _log.exception("alarmas (patata): no pude reclamar la consola")
                return
            self._reclamo = tok

    def _soltar_reclamo(self) -> None:
        with self._lock:
            tok, self._reclamo = self._reclamo, None
        if tok is not None:
            try:
                tok["cancelar"]()
            except Exception:
                pass

    def _actualizar_prompt(self) -> None:
        """Cuenta atrás del bloqueo en el prompt (si la consola sabe cambiarlo)."""
        with self._lock:
            tok = self._reclamo
            if tok is None or self.aviso.sonando is None:
                return
            nuevo = self._prompt()
            if nuevo == tok.get("prompt"):
                return
            cambiar = getattr(tok.get("cancelar"), "cambiar_prompt", None)
            tok["prompt"] = nuevo
        if callable(cambiar):
            try:
                cambiar(nuevo)
            except Exception:
                pass

    def _atender(self, linea: str, tok: dict):
        """La línea que llegó con la alarma sonando. None = consumida; False = sigue al chat."""
        with self._lock:
            if self._reclamo is tok:
                self._reclamo = None             # el reclamo se consume al entregar la línea
        s = str(linea or "").strip().lower()
        if self.aviso.sonando is None:
            return False
        if s in _APAGAR or s in _POSPONER:
            if not self.aviso.puede_apagar():
                falta = int(math.ceil(self.aviso.restante_bloqueo())) or 1
                self._imprimir(f"{self.c['dim']}(espera {falta} s){self.c['reset']}")
                self._reclamar()
                return None
            if s in _POSPONER:
                if self.aviso.posponer():
                    mins = int(round(float(self.aviso.posponer_min)))
                    self._imprimir(f"{self.c['dim']}💤 Pospuesta {mins} min.{self.c['reset']}")
            else:
                self.aviso.apagar()
            return None
        # Otra cosa: si ya se puede, apaga y la línea sigue su camino (chat o comando).
        if self.aviso.puede_apagar():
            self.aviso.apagar()
            try:
                tok["cancelar"]()
            except Exception:
                pass
            return False
        with self._lock:
            if self._reclamo is None:
                self._reclamo = tok              # la consola lo vuelve a poner en la cola
        return False

    # ── API ────────────────────────────────────────────────────────────────────
    def registrar_herramientas(self, tools: Any) -> None:
        """temporizador, alarma, cancelar_alarma y listar_alarmas sobre este almacén."""
        al.registrar_herramientas(tools, self.almacen, self.config)

    def probar(self) -> bool:
        ahora = self._ahora()
        self.aviso.disparar(Disparo("prueba", "Prueba de alarma", "prueba", 0.0,
                                    ahora.strftime("%H:%M"), self._epoch()))
        return True

    def _aviso_apagadas(self) -> str:
        return "" if self._activo() else "\n(Las alarmas están apagadas: /alarmas on para encenderlas.)"

    def comando(self, linea: str) -> Optional[str]:
        """Atiende /alarma, /alarmas, /borrar_alarma, /timer, /timers, /apagar y
        /posponer. Devuelve el texto a imprimir, o None si la línea no es suya."""
        s = str(linea or "").strip()
        if not s.startswith("/"):
            return None
        cmd, _, arg = s.partition(" ")
        cmd, arg = cmd.lower(), arg.strip()
        try:
            if cmd == "/alarma":
                return self._cmd_alarma(arg)
            if cmd == "/alarmas":
                return self._cmd_alarmas(arg)
            if cmd in ("/borrar_alarma", "/borraralarma", "/quitar_alarma"):
                return self._cmd_borrar(arg)
            if cmd in ("/timer", "/temporizador"):
                return self._cmd_timer(arg)
            if cmd in ("/timers", "/temporizadores"):
                return self._cmd_timers()
            if cmd == "/apagar":
                return self._cmd_apagar(False)
            if cmd == "/posponer":
                return self._cmd_apagar(True)
        except Exception as e:
            _log.exception("alarmas (patata): %s falló", cmd)
            return f"No pude hacerlo: {e}"
        return None

    def _cmd_alarma(self, arg: str) -> str:
        if not arg:
            return ("Uso: /alarma HH:MM [lmxjvsd|todos] [texto]   (sin días = una sola vez)\n"
                    "     /alarma probar")
        if arg.lower() in ("probar", "prueba", "test"):
            self.probar()
            return "Sonando una alarma de prueba…"
        partes = arg.split(maxsplit=1)
        try:
            h, m = al.parsear_hora(partes[0])
        except ValueError as e:
            return f"{e}. Uso: /alarma 07:30 lmxjv gimnasio"
        resto = partes[1].strip() if len(partes) > 1 else ""
        dias, una_vez = 0, True
        if resto:
            primera, _, tras = resto.partition(" ")
            p = primera.lower()
            if re.fullmatch(f"[{al.DIAS}]+", p) or p in ("todos", "diario", "laborables", "finde"):
                dias = al.parsear_dias(p)
                una_vez = False
                resto = tras.strip()
        try:
            a = self.almacen.crear_alarma(h, m, dias, una_vez=una_vez, texto=resto)
        except ValueError as e:
            return f"No pude poner la alarma: {e}"
        return f"⏰ Alarma {a.id}: {al.texto_alarma(a, self._ahora())}.{self._aviso_apagadas()}"

    def _cmd_alarmas(self, arg: str) -> str:
        a = arg.lower()
        if a in ("on", "off", "si", "sí", "no"):
            on = a in ("on", "si", "sí")
            try:
                self.config.set("alarmas", "activo", on)
            except Exception as e:
                return f"No pude guardarlo: {e}"
            self.recargar_config()
            return "Alarmas encendidas." if on else "Alarmas apagadas (no sonará ninguna hasta /alarmas on)."
        if a:
            return "Uso: /alarmas [on|off]"
        return al.resumen(self.almacen, self._ahora(), self._epoch()) + self._aviso_apagadas()

    def _ordenados(self) -> List[Any]:
        return [*self.almacen.alarmas(), *self.almacen.temporizadores()]

    def _cmd_borrar(self, arg: str) -> str:
        if not arg:
            return "Uso: /borrar_alarma <id|n>   (el id o el número de /alarmas)"
        objetivo = None
        if arg.isdigit():
            lista = self._ordenados()
            n = int(arg)
            if 1 <= n <= len(lista):
                objetivo = lista[n - 1]
        else:
            objetivo = self.almacen.obtener(arg.strip())
        if objetivo is None or not self.almacen.borrar(objetivo.id):
            return f"No encuentro «{arg}». Mira la lista con /alarmas."
        que = "el temporizador" if isinstance(objetivo, al.Temporizador) else "la alarma"
        nombre = f" «{objetivo.texto}»" if objetivo.texto else ""
        return f"Quitado {que}{nombre} ({objetivo.id})."

    def _cmd_timer(self, arg: str) -> str:
        if not arg:
            return "Uso: /timer 10m [texto]   (10m, 1h30, 90s, 1:30…)"
        partes = arg.split()
        seg, usados = None, 0
        for n in (2, 1):
            if len(partes) >= n:
                try:
                    seg = al.parsear_duracion(" ".join(partes[:n]))
                    usados = n
                    break
                except ValueError:
                    continue
        if seg is None:
            return f"No entiendo «{partes[0]}». Uso: /timer 10m [texto]"
        texto = " ".join(partes[usados:])
        try:
            t = self.almacen.crear_temporizador(seg, texto, iniciar=True, una_vez=True)
        except ValueError as e:
            return f"No pude poner el temporizador: {e}"
        fin = datetime.fromtimestamp(t.objetivo)
        etiqueta = f" «{t.texto}»" if t.texto else ""
        return (f"⏲ Temporizador {t.id} de {al.formato_duracion(seg)}{etiqueta}: "
                f"sonará a las {fin:%H:%M}.{self._aviso_apagadas()}")

    def _cmd_timers(self) -> str:
        temps = self.almacen.temporizadores()
        if not temps:
            return "No hay temporizadores."
        epoch = self._epoch()
        lineas = []
        for t in temps:
            estado = f"quedan {al.reloj_restante(t.falta(epoch))}" if t.corriendo else "parado"
            nombre = f" · {t.texto}" if t.texto else ""
            lineas.append(f"  {t.id} · {al.formato_duracion(t.duracion_s)}{nombre} · {estado}")
        return "Temporizadores:\n" + "\n".join(lineas)

    def _cmd_apagar(self, posponer: bool) -> str:
        if self.aviso.sonando is None:
            return "No suena ninguna alarma."
        if not self.aviso.puede_apagar():
            return f"(espera {int(math.ceil(self.aviso.restante_bloqueo())) or 1} s)"
        if posponer:
            self.aviso.posponer()
            return f"💤 Pospuesta {int(round(float(self.aviso.posponer_min)))} min."
        self.aviso.apagar()
        return "Alarma apagada."


__all__ = ("AlarmasTerminal",)
