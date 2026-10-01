"""
/probar y /diagnostico de patata (11.3) con pruebas FALSAS: la consola de prueba de
tests/test_patata.py, datos.json temporal y nada de red, Node ni subprocesos de verdad.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import patata  # noqa: E402
from nucleo import datos  # noqa: E402
from servicios import pruebas  # noqa: E402
from test_patata import _cmd, _sin_red_de_voces, crear, datos_tmp, esperar  # noqa: E402,F401  (fixtures)

TOKEN = "123456789:AAH-tokenSecretoDePrueba_0123456"


@pytest.fixture
def en_linea(monkeypatch):
    """_en_hilo corre al momento (así el test ve lo que se imprime)."""
    monkeypatch.setattr(patata, "_en_hilo", lambda fn: fn())


def _guardar(**apis_y_modelos):
    d = datos.cargar()
    for k, v in apis_y_modelos.items():
        (d.setdefault("modelos", {}) if k.startswith(("ollama", "openrouter_model")) else d.setdefault("apis", {}))[k] = v
    datos.guardar(d)


def test_ayuda_lista_probar_y_diagnostico(crear):
    texto = _cmd(crear(), "/ayuda")
    assert "/probar [nube|ollama|telegram|salida|todo]" in texto and "/diagnostico" in texto


def test_probar_nube_con_lo_guardado(crear, en_linea, monkeypatch):
    _guardar(openrouter_key="sk-guardada", openrouter_model="x/y")
    pedidas = []
    monkeypatch.setattr(pruebas, "probar_openrouter", lambda k, m: pedidas.append((k, m)) or
                        {"ok": False, "mensaje": "OpenRouter no reconoce esa clave: cópiala otra vez."})
    p = crear()
    _cmd(p, "/probar nube")
    assert esperar(lambda: "no reconoce" in p.out.getvalue())
    assert pedidas == [("sk-guardada", "x/y")]
    assert "[FALLA] Nube (OpenRouter)" in p.out.getvalue()


def test_probar_todo_y_lo_que_no_tienes_no_aplica(crear, en_linea, monkeypatch):
    llamadas = []
    monkeypatch.setattr(pruebas, "probar_openrouter", lambda k, m: llamadas.append("nube") or
                        {"ok": None, "mensaje": "Sin clave de OpenRouter."})
    monkeypatch.setattr(pruebas, "probar_ollama", lambda u, m: llamadas.append("ollama") or {"ok": True, "mensaje": "x"})
    monkeypatch.setattr(pruebas, "probar_telegram", lambda t, a: llamadas.append("telegram") or {"ok": True, "mensaje": "x"})
    monkeypatch.setattr(pruebas, "probar_salida", lambda v: llamadas.append("salida") or
                        {"ok": False, "mensaje": "No tengo motor de voz para sonar."})
    p = crear()
    _cmd(p, "/probar")
    assert esperar(lambda: "Salida de audio" in p.out.getvalue())
    out = p.out.getvalue()
    assert llamadas == ["nube", "salida"]               # sin modelo de Ollama ni token: no se prueban
    assert "[--]    Ollama (modelo local): No uso Ollama" in out
    assert "[--]    Bot de Telegram: Sin token de Telegram" in out
    assert "[FALLA] Salida de audio" in out


def test_probar_telegram_dice_que_falla_sin_el_token(crear, en_linea, monkeypatch):
    _guardar(telegram_token=TOKEN, telegram_admin_id="42")
    vistos = []

    def probar(t, a):
        vistos.append((t, a))
        return {"ok": False, "mensaje": "Falta Node.js 18 o más nuevo.",
                "items": [{"nombre": "Node.js 18+", "ok": False, "detalle": "Falta Node.js 18 o más nuevo."},
                          {"nombre": "Carpeta del bot", "ok": False, "detalle": "No encuentro la carpeta del bot."}]}
    monkeypatch.setattr(pruebas, "probar_telegram", probar)
    p = crear()
    _cmd(p, "/probar bot")
    assert esperar(lambda: "Carpeta del bot" in p.out.getvalue())
    assert vistos == [(TOKEN, "42")] and TOKEN not in p.out.getvalue()
    assert p.out.getvalue().count("Falta Node.js") == 1              # el detalle repetido no sale dos veces


def test_probar_algo_que_no_existe(crear):
    assert "Uso: /probar" in _cmd(crear(), "/probar cafetera")


def test_probar_no_bloquea_la_consola(crear, monkeypatch):
    hilos = []
    monkeypatch.setattr(patata, "_en_hilo", hilos.append)
    p = crear()
    assert "Probando nube (openrouter)" in _cmd(p, "/probar nube")
    assert len(hilos) == 1


def test_diagnostico_en_otro_proceso(crear, en_linea, monkeypatch):
    escrito = []
    monkeypatch.setattr(patata, "diagnostico_en_otro_proceso", lambda escribir: escrito.append(escribir) or
                        escribir("  [ok]    Internet  Hay internet.") or 0)
    p = crear()
    assert "otro proceso" in _cmd(p, "/diagnostico")
    assert esperar(lambda: "Hay internet." in p.out.getvalue())


class PopenFalso:
    def __init__(self, orden, **kw):
        PopenFalso.ultimo = (orden, kw)
        self.stdout = iter(["Lune CD 11.3 - comprobando\n", "\n", "Red y servicios\n", "  [ok]    Internet\n"])

    def wait(self, timeout=None):
        return 0


def test_diagnostico_lanza_comprobar_con_red_y_pasa_las_lineas():
    lineas = []
    assert patata.diagnostico_en_otro_proceso(lineas.append, popen=PopenFalso) == 0
    orden, kw = PopenFalso.ultimo
    assert orden[-2:] == ["--comprobar", "--red"]
    assert kw["env"]["PYTHONIOENCODING"] == "utf-8" and kw["encoding"] == "utf-8"
    assert lineas == ["Lune CD 11.3 - comprobando", "Red y servicios", "  [ok]    Internet"]

    def no_arranca(*a, **k):
        raise OSError("no")
    assert patata.diagnostico_en_otro_proceso(lineas.append, popen=no_arranca) == -1
    assert "No pude lanzar" in lineas[-1]
