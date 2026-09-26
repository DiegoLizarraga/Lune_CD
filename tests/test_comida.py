"""
Tests de nucleo/comida.py (sin Qt): el catálogo, alternar (aparece, guarda y
CAMBIA, que corrige a Mate-Engine), el acierto segmento-círculo por flanco con
0.35 s de enfriamiento, la reacción (tono 0.65–1.25, trago/mordisco), el
balanceo con los valores de la escena (topes 25°/10°, signo, sobrepaso ≈31 %
con ζ 0.35, mezcla de 8/s), la comida que se guarda sola a los 2 min (D4), los
sonidos por el Mezclador (pack, volumen, silencio en juego) y la herramienta
`dar_de_comer`.
"""
import math
import random
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo import comida as nc  # noqa: E402
from nucleo.fisica import sobrepaso_teorico  # noqa: E402


class Reloj:
    def __init__(self, t: float = 100.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


class Config:
    def __init__(self, **secciones):
        self.d = {"avatar": {"volumen_sfx": 0.7, "pack_sonidos": "default"},
                  "juego": {"silenciar": True}, "comida": {"activa": True}}
        for sec, vals in secciones.items():
            self.d.setdefault(sec, {}).update(vals)

    def get(self, sec, clave, defecto=None):
        return self.d.get(sec, {}).get(clave, defecto)

    def set(self, sec, clave, valor):
        self.d.setdefault(sec, {})[clave] = valor


class MezcladorFalso:
    def __init__(self):
        self.sonados = []

    def cargar_audio(self, ruta):
        return Path(ruta)

    def reproducir(self, buf, vol=1.0, velocidad=1.0, bucle=False, canal=None):
        self.sonados.append({"archivo": Path(buf).name, "vol": vol, "velocidad": velocidad, "canal": canal})
        return len(self.sonados)


def gestor(semilla=1, t=100.0):
    reloj = Reloj(t)
    return nc.GestorComida(azar=random.Random(semilla), reloj=reloj), reloj


# ── Catálogo ─────────────────────────────────────────────────────────────────────

def test_catalogo_batido_y_pastel_con_sus_variantes():
    assert list(nc.CATALOGO) == ["batido", "pastel"]
    b, p = nc.CATALOGO["batido"], nc.CATALOGO["pastel"]
    assert (b.tipo, p.tipo) == ("beber", "comer")
    assert [(v.id, v.color) for v in b.variantes] == [
        ("fresa", "#FF6FA8"), ("mango", "#FFB547"), ("matcha", "#8BC34A")]
    assert [(v.id, v.color) for v in p.variantes] == [
        ("chocolate", "#6B3E26"), ("fresa", "#FF8FB1"), ("limon", "#FFE45C"), ("vainilla", "#FFF1C9")]
    for c in nc.CATALOGO.values():
        for v in c.variantes:
            assert re.fullmatch(r"#[0-9A-F]{6}", v.color) and v.nombre == v.nombre.lower()
    assert (nc.APARECER_S, nc.GUARDAR_S, nc.COOLDOWN_S, nc.TONO, nc.GUARDAR_SOLA_S) == (
        0.25, 0.20, 0.35, (0.65, 1.25), 120)


def test_catalogo_para_web():
    web = nc.catalogo_para_web()
    assert [c["id"] for c in web] == ["batido", "pastel"]
    assert web[0] == {"id": "batido", "nombre": "Batido", "tipo": "beber", "variantes": [
        {"id": "fresa", "nombre": "fresa", "color": "#FF6FA8"},
        {"id": "mango", "nombre": "mango", "color": "#FFB547"},
        {"id": "matcha", "nombre": "matcha", "color": "#8BC34A"}]}
    assert web[1]["variantes"][2] == {"id": "limon", "nombre": "limón", "color": "#FFE45C"}


def test_alias_y_variantes():
    assert nc.normalizar_id(" Tarta ") == "pastel" and nc.normalizar_id("SMOOTHIE") == "batido"
    assert nc.normalizar_id("pizza") is None and nc.normalizar_id(None) is None
    assert nc.variante_de("pastel", "LIMÓN").nombre == "limón"
    assert nc.variante_de("batido", "no-existe").id == "fresa"           # cae en la primera
    assert nc.variante_exacta("batido", "no-existe") is None
    assert nc.variante_exacta("pastel", "Limon").id == "limon"


# ── Alternar ─────────────────────────────────────────────────────────────────────

def test_alternar_aparece_guarda_y_cambia():
    g, _ = gestor()
    assert g.activa is None
    assert g.alternar("batido") == nc.APARECE
    assert g.activa[0] == "batido" and g.activa[1] in {"fresa", "mango", "matcha"}
    # Pedir OTRA la cambia (Mate-Engine la guardaba: ToggleById → DespawnActive)
    assert g.alternar("pastel") == nc.CAMBIA
    assert g.activa[0] == "pastel" and g.ultima == "pastel"
    # Pedir la misma la guarda
    assert g.alternar("tarta") == nc.GUARDA
    assert g.activa is None and g.ultima == "pastel"
    assert g.guardar() is False
    with pytest.raises(ValueError):
        g.alternar("pizza")


def test_mostrar_con_variante_y_variantes_al_azar():
    g, _ = gestor(semilla=3)
    assert g.mostrar("pastel", "limon") == nc.APARECE and g.activa == ("pastel", "limon")
    assert g.mostrar("pastel") == nc.CAMBIA and g.activa[1] != "limon"      # otra variante
    vistos = set()
    for _ in range(60):
        g.guardar()
        g.mostrar("batido")
        vistos.add(g.activa[1])
    assert vistos == {"fresa", "mango", "matcha"}


# ── Acierto ──────────────────────────────────────────────────────────────────────

def test_segmento_circulo_pasada_rapida_cuenta_y_tangente_no():
    c, r = (0, 0), 10
    assert nc.segmento_toca_circulo((-100, 0), (100, 0), c, r)              # cruza entero en un paso
    assert nc.segmento_toca_circulo((-100, 9), (100, 9), c, r)
    assert not nc.segmento_toca_circulo((-100, 10), (100, 10), c, r)        # tangente
    assert not nc.segmento_toca_circulo((-100, 30), (100, 30), c, r)
    assert not nc.segmento_toca_circulo((20, -50), (20, 50), c, r)
    assert not nc.segmento_toca_circulo((-100, 0), (-20, 0), c, r)          # se queda antes
    assert nc.segmento_toca_circulo((3, 3), (3, 3), c, r)                   # quieto dentro
    assert not nc.segmento_toca_circulo((30, 3), (30, 3), c, r)
    assert not nc.segmento_toca_circulo((0, 0), (1, 1), c, 0)
    assert not nc.segmento_toca_circulo((0, float("nan")), (1, 1), c, r)


def test_acierto_por_flanco_con_enfriamiento():
    g, _ = gestor()
    cab = (500, 300, 40)
    assert not g.al_mover(1.0, (0, 0), (10, 0), cab)                         # sin comida
    g.mostrar("batido")
    assert not g.al_mover(1.0, (100, 300), (200, 300), cab)                  # lejos
    assert g.al_mover(1.1, (300, 300), (700, 300), cab)                      # pasada rápida
    assert not g.al_mover(1.2, (700, 300), (800, 300), cab)                  # ya fuera
    # entra y se queda dentro: un solo acierto
    assert g.al_mover(2.0, (400, 300), (490, 300), cab)
    assert not g.al_mover(2.1, (490, 300), (505, 305), cab)
    assert not g.al_mover(2.2, (505, 305), (505, 305), cab)
    assert not g.al_mover(2.3, (505, 305), (600, 300), cab)                  # sale
    assert g.al_mover(2.4, (600, 300), (500, 300), cab)                      # y vuelve a entrar: cuenta
    # sale y vuelve a entrar antes de 0.35 s: no cuenta (y la entrada se gasta)
    g2, _ = gestor()
    g2.mostrar("pastel")
    assert g2.al_mover(5.0, (400, 300), (500, 300), cab)
    assert not g2.al_mover(5.1, (500, 300), (600, 300), cab)
    assert not g2.al_mover(5.2, (600, 300), (500, 300), cab)                 # 0.2 s: enfriándose
    assert not g2.al_mover(5.4, (500, 300), (505, 300), cab)                 # sigue dentro: sin flanco
    assert not g2.al_mover(5.5, (505, 300), (650, 300), cab)
    assert g2.al_mover(5.6, (650, 300), (500, 300), cab)                     # pasado el enfriamiento
    # la cabeza que llega hasta el cursor quieto también cuenta
    assert not g2.al_mover(7.0, (100, 100), (100, 100), (500, 300, 40))
    assert g2.al_mover(7.1, (100, 100), (100, 100), (110, 100, 40))
    assert not g2.al_mover(7.2, (100, 100), (100, 100), (110, 100, 40))
    # sin cabeza (o cabeza rota) no hay acierto
    assert not g2.al_mover(9.0, (0, 300), (900, 300), None)
    assert not g2.al_mover(9.5, (0, 300), (900, 300), (1, 2))


def test_acierto_externo_solo_con_enfriamiento():
    g, reloj = gestor()
    assert not g.acierto(1.0)
    g.mostrar("batido")
    assert g.acierto(1.0) and not g.acierto(1.2) and g.acierto(1.36)


def test_se_guarda_sola_a_los_dos_minutos_sin_moverla():
    g, reloj = gestor(t=10.0)
    g.mostrar("batido")
    assert not g.caducada(10.0 + 119.9)
    g.al_mover(60.0, (5, 5), (5, 5), None)                                   # quieta: no cuenta
    assert g.caducada(130.0)
    g.al_mover(100.0, (5, 5), (6, 5), None)                                  # la mueve
    assert not g.caducada(219.0) and g.caducada(220.0)
    reloj.t = 400.0
    assert g.caducada()
    g.guardar()
    assert not g.caducada()


# ── Reacción ─────────────────────────────────────────────────────────────────────

def test_reaccion_trago_para_beber_y_mordisco_para_comer():
    g, _ = gestor(semilla=7)
    g.mostrar("batido", "mango")
    r = g.reaccion()
    assert (r.tipo, r.estado, r.ms, r.id, r.variante) == ("beber", "happy", 2500, "batido", "mango")
    assert re.fullmatch(r"trago_[123]", r.sonido) and r.indice == int(r.sonido[-1]) - 1
    assert r.texto == "*glup glup* (batido de mango)"
    p = g.reaccion("pastel", "limon")
    assert p.tipo == "comer" and re.fullmatch(r"mordisco_[123]", p.sonido)
    assert p.texto == "*ñam ñam* (pastel de limón)"
    # sin variante (o una que no existe) y otra comida en la mano: una al azar
    assert g.reaccion("pastel", "xx").variante in {v.id for v in nc.CATALOGO["pastel"].variantes}
    assert nc.GestorComida().reaccion().id == "batido"


def test_tono_entre_065_y_125_con_semilla():
    g1, _ = gestor(semilla=42)
    g2, _ = gestor(semilla=42)
    t1 = [g1.reaccion("batido").tono for _ in range(400)]
    t2 = [g2.reaccion("batido").tono for _ in range(400)]
    assert t1 == t2
    assert all(0.65 <= t <= 1.25 for t in t1)
    assert min(t1) < 0.7 and max(t1) > 1.2                                   # cubre el rango
    assert {g1.reaccion("pastel").sonido for _ in range(60)} == {"mordisco_1", "mordisco_2", "mordisco_3"}


def test_textos():
    assert nc.texto_terminal("batido", "mango") == "Lune (^o^)~ *glup glup* (batido de mango)"
    assert nc.texto_terminal("pastel", "fresa", kaomoji=True, nombre="Aria") == \
        "Aria (っ˘ڡ˘ς) *ñam ñam* (pastel de fresa)"
    assert nc.texto_terminal("pizza") == "" and nc.texto_reaccion("pizza") == ""
    assert nc.motivo_legible("juego") == "hay un juego delante"


# ── Balanceo ─────────────────────────────────────────────────────────────────────

def test_balanceo_signo():
    dt = 1 / 60
    b = nc.BalanceoComida()
    for _ in range(30):
        l, c = b.paso(dt, 4, 0)
    assert l > 1 and abs(c) < 1e-9                   # a la derecha: se inclina a la derecha (horario)
    b = nc.BalanceoComida()
    for _ in range(30):
        l, c = b.paso(dt, -4, 0)
    assert l < -1
    b = nc.BalanceoComida()
    for _ in range(30):
        l, c = b.paso(dt, 0, -2)
    assert c > 0.5 and abs(l) < 1e-9                 # hacia arriba: la parte de arriba se aleja
    b = nc.BalanceoComida()
    for _ in range(30):
        l, c = b.paso(dt, 0, 2)
    assert c < -0.5


def test_balanceo_topes_y_sobrepaso_de_la_escena():
    dt = 1 / 60
    b = nc.BalanceoComida()
    hist = [b.paso(dt, 200, -200) for _ in range(600)]                 # muy deprisa: satura
    ladeos = [h[0] for h in hist]
    cabeceos = [h[1] for h in hist]
    assert hist[-1][0] == pytest.approx(25.0, abs=0.05)                 # tope 25°
    assert hist[-1][1] == pytest.approx(10.0, abs=0.05)                 # tope 10°
    sobre = max(ladeos) / 25.0 - 1.0
    assert sobre == pytest.approx(sobrepaso_teorico(0.35), abs=0.03)     # ≈31 % con ζ 0.35
    assert max(cabeceos) / 10.0 - 1.0 == pytest.approx(sobre, abs=0.01)
    # igual a otra frecuencia de pasos (la velocidad se normaliza a 60 Hz)
    b2 = nc.BalanceoComida()
    for _ in range(300):
        l2, _c = b2.paso(1 / 30, 400, 0)
    assert l2 == pytest.approx(25.0, abs=0.05)


def test_balanceo_mezcla_de_8_por_segundo_y_reinicio():
    b = nc.BalanceoComida()
    b.paso(1 / 32, 3, 0)
    assert b.peso == pytest.approx(0.25)
    b.paso(1 / 32, 3, 0)
    assert b.peso == pytest.approx(0.5)
    for _ in range(4):
        b.paso(1 / 32, 3, 0)
    assert b.peso == 1.0
    b.reiniciar()
    assert (b.peso, b.ladeo, b.cabeceo) == (0.0, 0.0, 0.0)
    assert b.paso(0, 50, 50) == (0.0, 0.0) and b.paso(float("nan"), 1, 1) == (0.0, 0.0)
    # quieto tras moverse: vuelve a 0 (amortiguado)
    b = nc.BalanceoComida()
    for _ in range(40):
        b.paso(1 / 60, 5, 0)
    for _ in range(600):
        l, c = b.paso(1 / 60, 0, 0)
    assert abs(l) < 0.05 and math.isfinite(c)


# ── Sonidos ──────────────────────────────────────────────────────────────────────

def sonidos(config=None, juego=False, semilla=1):
    mez = MezcladorFalso()
    s = nc.SonidosComida(config or Config(), mezclador=mez, lanzar=lambda f: f(),
                         en_juego=lambda: juego, azar=random.Random(semilla))
    return s, mez


def test_sonidos_de_aparecer_capa_solo_en_el_batido():
    s, mez = sonidos()
    assert s.aparecer("batido")
    nombres = [x["archivo"] for x in mez.sonados]
    assert nombres[0] == "comida_aparece.wav" and nombres[1] in {"comida_capa_1.wav", "comida_capa_2.wav"}
    assert all(x["canal"] == "sfx" and 0.65 <= x["velocidad"] <= 1.25 for x in mez.sonados)
    assert all(x["vol"] == pytest.approx(0.7) for x in mez.sonados)       # avatar.volumen_sfx × pack
    mez.sonados.clear()
    s.aparecer("pastel")
    assert [x["archivo"] for x in mez.sonados] == ["comida_aparece.wav"]
    mez.sonados.clear()
    assert not s.aparecer("pizza") and mez.sonados == []


def test_sonido_de_la_reaccion_con_su_tono_y_su_numero():
    s, mez = sonidos(Config(avatar={"volumen_sfx": 0.5}))
    g, _ = gestor(semilla=5)
    r = g.reaccion("batido", "fresa")
    assert s.reaccion(r)
    x = mez.sonados[-1]
    assert x["archivo"] == f"{r.sonido}.wav" and x["velocidad"] == r.tono and x["vol"] == pytest.approx(0.5)
    r = g.reaccion("pastel")
    s.reaccion(r)
    assert mez.sonados[-1]["archivo"] == f"{r.sonido}.wav"


def test_al_guardar_calla_con_el_pack_por_defecto():
    s, mez = sonidos()
    s.guardar()
    assert mez.sonados == []                                              # ME no suena al guardar


def test_silencio_en_juego_y_con_volumen_cero():
    s, mez = sonidos(juego=True)
    assert s.silenciado() and not s.aparecer("batido") and mez.sonados == []
    s, mez = sonidos(Config(juego={"silenciar": False}), juego=True)
    assert not s.silenciado() and s.aparecer("pastel") and mez.sonados
    s, mez = sonidos(Config(avatar={"volumen_sfx": 0}))
    assert s.silenciado() and not s.aparecer("batido")


def test_pack_que_no_existe_usa_el_de_por_defecto():
    s, mez = sonidos(Config(avatar={"pack_sonidos": "no_existe_este_pack"}))
    s.aparecer("pastel")
    assert [x["archivo"] for x in mez.sonados] == ["comida_aparece.wav"]


def test_un_sonido_roto_no_revienta():
    class Roto(MezcladorFalso):
        def reproducir(self, *a, **k):
            raise RuntimeError("sin tarjeta")
    s = nc.SonidosComida(Config(), mezclador=Roto(), lanzar=lambda f: f())
    assert s.aparecer("batido") is True


# ── Herramienta ──────────────────────────────────────────────────────────────────

class ControlFalso:
    def __init__(self, texto="*glup glup* (batido de fresa)", motivo=""):
        self.pedidos = []
        self.texto = texto
        self.ultimo_motivo = motivo

    def comer_directo(self, id_):
        self.pedidos.append(id_)
        return self.texto


def test_herramienta_con_controlador_y_en_ui():
    ctl = ControlFalso()
    en_ui = []

    def correr(fn):
        en_ui.append(fn)
        return fn()
    assert nc.herramienta({"comida": "batido"}, {"comida": ctl, "en_ui": correr}) == "*glup glup* (batido de fresa)"
    assert ctl.pedidos == ["batido"] and len(en_ui) == 1
    # el Ejecutor envuelve los ctx que no son dict en «contexto»
    assert nc.herramienta({"comida": "Tarta"}, {"contexto": {"comida": ctl}}) and ctl.pedidos[-1] == "pastel"


def test_herramienta_denegada_y_errores():
    ctl = ControlFalso(texto="", motivo="juego")
    ok, texto = nc.herramienta({"comida": "pastel"}, {"comida": ctl})
    assert ok is False and "juego" in texto
    ok, texto = nc.herramienta({"comida": "pizza"}, {"comida": ctl})
    assert ok is False and "batido" in texto

    class Rompe:
        def comer_directo(self, id_):
            raise RuntimeError("¡pum!")
    ok, texto = nc.herramienta({"comida": "batido"}, {"comida": Rompe()})
    assert ok is False and "pum" in texto


def test_herramienta_sin_controlador_devuelve_el_texto():
    t = nc.herramienta({"comida": "batido"}, None)
    assert re.fullmatch(r"\*glup glup\* \(batido de (fresa|mango|matcha)\)", t)
    t = nc.herramienta({"comida": "pastel"}, {})
    assert t.startswith("*ñam ñam* (pastel de ")
