"""
servicios/bailes_terminal.py — Los bailes de tu biblioteca en el modo patata (corte 9, D1).

En patata no hay mascota ni esqueleto: la canción de un baile (bailes/, nucleo/bailes.py)
suena por el Mezclador (servicios/cancion_python.ReproductorCancion, canal «musica») y el
TÍTULO de la ventana baila al pulso ANALIZADO de esa canción
(nucleo/bailes.Biblioteca.analizar_pulso → servicios/baile_terminal.BaileTerminal.
bailar_con): «ヽ(^o^)ﾉ ♪ Senbonzakura · 154 BPM». Como en la animada y en los sprites,
«aquí no tengo esqueleto: bailo a mi manera».

    /bailes [texto]              tus bailes con canción, numerados (con texto: los que lo tienen)
    /bailes <n>                  pone el n.º de la última lista (Enter en vacío o /parar para)
    /bailes parar | pausa | siguiente | anterior
    /bailes bucle on|off         repetir la misma (off: al acabar manda baile.al_terminar, y si
                                 es «repetir», para: el bucle apagado gana)
    /parar                       con una canción puesta, la para (y el baile del título)

- Con un juego delante (`en_juego()`) no se pone; si empieza uno a mitad, se para.
- Al acabar: baile.al_terminar (parar | siguiente | repetir | aleatorio) con nucleo/bailes.Cola,
  solo entre los bailes con canción (los desactivados no salen).
- `registrar_herramientas(tools)`: listar_bailes (nucleo.bailes.herramienta_listar) y
  mascota_bailar / parar_baile (nucleo.baile) con ESTE objeto como ctx["mmd"]
  (reproducir_por_texto, ultimo_motivo, activo, parar, lista) y el baile del título como
  ctx["baile"]. Los títulos son nombres de archivo: al modelo van saneados.

Sin Qt; la biblioteca, la canción (fábrica), el baile del título, el reloj y los hilos son
inyectables (tests/test_bailes_terminal.py).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from nucleo import baile as nb
from nucleo import bailes as nbl

_log = logging.getLogger("lune.bailes_terminal")

AYUDA = ("/bailes [texto] · /bailes <n> · /bailes parar|pausa|siguiente|anterior · "
         "/bailes bucle on|off")
AVISO_SIN_ESQUELETO = "Aquí no tengo esqueleto: bailo a mi manera (el título, al ritmo de la canción)."
ENERGIA = 0.7                  # la de los sprites con una canción (ui/mmd_qt ENERGIA_D1)
VIGILAR_S = 0.25               # el vigía mira el fin de la canción y el modo juego
MAX_LISTA = 30
_SI = {"on", "si", "sí", "1", "true", "activar", "encender"}
_NO = {"off", "no", "0", "false", "desactivar", "apagar"}
_COMANDOS = ("/bailes", "/baile")


def _mmss(s: Any) -> str:
    try:
        s = max(0, int(float(s)))
    except (TypeError, ValueError):
        return "?:??"
    return f"{s // 60}:{s % 60:02d}"


def _con_cancion(b: Any) -> bool:
    return bool(getattr(b, "jugable", False)) and getattr(b, "audio", None) is not None


class _BaileDelTitulo:
    """El baile del título (BaileTerminal) con la forma que espera nucleo.baile:
    bailar(seg, origen=…) → bool (False con `ultimo_motivo`) y parar() → bool."""

    def __init__(self, terminal: "BailesTerminal"):
        self._t = terminal
        self.ultimo_motivo = ""

    def bailar(self, segundos: Any = None, origen: str = "manual") -> bool:
        bt = self._t.baile
        if self._t._juego():
            self.ultimo_motivo = "juego"
            return False
        if bt is None or not callable(getattr(bt, "bailar", None)):
            self.ultimo_motivo = ""
            return False
        if self._t.activo:
            self.ultimo_motivo = "mmd"                 # «ya estoy con otro baile»
            return False
        self.ultimo_motivo = ""
        bt.bailar(segundos)
        return True

    def parar(self) -> bool:
        bt = self._t.baile
        f = getattr(bt, "parar", None) if bt is not None else None
        return bool(f(silenciar_auto=True)) if callable(f) else False


class BailesTerminal:
    """/bailes y los bailes de la biblioteca en patata (ver la cabecera del módulo)."""

    def __init__(self, consola: Any, config: Any, *, biblioteca: Any = None,
                 cancion: Optional[Callable[[], Any]] = None, colores: Optional[dict] = None,
                 en_juego: Callable[[], bool] = lambda: False, baile: Any = None,
                 reloj: Callable[[], float] = time.monotonic, hilo: bool = True, rng: Any = None):
        self.consola = consola
        self.config = config
        self.c = dict(colores) if colores else {}
        self._en_juego = en_juego
        self._reloj = reloj
        self._hilo = bool(hilo)
        self.biblioteca = biblioteca if biblioteca is not None else nbl.biblioteca_compartida(config)
        self.cola = nbl.Cola(self.biblioteca, rng=rng)
        self._fab_cancion = cancion
        self._cancion: Any = None
        self.baile = baile                    # BaileTerminal (el de patata: la misma capa del título)
        self._lock = threading.RLock()
        self._gen = 0
        self._actual: Any = None              # el Baile puesto
        self._fase = "parado"                 # parado | cargando | sonando | pausado
        self._pausa_pedida = False
        self._pulso: Dict[str, float] = {"bpm": nbl.BPM_DEFECTO, "fase0": 0.0}
        self._offset = 0.0
        self._bucle = self._al_terminar() == "repetir"
        self._lista: List[Any] = []
        self._aviso_dado = False
        self._iniciado = False
        self._vigia: Optional[threading.Thread] = None
        self._despertar = threading.Event()
        self.ultimo_motivo = ""
        self._adaptador = _BaileDelTitulo(self)

    # ── Ciclo de vida (como los módulos de los cortes 5–8) ───────────────────────
    def iniciar(self) -> None:
        self._iniciado = True

    def detener(self) -> None:
        self._iniciado = False
        self.parar()
        c = self._cancion
        if c is not None:
            try:
                c.liberar()
            except Exception:
                pass
        nbl.matar_procesos()                        # ningún ffmpeg (pulso, canción) sigue solo
        self._despertar.set()

    # ── Utilidades ───────────────────────────────────────────────────────────────
    def _juego(self) -> bool:
        try:
            return bool(self._en_juego())
        except Exception:
            return False

    def _cfg(self, clave: str, defecto: Any) -> Any:
        try:
            return self.config.get("baile", clave, defecto) if self.config is not None else defecto
        except Exception:
            return defecto

    def _al_terminar(self) -> str:
        v = str(self._cfg("al_terminar", nbl.AL_TERMINAR_DEFECTO) or "")
        return v if v in nbl.AL_TERMINAR else nbl.AL_TERMINAR_DEFECTO

    def _modo_fin(self) -> str:
        """Qué pasa al acabar: el bucle manda (on: repetir; off: baile.al_terminar, y si ese
        es «repetir», parar: «/bailes bucle off» gana a la config)."""
        if self._bucle:
            return "repetir"
        modo = self._al_terminar()
        return "parar" if modo == "repetir" else modo

    def _vol(self) -> float:
        try:
            v = float(self._cfg("volumen", 0.25))
        except (TypeError, ValueError):
            v = 0.25
        return max(0.0, min(1.0, v)) if v == v else 0.25

    def _cancion_obj(self) -> Any:
        if self._cancion is None:
            fab = self._fab_cancion
            if fab is not None:
                self._cancion = fab() if callable(fab) and not hasattr(fab, "cargar") else fab
            else:
                from servicios.cancion_python import ReproductorCancion
                self._cancion = ReproductorCancion(hilo=self._hilo)
        return self._cancion

    def _aviso(self, texto: str) -> None:
        try:
            self.consola.aviso(texto)
        except Exception:
            _log.debug("bailes (patata): no pude avisar", exc_info=True)

    def _lanzar(self, fn: Callable[[], None], nombre: str) -> None:
        if self._hilo:
            threading.Thread(target=fn, name=nombre, daemon=True).start()
        else:
            fn()

    @property
    def activo(self) -> bool:
        """¿Hay una canción de la biblioteca puesta (cargando, sonando o en pausa)?"""
        return self._fase != "parado"

    @property
    def actual(self) -> Any:
        return self._actual

    def estado(self) -> dict:
        b = self._actual
        c = self._cancion
        pos = None
        if c is not None:
            try:
                pos = c.posicion()
            except Exception:
                pos = None
        return {"fase": self._fase, "id": getattr(b, "id", "") if b is not None else "",
                "titulo": nbl.texto_limpio(getattr(b, "titulo", "")) if b is not None else "",
                "t": round(float(pos), 1) if isinstance(pos, (int, float)) else 0.0,
                "total": round(float(getattr(c, "duracion", 0.0) or 0.0), 1) if c is not None else 0.0,
                "bpm": round(float(self._pulso["bpm"]), 1), "bucle": self._bucle}

    # ── Lista ────────────────────────────────────────────────────────────────────
    def _buscar(self, q: str) -> List[Any]:
        """Lo que hay AHORA en la carpeta (patata no tiene hilo de Qt: escanea) con `q` o todo."""
        return self.biblioteca.filtrar(self.biblioteca.escanear(), q)

    def lista(self, texto: Any = "") -> List[dict]:
        """Los bailes (dicts de nucleo.bailes.baile_a_dict) con `texto` o todos; para
        listar_bailes y el panel. Todos: también los que no tienen canción (salen marcados)."""
        q = nbl.texto_limpio(texto, 60)
        try:
            bailes = self._buscar(q)
        except Exception:
            _log.exception("bailes (patata): no pude leer la biblioteca")
            return []
        return [nbl.baile_a_dict(b) for b in bailes]

    def _listar(self, texto: str) -> str:
        q = nbl.texto_limpio(texto, 60)
        try:
            bailes = self._buscar(q)
        except Exception as e:
            return f"No pude leer tus bailes: {e}"[:200]
        con = [b for b in bailes if _con_cancion(b)]
        sin = len(bailes) - len(con)
        with self._lock:
            self._lista = con[:MAX_LISTA]
        if not con:
            if q:
                return f"No encontré «{nbl.texto_limpio(q, 60)}» en tus bailes con canción."
            return ("Aún no tienes bailes con canción. Mételos en la carpeta «bailes» de Lune (un .vmd o "
                    ".vrma con su canción) o impórtalos desde la app (Mis bailes).")
        dim, rst = self.c.get("dim", ""), self.c.get("reset", "")
        lineas = [("Tus bailes" + (f" con «{nbl.texto_limpio(q, 60)}»" if q else "") + f" ({len(con)}):")]
        for i, b in enumerate(self._lista, 1):
            autor = nbl.texto_limpio(b.meta.get("autor_cancion") if isinstance(b.meta, dict) else "", 60)
            dur = f" {dim}{_mmss(b.duracion)}{rst}" if b.duracion else ""
            lineas.append(f"  {i:>2}. {nbl.texto_limpio(b.titulo)}" + (f" — {autor}" if autor else "")
                          + (" ★" if b.favorito else "") + dur)
        if len(con) > MAX_LISTA:
            lineas.append(f"  … y {len(con) - MAX_LISTA} más (busca con /bailes <texto>).")
        if sin:
            lineas.append(f"  {dim}({sin} sin canción que pueda sonar aquí){rst}")
        lineas.append(f"  {dim}/bailes <n> para ponerlo · Enter en vacío o /parar para{rst}")
        return "\n".join(lineas)

    # ── Poner, pausar, parar ─────────────────────────────────────────────────────
    def reproducir(self, id_: Any = None, *, origen: str = "usuario") -> Tuple[bool, str]:
        """Pone un baile (sin id: sigue si estaba en pausa, o el primero con canción)."""
        if id_ in (None, ""):
            if self._fase == "pausado":
                self.pausa(False)
                return True, "♪ Sigo."
            if self._actual is not None and self.activo:
                return True, f"♪ Ya suena «{nbl.texto_limpio(self._actual.titulo)}»."
            nid = self.cola.siguiente(None, "siguiente", _con_cancion)
            b = self.biblioteca.obtener(nid) if nid else None
            if b is None:
                self.ultimo_motivo = "sin_bailes"
                return False, "No tienes bailes con canción todavía: mételos en la carpeta «bailes»."
            return self._reproducir(b, origen)
        b = self.biblioteca.obtener(id_)
        if b is None:
            self.ultimo_motivo = "no_encontrado"
            return False, "No encuentro ese baile."
        return self._reproducir(b, origen)

    def reproducir_por_texto(self, texto: Any) -> Tuple[bool, str]:
        """Busca (título y autores, sin tildes) y pone el primero con canción (el título
        exacto antes). Para mascota_bailar {cancion}."""
        q = nbl.texto_limpio(texto, 80)
        if not q:
            return self.reproducir(None, origen="modelo")
        try:
            cands = [b for b in self._buscar(q) if _con_cancion(b)]
        except Exception:
            cands = []
        if not cands:
            self.ultimo_motivo = "no_encontrado"
            return False, f"No encontré «{nbl.titulo_seguro(q)}» en tus bailes."
        nq = nbl.normalizar(q)
        cands.sort(key=lambda b: nbl.normalizar(b.titulo) != nq)
        return self._reproducir(cands[0], "modelo")

    def _reproducir(self, b: Any, origen: str) -> Tuple[bool, str]:
        titulo = nbl.titulo_seguro(getattr(b, "titulo", ""))
        if self._juego():
            self.ultimo_motivo = "juego"
            return False, "En modo juego no pongo canciones (luego sí)."
        if getattr(b, "problema", ""):
            self.ultimo_motivo = "problema"
            return False, f"«{titulo}» no se puede poner: {nbl.texto_limpio(b.problema, 160)}"
        if getattr(b, "audio", None) is None:
            self.ultimo_motivo = "problema"
            return False, f"«{titulo}» no trae canción: sin esqueleto, aquí no puedo bailarlo."
        self.ultimo_motivo = ""
        c = self._cancion_obj()
        meta = b.meta if isinstance(b.meta, dict) else {}
        with self._lock:
            self._gen += 1
            gen = self._gen
            self._actual = b
            self._fase = "cargando"
            self._pausa_pedida = False
            try:
                self._offset = max(-0.5, min(0.5, float(meta.get("offset_ms") or 0) / 1000.0))
            except (TypeError, ValueError):
                self._offset = 0.0
            bpm_meta = meta.get("bpm")
            self._pulso = {"bpm": float(bpm_meta) if isinstance(bpm_meta, (int, float)) and bpm_meta > 0
                           else nbl.BPM_DEFECTO, "fase0": 0.0}
        try:
            c.parar()                               # la de antes calla (el baile del título sigue)
        except Exception:
            pass

        def trabajo() -> None:
            try:
                p = self.biblioteca.analizar_pulso(b)
                pulso = {"bpm": float(p.get("bpm") or nbl.BPM_DEFECTO), "fase0": float(p.get("fase0") or 0.0) % 1.0}
            except Exception:
                _log.debug("bailes (patata): sin pulso analizado", exc_info=True)
                pulso = None
            with self._lock:
                if gen != self._gen:
                    return
                if pulso is not None:
                    self._pulso = pulso
            c.cargar(b.audio, lambda ok, texto: self._cargada(gen, bool(ok), str(texto or "")))

        self._lanzar(trabajo, "lune-bailes-pulso")
        texto = f"♪ Pongo «{titulo}»"
        if not self._aviso_dado:
            self._aviso_dado = True
            texto += f". {AVISO_SIN_ESQUELETO}"
        return True, texto + ". Enter en vacío o /parar para."

    def _cargada(self, gen: int, ok: bool, texto: str) -> None:
        """La canción se cargó (desde el hilo de la canción): suena y el título baila."""
        with self._lock:
            if gen != self._gen or self._actual is None:
                return
            b = self._actual
        titulo = nbl.texto_limpio(b.titulo, 60)
        if not ok:
            self._terminar()
            self._aviso(f"No pude poner «{titulo}»: {nbl.texto_limpio(texto, 200) or 'error'}")
            return
        if self._juego():
            self._terminar()
            self._aviso("En modo juego no pongo canciones (luego sí).")
            return
        c = self._cancion_obj()
        if not c.reproducir(self._vol()):
            self._terminar()
            self._aviso(f"No pude poner «{titulo}»: {nbl.texto_limpio(getattr(c, 'error', ''), 200) or 'error'}")
            return
        with self._lock:
            if gen != self._gen:
                return
            pausa = self._pausa_pedida
            self._fase = "pausado" if pausa else "sonando"
        if pausa:
            c.pausar(True)
            self._parar_titulo()
        else:
            self._bailar_titulo(titulo)
        self._arrancar_vigia()

    def _pulso_actual(self) -> Optional[Tuple[float, float, float]]:
        """(bpm, fase, energía) en la posición de la canción (sin cerrojo: lo llama el hilo
        del baile del título con el suyo)."""
        c = self._cancion
        p = self._pulso
        if c is None:
            return None
        try:
            pos = c.posicion()
        except Exception:
            return None
        if pos is None:
            return None
        bpm = float(p.get("bpm") or nbl.BPM_DEFECTO)
        return bpm, nbl.fase_en(float(pos) + self._offset, bpm, float(p.get("fase0") or 0.0)), ENERGIA

    def _bailar_titulo(self, titulo: str) -> None:
        bt = self.baile
        f = getattr(bt, "bailar_con", None) if bt is not None else None
        if not callable(f):
            return
        c = self._cancion
        try:
            f(self._pulso_actual, titulo,
              lambda: getattr(c, "duracion", None), (lambda: c.posicion()) if c is not None else None,
              al_parar=self._al_parar_titulo)
        except Exception:
            _log.exception("bailes (patata): el título no pudo bailar")

    def _parar_titulo(self) -> None:
        bt = self.baile
        f = getattr(bt, "parar_externo", None) if bt is not None else None
        if callable(f):
            try:
                f()
            except Exception:
                pass

    def _al_parar_titulo(self) -> None:
        """Lo paró la persona en el baile del título (Enter, /parar) o el modo juego."""
        if self.activo:
            self._terminar(titulo=False)

    def pausa(self, on: Optional[bool] = None) -> bool:
        """Pausa o sigue (sin argumento, alterna). False si no hay canción."""
        with self._lock:
            if not self.activo:
                return False
            quiere = (self._fase != "pausado" and not self._pausa_pedida) if on is None else bool(on)
            self._pausa_pedida = quiere
            fase = self._fase
            b = self._actual
        c = self._cancion
        if fase == "cargando" or c is None:
            return True                               # se aplica al acabar de cargar
        if quiere and fase == "sonando":
            c.pausar(True)
            with self._lock:
                self._fase = "pausado"
            self._parar_titulo()
        elif not quiere and fase == "pausado":
            if self._juego():
                return False
            c.pausar(False)
            with self._lock:
                self._fase = "sonando"
            self._bailar_titulo(nbl.texto_limpio(b.titulo, 60))
            self._arrancar_vigia()
        return True

    def parar(self) -> bool:
        """Para la canción y el baile del título. True si sonaba algo."""
        if not self.activo:
            return False
        self._terminar()
        return True

    def _terminar(self, titulo: bool = True) -> None:
        with self._lock:
            self._gen += 1
            self._actual = None
            self._fase = "parado"
            self._pausa_pedida = False
        c = self._cancion
        if c is not None:
            try:
                c.liberar()                           # suelta el buffer (~21 MB por minuto)
            except Exception:
                pass
        if titulo:
            self._parar_titulo()
        self._despertar.set()

    def siguiente(self, paso: int = 1) -> Tuple[bool, str]:
        actual = self._actual.id if self._actual is not None else None
        if paso > 0:
            modo = "aleatorio" if self._al_terminar() == "aleatorio" else "siguiente"
            nid = self.cola.siguiente(actual, modo, _con_cancion)
        else:
            nid = self.cola.anterior(actual, _con_cancion)
        b = self.biblioteca.obtener(nid) if nid else None
        if b is None:
            return False, "No hay otro baile con canción."
        return self._reproducir(b, "usuario")

    # ── Vigía: fin de la canción y modo juego ────────────────────────────────────
    def paso(self) -> None:
        """Un paso del vigía (el hilo lo llama cada 0.25 s; los tests, a mano)."""
        with self._lock:
            fase, b = self._fase, self._actual
        if fase not in ("sonando", "pausado") or b is None:
            return
        if self._juego():
            self._terminar()
            self._aviso("♪ Hay un juego delante: paro la canción.")
            return
        c = self._cancion
        if fase != "sonando" or c is None:
            return
        try:
            acabo = bool(c.terminado)
        except Exception:
            acabo = False
        if acabo:
            self._al_fin(b)

    def _al_fin(self, b: Any) -> None:
        modo = self._modo_fin()
        titulo = nbl.texto_limpio(b.titulo, 60)
        if modo == "repetir":
            c = self._cancion
            if c is not None and c.reproducir(self._vol()):
                return
        nid = self.cola.siguiente(b.id, modo, _con_cancion) if modo in ("siguiente", "aleatorio") else None
        nuevo = self.biblioteca.obtener(nid) if nid else None
        if nuevo is not None:
            ok, texto = self._reproducir(nuevo, "cola")
            if ok:
                self._aviso(f"♪ Siguiente: «{nbl.texto_limpio(nuevo.titulo, 60)}».")
                return
        self._terminar()
        self._aviso(f"♪ Fin de «{titulo}».")

    def _arrancar_vigia(self) -> None:
        if not self._hilo:
            return
        with self._lock:
            if self._vigia is not None and self._vigia.is_alive():
                return
            self._despertar.clear()
            self._vigia = threading.Thread(target=self._vigilar, name="lune-bailes-vigia", daemon=True)
            self._vigia.start()

    def _vigilar(self) -> None:
        try:
            while self.activo:
                try:
                    self.paso()
                except Exception:
                    _log.exception("bailes (patata): fallo del vigía")
                self._despertar.wait(VIGILAR_S)
                self._despertar.clear()
        finally:
            with self._lock:
                if self._vigia is threading.current_thread():
                    self._vigia = None

    # ── Comandos ─────────────────────────────────────────────────────────────────
    def comando(self, linea: str) -> Optional[str]:
        """/bailes … y /parar con una canción puesta. None si la línea no es suya."""
        texto = str(linea or "").strip()
        partes = texto.split()
        if not partes:
            return None
        cmd = partes[0].lower()
        if cmd in ("/parar", "/parar_baile") and len(partes) == 1:
            return "♪ Vale, paro la canción." if self.parar() else None
        if cmd not in _COMANDOS:
            return None
        args = partes[1:]
        if not args:
            return self._listar("")
        a0 = args[0].lower()
        if a0 in ("ayuda", "?", "-h", "--help"):
            return f"Uso: {AYUDA}"
        if a0.isdigit():
            return self._cmd_numero(int(a0))
        if a0 in ("parar", "stop"):
            return "♪ Vale, paro la canción." if self.parar() else "No suena ningún baile."
        if a0 in ("pausa", "pausar", "seguir", "sigue", "continuar"):
            if not self.activo:
                return "No suena ningún baile."
            # «/bailes pausa» alterna; «seguir» siempre sigue
            on = a0.startswith("paus") and self._fase != "pausado" and not self._pausa_pedida
            if not self.pausa(on):
                return "En modo juego no pongo canciones (luego sí)." if self._juego() else "No suena ningún baile."
            return "♪ En pausa (/bailes pausa para seguir)." if on else "♪ Sigo."
        if a0 in ("siguiente", "sig", ">", "anterior", "ant", "<"):
            ok, t = self.siguiente(1 if a0 in ("siguiente", "sig", ">") else -1)
            return t
        if a0 == "bucle":
            return self._cmd_bucle(args[1:])
        return self._listar(" ".join(args))

    def _cmd_numero(self, n: int) -> str:
        with self._lock:
            lista = list(self._lista)
        if not lista:
            self._listar("")
            with self._lock:
                lista = list(self._lista)
        if not 1 <= n <= len(lista):
            return f"No hay baile n.º {n}. Mira la lista con /bailes."
        ok, texto = self._reproducir(lista[n - 1], "usuario")
        return texto

    def _cmd_bucle(self, resto: List[str]) -> str:
        if not resto:
            sin_bucle = "parar" if self._al_terminar() == "repetir" else self._al_terminar()
            return (f"Repetir la misma: {'sí' if self._bucle else 'no'}. Cámbialo con /bailes bucle on|off "
                    f"(al acabar, si no: {sin_bucle}).")
        v = resto[0].lower()
        if v in _SI:
            self._bucle = True
        elif v in _NO:
            self._bucle = False
        else:
            return "Usa /bailes bucle on o /bailes bucle off."
        if self._bucle:
            return "♪ Repetiré la misma."
        texto = "Vale: al acabar, " + {"parar": "paro.", "siguiente": "la siguiente.",
                                       "aleatorio": "otra al azar."}[self._modo_fin()]
        if self._al_terminar() == "repetir":
            texto = texto[:-1] + " (el bucle está apagado)."
        return texto

    # ── Herramientas del modelo ──────────────────────────────────────────────────
    def _ctx(self, ctx: Any) -> dict:
        base = dict(ctx) if isinstance(ctx, dict) else ({"contexto": ctx} if ctx is not None else {})
        base["mmd"] = self
        base["baile"] = self._adaptador
        return base

    def bailar_pedido(self, args: Any = None) -> Any:
        """«baila [X]» / mascota_bailar {segundos?, cancion?}: con canción, de la biblioteca; si no
        la encuentra (o sin canción), el baile del título a su manera. Lo que devuelve nucleo.baile."""
        return nb.herramienta_bailar(args, self._ctx(None))

    def parar_pedido(self) -> Any:
        """«para de bailar» / parar_baile: el título y, si suena, la canción."""
        return nb.herramienta_parar({}, self._ctx(None))

    def registrar_herramientas(self, tools: Any) -> None:
        """listar_bailes, mascota_bailar (con «cancion»: de tu biblioteca) y parar_baile."""
        handlers = {
            "listar_bailes": lambda args=None, ctx=None: nbl.herramienta_listar(args, self._ctx(ctx)),
            "mascota_bailar": lambda args=None, ctx=None: nb.herramienta_bailar(args, self._ctx(ctx)),
            "parar_baile": lambda args=None, ctx=None: nb.herramienta_parar(args, self._ctx(ctx)),
        }
        for nombre, fn in handlers.items():
            try:
                tools.registrar_handler(nombre, fn)
            except Exception:
                _log.exception("bailes (patata): no pude registrar %s", nombre)


__all__ = ("BailesTerminal", "AYUDA", "AVISO_SIN_ESQUELETO")
