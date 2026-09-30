"""
Tests de nucleo/asiento.py (corte 7): la máquina de «sentada» portada de
AvatarWindowHandler / AvatarTaskbarController de Mate-Engine, en seco (reloj a
mano, px físicos, sin Qt ni Win32): agarre y arrastre mínimos, radio y lados,
oclusión, guardia, enfriamiento, bloqueo vertical, bloqueo de 0.43 s y banda del
cursor, deslizamiento, SmoothDamp que converge y queda rígido, anti-hundimiento
solo arrastrando, estados → Desnap, la zona rosa de la barra con histéresis,
radios × dpr, variantes con semilla y la herramienta `asistente_sentarse`.
"""
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo import asiento as na  # noqa: E402
from nucleo.asiento import (Desnap, MaquinaAsiento, Mover, Objetivo, ParamsAsiento, Rect, Snap,  # noqa: E402
                            punto_fisico, radio_sonda, toca_barra, zona_barra)


class C:
    """Candidata mínima (como servicios.ventanas_ajenas.Candidata)."""

    def __init__(self, hwnd, rect, es_barra=False, topmost=False):
        self.hwnd, self.rect, self.es_barra, self.topmost = hwnd, Rect(*rect), es_barra, topmost


BLOC = C(2, (300, 400, 1100, 900))
BARRA = C(9, (0, 1032, 1920, 1080), es_barra=True, topmost=True)
R = 40.0                         # radio (px físicos)


def maquina(seed=1, **kw):
    return MaquinaAsiento(ParamsAsiento(**kw), azar=random.Random(seed))


def arrastrar_hasta(m, t, cursor, sonda, cands=(BLOC,), ocluida=None, **kw):
    return m.al_arrastrar(t, cursor, sonda, R, list(cands), ocluida, **kw)


def encajar(m, t, cursor, sonda, cands=(BLOC,), ocluida=None, **kw):
    """Medio segundo con la sonda sobre el borde: una muestra al llegar (t − 0.5) y otra en t."""
    r = arrastrar_hasta(m, t - 0.5, cursor, sonda, cands, ocluida, **kw)
    return r if r is not None else arrastrar_hasta(m, t, cursor, sonda, cands, ocluida, **kw)


# ── Encajar en una ventana ─────────────────────────────────────────────────────

def test_no_encaja_sin_medio_segundo_sobre_el_borde():
    """Revisión 7-10 (SV1): el medio segundo cuenta desde que la sonda LLEGA al borde, no
    desde que se cogió (README: «mantenme medio segundo sobre el borde»)."""
    m = maquina()
    m.al_pulsar(0.0, (100, 100))
    assert arrastrar_hasta(m, 3.0, (400, 300), (700, 600)) is None        # lejos del borde
    assert arrastrar_hasta(m, 3.2, (400, 300), (700, 410)) is None        # llega: aún no
    assert arrastrar_hasta(m, 3.69, (400, 300), (700, 410)) is None
    s = arrastrar_hasta(m, 3.70, (400, 300), (700, 410))
    assert isinstance(s, Snap) and s.modo == "ventana" and s.objetivo.hwnd == 2
    assert s.frac == pytest.approx((700 - 300) / 800) and s.cursor_y == 300
    assert m.sentada is s


def test_pasar_por_encima_del_borde_no_la_sienta_y_salir_reinicia_la_cuenta():
    m = maquina()
    m.al_pulsar(0.0, (100, 100))
    assert arrastrar_hasta(m, 2.0, (400, 300), (700, 410)) is None        # llega…
    assert arrastrar_hasta(m, 2.3, (400, 300), (700, 480)) is None        # …se va (fuera del radio)…
    assert arrastrar_hasta(m, 2.4, (400, 300), (700, 410)) is None        # …vuelve: cuenta de nuevo
    assert arrastrar_hasta(m, 2.8, (400, 300), (700, 410)) is None        # 0.8 s desde la primera
    assert isinstance(arrastrar_hasta(m, 2.9, (400, 300), (700, 410)), Snap)


def test_no_encaja_con_menos_de_10_px_de_arrastre():
    m = maquina()
    m.al_pulsar(0.0, (100, 100))
    assert encajar(m, 1.0, (109, 91), (700, 410)) is None
    assert isinstance(encajar(m, 2.0, (110, 100), (700, 410)), Snap)


def test_el_arrastre_minimo_escala_con_el_dpr():
    m = maquina()
    m.al_pulsar(0.0, (100, 100))
    assert encajar(m, 1.0, (112, 100), (700, 410), dpr=1.5) is None     # 15 px a 150 %
    assert isinstance(encajar(m, 2.0, (115, 100), (700, 410), dpr=1.5), Snap)


@pytest.mark.parametrize("sonda,encaja", [
    ((700, 400 - R), True), ((700, 400 + R), True),                # en el radio (por arriba y por abajo)
    ((700, 400 - R - 1), False), ((700, 441), False),
    ((300, 410), True), ((1100, 410), True),                       # los lados cuentan
    ((299, 410), False), ((1101, 410), False),
])
def test_encaja_dentro_del_radio_y_entre_los_lados(sonda, encaja):
    m = maquina()
    m.al_pulsar(0.0, (0, 0))
    assert isinstance(encajar(m, 1.0, (50, 50), sonda), Snap) is encaja


def test_tapada_no_encaja_y_se_pregunta_por_el_punto_de_la_sonda():
    preguntas = []

    def ocluida(h, x, y):
        preguntas.append((h, x, y))
        return h == 2

    m = maquina()
    m.al_pulsar(0.0, (0, 0))
    otra = C(3, (200, 405, 1000, 800))
    s = encajar(m, 1.0, (50, 50), (700.4, 410.6), cands=(BLOC, otra), ocluida=ocluida)
    assert preguntas[:2] == [(2, 700, 411), (3, 700, 411)]
    assert s.objetivo.hwnd == 3                                    # la de debajo, que no está tapada


def test_la_primera_en_orden_z_gana():
    m = maquina()
    m.al_pulsar(0.0, (0, 0))
    otra = C(3, (200, 405, 1000, 800))
    assert encajar(m, 1.0, (50, 50), (700, 410), cands=(otra, BLOC)).objetivo.hwnd == 3


# ── Soltarse arrastrando: bloqueo, banda, guardia, enfriamiento, bloqueo vertical ──

def _sentada_arrastrando(m, t=1.0):
    m.al_pulsar(0.0, (500, 500))
    s = encajar(m, t, (500, 520), (700, 410))
    assert isinstance(s, Snap)
    return s


def test_durante_el_bloqueo_no_se_suelta_y_la_banda_del_cursor_si():
    m = maquina()
    _sentada_arrastrando(m)
    assert arrastrar_hasta(m, 1.42, (500, 900), (700, 800)) is None    # 0.42 s: aunque tire lejos
    assert m.sentada is not None
    assert arrastrar_hasta(m, 1.44, (500, 520 + R), (700, 410)) is None   # dentro de la banda (máx(16, radio))
    d = arrastrar_hasta(m, 1.45, (500, 520 + R + 1), (700, 410))
    assert d == Desnap("arrastre") and m.sentada is None


def test_banda_minima_de_16_px_por_dpr():
    m = maquina()
    m.al_pulsar(0.0, (500, 500))
    assert m.al_arrastrar(0.5, (500, 520), (700, 403), 5.0, [BLOC], None) is None
    assert isinstance(m.al_arrastrar(1.0, (500, 520), (700, 403), 5.0, [BLOC], None), Snap)
    assert m.al_arrastrar(2.0, (500, 544), (700, 403), 5.0, [BLOC], None, dpr=1.5) is None   # 24 = 16·1.5
    assert m.al_arrastrar(2.1, (500, 545), (700, 403), 5.0, [BLOC], None, dpr=1.5) == Desnap("arrastre")


def test_desliza_por_el_borde_y_se_suelta_al_salir_por_un_lado():
    m = maquina()
    _sentada_arrastrando(m)
    assert arrastrar_hasta(m, 2.0, (600, 522), (900, 380), asiento=(900, 395)) is None
    assert m.sentada.frac == pytest.approx((900 - 300) / 800)            # la x del asiento libre manda
    assert arrastrar_hasta(m, 2.1, (900, 522), (1101, 380), asiento=(1101, 395)) == Desnap("arrastre")


def test_se_suelta_si_el_objetivo_ya_no_esta():
    m = maquina()
    _sentada_arrastrando(m)
    assert arrastrar_hasta(m, 2.0, (500, 520), (700, 410), cands=()) == Desnap("arrastre")


def test_tras_soltarse_enfriamiento_guardia_y_bloqueo_vertical():
    m = maquina()
    _sentada_arrastrando(m)
    assert arrastrar_hasta(m, 2.0, (500, 700), (700, 470)) == Desnap("arrastre")   # guardia en (700, 470)
    # enfriamiento de 0.275 s
    assert arrastrar_hasta(m, 2.2, (500, 700), (900, 405)) is None
    # guardia: hasta salir de 1.15·radio (46 px) del punto donde se soltó
    assert arrastrar_hasta(m, 2.3, (500, 700), (700, 425)) is None                  # a 45 px
    # bloqueo vertical: fuera de la guardia pero a < máx(16, radio) del borde en vertical
    assert arrastrar_hasta(m, 2.4, (500, 700), (800, 420)) is None
    assert arrastrar_hasta(m, 2.5, (500, 700), (800, 441)) is None                  # se aleja: fin del bloqueo…
    assert arrastrar_hasta(m, 2.6, (500, 700), (800, 420)) is None                  # …vuelve al borde…
    s = arrastrar_hasta(m, 3.1, (500, 700), (800, 420))                             # …y medio segundo después, encaja
    assert isinstance(s, Snap)


def test_al_volver_a_cogerla_sentada_no_hay_bloqueo_y_la_banda_parte_del_nuevo_cursor():
    m = maquina()
    _sentada_arrastrando(m)
    m.al_soltar(3.0)
    assert m.sentada is not None and not m.arrastrando
    m.al_pulsar(10.0, (800, 300))
    assert m.sentada.cursor_y == 300
    assert m.al_arrastrar(10.01, (800, 300 + R + 1), (700, 410), R, [BLOC], None) == Desnap("arrastre")


# ── Clavar (pin) ───────────────────────────────────────────────────────────────

def _pin_hasta_quieta(m, rect_m, asiento_rel=(150, 400), rect_obj=BLOC.rect, arrastrando=False, dt=1 / 60):
    movs = []
    for i in range(200):
        r = m.pin(i * dt, dt, rect_obj, asiento_rel, rect_m, arrastrando=arrastrando)
        if r is None:
            return movs, rect_m
        assert isinstance(r, Mover)
        movs.append(r)
        rect_m = Rect(r.x, r.y, r.x + rect_m.ancho, r.y + rect_m.alto)
    raise AssertionError("no convergió")


def test_smoothdamp_converge_a_menos_de_un_px_y_queda_rigida():
    m = maquina()
    m.sentar_directo(Objetivo(2, False, BLOC.rect), frac=0.5)
    assert m.suavizando
    movs, rm = _pin_hasta_quieta(m, Rect(0, 0, 300, 500))
    # asiento (150, 400) de la ventana → (700, 400) del escritorio
    assert (rm.izq + 150, rm.arriba + 400) == (700, 400)
    assert len(movs) > 3, "se desliza, no salta"
    assert not m.suavizando                                     # ya rígida
    assert m.pin(10.0, 1 / 60, BLOC.rect, (150, 400), rm, arrastrando=False) is None


def test_objetivo_movido_se_sigue_rigido_sin_retraso():
    m = maquina()
    m.sentar_directo(Objetivo(2, False, BLOC.rect), frac=0.5)
    _, rm = _pin_hasta_quieta(m, Rect(0, 0, 300, 500))
    m.suavizar()                                                  # aunque volviera a suavizar…
    m.pin(0.0, 1 / 60, BLOC.rect, (150, 400), rm, arrastrando=False)
    movido = Rect(350, 380, 1150, 880)                            # …si el objetivo se mueve: rígida
    r = m.pin(0.1, 1 / 60, movido, (150, 400), rm, arrastrando=False)
    assert r == Mover(750 - 150, 380 - 400) and not m.suavizando


def test_offset_sube_o_baja_el_asiento():
    m = maquina()
    m.offset_px = -12
    m.sentar_directo(Objetivo(2, False, BLOC.rect), frac=0.0)
    _, rm = _pin_hasta_quieta(m, Rect(0, 0, 300, 500))
    assert (rm.izq + 150, rm.arriba + 400) == (300, 388)


def test_anti_hundimiento_solo_arrastrando():
    abajo = Rect(550, 100, 850, 600)                              # asiento en y=500: 100 px bajo el borde
    a, b = maquina(), maquina()
    for m in (a, b):
        m.sentar_directo(Objetivo(2, False, BLOC.rect), frac=0.5)
    ra = a.pin(0.0, 1 / 60, BLOC.rect, (150, 400), abajo, arrastrando=True)
    rb = b.pin(0.0, 1 / 60, BLOC.rect, (150, 400), abajo, arrastrando=False)
    assert ra.y == 0 and not a.suavizando                          # arrastrando: sube de golpe al borde
    assert rb.y > 10 and b.suavizando                              # quieta: se desliza


def test_pin_con_dpr_usa_px_logicos_del_asiento():
    m = maquina()
    m.sentar_directo(Objetivo(2, False, BLOC.rect), frac=0.5)
    m._parar_suavizado()
    r = m.pin(0.0, 1 / 60, BLOC.rect, (100, 200), Rect(0, 0, 300, 500), arrastrando=False, dpr=1.5)
    assert r == Mover(700 - 150, 400 - 300)


def test_sin_rect_del_objetivo_se_levanta():
    m = maquina()
    m.sentar_directo(Objetivo(2, False, BLOC.rect))
    assert m.pin(0.0, 1 / 60, None, (1, 1), Rect(0, 0, 10, 10), arrastrando=False) == Desnap("cerrada")
    assert m.sentada is None


@pytest.mark.parametrize("estado", ["cerrada", "oculta", "minimizada", "maximizada", "pantalla_completa",
                                    "cloaked"])
def test_estados_de_la_ventana_levantan_con_su_motivo(estado):
    m = maquina()
    m.sentar_directo(Objetivo(2, False, BLOC.rect))
    assert m.comprobar("ok") is None and m.sentada is not None
    assert m.comprobar(estado) == Desnap(estado) and m.sentada is None
    assert m.comprobar(estado) is None                            # ya de pie


def test_levantar_con_motivo_desconocido_es_usuario():
    m = maquina()
    m.sentar_directo(Objetivo(2, False, BLOC.rect))
    assert m.levantar("??") == Desnap("usuario")


# ── Barra ──────────────────────────────────────────────────────────────────────

def test_zona_rosa_encaja_en_la_barra_sin_agarre():
    m = maquina()
    m.al_pulsar(0.0, (500, 500))
    s = m.al_arrastrar(0.05, (500, 510), (960, 1030), R, [BARRA], None)
    assert isinstance(s, Snap) and s.modo == "barra" and s.variante == 0 and s.objetivo.hwnd == 9
    assert s.frac == pytest.approx(0.5)


def test_zona_rosa_no_toca_si_esta_lejos_de_la_franja():
    m = maquina()
    m.al_pulsar(0.0, (500, 500))
    assert m.al_arrastrar(1.0, (500, 510), (960, 1026), R, [BARRA], None) is None     # zona hasta 1031
    assert m.al_arrastrar(1.0, (500, 510), (960, 1042), R, [BARRA], None) is None     # franja hasta 1037


def test_histeresis_de_la_barra():
    m = maquina()
    m.al_pulsar(0.0, (500, 500))
    assert isinstance(m.al_arrastrar(0.05, (500, 510), (960, 1030), R, [BARRA], None), Snap)
    m.al_soltar(0.1)
    m.levantar("usuario")                                          # «bájate»: se queda tocando la barra
    m.al_pulsar(5.0, (500, 500))
    assert m.al_arrastrar(5.1, (500, 510), (960, 1030), R, [BARRA], None) is None     # sigue tocando: no
    assert m.al_arrastrar(5.2, (500, 510), (960, 1010), R, [BARRA], None) is None     # sube 20 px
    assert m.al_arrastrar(5.3, (500, 510), (960, 1006), R, [BARRA], None) is None     # zona < borde − 20
    assert isinstance(m.al_arrastrar(5.4, (500, 510), (960, 1030), R, [BARRA], None), Snap)


def test_en_la_barra_la_banda_es_de_20_px():
    m = maquina()
    m.al_pulsar(0.0, (500, 500))
    m.al_arrastrar(0.05, (500, 500), (960, 1030), 5.0, [BARRA], None)
    assert m.al_arrastrar(1.0, (700, 520), (1160, 1050), 5.0, [BARRA], None) is None
    assert m.sentada.frac == pytest.approx(1160 / 1920)
    assert m.al_arrastrar(1.1, (700, 479), (1160, 1009), 5.0, [BARRA], None) == Desnap("arrastre")


def test_zona_barra_y_franja_escalan_con_el_dpr():
    assert zona_barra((960, 1030), 1.0) == Rect(910, 1025, 1010, 1035)
    assert zona_barra((960, 1030), 2.0) == Rect(860, 1020, 1060, 1040)
    b = Rect(0, 1032, 1920, 1080)
    assert toca_barra(Rect(0, 1020, 10, 1033), b, 5) and not toca_barra(Rect(0, 1020, 10, 1032), b, 5)
    assert not toca_barra(Rect(0, 1037, 10, 1040), b, 5) and toca_barra(Rect(0, 1037, 10, 1040), b, 6)


def test_radio_de_la_sonda_por_alto_y_dpr():
    assert radio_sonda(520, 1.0) == pytest.approx(46.8)
    assert radio_sonda(100, 1.0) == 18                              # mínimo
    assert radio_sonda(100, 1.5) == 27
    assert radio_sonda(2000, 1.0) == 64 and radio_sonda(2000, 1.5) == 96


def test_punto_fisico():
    assert punto_fisico(Rect(100, 200, 400, 700), (150, 390), 1.0) == (250, 590)
    assert punto_fisico(Rect(100, 200, 400, 700), (100, 200), 1.5) == (250, 500)


# ── Variantes y sprites ────────────────────────────────────────────────────────

def test_variantes_de_0_a_3_con_semilla():
    def variantes(seed):
        m = maquina(seed)
        vs = []
        for i in range(40):
            vs.append(m.sentar_directo(Objetivo(2, False, BLOC.rect)).variante)
        return vs
    a, b = variantes(7), variantes(7)
    assert a == b and set(a) == {0, 1, 2, 3}
    assert maquina(7).sentar_directo(Objetivo(9, True, BARRA.rect)).variante == 0


def test_sprites_encajan_al_soltar_con_agarre():
    m = maquina()
    m.al_pulsar(0.0, (100, 100))
    assert m.al_soltar(0.3, sonda=(700, 410), radio=R, candidatas=[BLOC], cursor=(300, 400)) is None
    m.al_pulsar(1.0, (100, 100))
    assert m.al_soltar(1.6, sonda=(700, 410), radio=R, candidatas=[BLOC], cursor=(105, 100)) is None  # < 10 px
    m.al_pulsar(2.0, (100, 100))
    s = m.al_soltar(2.6, sonda=(700, 410), radio=R, candidatas=[BLOC], cursor=(300, 400))
    assert isinstance(s, Snap) and not m.arrastrando
    m2 = maquina()
    m2.al_pulsar(0.0, (100, 100))
    assert m2.al_soltar(0.05, sonda=(960, 1030), radio=R, candidatas=[BARRA]).modo == "barra"   # barra: sin agarre


def test_al_soltar_un_arrastre_muestreado_encaja_si_ya_llevaba_medio_segundo_en_el_borde():
    m = maquina()
    m.al_pulsar(0.0, (100, 100))
    assert arrastrar_hasta(m, 1.0, (300, 400), (700, 410)) is None
    s = m.al_soltar(1.55, sonda=(700, 410), radio=R, candidatas=[BLOC], cursor=(300, 400), muestreado=True)
    assert isinstance(s, Snap)
    m2 = maquina()
    m2.al_pulsar(5.0, (100, 100))
    assert arrastrar_hasta(m2, 6.0, (300, 400), (700, 410)) is None
    assert m2.al_soltar(6.2, sonda=(700, 410), radio=R, candidatas=[BLOC], cursor=(300, 400),
                        muestreado=True) is None                          # solo 0.2 s en el borde
    assert not m2.arrastrando and m2.sentada is None


def test_anular_pone_enfriamiento():
    m = maquina()
    m.al_pulsar(0.0, (0, 0))
    assert isinstance(encajar(m, 1.0, (50, 50), (700, 410)), Snap)
    m.anular(1.0)
    assert m.sentada is None
    assert arrastrar_hasta(m, 1.2, (50, 50), (700, 410)) is None


# ── Herramienta ────────────────────────────────────────────────────────────────

class AsientoFalso:
    def __init__(self, ok=True):
        self.ok = ok
        self.llamadas = []

    def sentar(self, sitio):
        self.llamadas.append(("sentar", sitio))
        return (self.ok, "Me senté en la barra de tareas." if self.ok else "Ahora no puedo: hay un juego delante.")

    def bajar(self, motivo="usuario"):
        self.llamadas.append(("bajar", motivo))
        return self.ok


def test_herramienta_con_en_ui():
    a, hilos = AsientoFalso(), []

    def en_ui(fn):
        hilos.append("ui")
        return fn()
    assert na.herramienta({"sitio": "barra"}, {"asiento": a, "en_ui": en_ui}) == "Me senté en la barra de tareas."
    assert na.herramienta({"sitio": "bajar"}, {"asiento": a, "en_ui": en_ui}) == "Vale, ya me bajé."
    assert a.llamadas == [("sentar", "barra"), ("bajar", "usuario")] and hilos == ["ui", "ui"]


def test_herramienta_errores():
    assert na.herramienta({"sitio": "barra"}, {}) == (False, na.TEXTO_SIN_CONTROL)
    assert na.herramienta({"sitio": "techo"}, {"asiento": AsientoFalso()})[0] is False
    no = AsientoFalso(ok=False)
    assert na.herramienta({"sitio": "ventana"}, {"asiento": no}) == (False, "Ahora no puedo: hay un juego delante.")
    assert na.herramienta({"sitio": "bajar"}, {"asiento": no}) == "No estaba sentada."
    assert na.herramienta({"sitio": "barra"}, {"contexto": {"asiento": AsientoFalso()}}) == \
        "Me senté en la barra de tareas."

    def en_ui_caida(fn):
        raise TimeoutError("la interfaz no respondió a tiempo")
    ok, texto = na.herramienta({"sitio": "barra"}, {"asiento": AsientoFalso(), "en_ui": en_ui_caida})
    assert ok is False and "no respondió" in texto
