"""
ui/puente_vida.py (objeto `vida` del QWebChannel, window.luneVida), cortes 7 y 8.

Con dobles de ControlAsiento, ControlComida y ControlDiscord (QObject con sus señales) y un
módulo de autoinicio falso:
  · validación estricta de cada ranura (JSON ≤ 16 KB, claves conocidas, tipos, enums y
    rangos: sitio, ids exactos del catálogo, offset −64..64, Application ID de 17–20 cifras,
    https ≤ 512 B, como y retraso 0–120) y rechazo sin tocar la config;
  · sin servicios: estado por defecto y la config se lee y se guarda igual (Config real en tmp);
  · servicios tardíos (enlazar con ServiciosCorte4.vida, ServiciosVida o el escritorio),
    señales reemitidas normalizadas y soltarse al desmontar;
  · PRIVACIDAD de Discord: «Discord ve» solo con los textos fijos (con la presencia de
    verdad, todos pasan; un título de ventana, nunca).
"""
import json
import os
from types import SimpleNamespace
from typing import List

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QObject, pyqtSignal  # noqa: E402

from nucleo.config import Config  # noqa: E402
from ui import puente_vida as pv  # noqa: E402
from ui.puente_vida import PuenteVida, registrar_puente_vida  # noqa: E402

ID = "123456789012345678"


@pytest.fixture(scope="module", autouse=True)
def _app():
    from PyQt6.QtCore import QCoreApplication
    app = QCoreApplication.instance() or QCoreApplication([])
    yield app


@pytest.fixture
def cfg(tmp_path):
    return Config(str(tmp_path / "config.json"))


def cap(senal) -> List[str]:
    out: List[str] = []
    senal.connect(out.append)
    return out


class AsientoFalso(QObject):
    cambio = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.llamadas = []
        self.sentada = ""
        self.texto = "Me senté en la barra de tareas.\x07"

    def estado(self):
        return {"sentada": self.sentada, "variante": 2 if self.sentada else 0, "ventanas": "x", "barra": True,
                "offset": 999, "disponible": True, "juego": False, "arrastrando": False, "cedida": False}

    def sentar(self, sitio):
        self.llamadas.append(("sentar", sitio))
        self.sentada = sitio
        return True, self.texto

    def bajar(self, motivo="usuario"):
        self.llamadas.append(("bajar",))
        estaba, self.sentada = bool(self.sentada), ""
        return estaba

    def recargar_config(self):
        self.llamadas.append(("recargar",))


class ComidaFalsa(QObject):
    cambio = pyqtSignal(str)
    comida_web = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.llamadas = []
        self.act = None
        self.ultimo_motivo = ""
        self.respuesta = None

    def estado(self):
        a = self.act
        return {"activa": a is not None, "id": a[0] if a else "", "variante": a[1] if a else "",
                "color": "red; background:url(x)" if a else "", "tipo": "beber" if a else "",
                "vista": "web" if a else "", "disponible": True}

    def alternar(self, id_):
        self.llamadas.append(("alternar", id_))
        if self.respuesta is not None:
            return self.respuesta
        self.act = None if self.act and self.act[0] == id_ else (id_, "mango")
        return "aparece" if self.act else "guarda"

    def guardar(self, sonido=True):
        self.llamadas.append(("guardar",))
        estaba, self.act = self.act is not None, None
        return estaba

    def acierto_web(self, id_):
        self.llamadas.append(("acierto", id_))
        return True

    def recargar_config(self):
        self.llamadas.append(("recargar",))


class DiscordFalso(QObject):
    estado_cambio = pyqtSignal(str)

    def __init__(self, config=None):
        super().__init__()
        self.config = config
        self.llamadas = []
        self.e = {"conectado": False, "usuario": "", "error": "", "publicando": None, "vista_previa": None}

    @property
    def activo(self):
        return bool(self.config.get("discord", "activo", False)) if self.config is not None else False

    def estado(self):
        return {**self.e, "activo": self.activo}

    def alternar(self):
        self.llamadas.append(("alternar",))
        nuevo = not self.activo
        self.config.set("discord", "activo", nuevo)
        return nuevo

    def recargar_config(self):
        self.llamadas.append(("recargar",))


class AutoinicioFalso:
    def __init__(self, **e):
        self.e = {"activo": False, "registrado": False, "aprobado": True, "ruta_ok": False, "modo_ok": False,
                  "comando": "wscript.exe \"C:\\Users\\alguien\\Lune\\iniciar_lune.vbs\" /autoinicio",
                  "esperado": "x", **e}
        self.modos = []

    def estado(self, modo=None, reg=None):
        self.modos.append(modo)
        return dict(self.e)


def puente(cfg=None, **kw):
    kw.setdefault("autoinicio", AutoinicioFalso())
    return PuenteVida(config=cfg, **kw)


def servicios(cfg=None):
    vida = SimpleNamespace(asiento=AsientoFalso(), comida=ComidaFalsa(), discord=DiscordFalso(cfg), _deshacer=[])
    return SimpleNamespace(vida=vida, escritorio=None, _deshacer=[])


# ── Sin servicios ─────────────────────────────────────────────────────────────

def test_sin_servicios_estado_por_defecto(cfg):
    p = puente(cfg)
    a = json.loads(p.asiento_estado())
    assert a == {"sentada": "", "variante": 0, "ventanas": False, "barra": True, "offset": 0, "servicio": False,
                 "asistente": False, "juego": False, "arrastrando": False, "cedida": False}
    c = json.loads(p.comida_estado())
    assert c["activa"] is False and c["disponible"] is True and c["servicio"] is False and c["vista"] == ""
    assert [x["id"] for x in c["catalogo"]] == ["batido", "pastel"]
    assert all(v["color"].startswith("#") for x in c["catalogo"] for v in x["variantes"])
    d = json.loads(p.discord_estado())
    assert d["activo"] is False and d["servicio"] is False and d["vista_previa"] is None
    assert d["config"] == {"client_id": "", "mostrar_modelo": False, "boton_url": ""}
    r = json.loads(p.asiento_sentar("barra"))
    assert r["ok"] is False and "app" in r["texto"]
    assert p.asiento_bajar() is False and p.comida_guardar() is False and p.comida_evento("batido") is False
    assert json.loads(p.comida_alternar("batido"))["motivo"] == "sin_servicio"


def test_sin_servicios_la_config_se_guarda_igual(cfg):
    p = puente(cfg)
    r = json.loads(p.asiento_config_guardar(json.dumps({"ventanas": True, "offset": -12})))
    assert r["ok"] and r["estado"]["ventanas"] is True and r["estado"]["offset"] == -12
    assert Config(cfg.config_path).get("avatar", "sentarse_ventanas") is True
    assert Config(cfg.config_path).get("avatar", "sentarse_offset_px") == -12
    assert json.loads(p.comida_config_guardar('{"activa": false}'))["estado"]["disponible"] is False
    assert Config(cfg.config_path).get("comida", "activa") is False
    assert p.discord_alternar() is True and cfg.get("discord", "activo") is True
    assert p.discord_alternar() is False


# ── Validación ────────────────────────────────────────────────────────────────

MALOS_ASIENTO = ["", "x", "[]", "null", '{"ventanas": 1}', '{"barra": "true"}', '{"offset": 65}', '{"offset": -65}',
                 '{"offset": 3.5}', '{"offset": true}', '{"offset": "3"}', '{"otra": true}', '{"offset": NaN}',
                 "{" + '"offset": 1,' * 5000 + '"barra": true}']


@pytest.mark.parametrize("payload", MALOS_ASIENTO, ids=range(len(MALOS_ASIENTO)))
def test_asiento_config_rechaza(cfg, payload):
    s = servicios(cfg)
    p = puente(cfg)
    p.enlazar(s)
    r = json.loads(p.asiento_config_guardar(payload))
    assert r["ok"] is False and r["error"]
    assert ("recargar",) not in s.vida.asiento.llamadas
    assert cfg.get("avatar", "sentarse_offset_px") == 0 and cfg.get("avatar", "sentarse_ventanas") is False


def test_asiento_config_guarda_solo_lo_que_cambia_y_aplica(cfg):
    s = servicios(cfg)
    p = puente(cfg)
    p.enlazar(s)
    visto = cap(p.asiento_cambio)
    sets = []
    real = cfg.set
    cfg.set = lambda *a: (sets.append(a), real(*a))
    r = json.loads(p.asiento_config_guardar(json.dumps({"barra": True, "offset": 64.0, "ventanas": False})))
    assert r["ok"] and sets == [("avatar", "sentarse_offset_px", 64)]           # barra y ventanas ya estaban
    assert ("recargar",) in s.vida.asiento.llamadas
    assert json.loads(visto[-1])["offset"] == 64


def test_asiento_sentar_y_bajar(cfg):
    s = servicios(cfg)
    p = puente(cfg)
    p.enlazar(s)
    for malo in ("", "bajar", "BARRA", "ventana ", "<b>"):
        assert json.loads(p.asiento_sentar(malo))["ok"] is False, malo
    assert s.vida.asiento.llamadas == []
    r = json.loads(p.asiento_sentar("barra"))
    assert r["ok"] is True and r["texto"] == "Me senté en la barra de tareas."            # sin el \x07
    assert r["estado"]["sentada"] == "barra" and r["estado"]["variante"] == 2
    # lo que da el controlador se normaliza (ventanas y offset, de la config)
    assert r["estado"]["ventanas"] is False and r["estado"]["offset"] == 0 and r["estado"]["asistente"] is True
    assert p.asiento_bajar() is True and p.asiento_bajar() is False


@pytest.mark.parametrize("malo", ["", "Batido", "tarta", "batido ", "comida", "__proto__", "x" * 500])
def test_comida_ids_exactos_del_catalogo(cfg, malo):
    s = servicios(cfg)
    p = puente(cfg)
    p.enlazar(s)
    assert json.loads(p.comida_alternar(malo))["ok"] is False
    assert p.comida_evento(malo) is False
    assert s.vida.comida.llamadas == []


def test_comida_alternar_evento_guardar_y_motivos(cfg):
    s = servicios(cfg)
    p = puente(cfg)
    p.enlazar(s)
    r = json.loads(p.comida_alternar("batido"))
    assert r["ok"] and r["accion"] == "aparece"
    e = r["estado"]
    assert (e["activa"], e["id"], e["variante"], e["tipo"], e["vista"]) == (True, "batido", "mango", "beber", "web")
    assert e["color"] == "#FFB547", "el color sale del catálogo, no de lo que diga el controlador"
    assert p.comida_evento("batido") is True and ("acierto", "batido") in s.vida.comida.llamadas
    assert p.comida_guardar() is True
    c = s.vida.comida
    c.respuesta, c.ultimo_motivo = "", "desactivada"
    r = json.loads(p.comida_alternar("pastel"))
    assert r["ok"] is False and r["texto"] == "La comida está desactivada."
    c.ultimo_motivo = "juego"
    assert json.loads(p.comida_alternar("pastel"))["texto"].startswith("Ahora no puedo comer")
    c.ultimo_motivo = "<img src=x>"
    r = json.loads(p.comida_alternar("pastel"))
    assert r["motivo"] == "" and r["texto"] == "Ahora no puedo comer."


def test_comida_config(cfg):
    s = servicios(cfg)
    p = puente(cfg)
    p.enlazar(s)
    for malo in ("{}", '{"activa": 0}', '{"activa": true, "catalogo_extra": []}'):
        assert json.loads(p.comida_config_guardar(malo))["ok"] is False
    assert json.loads(p.comida_config_guardar('{"activa": false}'))["ok"] is True
    assert cfg.get("comida", "activa") is False and ("recargar",) in s.vida.comida.llamadas


def test_comida_web_reemitida_con_el_catalogo(cfg):
    s = servicios(cfg)
    p = puente(cfg)
    p.enlazar(s)
    visto = cap(p.comida_web)
    c = s.vida.comida
    c.comida_web.emit(json.dumps({"accion": "aparece", "id": "pastel", "variante": "limon",
                                  "color": "url(javascript:x)", "tipo": "beber", "nombre": "<b>x</b>"}))
    assert json.loads(visto[-1]) == {"accion": "aparece", "id": "pastel", "variante": "limon", "color": "#FFE45C",
                                     "tipo": "comer", "nombre": "Pastel"}
    c.comida_web.emit(json.dumps({"accion": "guarda", "id": "batido", "variante": "nada"}))
    assert json.loads(visto[-1])["variante"] == "fresa"                 # la primera si no existe
    n = len(visto)
    for malo in ("no json", json.dumps({"accion": "borrar", "id": "batido"}), json.dumps({"accion": "aparece", "id": "x"})):
        c.comida_web.emit(malo)
    assert len(visto) == n, "lo que no vale no llega a la página"


def test_discord_config_valida(cfg):
    s = servicios(cfg)
    p = puente(cfg)
    p.enlazar(s)
    malos = ['{"client_id": "12345678901234567a"}', '{"client_id": "1234567890123456"}',
             '{"client_id": "123456789012345678901"}', '{"client_id": 123456789012345678}',
             '{"boton_url": "http://lune.example.com"}', '{"boton_url": "javascript:alert(1)"}',
             '{"boton_url": "https://sinpunto"}', '{"boton_url": "https://a.b/x y"}',
             json.dumps({"boton_url": "https://lune.example.com/" + "a" * 500}),
             '{"activo": "si"}', '{"usuario": "x"}', "{}"]
    for m in malos:
        r = json.loads(p.discord_config_guardar(m))
        assert r["ok"] is False and r["error"], m
    assert s.vida.discord.llamadas == []
    assert cfg.get("discord", "client_id") == "" and cfg.get("discord", "boton_url") == ""
    visto = cap(p.discord_cambio)
    r = json.loads(p.discord_config_guardar(json.dumps({"client_id": f"  {ID} ", "boton_url": "https://lune.example.com/x",
                                                        "mostrar_modelo": True, "activo": True})))
    assert r["ok"], r
    assert cfg.get("discord", "client_id") == ID and cfg.get("discord", "boton_url") == "https://lune.example.com/x"
    assert r["estado"]["config"] == {"client_id": ID, "mostrar_modelo": True, "boton_url": "https://lune.example.com/x"}
    assert r["estado"]["client_id_ok"] and not r["estado"]["sin_id"]
    assert ("recargar",) in s.vida.discord.llamadas and visto
    assert json.loads(p.discord_config_guardar('{"client_id": ""}'))["ok"] and cfg.get("discord", "client_id") == ""
    assert json.loads(p.discord_estado())["sin_id"] is True             # activo sin id: D1


def test_discord_privacidad_solo_textos_fijos(cfg):
    s = servicios(cfg)
    p = puente(cfg)
    p.enlazar(s)
    cfg.set("discord", "activo", True)
    d = s.vida.discord
    d.e = {"conectado": True, "usuario": "diego\x1b[31m", "error": "",
           "publicando": {"details": "Lune CD · Ventana", "state": "YouTube - Google Chrome"},
           "vista_previa": {"details": "Lune CD · Escritorio · 3D", "state": "Bailando ♪", "large_text": "C:\\secreto"}}
    e = json.loads(p.discord_estado())
    assert e["publicando"] is None, "un título de ventana nunca llega a la tarjeta"
    assert e["vista_previa"] == {"details": "Lune CD · Escritorio · 3D", "state": "Bailando ♪"}
    assert e["usuario"] == "diego[31m"
    for malo in ({"details": "Spotify · Lune CD", "state": "Charlando"}, {"details": "Lune CD · Ventana"},
                 {"details": "Lune CD · Ventana", "state": "Charlando con Ana"}, "Lune CD · Ventana", None):
        assert pv.publicacion_segura(malo) is None, malo
    d.e = {**d.e, "conectado": False, "publicando": {"details": "Lune CD · Ventana", "state": "Charlando"}}
    assert json.loads(p.discord_estado())["publicando"] is None, "sin conexión no publica nada"


def test_discord_ve_con_la_presencia_de_verdad():
    """Todo lo que construye servicios/discord_presencia pasa la lista fija; la foto con cosas privadas no las filtra."""
    from servicios import discord_presencia as dp
    cfg = {"discord": {"mostrar_modelo": True, "boton_url": "https://lune.example.com"}}
    base = {"render": "", "visible": False, "juego": False}
    fotos = []
    for render, visible in (("vrm", True), ("animado", True), ("sprites", True), ("carita", True), ("", False)):
        for campo in ("alarma", "grande", "salvapantallas", "llamada", "arrastrando", "comiendo", "durmiendo",
                      "pensando", "hablando", None):
            f = {**base, "render": render, "visible": visible, "modelo": "C:\\Users\\x\\secreto.vrm",
                 "titulo_ventana": "Banco - Chrome", "app_musica": "Spotify", "personaje": "Ana"}
            if campo:
                f[campo] = True
            fotos.append(f)
        fotos.append({**base, "render": render, "visible": visible, "bailando": "musica"})
        fotos.append({**base, "render": render, "visible": visible, "sentada": "barra"})
        fotos.append({**base, "render": render, "visible": visible, "sentada": "ventana", "durmiendo": True})
    for modo in ("normal", "br", "patata"):
        for f in fotos:
            act = dp.actividad_de({**f, "modo": modo}, config=cfg, inicio_ms=0)
            vp = {"details": act["details"], "state": act["state"]}
            assert pv.publicacion_segura(vp) == vp, vp
    assert dp.actividad_de({**base, "juego": True, "modo": "normal"}, config=cfg, inicio_ms=0) is None
    assert pv.estados_discord() == frozenset(t for _, t in dp.ESTADOS)


def test_discord_alternar_con_controlador(cfg):
    s = servicios(cfg)
    p = puente(cfg)
    p.enlazar(s)
    visto = cap(p.discord_cambio)
    assert p.discord_alternar() is True and ("alternar",) in s.vida.discord.llamadas
    assert json.loads(visto[-1])["activo"] is True


def test_url_boton_valida_como_discord_presencia():
    from servicios.discord_presencia import url_boton
    casos = ["https://lune.example.com", "https://lune.example.com/a?b=c#d", "http://lune.example.com", "https://x",
             "https://a.b/ c", "ftp://a.b", "https://a.b/<x>", "https://" + "a" * 600 + ".com", " https://a.b", ""]
    for u in casos:
        assert pv.url_boton_valida(u) == (bool(u) and url_boton(u) == u), u


# ── Autoinicio ────────────────────────────────────────────────────────────────

def test_autoinicio_estado_con_el_modo_de_la_config(cfg):
    auto = AutoinicioFalso(registrado=True, aprobado=False, ruta_ok=True, modo_ok=True)
    cfg.set("interfaz", "modo", "patata")
    cfg.set("sistema", "autoinicio_como", "raro")
    cfg.set("sistema", "autoinicio_retraso_s", 45)
    p = puente(cfg, autoinicio=auto)
    e = json.loads(p.autoinicio_estado())
    assert e == {"activo": False, "registrado": True, "aprobado": False, "ruta_ok": True, "modo_ok": True,
                 "como": "bandeja", "retraso_s": 45, "disponible": True}
    assert auto.modos == ["patata"], "el modo de la config, no el config.json del disco"
    assert "comando" not in e and "esperado" not in e, "sin rutas de la carpeta del usuario"


@pytest.mark.parametrize("malo", ['{"como": "escritorio"}', '{"retraso_s": 121}', '{"retraso_s": -1}',
                                  '{"retraso_s": 5.5}', '{"retraso_s": true}', '{"activo": true}', '[]', ""])
def test_autoinicio_opciones_rechaza(cfg, malo):
    p = puente(cfg)
    r = json.loads(p.autoinicio_opciones(malo))
    assert r["ok"] is False and r["error"]
    assert cfg.get("sistema", "autoinicio_como") == "bandeja" and cfg.get("sistema", "autoinicio_retraso_s") == 20


def test_autoinicio_opciones_guarda(cfg):
    p = puente(cfg)
    visto = cap(p.autoinicio_cambio)
    r = json.loads(p.autoinicio_opciones(json.dumps({"como": "asistente", "retraso_s": 120})))
    assert r["ok"] and r["estado"]["como"] == "asistente" and r["estado"]["retraso_s"] == 120
    assert Config(cfg.config_path).get("sistema", "autoinicio_como") == "asistente"
    assert json.loads(visto[-1])["retraso_s"] == 120
    assert json.loads(p.autoinicio_opciones('{"retraso_s": 0}'))["estado"]["retraso_s"] == 0


# ── Enlazar, señales y canal ─────────────────────────────────────────────────

def test_servicios_tardios_y_senales_reemitidas(cfg):
    p = puente(cfg)
    a, c, d = cap(p.asiento_cambio), cap(p.comida_cambio), cap(p.discord_cambio)
    s = servicios(cfg)
    p.enlazar(s)
    assert p.asiento is s.vida.asiento and p.comida is s.vida.comida and p.discord is s.vida.discord
    assert json.loads(a[-1])["servicio"] is True and json.loads(c[-1])["servicio"] is True
    assert json.loads(d[-1])["servicio"] is True
    assert "catalogo" not in json.loads(c[-1])
    n = len(a)
    s.vida.asiento.sentada = "ventana"
    s.vida.asiento.cambio.emit("{}")
    assert len(a) == n + 1 and json.loads(a[-1])["sentada"] == "ventana"
    s.vida.comida.act = ("pastel", "chocolate")
    s.vida.comida.cambio.emit("{}")
    assert json.loads(c[-1])["id"] == "pastel"
    s.vida.discord.estado_cambio.emit("{}")
    assert len(d) >= 2
    # soltar: las señales viejas ya no llegan
    p.enlazar(None)
    n = len(a)
    s.vida.asiento.cambio.emit("{}")
    assert len(a) == n and p.asiento is None
    assert json.loads(a[-1])["servicio"] is False


def test_desmontar_suelta_los_controladores(cfg):
    s = servicios(cfg)
    p = puente(cfg)
    p.enlazar(s)
    p.enlazar(s)                                          # otra vez: un solo enganche
    assert len(s._deshacer) == 1
    for f in reversed(s._deshacer):
        f()
    assert p.asiento is None and p.comida is None and p.discord is None


def test_con_un_serviciosvida_o_el_escritorio(cfg):
    s = servicios(cfg)
    p = puente(cfg)
    p.enlazar(s.vida)
    assert p.comida is s.vida.comida and len(s.vida._deshacer) == 1
    registrados = {"asiento": AsientoFalso(), "comida": ComidaFalsa(), "discord": DiscordFalso(cfg)}
    s4 = SimpleNamespace(vida=None, escritorio=SimpleNamespace(obtener=registrados.get), _deshacer=[])
    p.enlazar(s4)
    assert p.asiento is registrados["asiento"] and p.discord is registrados["discord"]


def test_registrar_en_el_canal_y_cerrar(cfg):
    class Canal:
        def __init__(self):
            self.objetos = {}

        def registerObject(self, n, o):
            self.objetos[n] = o

        def deregisterObject(self, o):
            self.objetos = {k: v for k, v in self.objetos.items() if v is not o}
    canal = Canal()
    s = servicios(cfg)
    p = registrar_puente_vida(canal, cfg, s, autoinicio=AutoinicioFalso())
    assert canal.objetos == {"vida": p} and p.comida is s.vida.comida
    p.cerrar()
    p.cerrar()                                            # idempotente
    assert canal.objetos == {} and p.comida is None
    p.enlazar(s)                                          # cerrado: no vuelve a enganchar
    assert p.comida is None
    assert json.loads(p.asiento_estado())["servicio"] is False
