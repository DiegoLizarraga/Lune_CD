"""
ui/puente_escritorio.py — el segundo objeto del QWebChannel (window.luneEscritorio).

Con dobles de los controladores del corte 4 (Despachador, ControlTema, GestorAtajosQt,
ControlModoJuego, anfitrión, asistente) y una Config real en una carpeta temporal:
validación y rechazo de todo lo que llega de la página, vista previa del tema sin disco,
efectos en config.efectos, juego_forzar 1/0/-1, reemisión de las señales y registro en
el canal. Un test más con los módulos reales de nucleo/ (si existen) comprueba el contrato.
"""
import json
from types import SimpleNamespace

import pytest

from nucleo.config import Config

pytest.importorskip("PyQt6.QtCore")
from PyQt6.QtCore import QObject, pyqtSignal  # noqa: E402

from ui.puente_escritorio import MAX_JSON, PuenteEscritorio, leer_json, registrar_en_canal  # noqa: E402


# ── Dobles ─────────────────────────────────────────────────────────────────────
class Accion(SimpleNamespace):
    pass


ACCIONES = {i: Accion(id=i, etiqueta=i.capitalize(), icono="ic_" + i, usos=frozenset(u))
            for i, u in (("ajustes", "rb"), ("voz", "rbt"), ("dormir", "rbt"), ("expresiones", "r"),
                         ("expresion", ""), ("asistente", "rbt"), ("mostrar_lune", "rbt"), ("salir", "rb"),
                         ("bailar", "rbt"), ("modo_juego_forzar", "rbt"))}
for _a in ACCIONES.values():
    _a.usos = frozenset({"r": "radial", "b": "bandeja", "t": "atajo"}[c] for c in _a.usos)


def acciones_falsas(registro):
    """nucleo.acciones_ui falso: mismo contrato, apunta lo que recibe."""
    def items_radial(desp, estado, ctx, ids):
        registro.append(("items_radial", estado, ctx, list(ids)))
        return [{"id": i, "etiqueta": ACCIONES[i].etiqueta, "icono": ACCIONES[i].icono}
                for i in ids if i in ACCIONES and desp.tiene(i)] + [{"id": "<malo>", "etiqueta": "x"}]

    def items_expresiones(desp):
        return [{"id": "expresion", "etiqueta": "Contenta", "icono": "smile", "arg": "happy"}]

    def catalogo(desp, estado, ctx, tipo=None):
        registro.append(("catalogo", tipo))
        return [{"id": i, "etiqueta": a.etiqueta, "icono": a.icono, "disponible": desp.tiene(i),
                 "usos": sorted(a.usos), "marcado": None}
                for i, a in ACCIONES.items() if tipo is None or tipo in a.usos]

    def validar_lista(ids, *, maximo=None, uso=None):
        registro.append(("validar_lista", uso, maximo))
        out = []
        for x in ids:
            if isinstance(x, str) and x in ACCIONES and x not in out and (uso is None or uso in ACCIONES[x].usos):
                out.append(x)
        return out[:maximo] if maximo else out

    return SimpleNamespace(ACCIONES=ACCIONES, MAX_RADIAL=10, items_radial=items_radial,
                           items_expresiones=items_expresiones, catalogo=catalogo, validar_lista=validar_lista,
                           Contexto=lambda **kw: SimpleNamespace(**kw))


class Despachador:
    def __init__(self, ids=("ajustes", "voz", "dormir", "expresiones", "expresion", "asistente", "mostrar_lune",
                            "bailar", "modo_juego_forzar")):
        self.ids = set(ids)
        self.ejecutadas = []

    def tiene(self, i):
        return i in self.ids

    def ejecutar(self, i, arg=""):
        self.ejecutadas.append((i, arg))
        return i in self.ids


class Tema(QObject):
    cambio = pyqtSignal(str)

    def __init__(self, emite=True):
        super().__init__()
        self.emite = emite
        self.vista, self.guardados, self.restablecido = [], [], 0
        self._cfg = {"preset": "cian", "hue": 0.0, "saturacion": 1.0, "tenir_pop": False, "tenir_fondo": False}
        self._css = "null"

    def actual(self):
        return dict(self._cfg)

    def css_json(self):
        return self._css

    def previsualizar(self, cfg):
        self.vista.append(dict(cfg))
        self._cfg.update(cfg)
        self._css = json.dumps({"--cyan-500": "#FF00FF", "--cyan-500-rgb": "255 0 255"})
        if self.emite:
            self.cambio.emit(self._css)
        return self.actual()

    def guardar(self, cfg=None):
        self.guardados.append(dict(cfg or {}))
        self._cfg.update(cfg or {})
        return self.actual()

    def restablecer(self):
        self.restablecido += 1
        return self.actual()


class Atajos(QObject):
    cambio = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.llamadas = []
        self.error_cambiar = None

    def estado(self):
        return [{"id": "mostrar_lune", "etiqueta": "Abrir Lune", "combo": "ctrl+alt+shift+l", "texto": "Ctrl+Alt+Shift+L",
                 "error": None, "aviso": None, "disponible": True, "siempre": True},
                {"id": "voz", "combo": "ctrl+alt+shift+v", "texto": "Ctrl+Alt+Shift+V", "disponible": True},
                {"id": "<x>", "combo": "a"}]

    def validar(self, combo, id_=None):
        self.llamadas.append(("validar", combo, id_))
        conflicto = "mostrar_lune" if combo == "ctrl+alt+shift+l" and id_ != "mostrar_lune" else ""
        return {"ok": True, "combo": combo, "error": None, "aviso": None, "conflicto": conflicto}

    def cambiar(self, id_, combo):
        self.llamadas.append(("cambiar", id_, combo))
        return self.error_cambiar

    def activar(self, on):
        self.llamadas.append(("activar", on))

    def capturando(self, on):
        self.llamadas.append(("capturando", on))

    def restablecer(self):
        self.llamadas.append(("restablecer",))

    def recargar(self):
        self.llamadas.append(("recargar",))


class Juego(QObject):
    cambio = pyqtSignal(bool, str)

    def __init__(self):
        super().__init__()
        self.forzados, self.recargas = [], 0
        self.est = {"activo": False, "motivo": "", "forzado": None, "exe": ""}

    def estado(self):
        return dict(self.est)

    def forzar(self, on):
        self.forzados.append(on)

    def recargar_config(self):
        self.recargas += 1


class Asistente:
    def __init__(self):
        self.llamadas = []

    def set_fps_max(self, n):
        self.llamadas.append(("fps", n))

    def set_encima(self, on):
        self.llamadas.append(("encima", on))


class Bus:
    def actual(self):
        return SimpleNamespace(grande=False, sentada="")


@pytest.fixture
def config(tmp_path):
    return Config(config_path=str(tmp_path / "config.json"))


def montar(config, *, tema=None, atajos=None, juego=None, registro=None, **kw):
    registro = [] if registro is None else registro
    desp = Despachador()
    anfitrion = SimpleNamespace(barra=[], set_en_barra=lambda on: anfitrion.barra.append(on))
    ctx = SimpleNamespace(modo="normal", asistente_visible=True)
    serv = SimpleNamespace(despachador=desp, tema=tema, atajos=atajos, juego=juego, radial=None, bandeja=None,
                           contexto=lambda: ctx, anfitrion=anfitrion)
    esc = SimpleNamespace(estado=Bus(), asistente=Asistente())
    kw.setdefault("tema_mod", SimpleNamespace(PRESETS={"cian": 0.0, "violeta": 0.233},
                                              css_json=lambda cfg: json.dumps({"--cyan-500": "#123456"}),
                                              normalizar=lambda cfg: dict(cfg)))
    kw.setdefault("modo_juego_mod", SimpleNamespace(normalizar_app=lambda n: (n.strip().lower() + ("" if n.strip().lower().endswith(".exe") else ".exe"))
                                                    if isinstance(n, str) and n.strip() and all(c not in n for c in "\\/:*?") else None))
    p = PuenteEscritorio(serv, esc, config, acciones_ui=acciones_falsas(registro), **kw)
    return p, SimpleNamespace(desp=desp, anfitrion=anfitrion, ctx=ctx, esc=esc, registro=registro)


def emisiones(senal):
    out = []
    senal.connect(lambda *a: out.append(a[0] if len(a) == 1 else a))
    return out


def disco(config):
    return json.loads(config.config_path.read_text(encoding="utf-8")) if config.config_path.exists() else {}


# ── JSON de la página ──────────────────────────────────────────────────────────
def test_leer_json_valida_tamano_tipo_y_nan():
    assert leer_json('{"a": 1}') == {"a": 1}
    assert leer_json("[1]") is None and leer_json("[1]", list) == [1]
    for malo in (None, "", "no json", '{"a": NaN}', '{"a": Infinity}', "x" * (MAX_JSON + 1), 5, b"{}"):
        assert leer_json(malo) is None, malo


# ── Registro en el canal ───────────────────────────────────────────────────────
def test_registrar_en_canal_como_escritorio(qapp, config):
    class Canal(QObject):
        def __init__(self):
            super().__init__()
            self.registrados, self.quitados = [], []

        def registerObject(self, nombre, obj):
            self.registrados.append((nombre, obj))

        def deregisterObject(self, obj):
            self.quitados.append(obj)

    canal = Canal()
    tema = Tema()
    anfitrion = SimpleNamespace(navegar=None)
    serv = SimpleNamespace(despachador=Despachador(), tema=tema, anfitrion=anfitrion, _deshacer=[])
    p = registrar_en_canal(canal, serv, SimpleNamespace(estado=Bus(), asistente=None), config)
    assert isinstance(p, PuenteEscritorio)
    assert canal.registrados == [("escritorio", p)]
    assert p.parent() is canal, "vive lo que vive el canal"
    # AnfitrionWeb.abrir_ajustes → anfitrion.navegar("settings") → señal navegar (validada)
    vistas = emisiones(p.navegar)
    anfitrion.navegar("settings")
    anfitrion.navegar("otra")
    assert vistas == ["settings"]
    # ServiciosCorte4.desmontar() corre _deshacer: fuera del canal, sin señales y sin enganche
    assert serv._deshacer == [p.cerrar]
    cambios = emisiones(p.tema_cambio)
    serv._deshacer[0]()
    assert canal.quitados == [p] and anfitrion.navegar is None
    tema.cambio.emit("null")
    assert cambios == []
    p.cerrar()
    assert canal.quitados == [p], "idempotente"
    # Un navegar que ya puso otro no se pisa
    otro = SimpleNamespace(navegar=print)
    registrar_en_canal(Canal(), SimpleNamespace(despachador=Despachador()), None, config, anfitrion=otro)
    assert otro.navegar is print
    # Con el QWebChannel de verdad (sin leer registeredObjects: PyQt crea un envoltorio que lo borraría).
    canal_mod = pytest.importorskip("PyQt6.QtWebChannel")
    real = canal_mod.QWebChannel()
    p2 = registrar_en_canal(real, serv, None, config)
    assert p2.parent() is real
    p2.cerrar()


def test_sin_servicios_todo_responde_sin_lanzar(qapp, config):
    p = PuenteEscritorio(None, None, config, acciones_ui=acciones_falsas([]))
    assert json.loads(p.acciones_catalogo("radial")) == []
    assert p.accion_menu("voz", "") is False
    assert json.loads(p.tema_estado())["cfg"]["preset"] == "cian"
    p.tema_previsualizar('{"preset": "cian"}')
    assert json.loads(p.juego_estado_json())["activo"] is False
    p.juego_forzar(1)
    p.atajos_capturando(True)
    assert json.loads(p.atajos_estado())["lista"]
    assert json.loads(p.liberar_memoria())["ok"] in (True, False)


# ── Acciones ───────────────────────────────────────────────────────────────────
def test_accion_menu_valida_id_catalogo_handler_y_arg(qapp, config):
    p, x = montar(config)
    assert p.accion_menu("voz", "") is True
    assert p.accion_menu("expresion", "happy") is True
    for id_, arg in (("desconocida", ""), ("salir", ""), ("Voz", ""), ("voz;rm", ""), ("", ""),
                     ("voz", "../../x"), ("voz", "a" * 41), ("voz", "<b>"), ("voz", "C:\\x")):
        assert p.accion_menu(id_, arg) is False, (id_, arg)
    assert x.desp.ejecutadas == [("voz", ""), ("expresion", "happy")]


def test_acciones_catalogo_radial_expresiones_y_todas(qapp, config):
    p, x = montar(config)
    config.set("menu_radial", "principal", ["voz", "ajustes", "salir", "<x>"])
    r = json.loads(p.acciones_catalogo("radial"))
    assert [i["id"] for i in r] == ["voz", "ajustes"]
    assert r[0] == {"id": "voz", "etiqueta": "Voz", "icono": "ic_voz", "arg": "", "habilitado": True, "marcado": None}
    llamada = next(c for c in x.registro if c[0] == "items_radial")
    assert llamada[2] is x.ctx and llamada[3] == ["voz", "ajustes", "salir"], "contexto del montaje; ids con patrón (B filtra)"
    assert llamada[1].grande is False, "la foto del estado (bus.actual()), no el bus"
    e = json.loads(p.acciones_catalogo("expresiones"))
    assert e == [{"id": "expresion", "etiqueta": "Contenta", "icono": "smile", "arg": "happy", "habilitado": True, "marcado": None}]
    todas = json.loads(p.acciones_catalogo("todas"))
    assert {i["id"] for i in todas} >= {"ajustes", "voz"} and "salir" not in {i["id"] for i in todas}
    assert json.loads(p.acciones_catalogo("otra")) == [] and json.loads(p.acciones_catalogo("")) == []


# ── Tema ───────────────────────────────────────────────────────────────────────
def test_tema_estado_y_vista_previa_sin_disco(qapp, config):
    tema = Tema()
    p, _ = montar(config, tema=tema)
    antes = config.config_path.read_bytes()
    cambios = emisiones(p.tema_cambio)
    est = json.loads(p.tema_estado())
    assert est["cfg"]["preset"] == "cian" and est["vars"] is None and est["presets"]["violeta"] == 0.233
    p.tema_previsualizar(json.dumps({"preset": "personalizado", "hue": 400, "saturacion": 9}))
    assert tema.vista == [{"preset": "personalizado", "hue": 40.0, "saturacion": 2.0}], "parcial, validado y acotado"
    assert json.loads(cambios[-1]) == {"--cyan-500": "#FF00FF", "--cyan-500-rgb": "255 0 255"}
    assert len(cambios) == 1, "una sola emisión por vista previa"
    assert tema.guardados == [] and config.config_path.read_bytes() == antes, "vista previa: nada al disco"
    for malo in ('{"preset": "verde_raro"}', '{"hue": "90"}', '{"tenir_pop": "true"}', '{"saturacion": NaN}',
                 "[]", "{}", "no json", '{"preset": "<x>"}', json.dumps({"hue": 1, "x": "y" * MAX_JSON})):
        p.tema_previsualizar(malo)
    assert len(tema.vista) == 1


def test_tema_vista_previa_sin_senal_emite_el_mapa_igual(qapp, config):
    tema = Tema(emite=False)
    p, _ = montar(config, tema=tema)
    cambios = emisiones(p.tema_cambio)
    p.tema_previsualizar('{"preset": "violeta"}')
    assert [json.loads(c) for c in cambios] == [{"--cyan-500": "#123456"}]


def test_tema_guardar_y_restablecer(qapp, config):
    tema = Tema()
    p, _ = montar(config, tema=tema)
    r = json.loads(p.tema_guardar('{"preset": "violeta", "tenir_fondo": true}'))
    assert r["ok"] and tema.guardados == [{"preset": "violeta", "tenir_fondo": True}]
    assert r["estado"]["cfg"]["preset"] == "violeta"
    r = json.loads(p.tema_guardar('{"tenir_fondo": 1}'))
    assert r["ok"] is False and len(tema.guardados) == 1
    assert json.loads(p.tema_restablecer())["ok"] and tema.restablecido == 1


def test_tema_sin_controlador_guarda_en_config(qapp, config):
    p, _ = montar(config)
    assert json.loads(p.tema_guardar('{"hue": 90}'))["ok"]
    assert disco(config)["tema"]["hue"] == 90 and disco(config)["tema"]["preset"] == "personalizado"


def test_senal_de_tema_se_reemite_y_cerrar_la_suelta(qapp, config):
    tema = Tema()
    p, _ = montar(config, tema=tema)
    cambios = emisiones(p.tema_cambio)
    tema.cambio.emit('{"--blue-500": "#010203", "otra": "x", "--x": {"a": 1}}')
    tema.cambio.emit("null")
    assert [json.loads(c) for c in cambios] == [{"--blue-500": "#010203"}, None]
    p.cerrar()
    tema.cambio.emit("null")
    assert len(cambios) == 2


# ── Efectos ────────────────────────────────────────────────────────────────────
def test_efectos_en_config_efectos(qapp, config):
    p, _ = montar(config)
    assert json.loads(p.efectos()) == {"fondo": True, "barrido": True, "micro": True, "pausar_sin_foco": True}
    r = json.loads(p.efectos_guardar('{"barrido": false, "micro": false}'))
    assert r["ok"] and r["estado"] == {"fondo": True, "barrido": False, "micro": False, "pausar_sin_foco": True}
    assert disco(config)["efectos"] == {"fondo": True, "barrido": False, "micro": False, "pausar_sin_foco": True}
    # Lune en reposo (11.2): «Quedarme quieta cuando no me usas» se guarda igual que los demás
    r = json.loads(p.efectos_guardar('{"pausar_sin_foco": false}'))
    assert r["ok"] and r["estado"]["pausar_sin_foco"] is False
    assert Config(config_path=str(config.config_path)).get("efectos", "pausar_sin_foco") is False
    assert Config(config_path=str(config.config_path)).get("efectos", "barrido") is False
    for malo in ('{"fondo": "no"}', '{"otra": true}', "[]", "{}", "x"):
        assert json.loads(p.efectos_guardar(malo))["ok"] is False
    assert disco(config)["efectos"]["fondo"] is True


# ── Atajos ─────────────────────────────────────────────────────────────────────
def test_atajos_estado_validar_y_guardar(qapp, config):
    at = Atajos()
    p, _ = montar(config, atajos=at)
    est = json.loads(p.atajos_estado())
    assert [f["id"] for f in est["lista"]] == ["mostrar_lune", "voz"] and est["activo"] is True
    assert est["lista"][0]["etiqueta"] == "Abrir Lune" and est["lista"][0]["siempre"] is True
    assert est["lista"][1]["etiqueta"] == "Voz", "sin etiqueta: la del catálogo"
    v = json.loads(p.atajo_validar("Shift+Ctrl+Alt+KeyJ"))
    assert v == {"ok": True, "combo": "ctrl+alt+shift+j", "texto": "Ctrl+Alt+Shift+J", "error": None, "aviso": None}
    for malo in ("F12", "a", "shift+a", "win+alt+r", "", "x" * 65, "ctrl+\x00", "altgr+e"):
        assert json.loads(p.atajo_validar(malo))["ok"] is False, malo
    assert json.loads(p.atajo_validar("ctrl+alt+e"))["aviso"], "AltGr: aviso, no error"
    assert "ya lo usa «Mostrar_lune»" in json.loads(p.atajo_validar("ctrl+alt+shift+l"))["error"]
    r = json.loads(p.atajo_guardar("voz", "ctrl+alt+shift+KeyJ"))
    assert r["ok"] and ("cambiar", "voz", "ctrl+alt+shift+j") in at.llamadas
    assert ("validar", "ctrl+alt+shift+j", "voz") in at.llamadas
    at.error_cambiar = "Otra app ya lo tiene."
    r = json.loads(p.atajo_guardar("voz", "ctrl+alt+shift+k"))
    assert r["ok"] is False and r["error"] == "Otra app ya lo tiene."
    at.error_cambiar = None
    assert json.loads(p.atajo_guardar("voz", ""))["ok"] and ("cambiar", "voz", "") in at.llamadas, "vacío = sin atajo"
    assert json.loads(p.atajo_guardar("bailar", "ctrl+alt+shift+b"))["ok"], "acción con uso «atajo» aunque no esté en la lista"
    n = len([c for c in at.llamadas if c[0] == "cambiar"])
    for id_, combo in (("salir", "ctrl+alt+shift+q"), ("<x>", "ctrl+alt+shift+q"), ("voz", "F12"), ("voz", None)):
        assert json.loads(p.atajo_guardar(id_, combo))["ok"] is False, (id_, combo)
    assert len([c for c in at.llamadas if c[0] == "cambiar"]) == n


def test_atajos_activar_capturando_restablecer_y_senal(qapp, config):
    at = Atajos()
    p, _ = montar(config, atajos=at)
    cambios = emisiones(p.atajos_cambio)
    p.atajos_activar(False)
    p.atajos_capturando(True)
    p.atajos_capturando(False)
    assert json.loads(p.atajos_restablecer())["ok"]
    assert at.llamadas == [("activar", False), ("capturando", True), ("capturando", False), ("restablecer",)]
    at.cambio.emit("[]")
    assert len(cambios) == 1 and json.loads(cambios[0])["lista"][0]["id"] == "mostrar_lune"


def test_atajos_sin_gestor_guardan_en_config(qapp, config):
    p, _ = montar(config)
    assert json.loads(p.atajo_guardar("voz", "ctrl+alt+shift+KeyU"))["ok"]
    lista = {e["id"]: e["combo"] for e in disco(config)["atajos"]["lista"]}
    assert lista["voz"] == "ctrl+alt+shift+u"
    est = json.loads(p.atajos_estado())
    fila = next(f for f in est["lista"] if f["id"] == "voz")
    assert fila["texto"] == "Ctrl+Alt+Shift+U" and fila["disponible"] is False


# ── Radial y bandeja ───────────────────────────────────────────────────────────
def test_radial_estado_y_guardar(qapp, config):
    p, x = montar(config)
    est = json.loads(p.radial_estado())
    assert est["max"] == 10 and est["sonidos"] is True and est["volumen"] == 0.6
    assert est["defecto"][:3] == ["ajustes", "chat", "comentar"]
    assert {a["id"] for a in est["catalogo"]} == {"ajustes", "voz", "dormir", "expresiones", "asistente", "mostrar_lune",
                                                  "bailar", "modo_juego_forzar"}, "solo uso radial y con handler"
    assert ("catalogo", "radial") in x.registro
    r = json.loads(p.radial_guardar('{"principal": ["voz", "voz", "salir", "nada", "ajustes"], "sonidos": false, "volumen": 3}'))
    assert r["ok"] and r["descartados"] == ["nada"], "los duplicados se quitan sin avisar; lo desconocido se avisa"
    assert disco(config)["menu_radial"]["principal"] == ["voz", "salir", "ajustes"]
    assert disco(config)["menu"] == {"sonidos": False, "volumen": 1.0}
    assert ("validar_lista", "radial", 10) in x.registro
    for malo in ('{"principal": ' + json.dumps(["voz"] * 11) + "}", '{"principal": "voz"}', '{"otra": 1}',
                 '{"sonidos": "no"}', '{"volumen": "alto"}', "[]"):
        assert json.loads(p.radial_guardar(malo))["ok"] is False, malo
    assert disco(config)["menu_radial"]["principal"] == ["voz", "salir", "ajustes"]


def test_bandeja_estado_y_guardar(qapp, config):
    p, x = montar(config)
    est = json.loads(p.bandeja_estado())
    assert est["acciones"][0] == "asistente" and est["max"] == 20
    assert "expresiones" not in {a["id"] for a in est["catalogo"]}, "las de solo radial no salen"
    r = json.loads(p.bandeja_guardar('{"acciones": ["voz", "expresiones", "dormir"]}'))
    assert r["ok"] and disco(config)["bandeja"]["acciones"] == ["voz", "dormir"] and r["descartados"] == ["expresiones"]
    for malo in ('{"acciones": "voz"}', '{"acciones": []  , "x": 1}', json.dumps({"acciones": ["voz"] * 21})):
        assert json.loads(p.bandeja_guardar(malo))["ok"] is False


# ── Modo juego ─────────────────────────────────────────────────────────────────
def test_juego_forzar_1_0_menos1_y_nada_mas(qapp, config):
    j = Juego()
    p, _ = montar(config, juego=j)
    for v in (1, 0, -1, 2, -2, True):
        p.juego_forzar(v)
    assert j.forzados == [True, None, False]


def test_juego_estado_sin_rutas_y_senal(qapp, config):
    j = Juego()
    p, _ = montar(config, juego=j)
    estados = emisiones(p.juego_estado)
    j.est = {"activo": True, "motivo": "quns3", "forzado": None, "exe": "D:\\Steam\\steamapps\\common\\Elden\\Elden.EXE"}
    e = json.loads(p.juego_estado_json())
    assert e == {"activo": True, "motivo": "quns3", "forzado": None, "exe": "elden.exe", "disponible": True}
    j.cambio.emit(True, "quns3")
    assert json.loads(estados[0])["exe"] == "elden.exe"


def test_juego_config_y_guardar_validado(qapp, config):
    j, at = Juego(), Atajos()
    p, _ = montar(config, juego=j, atajos=at)
    cfg = json.loads(p.juego_config())
    assert cfg["accion"] == "ocultar" and cfg["fps"] == 0 and cfg["pausar_atajos"] is True
    r = json.loads(p.juego_guardar(json.dumps({"accion": "fondo", "fps": 30, "silenciar": False,
                                               "apps": ["Game.EXE", "otro", "game.exe"], "pausar_atajos": False})))
    assert r["ok"] and r["estado"]["apps"] == ["game.exe", "otro.exe"]
    d = disco(config)
    assert d["juego"]["accion"] == "fondo" and d["juego"]["fps"] == 30 and d["juego"]["silenciar"] is False
    assert d["atajos"]["pausar_en_juegos"] is False
    assert j.recargas == 1 and ("recargar",) in at.llamadas
    for malo in ({"accion": "borrar"}, {"fps": 61}, {"fps": 2.5}, {"apps": ["C:\\x\\juego.exe"]}, {"apps": ["a/b.exe"]},
                 {"apps": "x.exe"}, {"apps": ["x.exe"] * 51}, {"activo": "sí"}, {"otra": 1}):
        assert json.loads(p.juego_guardar(json.dumps(malo)))["ok"] is False, malo
    assert disco(config)["juego"]["accion"] == "fondo" and disco(config)["juego"]["apps"] == ["game.exe", "otro.exe"]


def test_juego_apps_visibles_solo_nombres(qapp, config):
    p, _ = montar(config, apps_visibles=lambda: ["Juego.exe", "C:\\Program Files\\X\\x.exe", "bad*name", "", 5, "juego.exe"])
    assert json.loads(p.juego_apps_visibles()) == ["juego.exe", "x.exe"]
    p2, _ = montar(config, apps_visibles=lambda: 1 / 0)
    assert json.loads(p2.juego_apps_visibles()) == []


# ── Rendimiento y memoria ──────────────────────────────────────────────────────
def test_rendimiento_guarda_y_aplica(qapp, config):
    j = Juego()
    p, x = montar(config, juego=j)
    assert json.loads(p.rendimiento()) == {"fps_max": 60, "siempre_encima": True, "recorte_ram_auto": False, "en_barra_tareas": True}
    r = json.loads(p.rendimiento_guardar('{"fps_max": 30, "siempre_encima": false, "recorte_ram_auto": true, "en_barra_tareas": false}'))
    assert r["ok"] and r["estado"]["fps_max"] == 30
    assert x.esc.asistente.llamadas == [("fps", 30), ("encima", False)]
    assert x.anfitrion.barra == [False] and j.recargas == 1
    d = disco(config)
    assert (d["avatar"]["fps_max"], d["avatar"]["siempre_encima"], d["sistema"]["recorte_ram_auto"],
            d["interfaz"]["en_barra_tareas"]) == (30, False, True, False)
    p.rendimiento_guardar('{"fps_max": 30}')
    assert x.esc.asistente.llamadas == [("fps", 30), ("encima", False)], "sin cambio, no se reaplica"
    for malo in ('{"fps_max": 14}', '{"fps_max": 145}', '{"fps_max": "60"}', '{"siempre_encima": 1}', '{"x": true}'):
        assert json.loads(p.rendimiento_guardar(malo))["ok"] is False, malo


def test_liberar_memoria(qapp, config):
    p, _ = montar(config, recortar=lambda: (512.34, 300.0))
    assert json.loads(p.liberar_memoria()) == {"ok": True, "error": "", "antes": 512.3, "despues": 300.0, "liberado": 212.3}
    for mala in (lambda: 1 / 0, lambda: (float("nan"), 1.0), lambda: "x"):
        assert json.loads(montar(config, recortar=mala)[0].liberar_memoria())["ok"] is False


# ── Navegación ─────────────────────────────────────────────────────────────────
def test_pedir_vista_emite_navegar_solo_con_vistas_validas(qapp, config):
    p, _ = montar(config)
    vistas = emisiones(p.navegar)
    assert p.pedir_vista("settings") and p.pedir_vista("settings#atajos") and p.pedir_vista("chat")
    for mala in ("otra", "settings#<b>", "", None, "javascript:x"):
        assert p.pedir_vista(mala) is False
    assert vistas == ["settings", "settings#atajos", "chat"]


def test_pedir_vista_alarmas_cortes_5_y_6(qapp):
    p = PuenteEscritorio(None, None, {})
    v = []
    p.navegar.connect(v.append)
    assert p.pedir_vista("alarmas") is True and v == ["alarmas"]


# ── Con los módulos reales (contrato con nucleo/acciones_ui y nucleo/tema) ─────
def test_con_modulos_reales_de_nucleo(qapp, config):
    acc = pytest.importorskip("nucleo.acciones_ui")
    tema_mod = pytest.importorskip("nucleo.tema")
    desp = acc.Despachador()
    hechos = []
    desp.registrar("voz", lambda: hechos.append("voz"))
    desp.registrar("expresion", lambda arg: hechos.append(("expresion", arg)))
    ctx = acc.Contexto(modo="normal", render="vrm", asistente_visible=True)
    serv = SimpleNamespace(despachador=desp, tema=None, atajos=None, juego=None, contexto=lambda: ctx)
    esc = SimpleNamespace(estado=Bus(), asistente=None)
    p = PuenteEscritorio(serv, esc, config)
    items = json.loads(p.acciones_catalogo("radial"))
    assert [i["id"] for i in items] == ["voz"] and items[0]["etiqueta"] and "marcado" in items[0]
    assert {i["arg"] for i in json.loads(p.acciones_catalogo("expresiones"))} >= {"happy", "wave"}
    assert p.accion_menu("voz", "") and p.accion_menu("expresion", "sad") and not p.accion_menu("dormir", "")
    assert hechos == ["voz", ("expresion", "sad")]
    est = json.loads(p.radial_estado())
    assert [a["id"] for a in est["catalogo"]] == ["voz"], "solo lo que tiene handler"
    assert json.loads(p.radial_guardar('{"principal": ["voz", "tema", "voz"]}'))["estado"]["principal"] == ["voz"]
    assert set(json.loads(p.tema_estado())["presets"]) == set(tema_mod.PRESETS)
