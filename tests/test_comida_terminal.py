"""
Tests de servicios/comida_terminal.py (patata, sin Qt): /comer con su texto y
el sonido por el Mezclador (tono al azar, callado en juego con juego.silenciar),
el sabor opcional, kaomoji, color ANSI, /comer on|off y la herramienta
`dar_de_comer` registrada en un ToolManager falso.
"""
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from servicios.comida_terminal import AYUDA, ComidaTerminal  # noqa: E402


class Config:
    def __init__(self, **secciones):
        self.d = {"avatar": {"volumen_sfx": 0.7}, "juego": {"silenciar": True},
                  "comida": {"activa": True}, "patata": {"caritas": "clasico"}}
        for sec, vals in secciones.items():
            self.d.setdefault(sec, {}).update(vals)
        self.escrito = []

    def get(self, sec, clave, defecto=None):
        return self.d.get(sec, {}).get(clave, defecto)

    def set(self, sec, clave, valor):
        self.escrito.append((sec, clave, valor))
        self.d.setdefault(sec, {})[clave] = valor


class MezcladorFalso:
    def __init__(self):
        self.sonados = []

    def cargar_audio(self, ruta):
        return Path(ruta)

    def reproducir(self, buf, vol=1.0, velocidad=1.0, bucle=False, canal=None):
        self.sonados.append((Path(buf).stem, velocidad, canal))
        return len(self.sonados)


class ToolsFalso:
    def __init__(self):
        self.handlers = {}

    def registrar_handler(self, nombre, fn):
        self.handlers[nombre] = fn


def crear(config=None, juego=False, colores=None, nombre="Lune"):
    mez = MezcladorFalso()
    estado = {"juego": juego}
    ct = ComidaTerminal(None, config or Config(), colores=colores, mezclador=mez,
                        en_juego=lambda: estado["juego"], nombre=nombre, azar=random.Random(3),
                        lanzar_sonido=lambda f: f())
    return ct, mez, estado


def test_comer_batido_texto_y_trago_con_tono():
    ct, mez, _ = crear()
    r = ct.comando("/comer batido")
    assert re.fullmatch(r"Lune \(\^o\^\)~ \*glup glup\* \(batido de (fresa|mango|matcha)\)", r), r
    son, vel, canal = mez.sonados[-1]
    assert re.fullmatch(r"trago_[123]", son) and 0.65 <= vel <= 1.25 and canal == "sfx"
    r = ct.comando("/comer tarta")
    assert "*ñam ñam* (pastel de " in r and re.fullmatch(r"mordisco_[123]", mez.sonados[-1][0])


def test_sabor_opcional_y_comida_al_azar():
    ct, mez, _ = crear()
    assert ct.comando("/comer batido de mango").endswith("(batido de mango)")
    assert ct.comando("/COMER pastel Limón").endswith("(pastel de limón)")
    assert re.search(r"\(pastel de \w+\)$", ct.comando("/comer pastel pizza"))    # sabor que no hay: al azar
    vistos = {re.search(r"\((\w+) de", ct.comando("/comer")).group(1) for _ in range(30)}
    assert vistos == {"batido", "pastel"}


def test_lineas_ajenas_y_ayuda():
    ct, mez, _ = crear()
    assert ct.comando("hola") is None and ct.comando("/bailar") is None and ct.comando("") is None
    assert ct.comando("/comer pizza").startswith("No tengo «pizza»")
    assert AYUDA in ct.comando("/comer ayuda")
    assert mez.sonados == []


def test_en_juego_texto_sin_sonido():
    ct, mez, estado = crear(juego=True)
    assert "*glup glup*" in ct.comando("/comer batido")
    assert mez.sonados == []
    estado["juego"] = False
    ct.comando("/comer batido")
    assert len(mez.sonados) == 1
    # con juego.silenciar apagado suena también en juego
    ct2, mez2, _ = crear(Config(juego={"silenciar": False}), juego=True)
    ct2.comando("/comer pastel")
    assert len(mez2.sonados) == 1


def test_kaomoji_nombre_y_color():
    ct, _, _ = crear(Config(patata={"caritas": "kaomoji"}), nombre=lambda: "Aria")
    assert ct.comando("/comer batido mango") == "Aria (っ˘ω˘ς) *glup glup* (batido de mango)"
    ct, _, _ = crear(colores={"reset": "\x1b[0m", "dim": "\x1b[2m"})
    r = ct.comando("/comer batido mango")
    assert r == "Lune (^o^)~ *glup glup* \x1b[38;2;255;181;71m(batido de mango)\x1b[0m"


def test_comer_on_off_guarda_la_config():
    cfg = Config()
    ct, mez, _ = crear(cfg)
    assert "apagada" in ct.comando("/comer off")
    assert cfg.escrito == [("comida", "activa", False)]
    assert ct.comando("/comer batido") == "La comida está apagada. Enciéndela con /comer on."
    assert mez.sonados == []
    assert "encendida" in ct.comando("/comer on")
    assert cfg.d["comida"]["activa"] is True
    ct.comando("/comer on")
    assert len(cfg.escrito) == 2                                   # solo lo que cambia


def test_herramienta_dar_de_comer():
    ct, mez, estado = crear()
    tools = ToolsFalso()
    ct.registrar_herramientas(tools)
    fn = tools.handlers["dar_de_comer"]
    r = fn({"comida": "pastel"}, {"origen": "modelo"})
    assert r.startswith("*ñam ñam* (pastel de ") and "\x1b" not in r
    assert re.fullmatch(r"mordisco_[123]", mez.sonados[-1][0])
    estado["juego"] = True
    assert fn({"comida": "batido"}).startswith("*glup glup*") and len(mez.sonados) == 1
    ok, texto = fn({"comida": "pizza"})
    assert ok is False
    ct.config.set("comida", "activa", False)
    ok, texto = fn({"comida": "batido"})
    assert ok is False and "desactivada" in texto
