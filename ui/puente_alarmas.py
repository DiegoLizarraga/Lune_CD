"""
ui/puente_alarmas.py — objeto `alarmas` del QWebChannel (window.luneAlarmas), cortes 5 y 6.

Lo usa la piel web normal (extra/alarmas.jsx: vista «alarmas», AlarmaBanner, AlarmasCard y
PantallaGrandeCard) para hablar con:
  · ControlAlarmasQt (ui/alarmas_qt.py): alarmas, temporizadores, apagar/posponer/probar;
  · ControlPantallaGrande (ui/pantalla_grande_qt.py): pantalla grande y salvapantallas.
Los controladores llegan tarde con `enlazar(alarmas=…, grande=…)` (ver ui/puentes_ocio.py).
Sin ellos, las ranuras devuelven un estado por defecto y lo que es solo config
(config_alarmas*, config_grande*) se lee y se guarda igual.

Validación (la página es código que no controlamos del todo): JSON con tope y sin NaN;
ids `[A-Za-z0-9_-]{1,40}`; hora «HH:MM»; días `[lmxjvsd]*` (sin repetir) o máscara 0–127;
textos sin controles y recortados; números finitos y en rango; booleanos de verdad.

Ranuras (JS: el resultado llega por callback, `luneAlarmas.x(args…, cb)`):
    alarmas_json() → str             {disponible, activo, ahora (epoch s, el reloj del controlador),
                                      alarmas:[{id, activa, hora, minuto, dias (máscara, bit0 = lunes;
                                      0 = todos), una_vez, texto, proxima (epoch | 0)}],
                                      temporizadores:[{id, activo (en marcha), duracion_s, objetivo (epoch s
                                      | 0 = parado), restante_s, texto}], sonando: {…} | null,
                                      proxima: {id, tipo, texto, cuando (epoch)} | null}
    alarma_guardar(json) → str        {ok, error, id, estado}. json: {id?, hora:"HH:MM", dias:"lmx"|int,
                                      una_vez, texto, activa}; con id = editar (parcial vale)
    alarma_borrar(id) → str           {ok, error, estado}
    temporizador_crear(json) → str    {ok, error, id, estado}. json: {segundos | h,m,s, texto, iniciar}
    temporizador_accion(id, accion) → str   iniciar · parar · reiniciar · borrar → {ok, error, estado}
    alarma_apagar() → bool · alarma_posponer() → bool · alarma_probar() → bool
    config_alarmas() → str            {activo, pantalla_grande, decir_texto, bloqueo_s, recuperar_min,
                                      posponer_min, volumen, sonido, sonidos}
    config_alarmas_guardar(json) → str  {ok, error, estado}
    grande_estado_json() → str        {activa, motivo, disponible}
    grande_alternar() → bool · salvapantallas_probar() → bool
    config_grande() → str             {activo, paso, clic_sale_de_todo, fondo_oscuro, reloj,
                                      pasos:[{paso, segundos, etiqueta}]}
    config_grande_guardar(json) → str {ok, error, estado}
Señales:
    alarmas_cambio(str)   JSON de alarmas_json() (otro proceso o la bandeja cambiaron algo)
    alarma_sonando(str)   {texto, tipo, atraso_s, programado, apagar_en_ms, cola, posponer_min?}
    alarma_apagada()
    grande_estado(str)    JSON de grande_estado_json()
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from ui.puentes_ocio import (
    PuenteOcioBase, a_dict, acotar, dump, entero, es_bool, id_valido, leer_json, llamar, numero, texto_limpio,
)

_log = logging.getLogger("lune.puente_alarmas")

DIAS = "lmxjvsd"                                     # bit0 = lunes … bit6 = domingo
MAX_ALARMAS = 100                                    # filas que se mandan a la página
MAX_TEMPORIZADOR_S = 24 * 3600
TIPOS = ("alarma", "temporizador", "pospuesta", "prueba")
ACCIONES_TEMPORIZADOR = ("iniciar", "parar", "reiniciar", "borrar")
SONIDOS = ("azar", "alarma_1", "alarma_2", "alarma_3")
MOTIVOS_GRANDE = ("manual", "herramienta", "alarma", "salvapantallas")
# Tabla de 11 pasos del salvapantallas (Mate-Engine), por si nucleo.pantalla_grande no está.
TIEMPOS_RESPALDO = (30, 60, 300, 900, 1800, 2700, 3600, 5400, 7200, 9000, 10800)

# Rangos de la config (clave: (mín, máx, entero?)).
RANGOS_ALARMAS = {
    "bloqueo_s": (0, 30, True),
    "recuperar_min": (0, 120, True),
    "posponer_min": (1, 60, True),
    "volumen": (0.0, 1.0, False),
}
BOOLS_ALARMAS = ("activo", "pantalla_grande", "decir_texto")
DEFECTO_ALARMAS = {
    "activo": True, "pantalla_grande": True, "decir_texto": True, "bloqueo_s": 5,
    "recuperar_min": 10, "posponer_min": 5, "volumen": 0.8, "sonido": "azar",
}
BOOLS_GRANDE = ("activo", "clic_sale_de_todo", "fondo_oscuro", "reloj")
DEFECTO_GRANDE = {"activo": False, "paso": 0, "clic_sale_de_todo": True, "fondo_oscuro": True, "reloj": True}

_HORA = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_DIAS = re.compile(r"^[lmxjvsd]{0,7}$")
_PROGRAMADO = re.compile(r"^[0-9T:\- ]{0,25}$")


# ── Utilidades puras ───────────────────────────────────────────────────────────

def parsear_hora(v: Any) -> Optional[Tuple[int, int]]:
    """«7:05» / «07:05» → (7, 5); None si no vale."""
    if not isinstance(v, str):
        return None
    m = _HORA.match(v.strip())
    return (int(m.group(1)), int(m.group(2))) if m else None


def mascara_dias(v: Any) -> Optional[int]:
    """«lmxjv» → 0b0011111; máscara 0–127 tal cual; «» o 0 = todos los días. None si no vale
    (letras de fuera, repetidas, tipos raros)."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v if 0 <= v <= 127 else None
    if not isinstance(v, str):
        return None
    s = v.strip().lower()
    if s == "todos":
        return 0
    if not _DIAS.match(s) or len(set(s)) != len(s):
        return None
    m = 0
    for ch in s:
        m |= 1 << DIAS.index(ch)
    return m


def texto_dias(mask: int) -> str:
    """0 → «todos»; si no, las letras en orden (l m x j v s d)."""
    if not mask or mask & 127 == 127:
        return "todos"
    return "".join(ch for i, ch in enumerate(DIAS) if mask & (1 << i))


def etiqueta_tiempo(segundos: int) -> str:
    """30 → «30 s», 300 → «5 min», 5400 → «1 h 30 min»."""
    s = int(segundos)
    if s < 60:
        return f"{s} s"
    h, m = divmod(s // 60, 60)
    if not h:
        return f"{m} min"
    return f"{h} h" + (f" {m} min" if m else "")


def normalizar_alarma(item: Any) -> Optional[Dict[str, Any]]:
    """Alarma de ControlAlarmasQt.listar() (dict o dataclass) → fila segura para la página."""
    d = a_dict(item, ("id", "activa", "hora", "minuto", "dias", "una_vez", "texto"))
    iid = d.get("id")
    if not id_valido(iid):
        return None
    hora, minuto = entero(d.get("hora")), entero(d.get("minuto"))
    if hora is None and isinstance(d.get("hora"), str):          # «07:30» en un solo campo
        hm = parsear_hora(d.get("hora"))
        hora, minuto = hm if hm else (None, None)
    if hora is None or minuto is None or not (0 <= hora <= 23 and 0 <= minuto <= 59):
        return None
    # ControlAlarmasQt.listar() da «dias» en letras y «dias_mask»; un Alarma suelto, la máscara.
    dias = mascara_dias(d["dias_mask"]) if "dias_mask" in d else None
    if dias is None:
        dias = mascara_dias(d.get("dias", 0))
    proxima = numero(d.get("proxima"))
    return {
        "id": iid,
        "activa": d.get("activa", True) is not False,
        "hora": hora,
        "minuto": minuto,
        "dias": dias if dias is not None else 0,
        "una_vez": d.get("una_vez") is True,
        "texto": texto_limpio(d.get("texto")),
        "proxima": round(proxima, 3) if proxima and proxima > 0 else 0,
    }


def normalizar_temporizador(item: Any) -> Optional[Dict[str, Any]]:
    d = a_dict(item, ("id", "activo", "duracion_s", "objetivo", "restante_s", "texto"))
    iid = d.get("id")
    dur = numero(d.get("duracion_s"))
    if not id_valido(iid) or dur is None or dur <= 0:
        return None
    obj = numero(d.get("objetivo")) or 0.0
    rest = numero(d.get("restante_s"))
    activo = d.get("activo", True) is not False
    return {
        "id": iid,
        "activo": activo,
        "duracion_s": int(round(acotar(dur, 1, 10 * MAX_TEMPORIZADOR_S))),
        "objetivo": round(obj, 3) if obj > 0 and activo else 0,
        # parado sin restante (recién creado sin iniciar) = la duración entera, como Temporizador.falta
        "restante_s": int(round(acotar(rest, 0, 10 * MAX_TEMPORIZADOR_S))) if rest else int(dur),
        "texto": texto_limpio(d.get("texto")),
    }


def normalizar_sonando(obj: Any) -> Optional[Dict[str, Any]]:
    """Payload de ControlAlarmasQt.sonando (JSON o dict) → {texto, tipo, atraso_s, programado,
    apagar_en_ms, cola}; None si no es un aviso."""
    if isinstance(obj, str):
        obj = leer_json(obj)
    if not isinstance(obj, dict):
        d = a_dict(obj, ("texto", "tipo", "atraso_s", "programado", "apagar_en_ms", "cola"))
        if not d:
            return None
        obj = d
    tipo = obj.get("tipo") if obj.get("tipo") in TIPOS else "alarma"
    atraso = numero(obj.get("atraso_s")) or 0.0
    apagar = numero(obj.get("apagar_en_ms")) or 0.0
    cola = obj.get("cola")
    n_cola = len(cola) if isinstance(cola, (list, tuple)) else (entero(cola) or 0)
    prog = obj.get("programado") if isinstance(obj.get("programado"), str) else ""
    out = {
        "texto": texto_limpio(obj.get("texto")),
        "tipo": tipo,
        "atraso_s": round(acotar(atraso, 0, 7 * 86400), 1),
        "programado": prog if _PROGRAMADO.match(prog) else "",
        "apagar_en_ms": int(acotar(apagar, 0, 60000)),
        "cola": int(acotar(n_cola, 0, 99)),
    }
    pos = entero(obj.get("posponer_min"))
    if pos is not None and 1 <= pos <= 60:
        out["posponer_min"] = pos
    return out


def normalizar_proxima(obj: Any) -> Optional[Dict[str, Any]]:
    """«proxima» de ControlAlarmasQt.listar() → {id, tipo, texto, cuando (epoch s)} o None."""
    if not isinstance(obj, dict) or not id_valido(obj.get("id")):
        return None
    cuando = numero(obj.get("cuando"))
    if not cuando or cuando <= 0:
        return None
    return {
        "id": obj["id"],
        "tipo": "temporizador" if obj.get("tipo") == "temporizador" else "alarma",
        "texto": texto_limpio(obj.get("texto")),
        "cuando": round(cuando, 3),
    }


# ── Puente ─────────────────────────────────────────────────────────────────────

class PuenteAlarmas(PuenteOcioBase):
    """Objeto `alarmas` del QWebChannel (window.luneAlarmas)."""

    NOMBRE = "puente_alarmas"

    alarmas_cambio = pyqtSignal(str)
    alarma_sonando = pyqtSignal(str)
    alarma_apagada = pyqtSignal()
    grande_estado = pyqtSignal(str)

    def __init__(self, config: Any = None, *, alarmas: Any = None, grande: Any = None,
                 reloj: Callable[[], float] = time.time, monotonic: Callable[[], float] = time.monotonic,
                 pantalla_grande_mod: Any = None, parent: Optional[QObject] = None):
        super().__init__(config, parent)
        self._alarmas: Any = None
        self._grande: Any = None
        self._reloj = reloj
        self._mono = monotonic
        self._pg_mod = pantalla_grande_mod
        self._sonando: Optional[Tuple[Dict[str, Any], float]] = None   # (payload, monotonic al recibirlo)
        if alarmas is not None or grande is not None:
            self.enlazar(alarmas=alarmas, grande=grande)

    # ── Enlace con los controladores ───────────────────────────────────────────
    @property
    def alarmas(self) -> Any:
        return self._alarmas

    @property
    def grande(self) -> Any:
        return self._grande

    def enlazar(self, *, alarmas: Any = None, grande: Any = None) -> None:
        """ControlAlarmasQt y ControlPantallaGrande (o None: soltarlos). Reconecta las
        señales y, si cambió algo, avisa a la página con el estado nuevo."""
        if self._cerrado:
            alarmas = grande = None
        antes = (self._alarmas, self._grande)
        self._desconectar_todo()
        self._alarmas, self._grande = alarmas, grande
        if alarmas is None:
            self._sonando = None
        self._conectar(alarmas, "sonando", self._on_sonando)
        self._conectar(alarmas, "apagada", self._on_apagada)
        self._conectar(alarmas, "cambio", self._on_cambio)
        self._conectar(grande, "cambio", self._on_grande)
        if (alarmas, grande) != antes and not self._cerrado:
            self.alarmas_cambio.emit(self.alarmas_json())
            self.grande_estado.emit(self.grande_estado_json())

    def cerrar(self) -> None:
        self._alarmas = self._grande = None
        self._sonando = None
        super().cerrar()

    # ── Señales de los controladores ───────────────────────────────────────────
    def _on_sonando(self, payload: Any = None) -> None:
        d = normalizar_sonando(payload)
        if d is None:
            return
        self._sonando = (d, self._mono())
        self.alarma_sonando.emit(dump(d))

    def _on_apagada(self, *_a) -> None:
        self._sonando = None
        self.alarma_apagada.emit()

    def _on_cambio(self, *_a) -> None:
        self.alarmas_cambio.emit(self.alarmas_json())

    def _on_grande(self, activa: Any = None, motivo: Any = None) -> None:
        e = self._grande_estado()
        if isinstance(activa, bool):                 # la señal manda sobre estado()
            e["activa"] = activa
            e["motivo"] = motivo if activa and motivo in MOTIVOS_GRANDE else ""
        self.grande_estado.emit(dump(e))

    # ═══ Alarmas y temporizadores ════════════════════════════════════════════
    def _sonando_actual(self) -> Optional[Dict[str, Any]]:
        if self._sonando is None:
            return None
        d, t = self._sonando
        pasado_ms = max(0.0, (self._mono() - t) * 1000.0)
        return {**d, "apagar_en_ms": int(max(0.0, d["apagar_en_ms"] - pasado_ms))}

    def _estado(self) -> Dict[str, Any]:
        activo = self._cfg("alarmas", "activo", True) is not False
        base: Dict[str, Any] = {
            "disponible": self._alarmas is not None,
            "activo": activo,
            "ahora": round(float(self._reloj()), 3),
            "alarmas": [],
            "temporizadores": [],
            "sonando": self._sonando_actual(),
            "proxima": None,
        }
        if self._alarmas is None:
            return base
        crudo = llamar(self._alarmas, "listar")
        if not isinstance(crudo, dict):
            return base
        alarmas = [a for a in (normalizar_alarma(x) for x in (crudo.get("alarmas") or [])[:MAX_ALARMAS]) if a]
        temps = [t for t in (normalizar_temporizador(x) for x in (crudo.get("temporizadores") or [])[:MAX_ALARMAS]) if t]
        alarmas.sort(key=lambda a: (a["hora"], a["minuto"], a["id"]))
        base["alarmas"] = alarmas
        base["temporizadores"] = temps
        if isinstance(crudo.get("activo"), bool):
            base["activo"] = crudo["activo"]
        ahora = numero(crudo.get("ahora"))
        if ahora and ahora > 0:
            base["ahora"] = round(ahora, 3)                 # el reloj del controlador (objetivo sale de él)
        base["proxima"] = normalizar_proxima(crudo.get("proxima"))
        if base["sonando"] is None and crudo.get("sonando"):
            base["sonando"] = normalizar_sonando(crudo.get("sonando"))
        return base

    @pyqtSlot(result=str)
    def alarmas_json(self) -> str:
        return dump(self._estado())

    def _resultado(self, r: Any, fallo: str) -> Tuple[bool, str, str]:
        """(ok, error, id) de lo que devuelve el controlador (dict, bool u objeto)."""
        if r is None or r is False:
            return False, fallo, ""
        if r is True:
            return True, "", ""
        d = a_dict(r, ("id", "ok", "error"))
        if d.get("ok") is False or d.get("error"):
            return False, texto_limpio(d.get("error") or fallo, 300), ""
        iid = d.get("id")
        if not id_valido(iid):
            sub = d.get("alarma") or d.get("temporizador")
            iid = a_dict(sub, ("id",)).get("id") if sub is not None else ""
        return True, "", iid if id_valido(iid) else ""

    def _respuesta(self, ok: bool, error: str = "", **extra) -> str:
        return dump({"ok": ok, "error": "" if ok else error, **extra, "estado": self._estado()})

    def validar_alarma(self, obj: Any) -> Tuple[Optional[Dict[str, Any]], str]:
        """Payload de la página → (dict para ControlAlarmasQt.guardar_alarma, error)."""
        if not isinstance(obj, dict) or not obj:
            return None, "Alarma no válida."
        permitidas = {"id", "hora", "dias", "una_vez", "texto", "activa"}
        if any(k not in permitidas for k in obj):
            return None, "Alarma no válida."
        out: Dict[str, Any] = {}
        if "id" in obj and obj["id"] not in (None, ""):
            if not id_valido(obj["id"]):
                return None, "Esa alarma no existe."
            out["id"] = obj["id"]
        if "hora" in obj:
            hm = parsear_hora(obj["hora"])
            if hm is None:
                return None, "Hora no válida (HH:MM)."
            out["hora"], out["minuto"] = hm
        elif "id" not in out:
            return None, "Falta la hora."
        if "dias" in obj:
            m = mascara_dias(obj["dias"])
            if m is None:
                return None, "Días no válidos (l m x j v s d)."
            out["dias"] = m
        for k in ("una_vez", "activa"):
            if k in obj:
                if not es_bool(obj[k]):
                    return None, f"«{k}» tiene que ser sí o no."
                out[k] = obj[k]
        if "texto" in obj:
            if obj["texto"] is not None and not isinstance(obj["texto"], str):
                return None, "Texto no válido."
            out["texto"] = texto_limpio(obj["texto"])
        if "id" not in out:
            out.setdefault("dias", 0)
            out.setdefault("una_vez", False)
            out.setdefault("texto", "")
            out.setdefault("activa", True)
        return out, ""

    @pyqtSlot(str, result=str)
    def alarma_guardar(self, payload: str) -> str:
        d, error = self.validar_alarma(leer_json(payload))
        if d is None:
            return self._respuesta(False, error)
        if self._alarmas is None:
            return self._respuesta(False, "Las alarmas no están en marcha.")
        ok, error, iid = self._resultado(llamar(self._alarmas, "guardar_alarma", d), "No pude guardar la alarma.")
        return self._respuesta(ok, error, id=iid or d.get("id", ""))

    @pyqtSlot(str, result=str)
    def alarma_borrar(self, id_: str) -> str:
        if not id_valido(id_):
            return self._respuesta(False, "Esa alarma no existe.")
        if self._alarmas is None:
            return self._respuesta(False, "Las alarmas no están en marcha.")
        ok = llamar(self._alarmas, "borrar", id_) is True
        return self._respuesta(ok, "No encontré esa alarma.")

    def validar_temporizador(self, obj: Any) -> Tuple[Optional[Dict[str, Any]], str]:
        """{segundos | h, m, s, texto, iniciar} → (dict para crear_temporizador, error)."""
        if not isinstance(obj, dict) or not obj:
            return None, "Temporizador no válido."
        if any(k not in ("segundos", "h", "m", "s", "texto", "iniciar") for k in obj):
            return None, "Temporizador no válido."
        if "segundos" in obj:
            seg = entero(obj["segundos"])
            if seg is None or any(k in obj for k in ("h", "m", "s")):
                return None, "Duración no válida."
        else:
            partes = [entero(obj.get(k, 0)) for k in ("h", "m", "s")]
            if any(p is None or p < 0 for p in partes) or partes[1] > 59 or partes[2] > 59:
                return None, "Duración no válida."
            seg = partes[0] * 3600 + partes[1] * 60 + partes[2]
        if not 1 <= seg <= MAX_TEMPORIZADOR_S:
            return None, "Entre 1 segundo y 24 horas."
        iniciar = obj.get("iniciar", True)
        if not es_bool(iniciar):
            return None, "«iniciar» tiene que ser sí o no."
        texto = obj.get("texto", "")
        if texto is not None and not isinstance(texto, str):
            return None, "Texto no válido."
        return {"segundos": seg, "texto": texto_limpio(texto), "iniciar": iniciar}, ""

    @pyqtSlot(str, result=str)
    def temporizador_crear(self, payload: str) -> str:
        d, error = self.validar_temporizador(leer_json(payload))
        if d is None:
            return self._respuesta(False, error)
        if self._alarmas is None:
            return self._respuesta(False, "Las alarmas no están en marcha.")
        ok, error, iid = self._resultado(llamar(self._alarmas, "crear_temporizador", d),
                                         "No pude crear el temporizador.")
        return self._respuesta(ok, error, id=iid)

    @pyqtSlot(str, str, result=str)
    def temporizador_accion(self, id_: str, accion: str) -> str:
        if not id_valido(id_) or accion not in ACCIONES_TEMPORIZADOR:
            return self._respuesta(False, "Acción no válida.")
        if self._alarmas is None:
            return self._respuesta(False, "Las alarmas no están en marcha.")
        if accion == "borrar":
            ok = llamar(self._alarmas, "borrar", id_) is True
        else:
            ok = llamar(self._alarmas, "temporizador_accion", id_, accion) is True
        return self._respuesta(ok, "No encontré ese temporizador.")

    @pyqtSlot(result=bool)
    def alarma_apagar(self) -> bool:
        """Como un clic en la alarma: respeta el bloqueo de los primeros segundos."""
        return llamar(self._alarmas, "apagar") is True

    @pyqtSlot(result=bool)
    def alarma_posponer(self) -> bool:
        return llamar(self._alarmas, "posponer") is True

    @pyqtSlot(result=bool)
    def alarma_probar(self) -> bool:
        return llamar(self._alarmas, "probar") is True

    # ── Config de las alarmas ──────────────────────────────────────────────────
    def _config_alarmas(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for k in BOOLS_ALARMAS:
            out[k] = self._cfg("alarmas", k, DEFECTO_ALARMAS[k]) is not False
        for k, (lo, hi, ent) in RANGOS_ALARMAS.items():
            v = numero(self._cfg("alarmas", k, DEFECTO_ALARMAS[k]))
            v = acotar(v if v is not None else DEFECTO_ALARMAS[k], lo, hi)
            out[k] = int(round(v)) if ent else round(v, 2)
        sonido = self._cfg("alarmas", "sonido", "azar")
        out["sonido"] = sonido if sonido in SONIDOS else "azar"
        out["sonidos"] = list(SONIDOS)
        return out

    @pyqtSlot(result=str)
    def config_alarmas(self) -> str:
        return dump(self._config_alarmas())

    @pyqtSlot(str, result=str)
    def config_alarmas_guardar(self, payload: str) -> str:
        obj = leer_json(payload)

        def falla(msg: str) -> str:
            return dump({"ok": False, "error": msg, "estado": self._config_alarmas()})

        permitidas = set(BOOLS_ALARMAS) | set(RANGOS_ALARMAS) | {"sonido"}
        if not obj or any(k not in permitidas for k in obj):
            return falla("Ajustes de alarmas no válidos.")
        cambios: Dict[str, Any] = {}
        for k in BOOLS_ALARMAS:
            if k in obj:
                if not es_bool(obj[k]):
                    return falla(f"«{k}» tiene que ser sí o no.")
                cambios[k] = obj[k]
        for k, (lo, hi, ent) in RANGOS_ALARMAS.items():
            if k in obj:
                v = entero(obj[k]) if ent else numero(obj[k])
                if v is None or not lo <= v <= hi:
                    return falla(f"«{k}» entre {lo} y {hi}.")
                cambios[k] = int(v) if ent else round(float(v), 2)
        if "sonido" in obj:
            if obj["sonido"] not in SONIDOS:
                return falla("Sonido no válido.")
            cambios["sonido"] = obj["sonido"]
        ok = self._guardar_cambios("alarmas", cambios)
        llamar(self._alarmas, "recargar_config")
        if "activo" in cambios:
            self.alarmas_cambio.emit(self.alarmas_json())
        return dump({"ok": ok, "error": "" if ok else "No pude guardar.", "estado": self._config_alarmas()})

    # ═══ Pantalla grande y salvapantallas ════════════════════════════════════
    def _grande_estado(self) -> Dict[str, Any]:
        e = llamar(self._grande, "estado")
        if not isinstance(e, dict):
            activa = getattr(self._grande, "activo", False) if self._grande is not None else False
            motivo = getattr(self._grande, "motivo", "") if self._grande is not None else ""
            e = {"activa": activa is True, "motivo": motivo}
        activa = e.get("activa", e.get("activo", False)) is True
        motivo = e.get("motivo") if e.get("motivo") in MOTIVOS_GRANDE else ""
        return {"activa": activa, "motivo": motivo if activa else "", "disponible": self._grande is not None}

    @pyqtSlot(result=str)
    def grande_estado_json(self) -> str:
        return dump(self._grande_estado())

    @pyqtSlot(result=bool)
    def grande_alternar(self) -> bool:
        """True si entró o salió. (ControlPantallaGrande.alternar devuelve si queda activa:
        al salir devuelve False, y eso también es un éxito.)"""
        if self._grande is None:
            return False
        antes = self._grande_estado()["activa"]
        r = llamar(self._grande, "alternar")
        if r is None:
            return False
        return bool(r) or (antes and not self._grande_estado()["activa"])

    @pyqtSlot(result=bool)
    def salvapantallas_probar(self) -> bool:
        return llamar(self._grande, "probar_salvapantallas") is True

    def _pasos(self) -> List[Dict[str, Any]]:
        mod = self._pg_mod
        if mod is None:
            try:
                import importlib
                mod = importlib.import_module("nucleo.pantalla_grande")
            except Exception:
                mod = False                          # aún no existe: tabla propia
            self._pg_mod = mod
        tiempos = getattr(mod, "TIEMPOS", None) if mod else None
        if not isinstance(tiempos, (list, tuple)) or not tiempos:
            tiempos = TIEMPOS_RESPALDO
        et = getattr(mod, "etiqueta", None) if mod else None
        out = []
        for i, seg in enumerate(tiempos):
            etiqueta = ""
            if callable(et):
                try:
                    etiqueta = texto_limpio(et(i), 24)
                except Exception:
                    etiqueta = ""
            out.append({"paso": i, "segundos": int(seg), "etiqueta": etiqueta or etiqueta_tiempo(int(seg))})
        return out

    def _config_grande(self) -> Dict[str, Any]:
        pasos = self._pasos()
        out: Dict[str, Any] = {k: self._cfg("salvapantallas", k, DEFECTO_GRANDE[k]) is not False for k in BOOLS_GRANDE}
        out["activo"] = self._cfg("salvapantallas", "activo", False) is True
        p = entero(self._cfg("salvapantallas", "paso", 0))
        out["paso"] = int(acotar(p if p is not None else 0, 0, len(pasos) - 1))
        out["pasos"] = pasos
        return out

    @pyqtSlot(result=str)
    def config_grande(self) -> str:
        return dump(self._config_grande())

    @pyqtSlot(str, result=str)
    def config_grande_guardar(self, payload: str) -> str:
        obj = leer_json(payload)

        def falla(msg: str) -> str:
            return dump({"ok": False, "error": msg, "estado": self._config_grande()})

        if not obj or any(k not in (*BOOLS_GRANDE, "paso") for k in obj):
            return falla("Ajustes del salvapantallas no válidos.")
        cambios: Dict[str, Any] = {}
        for k in BOOLS_GRANDE:
            if k in obj:
                if not es_bool(obj[k]):
                    return falla(f"«{k}» tiene que ser sí o no.")
                cambios[k] = obj[k]
        if "paso" in obj:
            p = entero(obj["paso"])
            n = len(self._pasos())
            if p is None or not 0 <= p < n:
                return falla(f"Tiempo de espera entre 0 y {n - 1}.")
            cambios["paso"] = p
        ok = self._guardar_cambios("salvapantallas", cambios)
        llamar(self._grande, "recargar_config")
        return dump({"ok": ok, "error": "" if ok else "No pude guardar.", "estado": self._config_grande()})
