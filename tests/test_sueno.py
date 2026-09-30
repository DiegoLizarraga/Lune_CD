"""
Tests de nucleo/sueno.py: cuándo se duerme la asistente, el aviso diferido de
patata y los handlers de las herramientas asistente_dormir / asistente_despertar.

Sin Qt ni red: la asistente y el ctx son objetos falsos.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo import sueno  # noqa: E402
from nucleo.estado_asistente import EstadoAsistente  # noqa: E402

MIN = 60.0


# ── Regla ────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("estado", ["normal", "bored", " Normal ", "BORED"])
def test_duerme_en_normal_y_bored(estado):
    r = sueno.ReglaSueno(10)
    assert r.debe_dormir(10 * MIN, estado)
    assert r.debe_dormir(11 * MIN, estado)
    assert not r.debe_dormir(10 * MIN - 1, estado)                  # aún no toca


@pytest.mark.parametrize("estado", ["working", "thinking", "talking", "listening"])
def test_nunca_duerme_ocupada(estado):
    r = sueno.ReglaSueno(10)
    assert not r.debe_dormir(10_000 * MIN, estado)
    assert "está en" in r.motivo_no(estado)
    # …aunque alguien los meta en permitidos
    r2 = sueno.ReglaSueno(10, permitidos={"normal", estado})
    assert estado not in r2.permitidos
    assert not r2.debe_dormir(10_000 * MIN, estado)


@pytest.mark.parametrize("estado", ["happy", "angry", "surprised", "sleeping", "dragging", ""])
def test_otros_estados_no_permitidos(estado):
    r = sueno.ReglaSueno(10)
    esperado = estado == ""                                         # "" = normal
    assert r.debe_dormir(60 * MIN, estado) is esperado


def test_banderas_arrastre_voz_llamada_y_ya_dormida():
    r = sueno.ReglaSueno(10)
    assert not r.debe_dormir(60 * MIN, "normal", arrastrando=True)
    assert not r.debe_dormir(60 * MIN, "normal", hablando=True)
    assert not r.debe_dormir(60 * MIN, "normal", llamada=True)
    assert not r.debe_dormir(60 * MIN, "normal", durmiendo=True)
    assert r.motivo_no("normal", arrastrando=True) == "la están arrastrando"
    assert r.motivo_no("normal", durmiendo=True) == "ya está dormida"
    assert r.motivo_no("bored") == ""
    assert r.puede_dormir("bored") and not r.puede_dormir("bored", hablando=True)


def test_permitidos_personalizados():
    r = sueno.ReglaSueno(5, permitidos=["normal"])
    assert r.debe_dormir(5 * MIN, "normal")
    assert not r.debe_dormir(5 * MIN, "bored")
    assert "no deja dormir" in r.motivo_no("bored")


def test_con_estado_asistente():
    r = sueno.ReglaSueno(10)
    t = 30 * MIN
    assert r.debe_dormir(t, EstadoAsistente(render="vrm", visible=True))                    # neutral → normal
    assert r.debe_dormir(t, EstadoAsistente(emocion="bored"))
    assert not r.debe_dormir(t, EstadoAsistente(emocion="happy"))
    assert not r.debe_dormir(t, EstadoAsistente(emocion="think"))                          # → thinking
    for campo in ("arrastrando", "hablando", "llamada", "pensando", "alarma", "grande", "comiendo",
                  "menu_abierto", "durmiendo"):
        assert not r.debe_dormir(t, EstadoAsistente(**{campo: True})), campo
    assert not r.debe_dormir(t, EstadoAsistente(bailando="musica"))
    assert r.motivo_no(EstadoAsistente(bailando="mmd")) == "está bailando"
    # También un dict con los mismos campos
    assert r.debe_dormir(t, {"emocion": "neutral"})
    assert not r.debe_dormir(t, {"arrastrando": True})
    assert sueno.ReglaSueno.estado_visual(EstadoAsistente(hablando=True)) == "talking"
    assert sueno.ReglaSueno.estado_visual(EstadoAsistente(llamada=True)) == "listening"
    assert sueno.ReglaSueno.estado_visual(EstadoAsistente(arrastrando=True)) == "dragging"
    assert sueno.ReglaSueno.estado_visual(EstadoAsistente(durmiendo=True)) == "sleeping"
    assert sueno.ReglaSueno.estado_visual(None) == "normal"


def test_tiempo_desactivada_y_valores_raros():
    r = sueno.ReglaSueno(10)
    assert r.activa and r.umbral_s == 600
    assert r.segundos_restantes(0) == 600
    assert r.segundos_restantes(590) == 10
    assert r.segundos_restantes(10_000) == 0
    assert r.segundos_restantes(float("nan")) == 600
    assert r.segundos_restantes(-5) == 600
    assert r.segundos_restantes("x") == 600
    for apagada in (0, -3):
        a = sueno.ReglaSueno(apagada)
        assert not a.activa and a.umbral_s == float("inf")
        assert a.segundos_restantes(10 ** 9) is None
        assert not a.debe_dormir(10 ** 9, "normal")
    assert sueno.ReglaSueno("basura").dormir_min == 10.0
    assert sueno.ReglaSueno(0.5).umbral_s == 30


def test_desde_config():
    class Cfg:
        def __init__(self, v):
            self.v = v

        def get(self, seccion, clave, defecto=None):
            assert (seccion, clave) == ("avatar", "dormir_min")
            return self.v

    class Rota:
        def get(self, *a):
            raise RuntimeError("config rota")

    assert sueno.ReglaSueno.desde_config(Cfg(3)).dormir_min == 3
    assert sueno.ReglaSueno.desde_config(Cfg(0)).activa is False
    assert sueno.ReglaSueno.desde_config(None).dormir_min == 10
    assert sueno.ReglaSueno.desde_config(Rota()).dormir_min == 10


# ── Patata: aviso diferido ───────────────────────────────────────────────────────

def test_mensaje_diferido():
    r = sueno.ReglaSueno(10)
    assert r.mensaje_diferido(9 * MIN) is None                      # no llegó a dormirse
    assert r.mensaje_diferido(10 * MIN) == "Lune se quedó dormida hace un momento… (-_-) zzZ"
    assert r.mensaje_diferido(22 * MIN + 30) == "Lune se quedó dormida hace 12 min… (-_-) zzZ"
    assert r.mensaje_diferido(10 * MIN + 125 * MIN) == "Lune se quedó dormida hace 2 h 5 min… (-_-) zzZ"
    assert r.mensaje_diferido(10 * MIN + 120 * MIN) == "Lune se quedó dormida hace 2 h… (-_-) zzZ"
    assert r.mensaje_diferido(30 * MIN, nombre="Aria").startswith("Aria se quedó dormida hace 20 min")
    assert r.mensaje_diferido(30 * MIN, nombre="").startswith("Lune ")
    con = r.mensaje_diferido(30 * MIN, frase_despertar="¿Eh? Ya, ya estoy.")
    assert con.endswith("zzZ\n¿Eh? Ya, ya estoy.")
    assert sueno.ReglaSueno(0).mensaje_diferido(10 ** 6) is None


# ── Herramientas ─────────────────────────────────────────────────────────────────

class Asistente:
    """Asistente falsa con dormir()/despertar() y el atributo _durmiendo de companion.py."""

    def __init__(self, durmiendo=False, resultado=None):
        self._durmiendo = durmiendo
        self.resultado = resultado
        self.llamadas = []

    def dormir(self):
        self.llamadas.append("dormir")
        self._durmiendo = True
        return self.resultado

    def despertar(self):
        self.llamadas.append("despertar")
        self._durmiendo = False
        return self.resultado


def test_herramienta_dormir_y_despertar():
    m = Asistente()
    r = sueno.herramienta_dormir({}, {"asistente": m})
    assert isinstance(r, str) and "siesta" in r
    assert m.llamadas == ["dormir"] and m._durmiendo
    assert sueno.herramienta_dormir({}, {"asistente": m}) == "Ya estoy dormida. Shh."
    assert m.llamadas == ["dormir"]                                  # no la vuelve a dormir
    r = sueno.herramienta_despertar({}, {"asistente": m})
    assert isinstance(r, str) and "despierta" in r
    assert m.llamadas == ["dormir", "despertar"]
    assert sueno.herramienta_despertar(None, {"asistente": m}) == "Ya estaba despierta."


def _en_ui_otro_hilo(registro):
    """en_ui como el de web_bridge/main: corre fn en OTRO hilo y devuelve su resultado."""
    import threading

    def en_ui(fn):
        caja = {}

        def correr():
            registro.append(threading.get_ident())
            caja["r"] = fn()
        h = threading.Thread(target=correr)
        h.start()
        h.join(5)
        return caja.get("r")
    return en_ui


def test_herramienta_en_el_hilo_de_la_ui():
    import threading
    hilos = []
    m = Asistente(resultado=True)
    r = sueno.herramienta_dormir({}, {"asistente": m, "en_ui": _en_ui_otro_hilo(hilos)})
    assert isinstance(r, str) and "siesta" in r and m.llamadas == ["dormir"]
    # Todo (mirar si ya duerme y dormirla) en el hilo de la UI, en un solo salto.
    assert len(hilos) == 1 and hilos[0] != threading.get_ident()


def test_herramienta_en_ui_cuenta_el_resultado():
    """G5: con en_ui, un dormir() que devuelve False ya no cuenta como éxito."""
    m = Asistente(resultado=False)
    m.dormir = lambda: (m.llamadas.append("dormir"), False)[1]      # se niega y no se duerme
    r = sueno.herramienta_dormir({}, {"asistente": m, "en_ui": _en_ui_otro_hilo([])})
    assert r[0] is False and "liada" in r[1]


def test_herramienta_en_ui_sin_resultado_comprueba_durmiendo():
    """Un en_ui que no devuelve el resultado: se vuelve a mirar `durmiendo` (vía en_ui)."""
    hilos = []
    m = Asistente(resultado=None)                                      # dormir() sin valor, pero se duerme
    r = sueno.herramienta_dormir({}, {"asistente": m, "en_ui": _en_ui_otro_hilo(hilos)})
    assert isinstance(r, str) and "siesta" in r and len(hilos) == 2

    terca = Asistente(resultado=None)
    terca.dormir = lambda: terca.llamadas.append("dormir")          # no devuelve nada ni se duerme
    r = sueno.herramienta_dormir({}, {"asistente": terca, "en_ui": _en_ui_otro_hilo([])})
    assert r[0] is False

    # en_ui que solo encola (no devuelve nada ni corre ya): no se da por hecho.
    cola = []
    m2 = Asistente()
    r = sueno.herramienta_dormir({}, {"asistente": m2, "en_ui": cola.append})
    assert r[0] is False and "comprobar" in r[1] and m2.llamadas == []
    cola[0]()
    assert m2.llamadas == ["dormir"]


def test_herramienta_ctx_objeto_y_envuelto_por_el_ejecutor():
    """El Ejecutor envuelve un ctx objeto como {..., 'contexto': objeto}."""
    class Ctx:
        def __init__(self):
            self.asistente = Asistente()

    c = Ctx()
    assert isinstance(sueno.herramienta_dormir({}, c), str) and c.asistente.llamadas == ["dormir"]
    c2 = Ctx()
    r = sueno.herramienta_dormir({}, {"modo": "vrm", "origen": "usuario", "contexto": c2})
    assert isinstance(r, str) and c2.asistente.llamadas == ["dormir"]


def test_herramienta_sin_asistente_o_que_no_sabe():
    ok, motivo = sueno.herramienta_dormir({}, {})
    assert ok is False and "No estoy en el escritorio" in motivo
    ok, _ = sueno.herramienta_despertar({}, None)
    assert ok is False

    class Muda:
        pass
    ok, motivo = sueno.herramienta_dormir({}, {"asistente": Muda()})
    assert ok is False and "no sé dormirme" in motivo
    ok, motivo = sueno.herramienta_despertar({}, {"asistente": Muda()})
    assert ok is False and "no sé despertarme" in motivo


def test_herramienta_cuando_la_asistente_se_niega_o_falla():
    ok, motivo = sueno.herramienta_dormir({}, {"asistente": Asistente(resultado=False)})
    assert ok is False and "liada" in motivo

    class Rota(Asistente):
        def dormir(self):
            raise RuntimeError("WebEngine caído")
    ok, motivo = sueno.herramienta_dormir({}, {"asistente": Rota()})
    assert ok is False and "WebEngine caído" in motivo


def test_durmiendo_como_metodo_o_propiedad():
    class ConMetodo(Asistente):
        def durmiendo(self):
            return True
    assert sueno.herramienta_dormir({}, {"asistente": ConMetodo()}) == "Ya estoy dormida. Shh."

    class SinEstado:
        def __init__(self):
            self.n = 0

        def despertar(self):
            self.n += 1
    s = SinEstado()
    assert isinstance(sueno.herramienta_despertar({}, {"asistente": s}), str) and s.n == 1


def test_las_herramientas_las_entiende_el_ejecutor():
    """(False, motivo) y texto son salidas que el Ejecutor sabe normalizar."""
    from lune_core.acciones import _normalizar_salida
    assert _normalizar_salida(sueno.herramienta_dormir({}, {}))[0] is False
    assert _normalizar_salida(sueno.herramienta_dormir({}, {"asistente": Asistente()}))[0] is True


def test_catalogo_apunta_a_los_handlers():
    from lune_core import catalogo_herramientas as cat
    c = cat.CATALOGO
    assert c["asistente_dormir"].handler == "nucleo.sueno.herramienta_dormir"
    assert c["asistente_despertar"].handler == "nucleo.sueno.herramienta_despertar"
    assert callable(sueno.herramienta_dormir) and callable(sueno.herramienta_despertar)
