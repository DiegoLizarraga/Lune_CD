"""
Tests de ui/alarmas_dialogo.py (offscreen):

- DialogoAlarma: textos por tipo, cuenta atrás del bloqueo en «Apagar (N)», botones
  desactivados y sin señal durante el bloqueo, señales después; «Posponer» oculto
  en la prueba; se coloca dentro de la pantalla;
- DialogoAlarmas (editor de la nativa) sobre un ControlAlarmasQt de verdad:
  añadir con días y «una vez», editar, encender/apagar, borrar, error visible,
  temporizadores con cuenta atrás e Iniciar/Parar, interruptor general y refresco
  con la señal `cambio`.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest.importorskip("PyQt6.QtWidgets")


class Reloj:
    def __init__(self, t=0.0):
        self.t = t

    def __call__(self):
        return self.t


def test_tarjeta_cuenta_atras_y_senales(qapp):
    from ui.alarmas_dialogo import DialogoAlarma
    r = Reloj(10.0)
    d = DialogoAlarma(reloj=r)
    senales = []
    d.apagar.connect(lambda: senales.append("apagar"))
    d.posponer.connect(lambda: senales.append("posponer"))
    d.set_disparo("gimnasio (hace 3 min)", tipo="alarma", programado="07:30", bloqueo_ms=5000,
                  posponer_min=10, cola=2)
    assert d.texto.text() == "gimnasio (hace 3 min)" and d.hora.text() == "07:30"
    assert "ALARMA" in d.titulo.text() and d.cola.text() == "+2 en espera"
    assert not d.boton_apagar.isEnabled() and d.boton_apagar.text() == "Apagar (5)"
    assert d.boton_posponer.text() == "Posponer 10 min"
    d._pulsar_apagar()
    d._pulsar_posponer()
    assert senales == []
    r.t = 12.5
    d._actualizar_bloqueo()
    assert d.boton_apagar.text() == "Apagar (3)"
    r.t = 15.0
    d._actualizar_bloqueo()
    assert d.boton_apagar.isEnabled() and d.boton_apagar.text() == "Apagar"
    d.boton_apagar.click()
    d.boton_posponer.click()
    assert senales == ["apagar", "posponer"]
    d.cerrar()
    assert not d.isVisible()


def test_tarjeta_tipos_y_prueba(qapp):
    from ui.alarmas_dialogo import DialogoAlarma
    d = DialogoAlarma(reloj=Reloj())
    d.set_disparo("", tipo="temporizador")
    assert "TEMPORIZADOR" in d.titulo.text() and d.texto.text() == "Temporizador"
    d.set_disparo("Prueba de alarma", tipo="prueba")
    assert d.boton_posponer.isHidden()
    d.set_disparo("x", tipo="alarma")
    assert not d.boton_posponer.isHidden()


def test_tarjeta_dentro_de_la_pantalla(qapp):
    from PyQt6.QtGui import QGuiApplication
    from ui.alarmas_dialogo import DialogoAlarma
    d = DialogoAlarma(reloj=Reloj())
    d.set_disparo("hola")
    d.mostrar()
    g = QGuiApplication.primaryScreen().availableGeometry()
    assert g.contains(d.frameGeometry().topLeft()) and d.isVisible()
    d.cerrar()


class Cfg:
    def __init__(self):
        self.d = {"alarmas": {"activo": True}}

    def get(self, s, k, d=None):
        return self.d.get(s, {}).get(k, d)

    def set(self, s, k, v):
        self.d.setdefault(s, {})[k] = v


@pytest.fixture
def editor(qapp, tmp_path):
    from nucleo.alarmas import Almacen
    from ui.alarmas_dialogo import DialogoAlarmas
    from ui.alarmas_qt import ControlAlarmasQt

    class Mutex:
        es_dueno = False

        def adquirir(self):
            return False

    reloj = Reloj(1_000_000.0)
    alm = Almacen(tmp_path / "alarmas.json", reloj=reloj)
    ctl = ControlAlarmasQt(None, Cfg(), almacen=alm, mutex=Mutex(), epoch=reloj, intervalo_ms=10 ** 6)
    ed = DialogoAlarmas(ctl, reloj=reloj)
    yield ed, ctl, alm, reloj
    ed.close()


def test_editor_anade_alarma_con_dias(editor):
    from PyQt6.QtCore import QTime
    ed, ctl, alm, _ = editor
    assert ed.vacio_alarmas.isVisibleTo(ed)
    ed.hora.setTime(QTime(7, 30))
    for letra in "lmxjv":
        ed.botones_dia["lmxjvsd".index(letra)].setChecked(True)
    ed.texto.setText("gimnasio")
    ed.boton_guardar.click()
    a, = alm.alarmas()
    assert (a.hhmm, a.dias, a.una_vez, a.texto) == ("07:30", 31, False, "gimnasio")
    assert "de lunes a viernes" in ed.filas_alarma[a.id]["etiqueta"].text()
    assert ed.texto.text() == "" and ed.dias_marcados() == ""


def test_editor_edita_apaga_y_borra(editor):
    from PyQt6.QtCore import QTime
    ed, ctl, alm, _ = editor
    ctl.guardar_alarma({"hora": "07:00", "texto": "viejo"})
    ed.refrescar()
    fila = ed.filas_alarma["a1"]
    fila["editar"].click()
    assert ed.boton_guardar.text() == "Guardar cambios" and ed.texto.text() == "viejo"
    ed.hora.setTime(QTime(8, 15))
    ed.una_vez.setChecked(True)
    ed.boton_guardar.click()
    a = alm.obtener("a1")
    assert (a.hhmm, a.una_vez, a.texto) == ("08:15", True, "viejo") and len(alm.alarmas()) == 1
    ed.filas_alarma["a1"]["activa"].setChecked(False)
    assert alm.obtener("a1").activa is False
    ed.filas_alarma["a1"]["borrar"].click()
    assert alm.alarmas() == []


def test_editor_muestra_error(editor):
    ed, ctl, alm, _ = editor
    for i in range(50):
        alm.crear_alarma(7, i % 60)
    ed.boton_guardar.click()
    assert ed.error.isVisibleTo(ed) and "50" in ed.error.text()


def test_editor_temporizadores(editor):
    ed, ctl, alm, reloj = editor
    ed.t_h.setValue(0)
    ed.t_m.setValue(2)
    ed.t_s.setValue(5)
    ed.t_texto.setText("té")
    ed.boton_temp.click()
    t, = alm.temporizadores()
    assert t.duracion_s == 125 and t.corriendo
    fila = ed.filas_temp[t.id]
    assert fila["cuenta"].text() == "2:05" and fila["marcha"].text() == "Parar"
    reloj.t += 65
    ed._actualizar_cuentas()
    assert fila["cuenta"].text() == "1:00"
    fila["marcha"].click()
    assert not alm.obtener(t.id).corriendo
    fila = ed.filas_temp[t.id]
    assert fila["marcha"].text() == "Iniciar" and fila["cuenta"].text() == "1:00"
    fila["reiniciar"].click()
    assert ed.filas_temp[t.id]["cuenta"].text() == "2:05"


def test_editor_interruptor_general_y_refresco(editor, tmp_path):
    from nucleo.alarmas import Almacen
    ed, ctl, alm, _ = editor
    ed.activo.setChecked(False)
    assert ctl.config.get("alarmas", "activo") is False
    Almacen(tmp_path / "alarmas.json").crear_alarma(6, 0, texto="de fuera")
    ctl._iniciado = True
    ctl._tic()                                  # detecta el cambio del archivo → señal cambio
    assert "a1" in ed.filas_alarma


# ── Revisión 4-5-6 ─────────────────────────────────────────────────────────────

def _se_ve_literal(lbl):
    """El QLabel enseña su texto tal cual: con «<b>hola</b>» dentro mide más que el mismo
    QLabel interpretándolo como HTML («hola» en negrita)."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QLabel
    assert "<b>hola</b>" in lbl.text()
    html = QLabel()
    html.setFont(lbl.font())
    html.setWordWrap(lbl.wordWrap())
    html.setTextFormat(Qt.TextFormat.AutoText)
    html.setText(lbl.text())
    assert lbl.textFormat() == Qt.TextFormat.PlainText
    assert lbl.minimumSizeHint().width() > html.minimumSizeHint().width()


def test_tarjeta_ensena_el_texto_literal_sin_html(qapp):
    """SM1: «<b>hola</b>» (o <img src=//host/x>) de alarmas.json se veía como HTML."""
    from ui.alarmas_dialogo import DialogoAlarma
    d = DialogoAlarma(reloj=Reloj())
    d.set_disparo("<b>hola</b>", tipo="alarma", programado="<b>hola</b>")
    _se_ve_literal(d.texto)
    _se_ve_literal(d.hora)
    assert d.texto.text() == "<b>hola</b>"


def test_editor_ensena_textos_literales_sin_html(editor):
    ed, ctl, alm, _ = editor
    a = alm.crear_alarma(7, 0, texto="<b>hola</b>")
    t = alm.crear_temporizador(60, "<b>hola</b>", iniciar=False)
    ed.refrescar()
    _se_ve_literal(ed.filas_alarma[a.id]["etiqueta"])
    assert "<b>hola</b>" in ed.filas_alarma[a.id]["etiqueta"].text()
    _se_ve_literal(ed.filas_temp[t.id]["etiqueta"])
    ed._mostrar_error("<b>hola</b>")
    _se_ve_literal(ed.error)


def test_editor_dice_la_fecha_y_al_ponerle_dias_la_quita(editor):
    """MO3: editar «mañana a las 7» y ponerle días dejaba la fecha oculta (no volvía a
    sonar nunca). El editor enseña la fecha y, al guardar con días, se quita."""
    ed, ctl, alm, _ = editor
    a = alm.crear_alarma(7, 0, fecha="2026-09-27")
    ed.refrescar()
    assert "27/09" in ed.filas_alarma[a.id]["etiqueta"].text() or "mañana" in ed.filas_alarma[a.id]["etiqueta"].text()
    ed.filas_alarma[a.id]["editar"].click()
    assert ed.nota_fecha.isVisibleTo(ed) and "27/09/2026" in ed.nota_fecha.text()
    for letra in "lmxjv":
        ed.botones_dia["lmxjvsd".index(letra)].setChecked(True)
    ed.una_vez.setChecked(False)
    ed.boton_guardar.click()
    x = alm.obtener(a.id)
    assert (x.fecha, x.dias, x.una_vez) == ("", 31, False)
    assert not ed.nota_fecha.isVisibleTo(ed)
