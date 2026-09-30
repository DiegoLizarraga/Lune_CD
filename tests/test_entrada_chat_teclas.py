"""
Tests de ui/entrada_chat.py: la cajita para escribirle a Lune desde la asistente.

Sin red ni pantalla (QT_QPA_PLATFORM=offscreen). Lo principal es la función pura
`manejar_tecla` (Enter envía, Shift+Enter salta de línea, Esc cierra) y la
colocación junto a la asistente (`posicion_junto_a`). Con la ventana de verdad se
comprueban las banderas (acepta foco: sin WindowDoesNotAcceptFocus), el ancho
mínimo de 280 px, que las teclas lleguen a la caja por el filtro de eventos y el
precalentado de Ollama con un POST falso (nada sale a la red).
"""
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import QRect, Qt  # noqa: E402

from ui import entrada_chat as ec  # noqa: E402

K = Qt.Key
M = Qt.KeyboardModifier


# ── manejar_tecla (pura) ──────────────────────────────────────────────────────

@pytest.mark.parametrize("tecla,mods,texto,esperado", [
    (K.Key_Return, M.NoModifier, "hola", "enviar"),
    (K.Key_Enter, M.KeypadModifier, "hola", "enviar"),          # Enter del numérico
    (K.Key_Return, M.ControlModifier, "hola", "enviar"),
    (K.Key_Return, M.NoModifier, "", None),                     # vacío: no envía
    (K.Key_Return, M.NoModifier, "  \n\t ", None),              # solo espacios tampoco
    (K.Key_Return, M.ShiftModifier, "hola", "salto"),
    (K.Key_Return, M.ShiftModifier, "", "salto"),               # salto aunque esté vacío
    (K.Key_Enter, M.ShiftModifier | M.KeypadModifier, "x", "salto"),
    (K.Key_Return, M.AltModifier, "hola", None),
    (K.Key_Return, M.MetaModifier, "hola", None),
    (K.Key_Escape, M.NoModifier, "hola", "cerrar"),
    (K.Key_Escape, M.ShiftModifier, "", "cerrar"),
    (K.Key_A, M.NoModifier, "hola", None),
    (K.Key_Tab, M.NoModifier, "hola", None),
    (K.Key_Space, M.ShiftModifier, "hola", None),
])
def test_manejar_tecla(tecla, mods, texto, esperado):
    assert ec.manejar_tecla(tecla, mods, texto) == esperado


def test_manejar_tecla_acepta_enteros_y_texto_none():
    enter = int(K.Key_Return.value)
    shift = int(M.ShiftModifier.value)
    assert ec.manejar_tecla(enter, 0, "hola") == "enviar"
    assert ec.manejar_tecla(enter, shift, "") == "salto"
    assert ec.manejar_tecla(int(K.Key_Escape.value), 0, None) == "cerrar"
    assert ec.manejar_tecla(enter, 0, None) is None
    assert ec.manejar_tecla(None, None, "x") is None             # nada raro revienta
    assert (ec.ENVIAR, ec.SALTO, ec.CERRAR) == ("enviar", "salto", "cerrar")


# ── Colocación (pura) ─────────────────────────────────────────────────────────

PANTALLA = (0, 0, 1920, 1040)


def test_debajo_de_la_asistente_y_centrada():
    x, y = ec.posicion_junto_a((800, 300, 300, 400), (320, 60), PANTALLA)
    assert (x, y) == (800 + (300 - 320) // 2, 300 + 400 + ec.MARGEN)


def test_encima_si_no_cabe_debajo():
    x, y = ec.posicion_junto_a((800, 700, 300, 320), (320, 60), PANTALLA)
    assert y == 700 - ec.MARGEN - 60


def test_siempre_dentro_de_la_pantalla():
    # Asistente pegada a la esquina superior izquierda y más alta que la pantalla.
    x, y = ec.posicion_junto_a((-50, -30, 100, 2000), (320, 60), PANTALLA)
    assert 0 <= x <= 1920 - 320 and 0 <= y <= 1040 - 60
    # Pantalla secundaria a la izquierda (coordenadas negativas).
    x, y = ec.posicion_junto_a((-300, 100, 250, 300), (320, 60), (-1920, 0, 1920, 1080))
    assert -1920 <= x <= -320 and y == 100 + 300 + ec.MARGEN


def test_sin_ancla_esquina_inferior_derecha():
    x, y = ec.posicion_junto_a(None, (320, 60), (100, 50, 1000, 700))
    assert (x, y) == (100 + 1000 - 320 - 2 * ec.MARGEN, 50 + 700 - 60 - 2 * ec.MARGEN)


def test_preferencias_laterales_y_qrect():
    ancla = QRect(400, 300, 200, 200)
    x, y = ec.posicion_junto_a(ancla, (300, 100), PANTALLA, ("derecha", "izquierda"))
    assert (x, y) == (400 + 200 + ec.MARGEN, 300 + (200 - 100) // 2)
    # Pegada al borde derecho: a la izquierda.
    x, _ = ec.posicion_junto_a((1700, 300, 200, 200), (300, 100), PANTALLA, ("derecha", "izquierda"))
    assert x == 1700 - ec.MARGEN - 300
    # Preferencias desconocidas: debajo.
    _, y = ec.posicion_junto_a((400, 300, 200, 200), (300, 100), PANTALLA, ("diagonal",))
    assert y == 300 + 200 + ec.MARGEN


def test_rgba():
    assert ec.rgba("#0F1424", 0.96) == "rgba(15, 20, 36, 245)"
    assert ec.rgba("FFFFFF", 2) == "rgba(255, 255, 255, 255)"
    assert ec.rgba("#000000", -1) == "rgba(0, 0, 0, 0)"


# ── Ventana ───────────────────────────────────────────────────────────────────

@pytest.fixture
def caja(qapp, monkeypatch):
    activadas = []
    real = ec.traer_al_frente

    def espia(v):
        activadas.append(v)
        real(v)

    monkeypatch.setattr(ec, "traer_al_frente", espia)
    w = ec.EntradaChat(cerrar_al_perder_foco=False)
    w.activadas = activadas
    enviados = []
    w.enviado.connect(enviados.append)
    w.enviados = enviados
    yield w
    w.hide()
    w.deleteLater()
    qapp.processEvents()


def test_banderas_acepta_foco_y_ancho_minimo(caja):
    f = caja.windowFlags()
    assert f & Qt.WindowType.Tool
    assert f & Qt.WindowType.FramelessWindowHint
    assert f & Qt.WindowType.WindowStaysOnTopHint
    assert not (f & Qt.WindowType.WindowDoesNotAcceptFocus), "es la única ventana que acepta foco"
    assert caja.minimumWidth() >= 280 == ec.ANCHO_MIN
    assert not caja.testAttribute(Qt.WidgetAttribute.WA_QuitOnClose)


def test_mostrar_junto_a_ancla_ancho_y_activa(caja):
    from ui.entrada_chat import pantalla_disponible
    ancla = QRect(200, 100, 150, 200)                 # asistente estrecha
    caja.mostrar_junto_a(ancla)
    assert caja.isVisible()
    assert caja.width() >= 280
    assert caja.activadas == [caja], "activateWindow al abrir"
    pant = pantalla_disponible(ancla)
    esperado = ec.posicion_junto_a(ancla, (caja.width(), caja.sizeHint().height()), pant)
    assert (caja.x(), caja.y()) == esperado
    # Una asistente muy ancha no la estira más allá de ANCHO_MAX.
    caja.mostrar_junto_a((0, 0, 2000, 300))
    assert caja.width() == ec.ANCHO_MAX
    # Con texto inicial (p. ej. desde un atajo).
    caja.mostrar_junto_a(None, texto="/voz")
    assert caja.texto() == "/voz"


def test_enter_envia_limpia_y_cierra(caja):
    from PyQt6.QtTest import QTest
    caja.mostrar_junto_a((300, 300, 300, 300))
    QTest.keyClicks(caja.caja, "  hola Lune  ")
    QTest.keyClick(caja.caja, K.Key_Return)
    assert caja.enviados == ["hola Lune"]
    assert caja.texto() == ""
    assert not caja.isVisible(), "cerrar_al_enviar"


def test_shift_enter_salta_de_linea_y_enter_vacio_no_hace_nada(caja):
    from PyQt6.QtTest import QTest
    caja.mostrar_junto_a((300, 300, 300, 300))
    QTest.keyClick(caja.caja, K.Key_Return)             # vacío: ni envía ni mete salto
    assert caja.enviados == [] and caja.texto() == ""
    QTest.keyClicks(caja.caja, "uno")
    QTest.keyClick(caja.caja, K.Key_Return, M.ShiftModifier)
    QTest.keyClicks(caja.caja, "dos")
    assert caja.texto() == "uno\ndos"
    assert caja.enviados == [] and caja.isVisible()
    QTest.keyClick(caja.caja, K.Key_Return, M.AltModifier)   # Alt+Enter: se traga
    assert caja.texto() == "uno\ndos"
    QTest.keyClick(caja.caja, K.Key_Enter, M.KeypadModifier)
    assert caja.enviados == ["uno\ndos"]


def test_esc_cierra_y_conserva_el_borrador(caja):
    from PyQt6.QtTest import QTest
    cerrados = []
    caja.cerrado.connect(lambda: cerrados.append(1))
    caja.mostrar_junto_a((300, 300, 300, 300))
    QTest.keyClicks(caja.caja, "a medias")
    QTest.keyClick(caja.caja, K.Key_Escape)
    assert not caja.isVisible() and cerrados == [1]
    assert caja.enviados == []
    caja.mostrar_junto_a((300, 300, 300, 300))
    assert caja.texto() == "a medias"


def test_texto_largo_se_recorta(caja):
    caja.caja.setPlainText("x" * (ec.MAX_CARACTERES + 50))
    assert caja.enviar() is True
    assert len(caja.enviados[0]) == ec.MAX_CARACTERES
    assert caja.enviar() is False                        # ya vacía


def test_sin_cerrar_al_enviar(qapp):
    w = ec.EntradaChat(cerrar_al_enviar=False, cerrar_al_perder_foco=False)
    try:
        w.mostrar_junto_a((300, 300, 300, 300))
        w.caja.setPlainText("hola")
        assert w.enviar() and w.isVisible()
    finally:
        w.hide()
        w.deleteLater()


# ── Precalentar (POST falso) ──────────────────────────────────────────────────

class _Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _esperar(w, qapp):
    if w._hilo_pre is not None:
        w._hilo_pre.join(5)
    for _ in range(5):
        qapp.processEvents()


def test_precalentar_ok(qapp):
    llamadas = []
    listo = threading.Event()

    def poster(url, cuerpo, timeout):
        assert listo.wait(5)
        llamadas.append((url, cuerpo, timeout))
        return 200

    reloj = _Reloj()
    w = ec.EntradaChat(poster=poster, reloj=reloj, cerrar_al_perder_foco=False)
    try:
        assert w.precalentar("http://127.0.0.1:11434/", "qwen2.5:7b") is True
        assert w.estado.text() == ec.TEXTO_DESPERTANDO and not w.estado.isHidden()
        assert w.precalentar("http://127.0.0.1:11434", "qwen2.5:7b") is False, "ya hay uno en curso"
        listo.set()
        _esperar(w, qapp)
        assert llamadas == [("http://127.0.0.1:11434/api/generate",
                             {"model": "qwen2.5:7b", "keep_alive": "30m", "stream": False},
                             ec.TIMEOUT_PRECALENTAR_S)]
        assert w.estado.isHidden() and not w.ayuda.isHidden()
        # Recién precalentado: no se repite hasta PRECALENTAR_VALIDO_S.
        assert w.precalentar("http://127.0.0.1:11434", "qwen2.5:7b") is False
        reloj.t += ec.PRECALENTAR_VALIDO_S + 1
        assert w.precalentar("http://127.0.0.1:11434", "qwen2.5:7b") is True
        _esperar(w, qapp)
        # Otro modelo sí se precalienta aunque el anterior esté reciente.
        assert w.precalentar("http://127.0.0.1:11434", "llama3.2:3b") is True
        _esperar(w, qapp)
        assert len(llamadas) == 3
    finally:
        w.deleteLater()


def test_precalentar_falla_sin_lanzar(qapp):
    def poster(url, cuerpo, timeout):
        raise OSError("conexión rechazada")

    w = ec.EntradaChat(poster=poster, reloj=_Reloj(), cerrar_al_perder_foco=False)
    try:
        assert w.precalentar("http://192.0.2.1:11434", "qwen2.5:7b") is True
        _esperar(w, qapp)
        assert w.estado.text() == ec.TEXTO_NO_DESPIERTA
        # Como no se logró, se puede volver a intentar enseguida.
        assert w.precalentar("http://192.0.2.1:11434", "qwen2.5:7b") is True
        _esperar(w, qapp)
    finally:
        w.deleteLater()


def test_precalentar_codigo_http_de_error(qapp):
    w = ec.EntradaChat(poster=lambda u, c, t: 404, reloj=_Reloj(), cerrar_al_perder_foco=False)
    try:
        assert w.precalentar("http://127.0.0.1:11434", "no-existe") is True
        _esperar(w, qapp)
        assert w.estado.text() == ec.TEXTO_NO_DESPIERTA
    finally:
        w.deleteLater()


@pytest.mark.parametrize("url,modelo", [
    ("", "qwen2.5:7b"), ("127.0.0.1:11434", "qwen2.5:7b"), ("file:///C:/x", "qwen2.5:7b"),
    ("http://127.0.0.1:11434", ""), ("http://127.0.0.1:11434", "   "), (None, None),
])
def test_precalentar_datos_no_validos(qapp, url, modelo):
    llamadas = []
    w = ec.EntradaChat(poster=lambda *a: llamadas.append(a) or 200, cerrar_al_perder_foco=False)
    try:
        assert w.precalentar(url, modelo) is False
        assert w._hilo_pre is None and llamadas == []
        assert w.estado.isHidden()
    finally:
        w.deleteLater()
