"""
Tests de ui/aprobacion_qt.py: el «¿Lo hago?» junto a la asistente cuando la
ventana principal no está a la vista.

Sin pantalla (QT_QPA_PLATFORM=offscreen) y con un reloj falso para la cuenta
atrás. Se comprueba: texto del modelo siempre plano y limpio (sin control, bidi
ni ancho cero; recortado), la señal `resuelto` una sola vez, que sin respuesta
en 60 s sea NO, que «Sí, hazlo» no cuente antes de armarse, que Esc/cerrar sean
NO, que `descartar()` no emita y que acepte foco con «No» enfocado.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import QRect, Qt  # noqa: E402

from ui import aprobacion_qt as aq  # noqa: E402
from ui.theme import COLORS  # noqa: E402


# ── Texto seguro (puro) ───────────────────────────────────────────────────────

def test_limpiar_quita_control_bidi_y_ancho_cero():
    sucio = "abrir‮​⁦ gpj.exe\x00\x07\x1b[31m"
    assert aq.limpiar(sucio, 100) == "abrir gpj.exe[31m"
    assert aq.limpiar("línea 1\r\nlínea 2\rlínea 3 fin", 100) == \
        "línea 1 ⏎ línea 2 ⏎ línea 3 ⏎ fin"
    assert aq.limpiar("\ttab\t", 100) == "tab"
    assert aq.limpiar(None, 10) == "" and aq.limpiar(42, 10) == "42"


def test_limpiar_recorta_con_puntos():
    assert aq.limpiar("x" * 50, 10) == "x" * 9 + "…"
    assert len(aq.limpiar("y" * 500, aq.MAX_RESUMEN)) == aq.MAX_RESUMEN
    assert aq.limpiar("corto", 10) == "corto"


def test_formatear_args():
    assert aq.formatear_args(None) == "" and aq.formatear_args({}) == "" and aq.formatear_args([]) == ""
    texto = aq.formatear_args({"app": "notepad", "segundos": 30, "extra": {"a": [1, 2]}, "ok": True})
    assert texto.split("\n") == ["app: notepad", "segundos: 30", 'extra: {"a": [1, 2]}', "ok: true"]
    # Valores largos y con saltos: una línea por clave, recortada.
    largo = aq.formatear_args({"orden": "a\nb" + "z" * 400})
    assert "\n" not in largo and largo.startswith("orden: a ⏎ b") and largo.endswith("…")
    assert len(largo) <= len("orden: ") + aq.MAX_VALOR
    # Demasiadas claves.
    muchas = aq.formatear_args({f"k{i}": i for i in range(aq.MAX_LINEAS_ARGS + 3)})
    assert muchas.split("\n")[-1] == "… (3 más)"
    # Tope total.
    assert len(aq.formatear_args({f"k{i}": "v" * 150 for i in range(10)})) <= aq.MAX_ARGS
    # No dict: JSON en una línea.
    assert aq.formatear_args(["a", 1]) == '["a", 1]'
    # Claves con control también se limpian; valores no serializables no revientan.
    assert aq.formatear_args({"a‮b": object()}).startswith("ab: ")


def test_color_riesgo_y_cuenta():
    assert aq.color_riesgo("LECTURA") == COLORS["accent"]
    assert aq.color_riesgo("escritura") == COLORS["yellow"]
    assert aq.color_riesgo("PELIGROSO") == COLORS["error"]
    assert aq.color_riesgo("") == COLORS["text_muted"]
    assert aq.color_riesgo(None) == COLORS["text_muted"]
    assert aq.texto_cuenta(60) == "Si no contestas, en 60 s será que no"
    assert aq.texto_cuenta(-3).endswith(" 0 s será que no")


# ── Ventana ───────────────────────────────────────────────────────────────────

class _Reloj:
    def __init__(self):
        self.t = 5000.0

    def __call__(self):
        return self.t


@pytest.fixture
def crear(qapp):
    creados = []

    def _crear(herramienta="lanzar_app", resumen="Abrir el Bloc de notas",
               args=None, **kw):
        kw.setdefault("autodestruir", False)
        kw.setdefault("reloj", _Reloj())
        d = aq.DialogoAprobacion(herramienta, resumen,
                                 {"app": "notepad"} if args is None else args, **kw)
        d.emitidos = []
        d.resuelto.connect(d.emitidos.append)
        creados.append(d)
        return d

    yield _crear
    for d in creados:
        d._t_cuenta.stop()
        d._t_armado.stop()
        d.hide()
        d.deleteLater()
    qapp.processEvents()


def test_banderas_y_texto_plano(crear):
    d = crear("<b>lanzar_app</b>", "<img src=x onerror=alert(1)> abre‮ algo",
              {"app": "<i>notepad</i>"}, riesgo="escritura")
    f = d.windowFlags()
    assert f & Qt.WindowType.Tool
    assert f & Qt.WindowType.FramelessWindowHint
    assert f & Qt.WindowType.WindowStaysOnTopHint
    assert not (f & Qt.WindowType.WindowDoesNotAcceptFocus), "tiene que aceptar foco"
    for e in (d.titulo, d.etiqueta_riesgo, d.etiqueta_herramienta, d.etiqueta_resumen,
              d.etiqueta_args, d.etiqueta_cuenta):
        assert e.textFormat() == Qt.TextFormat.PlainText
    assert d.etiqueta_herramienta.text() == "<b>lanzar_app</b>"      # literal, sin HTML
    assert d.etiqueta_resumen.text() == "<img src=x onerror=alert(1)> abre algo"
    assert d.etiqueta_args.text() == "app: <i>notepad</i>"
    assert d.etiqueta_riesgo.text() == "ESCRITURA"
    assert d.boton_si.text() == "Sí, hazlo" and d.boton_no.text() == "No"
    assert d.etiqueta_cuenta.text() == aq.texto_cuenta(60)
    assert d.resultado is None


def test_etiquetas_vacias_se_ocultan(crear):
    d = crear("", "", {})
    assert d.herramienta == "herramienta"
    assert d.etiqueta_resumen.isHidden() and d.etiqueta_args.isHidden()
    assert d.etiqueta_riesgo.isHidden()


def test_si_no_cuenta_hasta_armarse_y_se_emite_una_vez(crear):
    d = crear(armado_ms=700)
    assert not d.armada() and not d.boton_si.isEnabled()
    assert d.resolver(True) is False                  # un clic que iba a otra cosa
    d.boton_si.click()                                # desactivado: no hace nada
    assert d.emitidos == [] and d.resultado is None
    d._armar()
    assert d.armada()
    assert d.resolver(True) is True
    assert d.emitidos == [True] and d.resultado is True
    assert d.resolver(False) is False and d.resolver(True) is False
    d.close()                                         # cerrar después tampoco emite
    assert d.emitidos == [True]
    assert not d.boton_si.isEnabled() and not d.boton_no.isEnabled()


def test_boton_no(crear):
    d = crear()
    d.boton_no.click()
    assert d.emitidos == [False] and d.resultado is False
    assert d.isHidden()


def test_armado_empieza_al_mostrarse(crear):
    from PyQt6.QtTest import QTest
    d = crear(armado_ms=50)
    assert not d._t_armado.isActive()
    d.mostrar_junto_a(QRect(300, 300, 200, 300))
    assert d._t_armado.isActive()
    QTest.qWait(150)
    assert d.armada()
    d.boton_si.click()
    assert d.emitidos == [True]


def test_sin_armado(crear):
    d = crear(armado_ms=0)
    assert d.armada()
    assert d.resolver(True) and d.emitidos == [True]


def test_cuenta_atras_60s_es_no(crear):
    reloj = _Reloj()
    d = crear(reloj=reloj, armado_ms=0)
    assert d.restante() == 60
    reloj.t += 20.4
    d._tick()
    assert d.etiqueta_cuenta.text() == aq.texto_cuenta(40)
    assert d.emitidos == []
    reloj.t += 39.5
    d._tick()
    assert d.restante() == 1 and d.emitidos == []
    reloj.t += 0.2
    d._tick()
    assert d.emitidos == [False] and d.resultado is False
    d._tick()
    assert d.emitidos == [False]


def test_cuenta_atras_con_el_temporizador_de_verdad(crear):
    from PyQt6.QtTest import QTest
    reloj = _Reloj()
    d = crear(reloj=reloj, segundos=60)
    assert d._t_cuenta.isActive() and d._t_cuenta.interval() == aq.TICK_MS
    reloj.t += 61
    QTest.qWait(aq.TICK_MS * 2 + 100)
    assert d.emitidos == [False]
    assert not d._t_cuenta.isActive()


def test_segundos_minimo_1(crear):
    reloj = _Reloj()
    d = crear(reloj=reloj, segundos=0)
    assert d.restante() == 1


def test_esc_y_cerrar_son_no(crear):
    from PyQt6.QtTest import QTest
    d = crear()
    d.mostrar_junto_a(None)
    QTest.keyClick(d.boton_no, Qt.Key.Key_Escape)
    assert d.emitidos == [False]

    d2 = crear()
    d2.mostrar_junto_a(None)
    d2.close()                                        # Alt+F4
    assert d2.emitidos == [False] and d2.resultado is False


def test_enter_con_foco_en_no_no_aprueba(crear):
    from PyQt6.QtTest import QTest
    d = crear(armado_ms=0)
    d.mostrar_junto_a((300, 300, 200, 300))
    QTest.keyClick(d.boton_no, Qt.Key.Key_Return)
    QTest.keyClick(d.boton_no, Qt.Key.Key_Enter)
    assert d.emitidos == []                           # Enter no pulsa nada
    QTest.keyClick(d.boton_no, Qt.Key.Key_Space)      # Espacio pulsa «No»
    assert d.emitidos == [False]


def test_descartar_no_emite(crear):
    d = crear()
    d.mostrar_junto_a(None)
    d.descartar()
    assert d.emitidos == [] and d.resultado is None and d.isHidden()
    assert d.resolver(False) is False
    d.close()
    assert d.emitidos == []
    d.mostrar_junto_a(None)                           # ya cerrada: no reaparece
    assert d.isHidden()


def test_mostrar_junto_a_la_asistente(crear):
    from ui.entrada_chat import pantalla_disponible, posicion_junto_a
    d = crear()
    ancla = QRect(400, 300, 200, 300)
    d.mostrar_junto_a(ancla)
    assert d.isVisible() and d.width() == aq.ANCHO
    esperado = posicion_junto_a(ancla, (d.width(), d.sizeHint().height()),
                                pantalla_disponible(ancla),
                                ("derecha", "izquierda", "arriba", "abajo"))
    assert (d.x(), d.y()) == esperado
    # Al lado (derecha o, si no cabe en la pantalla offscreen, izquierda): no tapa a la asistente.
    assert d.x() >= 400 + 200 or d.x() + d.width() <= 400
    assert d.focusWidget() in (None, d.boton_no)        # el foco va a «No», nunca a «Sí»
    assert d.focusWidget() is not d.boton_si


def test_autodestruir(qapp):
    from PyQt6 import sip
    d = aq.DialogoAprobacion("x", "y", {}, armado_ms=0)
    d.resolver(False)
    for _ in range(3):
        qapp.processEvents()
    from PyQt6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    assert sip.isdeleted(d)
