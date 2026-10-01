"""
servicios/actualizar_terminal.py — /version y /actualizar en la terminal (modo patata), sin Qt.

  /version                      mi versión, si estoy instalada o desde el código y dónde guardo tus cosas
  /actualizar [buscar]          ¿hay una versión nueva? (instalada: GitHub Releases; desde el
                                código: los commits nuevos de git; copia sin git: el enlace)
  /actualizar instalar          instalada: la descargo (comprobada con su SHA-256) con el progreso
                                aquí, abro el instalador y me cierro (me vuelvo a abrir sola).
                                Desde el código: git pull + pip (luego ciérrame y vuelve a abrirme)
  /actualizar omitir [versión]  no te aviso de esa versión (sin versión: la última que encontré;
                                «ninguna» vuelve a avisarte de todas)
  /actualizar cancelar          corta la descarga

La lógica es la de servicios/actualizador.py (la misma que las ventanas). Todo lo lento va en un
hilo y lo que dice sale con `decir` (patata: consola.aviso, que no rompe lo que escribes).

El aviso al iniciar (iniciar_aviso, lo llama patata.main): ~45 s después de abrir, como mucho
una vez cada 24 h (actualizaciones.ultima_comprobacion) y nunca con un juego delante; una línea.
Aquí no hay hilo de Qt: ultima_comprobacion se escribe desde el hilo del aviso (Config.set es
seguro entre hilos: RLock y mutex con nombre).
"""
from __future__ import annotations

import threading
from typing import Any, Callable, Dict, Optional

from servicios import actualizador

ESPERA_AVISO_S = 45.0           # el aviso al iniciar, cuando ya estás escribiendo
REINTENTO_JUEGO_S = 60.0        # con un juego delante, se vuelve a mirar cada minuto
PASO_PROGRESO = 10              # una línea de progreso cada 10 %
MAX_LINEAS_NOTAS = 8
MAX_COMMITS = 10
USO = ("Uso: /actualizar · /actualizar instalar · /actualizar omitir [versión|ninguna] · "
       "/actualizar cancelar · /version")


def _hilo(fn: Callable[[], Any]) -> None:
    threading.Thread(target=fn, name="lune-actualizar", daemon=True).start()


def _mb(n: Any) -> str:
    try:
        return f"{int(n) / (1024 * 1024):.0f} MB"
    except (TypeError, ValueError):
        return "? MB"


def _fecha_corta(iso: Any) -> str:
    """«2026-10-01T07:00:00Z» → «2026-10-01 07:00 UTC»."""
    d = actualizador._leer_fecha(iso)
    return d.strftime("%Y-%m-%d %H:%M UTC") if d else ""


class ActualizacionesTerminal:
    """/version y /actualizar (ver la cabecera). `decir(texto)` saca una línea; `salir()` cierra
    patata tras lanzar el instalador; `en_juego()` dice si hay partida. `funciones` (buscar,
    descargar, instalar, actualizar) y `lanzar(fn)` son para los tests."""

    def __init__(self, config, *, decir: Callable[[str], Any], salir: Optional[Callable[[], Any]] = None,
                 en_juego: Optional[Callable[[], bool]] = None, modo: Optional[str] = None,
                 funciones: Optional[Dict[str, Callable]] = None,
                 lanzar: Optional[Callable[[Callable[[], Any]], Any]] = None):
        self.config = config
        self._decir = decir
        self._salir = salir
        self._en_juego = en_juego or (lambda: False)
        self._modo = modo
        self._f: Dict[str, Callable] = {
            "buscar": actualizador.buscar_novedades, "descargar": actualizador.descargar,
            "instalar": actualizador.instalar, "actualizar": actualizador.actualizar,
            **(funciones or {}),
        }
        self._lanzar = lanzar or _hilo
        self._lock = threading.Lock()
        self._ocupado: Optional[str] = None      # "buscar" | "instalar" | "git" | "aviso"
        self._release: Optional[Dict] = None
        self._cancelar = threading.Event()
        self._parar = threading.Event()          # para el aviso al iniciar

    # ── Utilidades ─────────────────────────────────────────────────────────────
    @property
    def modo(self) -> str:
        if self._modo is None:
            self._modo = actualizador.modo()
        return self._modo

    def _cfg(self, clave: str, defecto: Any = None) -> Any:
        try:
            return self.config.get("actualizaciones", clave, defecto) if self.config is not None else defecto
        except Exception:
            return defecto

    def _di(self, texto: str) -> None:
        try:
            self._decir(str(texto))
        except Exception:
            pass

    def _rama(self) -> str:
        return str(self._cfg("rama", "master") or "master")

    def _tomar(self, que: str) -> Optional[str]:
        """Reserva el actualizador para `que`; si ya hay algo en marcha, el aviso de por qué no."""
        with self._lock:
            if self._ocupado is not None:
                return {"instalar": "Ya estoy descargando la versión nueva (/actualizar cancelar la corta).",
                        "git": "Ya estoy trayendo los cambios con git; espera a que termine."}.get(
                    self._ocupado, "Ya estoy mirando si hay versión nueva; un momento.")
            self._ocupado = que
        return None

    def _soltar(self) -> None:
        with self._lock:
            self._ocupado = None

    def _buscar_ya(self) -> Dict:
        try:
            res = self._f["buscar"](self.modo, rama=self._rama())
        except Exception as e:
            res = {"ok": False, "hay_novedades": False, "mensaje": f"No pude buscar: {e}"}
        res = res if isinstance(res, dict) else {"ok": False, "mensaje": "No pude buscar."}
        if self.config is not None:
            actualizador.marcar_comprobacion(self.config)
        if res.get("ok") and self.modo != actualizador.MODO_GIT:
            self._release = dict(res)
        return res

    # ── Comandos ───────────────────────────────────────────────────────────────
    def comando(self, linea: str) -> Optional[str]:
        """/version y /actualizar …; None = no es mío. "" = ya lo dirá el hilo."""
        partes = str(linea or "").strip().split(maxsplit=2)
        if not partes:
            return None
        cmd = partes[0].lower()
        if cmd == "/version":
            return self.texto_version()
        if cmd != "/actualizar":
            return None
        sub = partes[1].lower() if len(partes) > 1 else "buscar"
        arg = partes[2].strip() if len(partes) > 2 else ""
        if sub in ("buscar", "mirar", "comprobar"):
            return self._buscar()
        if sub == "instalar":
            return self._instalar()
        if sub == "omitir":
            return self._omitir(arg)
        if sub == "cancelar":
            return self._cancelar_descarga()
        return USO

    def texto_version(self) -> str:
        from nucleo import rutas
        como = {actualizador.MODO_INSTALADA: "instalada (Setup de GitHub)",
                actualizador.MODO_GIT: "desde el código (git)",
                actualizador.MODO_CARPETA: "desde una copia sin git"}.get(self.modo, self.modo)
        lineas = [f"Lune CD {actualizador.version_actual() or '?'} · {como}",
                  f"Tus datos: {rutas.DATOS}"]
        if bool(self._cfg("comprobar_al_iniciar", True)):
            ultima = _fecha_corta(self._cfg("ultima_comprobacion", ""))
            lineas.append("Busco versiones nuevas al abrirme: sí" + (f" (la última vez: {ultima})" if ultima else ""))
        else:
            lineas.append("Busco versiones nuevas al abrirme: no (/actualizar para mirar ahora)")
        omitida = str(self._cfg("omitir_version", "") or "")
        if omitida:
            lineas.append(f"Me pediste saltarte la {omitida} (/actualizar omitir ninguna lo quita).")
        return "\n".join(lineas)

    def _buscar(self) -> str:
        motivo = self._tomar("buscar")
        if motivo:
            return motivo

        def trabajo():
            try:
                self._di(self.texto_resultado(self._buscar_ya()))
            finally:
                self._soltar()
        self._lanzar(trabajo)
        return "Miro el remoto de git…" if self.modo == actualizador.MODO_GIT else "Busco en GitHub…"

    def texto_resultado(self, res: Dict) -> str:
        """Lo que se dice tras buscar (varias líneas)."""
        res = res if isinstance(res, dict) else {}
        mensaje = str(res.get("mensaje") or "")
        if not res.get("ok"):
            return mensaje or "No pude buscar actualizaciones."
        if self.modo == actualizador.MODO_GIT:
            if not res.get("hay_novedades"):
                return mensaje
            lineas = [mensaje, *(f"  · {c}" for c in (res.get("commits") or [])[:MAX_COMMITS])]
            if res.get("limpio") is False:
                lineas.append(f"Ojo: tienes {len(res.get('modificados') or [])} archivo(s) sin guardar; "
                              "no toco nada hasta que hagas commit (o lo descartes).")
            else:
                lineas.append("/actualizar instalar trae los cambios (git pull) y lo que falte.")
            return "\n".join(lineas)
        pagina = str(res.get("pagina") or actualizador.URL_RELEASES)
        if self.modo == actualizador.MODO_CARPETA:
            return f"{mensaje} Descárgame en {pagina}" if res.get("nueva") else mensaje
        if not res.get("nueva"):
            return mensaje
        lineas = [mensaje]
        notas = [n for n in str(res.get("notas") or "").splitlines() if n.strip()][:MAX_LINEAS_NOTAS]
        lineas += [f"  {n}" for n in notas]
        if not res.get("instalable"):
            lineas.append(f"No puedo comprobar su instalador (falta su SHA-256), así que no lo descargo. "
                          f"Mira {pagina}")
        elif res.get("omitida"):
            lineas.append("/actualizar instalar la instala igual · /actualizar omitir ninguna vuelve a avisarte.")
        else:
            lineas.append("/actualizar instalar la descarga y me instala (me cierro y vuelvo sola) · "
                          "/actualizar omitir la salta.")
        return "\n".join(lineas)

    def _instalar(self) -> str:
        if self.modo == actualizador.MODO_CARPETA:
            return ("Esta copia no se actualiza sola (no es la instalada ni un repositorio git). "
                    f"Descárgame en {actualizador.URL_RELEASES}")
        if self.modo == actualizador.MODO_GIT:
            return self._git_actualizar()
        motivo = self._tomar("instalar")
        if motivo:
            return motivo
        self._cancelar.clear()
        self._lanzar(self._trabajo_instalar)
        return ("Voy: descargo la versión nueva, la compruebo y me instalo. Puedes seguir escribiendo; "
                "/actualizar cancelar la corta.")

    def _trabajo_instalar(self) -> None:
        try:
            rel = self._release
            if not rel or not rel.get("nueva"):
                rel = self._buscar_ya()
                if not rel.get("ok"):
                    self._di(rel.get("mensaje") or "No pude buscar actualizaciones.")
                    return
                if not rel.get("nueva"):
                    self._di("Estoy al día: no hay nada que instalar.")
                    return
            if not rel.get("instalable"):
                self._di(f"No puedo comprobar el instalador de la {rel.get('version')} (falta su SHA-256), "
                         f"así que no lo descargo. Mira {rel.get('pagina') or actualizador.URL_RELEASES}")
                return
            total = int((rel.get("asset") or {}).get("tamano") or 0)
            self._di(f"Descargo la {rel.get('version')} ({_mb(total)})…")
            paso = {"siguiente": PASO_PROGRESO}

            def progreso(n, t):
                pct = int(n * 100 / t) if t else 0
                if pct >= paso["siguiente"] and pct < 100:
                    paso["siguiente"] = (pct // PASO_PROGRESO + 1) * PASO_PROGRESO
                    self._di(f"Descargando… {pct} % ({_mb(n)} de {_mb(t)})")

            res = self._f["descargar"](rel, on_progreso=progreso, cancelar=self._cancelar)
            if not isinstance(res, dict) or not res.get("ok"):
                self._di((res or {}).get("mensaje") if isinstance(res, dict) else "No pude descargarla.")
                return
            self._di("Descargada y comprobada (SHA-256). Abro el instalador y me cierro: vuelvo sola en un momento.")
            if not self._f["instalar"](res.get("ruta"), sha256=str(rel.get("sha256") or "")):
                self._di("No pude abrir el instalador. Vuelve a intentarlo con /actualizar instalar.")
                return
            if self._salir is not None:
                self._salir()
        except Exception as e:
            self._di(f"No pude instalarla: {e}")
        finally:
            self._soltar()

    def _git_actualizar(self) -> str:
        motivo = self._tomar("git")
        if motivo:
            return motivo

        def trabajo():
            try:
                try:
                    res = self._f["actualizar"](self._rama(), on_progreso=self._di)
                except Exception as e:
                    res = {"ok": False, "mensaje": f"Algo falló: {e}"}
                res = res if isinstance(res, dict) else {}
                if res.get("ok") and res.get("actualizado"):
                    extra = "" if res.get("requisitos_ok", True) else " Ojo: no pude instalar alguna dependencia."
                    self._di(f"{res.get('mensaje') or 'Actualizada.'}{extra} Ciérrame (/salir) y vuelve a "
                             "abrirme para usar lo nuevo.")
                else:
                    self._di(res.get("mensaje") or "No pude actualizar.")
            finally:
                self._soltar()
        self._lanzar(trabajo)
        return "Traigo los cambios con git…"

    def _omitir(self, arg: str) -> str:
        a = str(arg or "").strip()
        if a.lower() in ("ninguna", "nada", "no", "quitar"):
            v = ""
        elif a:
            v = actualizador.texto_version(a)
            if not v:
                return f"«{a[:20]}» no parece una versión (p. ej. 11.3)."
        else:
            v = str((self._release or {}).get("version") or "")
            if not v:
                return "¿Cuál? Busca primero (/actualizar) o dímela: /actualizar omitir 11.3"
        if self.config is None:
            return "No puedo guardar la configuración (config.json)."
        try:
            self.config.set("actualizaciones", "omitir_version", v)
        except Exception as e:
            return f"No pude guardarlo: {e}"
        if not v:
            return "Vale, vuelvo a avisarte de todas las versiones nuevas."
        return f"Vale: no te aviso de la {v}. Te digo cuando salga la siguiente."

    def _cancelar_descarga(self) -> str:
        with self._lock:
            descargando = self._ocupado == "instalar"
        if not descargando:
            return "No estoy descargando nada."
        self._cancelar.set()
        return "Corto la descarga…"

    # ── Aviso al iniciar ───────────────────────────────────────────────────────
    def iniciar_aviso(self, espera_s: float = ESPERA_AVISO_S, reintento_s: float = REINTENTO_JUEGO_S) -> bool:
        """~45 s después, si toca (Buscar al iniciar y 24 h desde la última) y sin juego delante,
        mira si hay algo nuevo y lo dice en una línea. False si no toca."""
        if self.config is None or not actualizador.toca_comprobar(self.config):
            return False
        self._parar.clear()

        def esperar_sin_juego() -> bool:
            while self._en_juego():
                if self._parar.wait(reintento_s):
                    return False
            return not self._parar.is_set()

        def trabajo():
            if self._parar.wait(espera_s) or not esperar_sin_juego():
                return
            if not actualizador.toca_comprobar(self.config):
                return
            if self._tomar("aviso"):
                return                                # ya lo estás mirando tú
            try:
                res = self._buscar_ya()
            finally:
                self._soltar()
            if res.get("ok") and res.get("hay_novedades") and esperar_sin_juego():
                self._di(actualizador.texto_aviso({**res, "modo": self.modo}, donde="patata"))
        self._lanzar(trabajo)
        return True

    def detener(self) -> None:
        """Al salir: sin aviso pendiente y la descarga cortada."""
        self._parar.set()
        self._cancelar.set()
