"""
ui/atajos_qt.py — Adaptador Qt de los atajos globales (servicios/atajos_globales.py).

`GestorAtajos` registra combinaciones con RegisterHotKey en un hilo propio (sin
hooks de teclado: nada que un anticheat vea como keylogger) y avisa con
`on_atajo(id)` en ESE hilo. Este adaptador:

- lee `atajos.lista` de la config ([{id, combo}], combos normalizados) y solo
  registra los ids con handler (`disponible(id)`: pantalla_grande o baile_pausa
  no ocupan su tecla hasta que llegue su corte) y con `atajos.activo`;
- reenvía la pulsación al hilo de Qt con una señal en cola → `accion(str)`;
- modo juego (`set_pausa(True)` con `atajos.pausar_en_juegos`): QUITA todos los
  registros salvo `mostrar_lune` (RegisterHotKey se tragaría la tecla dentro
  del juego aunque Lune no la atendiera);
- «Detectar» en la web (`capturando(True)`): quita TODOS mientras la página
  escucha el teclado, para que la combinación llegue a la página y no dispare
  la acción; se reanudan solos a los 15 s por si la página no avisa;
- `cambiar(id, combo)` valida (atajos_globales.comprobar), guarda normalizado y,
  si Windows no deja registrarlo (lo usa otra app, error 1409), vuelve al
  anterior y devuelve el motivo;
- `cambio(str)`: JSON de `estado()` cada vez que algo cambia (para la web).
"""
from __future__ import annotations

import copy
import json
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal

from nucleo import acciones_ui, nombres_antiguos
from servicios.atajos_globales import GestorAtajos, comprobar, normalizar, parsear_combo, texto_combo

_log = logging.getLogger("lune.atajos_qt")


def _lista_por_defecto() -> List[dict]:
    try:
        from nucleo.config import Config
        return copy.deepcopy(Config.DEFAULT_CONFIG["atajos"]["lista"])
    except Exception:
        return []


def _norm(combo: str) -> Optional[str]:
    try:
        return normalizar(combo)
    except ValueError:
        return None


class GestorAtajosQt(QObject):
    """Atajos globales de Lune (controlador de ServiciosEscritorio)."""

    accion = pyqtSignal(str)          # id pulsado (en el hilo de Qt)
    cambio = pyqtSignal(str)          # json de estado()
    _pulsado_hilo = pyqtSignal(str)   # interna: del hilo de atajos al de Qt

    SIEMPRE_ACTIVOS = frozenset({"mostrar_lune"})
    CAPTURA_MS = 15000

    def __init__(self, config, *, disponible: Callable[[str], bool], gestor=None,
                 parent: Optional[QObject] = None):
        super().__init__(parent)
        self._config = config
        self._disponible = disponible
        if gestor is None:
            gestor = GestorAtajos(self._desde_hilo)
        elif hasattr(gestor, "_on_atajo"):
            gestor._on_atajo = self._desde_hilo          # el falso de los tests o uno real ya creado
        self._gestor = gestor
        self._pulsado_hilo.connect(self._entregar, Qt.ConnectionType.QueuedConnection)
        self._iniciado = False
        self._pausa = False
        self._capturando = False
        self._registrados: Dict[str, str] = {}          # id → combo normalizado registrado
        self._errores: Dict[str, str] = {}
        self._t_captura = QTimer(self)
        self._t_captura.setSingleShot(True)
        self._t_captura.timeout.connect(lambda: self.capturando(False))

    # ── Config ─────────────────────────────────────────────────────────────
    def _get(self, clave: str, defecto: Any) -> Any:
        c = self._config
        try:
            if hasattr(c, "get") and not isinstance(c, dict):
                v = c.get("atajos", clave, defecto)
            else:
                v = (c or {}).get("atajos", {}).get(clave, defecto)
        except Exception:
            v = defecto
        return copy.deepcopy(v)

    def _set(self, clave: str, valor: Any) -> None:
        c = self._config
        if hasattr(c, "set") and not isinstance(c, dict):
            c.set("atajos", clave, valor)
        elif isinstance(c, dict):
            c.setdefault("atajos", {})[clave] = valor

    def activo(self) -> bool:
        return bool(self._get("activo", True))

    def _pausar_en_juegos(self) -> bool:
        return bool(self._get("pausar_en_juegos", True))

    def lista(self) -> List[Tuple[str, str]]:
        """[(id, combo)] de la config: ids del catálogo que admiten atajo, sin repetir.
        Un id de antes de la 11 que siga en config.json sale con su nombre de ahora
        (nucleo/nombres_antiguos; si están los dos, gana el nuevo)."""
        out: List[Tuple[str, str]] = []
        vistos = set()
        crudo, _ = nombres_antiguos.migrar_atajos(self._get("lista", []))
        for e in crudo if isinstance(crudo, list) else []:
            if not isinstance(e, dict):
                continue
            id_, combo = e.get("id"), e.get("combo", "")
            a = acciones_ui.ACCIONES.get(id_) if isinstance(id_, str) else None
            if a is None or acciones_ui.USO_ATAJO not in a.usos or id_ in vistos:
                continue
            vistos.add(id_)
            out.append((id_, combo if isinstance(combo, str) else ""))
        return out

    def _es_disponible(self, id_: str) -> bool:
        try:
            return bool(self._disponible(id_))
        except Exception:
            return False

    # ── Ciclo de vida ──────────────────────────────────────────────────────
    def iniciar(self) -> None:
        if self._iniciado:
            return
        self._iniciado = True
        if self.activo():
            self._arrancar_hilo()
        self._aplicar()

    def detener(self) -> None:
        """Suelta TODOS los atajos (desde su hilo) y para el hilo."""
        self._iniciado = False
        self._t_captura.stop()
        self._capturando = False
        try:
            self._gestor.quitar_todos()
        except Exception:
            _log.exception("atajos: quitar_todos falló")
        try:
            self._gestor.detener()
        except Exception:
            _log.exception("atajos: detener falló")
        self._registrados.clear()

    def _arrancar_hilo(self) -> None:
        try:
            activo = getattr(self._gestor, "activo", None)
            if callable(activo) and activo():
                return
            self._gestor.iniciar()
        except Exception:
            _log.exception("atajos: no arrancó el hilo")

    # ── Pausas ─────────────────────────────────────────────────────────────
    def set_pausa(self, on: bool) -> None:
        """Modo juego: con atajos.pausar_en_juegos solo queda mostrar_lune."""
        on = bool(on)
        if on == self._pausa:
            return
        self._pausa = on
        self._aplicar()

    def capturando(self, on: bool, timeout_ms: int = CAPTURA_MS) -> None:
        """La página está leyendo una combinación («Detectar»): todos fuera."""
        on = bool(on)
        if on:
            try:
                ms = int(timeout_ms)
            except (TypeError, ValueError):
                ms = self.CAPTURA_MS
            self._t_captura.start(max(500, min(ms, 60000)))
        else:
            self._t_captura.stop()
        if on == self._capturando:
            return
        self._capturando = on
        self._aplicar()

    @property
    def pausado(self) -> bool:
        return self._pausa

    @property
    def en_captura(self) -> bool:
        return self._capturando

    # ── Registro efectivo ──────────────────────────────────────────────────
    def _deseados(self) -> Dict[str, str]:
        if not self._iniciado or not self.activo() or self._capturando:
            return {}
        pausa = self._pausa and self._pausar_en_juegos()
        out: Dict[str, str] = {}
        for id_, combo in self.lista():
            if not combo or not self._es_disponible(id_):
                continue
            if pausa and id_ not in self.SIEMPRE_ACTIVOS:
                continue
            error, _aviso = comprobar(combo)
            if error:
                self._errores[id_] = error
                continue
            out[id_] = normalizar(combo)
        return out

    def _aplicar(self, emitir: bool = True) -> None:
        deseados = self._deseados()
        # Primero las bajas (incluidos los que cambian de combo): así intercambiar
        # dos combinaciones entre acciones no choca consigo mismo.
        for id_ in list(self._registrados):
            if deseados.get(id_) != self._registrados[id_]:
                try:
                    self._gestor.quitar(id_)
                except Exception:
                    _log.exception("atajos: quitar %s falló", id_)
                del self._registrados[id_]
        if deseados and self.activo():
            self._arrancar_hilo()
        for id_, combo in deseados.items():
            if self._registrados.get(id_) == combo:
                continue
            try:
                err = self._gestor.registrar(id_, combo)
            except Exception as e:                        # pragma: no cover - defensivo
                err = f"Error interno de atajos: {e}"
            if err:
                self._errores[id_] = str(err)
            else:
                self._registrados[id_] = combo
                self._errores.pop(id_, None)
        if emitir:
            self._emitir()

    def _emitir(self) -> None:
        try:
            self.cambio.emit(json.dumps(self.estado(), ensure_ascii=False))
        except RuntimeError:
            pass

    def recargar(self) -> None:
        """La config cambió desde fuera (panel nativo): volver a registrar."""
        if self._iniciado and self.activo():
            self._arrancar_hilo()
        self._aplicar()

    # ── Pulsaciones ────────────────────────────────────────────────────────
    def _desde_hilo(self, id_) -> None:
        """on_atajo del GestorAtajos (hilo de atajos): a la cola de Qt."""
        try:
            self._pulsado_hilo.emit(str(id_))
        except RuntimeError:
            pass                                          # el QObject ya se destruyó

    def pulsado(self, id_: str) -> None:
        """Lo mismo que una pulsación real (desde cualquier hilo)."""
        self._desde_hilo(id_)

    def _entregar(self, id_: str) -> None:
        # Una pulsación en cola de un atajo ya quitado (pausa, captura) no cuenta.
        if id_ not in self._registrados:
            return
        self.accion.emit(id_)

    # ── Para la interfaz ───────────────────────────────────────────────────
    def estado(self) -> List[dict]:
        """Una entrada por acción con atajo: los de la config y, detrás, las
        acciones disponibles que aún no tienen combinación."""
        out: List[dict] = []
        vistos = set()
        for id_, combo in self.lista():
            vistos.add(id_)
            out.append(self._entrada(id_, combo))
        for id_, a in acciones_ui.ACCIONES.items():
            if id_ in vistos or acciones_ui.USO_ATAJO not in a.usos or not self._es_disponible(id_):
                continue
            out.append(self._entrada(id_, ""))
        return out

    def _entrada(self, id_: str, combo: str) -> dict:
        texto, error, aviso = "", None, None
        if combo:
            error, aviso = comprobar(combo)
            if not error:
                texto = texto_combo(*parsear_combo(combo))
                combo = normalizar(combo)
        error = self._errores.get(id_) or error
        return {"id": id_, "etiqueta": acciones_ui.etiqueta_de(id_), "combo": combo, "texto": texto,
                "error": error, "aviso": aviso, "disponible": self._es_disponible(id_),
                "registrado": id_ in self._registrados, "siempre": id_ in self.SIEMPRE_ACTIVOS}

    def resumen(self) -> dict:
        return {"activo": self.activo(), "pausa": self._pausa, "capturando": self._capturando,
                "pausar_en_juegos": self._pausar_en_juegos(), "atajos": self.estado()}

    def validar(self, combo: str, id_: Optional[str] = None) -> dict:
        """{ok, combo (normalizado), texto, error, aviso, conflicto (id de otra
        acción de Lune con la misma combinación, sin contar `id_`)}."""
        error, aviso = comprobar(str(combo or ""))
        if error:
            return {"ok": False, "combo": "", "texto": "", "error": error, "aviso": None, "conflicto": ""}
        norm = normalizar(combo)
        conflicto = ""
        for otro, c in self.lista():
            if otro != id_ and c and _norm(c) == norm:
                conflicto = otro
                break
        return {"ok": True, "combo": norm, "texto": texto_combo(*parsear_combo(combo)),
                "error": None, "aviso": aviso, "conflicto": conflicto}

    def cambiar(self, id_: str, combo: str) -> Optional[str]:
        """Guarda el atajo de `id_` ("" = sin atajo). None si quedó bien; si no,
        el motivo (y la config no cambia)."""
        a = acciones_ui.ACCIONES.get(id_) if isinstance(id_, str) else None
        if a is None or acciones_ui.USO_ATAJO not in a.usos:
            return "Esa acción no admite atajo."
        combo = str(combo or "").strip()
        norm = ""
        if combo:
            error, _aviso = comprobar(combo)
            if error:
                return error
            norm = normalizar(combo)
            for otro, c in self.lista():
                if otro != id_ and c and _norm(c) == norm:
                    return (f"{texto_combo(*parsear_combo(norm))} ya lo usa "
                            f"«{acciones_ui.etiqueta_de(otro)}».")
        crudo, _ = nombres_antiguos.migrar_atajos(self._get("lista", []))
        crudo = [e for e in crudo if isinstance(e, dict)] if isinstance(crudo, list) else []
        anterior = copy.deepcopy(crudo)
        for e in crudo:
            if e.get("id") == id_:
                e["combo"] = norm
                break
        else:
            crudo.append({"id": id_, "combo": norm})
        self._set("lista", crudo)
        self._errores.pop(id_, None)
        self._aplicar(emitir=False)
        err = self._errores.get(id_) if norm else None
        if err:
            # Windows no lo deja (otra app lo tiene): se queda el anterior.
            self._set("lista", anterior)
            self._aplicar(emitir=False)
            self._emitir()
            return err
        self._emitir()
        return None

    def activar(self, on: bool) -> None:
        """atajos.activo: registrar o quitar todos."""
        self._set("activo", bool(on))
        if on and self._iniciado:
            self._arrancar_hilo()
        self._aplicar()

    def restablecer(self) -> List[dict]:
        """Los atajos de fábrica (DEFAULT_CONFIG)."""
        self._set("lista", _lista_por_defecto())
        self._errores.clear()
        self._aplicar()
        return self.estado()
