"""
ui/puente_tareas.py (objeto `tareas` del QWebChannel, window.luneTareas) y su montaje, 10.9.

Herméticos: la memoria es SIEMPRE MemoriaManager(path=tmp_path / "memoria.json").
  · ranuras estado/agregar/completar/al_mi_dia/quitar (JSON con {ok, error, tarea, estado}) y su validación;
  · señal `cambio` cuando la memoria cambia: el «recuerda que…» del chat, otro hilo (el hub, Telegram), otro
    proceso (patata escribe memoria.json: el sondeo lo recarga) y el cambio de día;
  · objetos borrados: el puente borrado deja de escuchar la memoria y nada revienta; cerrar() es idempotente;
  · una memoria que no sirve (doble de test) o una MemoriaRemota (usa su respaldo);
  · web_shell: `tareas` en el canal ANTES de setUrl con la MISMA memoria del puente web y fuera al liberar;
  · index.html (script y canal), paridad de ranuras/señales con el JS y el sandbox tests/js/tareas_web.test.mjs;
  · patata: /tareas, /tareas <texto>, /tareas hecha N, /tareas quita N y /ayuda.
Nada de QWebEnginePage real (tumba pytest): páginas y canal falsos.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import types
from datetime import datetime, timedelta
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
pytest.importorskip("PyQt6.QtWidgets")
try:
    import PyQt6.QtWebEngineWidgets  # noqa: E402,F401  (antes de la QApplication)
except ImportError:
    pass

from PyQt6 import sip  # noqa: E402
from PyQt6.QtCore import QCoreApplication, QObject  # noqa: E402

from nucleo.memoria import MemoriaManager  # noqa: E402
from nucleo.tareas import Tareas  # noqa: E402
from ui import puente_tareas as pt  # noqa: E402
from ui.puente_tareas import PuenteTareas, registrar_puente_tareas, resolver_memoria  # noqa: E402

from test_anfitriones_corte4 import entorno, sistema  # noqa: E402,F401  (fixtures)
from test_anfitriones_c78_int import patata_c78  # noqa: E402,F401  (fixture)

KIT = RAIZ / "ui_web" / "ui_kits" / "lune-desktop"
JSX = KIT / "extra" / "tareas.jsx"


class Reloj:
    def __init__(self, t=datetime(2026, 9, 29, 10, 0)):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def memoria(tmp_path):
    return MemoriaManager(path=tmp_path / "memoria.json")


@pytest.fixture
def reloj():
    return Reloj()


@pytest.fixture
def puente(qapp, memoria, reloj):
    p = PuenteTareas(memoria, ahora=reloj, sondeo_ms=0)
    yield p
    p.cerrar()


def procesar(qapp, veces=3):
    for _ in range(veces):
        qapp.processEvents()


def cap(senal):
    out = []
    senal.connect(out.append)
    return out


def j(s):
    return json.loads(s)


class CanalFalso(QObject):
    def __init__(self):
        super().__init__()
        self.registrados = {}

    def registerObject(self, nombre, obj):
        self.registrados[nombre] = obj

    def deregisterObject(self, obj):
        for n, o in list(self.registrados.items()):
            if o is obj:
                del self.registrados[n]


# ── Ranuras ─────────────────────────────────────────────────────────────────────

def test_estado_forma_y_fecha(puente):
    e = j(puente.estado())
    assert e["disponible"] is True
    assert e["mi_dia"] == {"fecha": "2026-09-29", "fecha_larga": "martes, 29 de septiembre", "pendientes": [], "hechas": []}
    assert e["sugerencias"] == {"ayer": [], "recientes": [], "antes": []}
    assert e["contador"] == {"hoy": 0, "total": 0}


def test_agregar_completar_mi_dia_y_quitar(puente, memoria):
    r = j(puente.agregar("  Comprar   pan  "))
    assert r["ok"] and r["error"] == "" and r["tarea"]["texto"] == "Comprar pan" and r["tarea"]["en_mi_dia"]
    tid = r["tarea"]["id"]
    assert [t["id"] for t in r["estado"]["mi_dia"]["pendientes"]] == [tid]
    assert r["estado"]["contador"] == {"hoy": 1, "total": 1}
    r = j(puente.completar(tid, True))
    assert r["ok"] and r["tarea"]["hecha"] and [t["id"] for t in r["estado"]["mi_dia"]["hechas"]] == [tid]
    r = j(puente.completar(tid, False))
    assert r["ok"] and not r["tarea"]["hecha"]
    r = j(puente.al_mi_dia(tid, False))
    assert r["ok"] and not r["tarea"]["en_mi_dia"] and [t["id"] for t in r["estado"]["sugerencias"]["recientes"]] == [tid]
    assert r["estado"]["contador"] == {"hoy": 0, "total": 1}
    r = j(puente.al_mi_dia(tid, True))
    assert r["ok"] and r["tarea"]["en_mi_dia"]
    r = j(puente.quitar(tid))
    assert r["ok"] and "tarea" not in r and r["estado"]["contador"] == {"hoy": 0, "total": 0}
    assert memoria.get_todos_recuerdos() == []


def test_validacion_de_lo_que_llega_de_la_pagina(puente, memoria):
    for malo in ("", "   ", "\x07", "x" * (pt.MAX_ENTRADA + 1)):
        r = j(puente.agregar(malo))
        assert r["ok"] is False and r["error"] and "tarea" not in r, repr(malo[:10])
    assert memoria.get_todos_recuerdos() == []
    assert len(j(puente.agregar("y" * 900))["tarea"]["texto"]) == 200
    hecho = memoria.agregar_recuerdo("me gusta el café", "preferencia")
    for rid in ("", "../x", "a b", "<x>", "z" * 41, "noexiste", hecho):
        for r in (j(puente.completar(rid, True)), j(puente.al_mi_dia(rid, True)), j(puente.quitar(rid))):
            assert r["ok"] is False and r["error"], rid
    assert memoria.buscar_recuerdo(hecho) is not None, "un recuerdo que no es tarea no se toca"


def test_memoria_que_no_sirve_y_memoria_remota(qapp, memoria):
    class MemFalsa:
        def obtener_contexto_para_prompt(self):
            return ""
    p = PuenteTareas(MemFalsa(), sondeo_ms=0)
    e = j(p.estado())
    assert e["disponible"] is False and e["contador"] == {"hoy": 0, "total": 0} and e["mi_dia"]["fecha_larga"]
    for r in (j(p.agregar("x")), j(p.completar("a1", True)), j(p.al_mi_dia("a1", True)), j(p.quitar("a1"))):
        assert r["ok"] is False and r["estado"]["disponible"] is False
    p.cerrar()
    remota = types.SimpleNamespace(respaldo=memoria, procesar_mensaje_usuario=lambda m: None)
    assert resolver_memoria(remota) is memoria
    assert resolver_memoria(None) is None and resolver_memoria(MemFalsa()) is None
    q = PuenteTareas(remota, sondeo_ms=0)
    assert q.tareas.memoria is memoria and j(q.agregar("desde el terminal"))["ok"]
    q.cerrar()


# ── Señal cambio ────────────────────────────────────────────────────────────────

def test_cambio_cuando_lune_anota_desde_el_chat(qapp, puente, memoria):
    cambios = cap(puente.cambio)
    assert memoria.procesar_mensaje_usuario("recuerda que tengo que llamar al banco") is not None
    procesar(qapp)
    assert cambios, "sale cambio"
    e = j(cambios[-1])
    assert [t["texto"] for t in e["sugerencias"]["recientes"] + e["mi_dia"]["pendientes"]] == ["tengo que llamar al banco"]
    antes = len(cambios)
    memoria.procesar_mensaje_usuario("hola, ¿qué tal?")      # conversación normal: sin cambio de recuerdos
    procesar(qapp)
    assert len(cambios) == antes


def test_cambio_desde_otro_hilo_llega_al_hilo_de_qt(qapp, puente, memoria):
    hilos = []
    puente.cambio.connect(lambda s: hilos.append(threading.current_thread() is threading.main_thread()))
    h = threading.Thread(target=lambda: memoria.agregar_recuerdo("desde el hub", "tarea"))
    h.start()
    h.join(5)
    procesar(qapp, 5)
    assert hilos and all(hilos), "la señal sale en el hilo de Qt"


def test_cambio_por_escritura_de_otro_proceso_y_por_cambio_de_dia(qapp, memoria, reloj, tmp_path):
    p = PuenteTareas(memoria, ahora=reloj, sondeo_ms=0)
    cambios = cap(p.cambio)
    otra = MemoriaManager(path=tmp_path / "memoria.json")       # patata
    Tareas(otra, ahora=reloj).agregar("desde patata")
    p._sondear()
    procesar(qapp)
    assert cambios and [t["texto"] for t in j(cambios[-1])["mi_dia"]["pendientes"]] == ["desde patata"]
    n = len(cambios)
    p._sondear()                                                # nada nuevo: nada
    procesar(qapp)
    assert len(cambios) == n
    reloj.t = reloj.t + timedelta(days=1)
    p._sondear()
    procesar(qapp)
    assert len(cambios) == n + 1
    e = j(cambios[-1])
    assert e["mi_dia"]["fecha_larga"] == "miércoles, 30 de septiembre" and e["mi_dia"]["pendientes"] == []
    assert [t["texto"] for t in e["sugerencias"]["ayer"]] == ["desde patata"]
    p.cerrar()


def test_el_sondeo_es_un_timer_hijo(qapp, memoria):
    p = PuenteTareas(memoria, sondeo_ms=pt.SONDEO_MS)
    assert p._timer.isActive() and p._timer.parent() is p
    p.cerrar()
    assert not p._timer.isActive()
    sin = PuenteTareas(object(), sondeo_ms=pt.SONDEO_MS)
    assert not sin._timer.isActive(), "sin memoria no sondea"
    sin.cerrar()


# ── Objetos borrados y cierre ───────────────────────────────────────────────────

def test_puente_borrado_deja_de_escuchar_y_no_revienta(qapp, memoria):
    p = PuenteTareas(memoria, sondeo_ms=0)
    assert len(memoria._oyentes) == 1
    sip.delete(p)
    assert memoria._oyentes == [], "se da de baja al destruirse"
    memoria.agregar_recuerdo("después", "tarea")
    procesar(qapp)
    # Un aviso ya en camino con el objeto muerto (el hilo aún no se enteró): no hace nada.
    q = PuenteTareas(memoria, sondeo_ms=0)
    oyente = q._oyente
    sip.delete(q)
    oyente("tarde")
    procesar(qapp)


def test_cerrar_es_idempotente_y_suelta_el_canal(qapp, memoria):
    canal = CanalFalso()
    p = registrar_puente_tareas(canal, memoria, sondeo_ms=0)
    assert canal.registrados == {"tareas": p} and p.parent() is canal
    cambios = cap(p.cambio)
    p.cerrar()
    p.cerrar()
    assert canal.registrados == {} and memoria._oyentes == []
    memoria.agregar_recuerdo("ya cerrado", "tarea")
    procesar(qapp)
    assert cambios == []
    assert j(p.estado())["disponible"] is False and j(p.agregar("x"))["ok"] is False
    canal.deleteLater()


# ── web_shell ───────────────────────────────────────────────────────────────────

def test_web_registra_tareas_antes_de_cargar_con_la_memoria_del_puente(entorno, sistema, tmp_path):
    from servicios.tools import ToolManager
    import test_anfitriones_corte4 as c4
    memoria = MemoriaManager(path=tmp_path / "memoria.json")
    v = entorno.ws.VentanaWeb(config=entorno.cfg, ai_manager=c4.AIFalso(), memoria=memoria, tools=ToolManager())
    try:
        assert "tareas" in v.web.objetos_al_cargar
        p = v._puente_tareas
        assert isinstance(p, PuenteTareas) and v._canal.registrados["tareas"] is p
        assert p.tareas.memoria is v.bridge.memoria is memoria, "la MISMA memoria, nunca otra instancia"
        assert j(p.agregar("desde la ventana"))["ok"]
        assert [r["contenido"] for r in memoria.get_todos_recuerdos()] == ["desde la ventana"]
        canal = v._canal
        v._liberar_todo()
        assert "tareas" not in canal.registrados and v._puente_tareas is None
        assert memoria._oyentes == [], "deja de escuchar la memoria"
        v._liberar_todo()
    finally:
        v.deleteLater()


def test_web_si_el_puente_falla_la_ventana_sigue(entorno, sistema, monkeypatch):
    def roto(*a, **k):
        raise RuntimeError("roto")
    monkeypatch.setattr(pt, "registrar_puente_tareas", roto)
    v = entorno.web()
    assert v._puente_tareas is None and "tareas" not in v.web.objetos_al_cargar
    assert "escenario" in v.web.objetos_al_cargar


# ── index.html, paridad y sandbox de JS ─────────────────────────────────────────

def _scripts(html):
    return [(m.group(1), attrs) for attrs in re.findall(r"<script\b([^>]*)>", html)
            for m in [re.search(r'src="([^"]+)"', attrs)] if m]


def test_index_html_carga_tareas_y_expone_luneTareas():
    html = (KIT / "index.html").read_text(encoding="utf-8")
    s = _scripts(html)
    i = {src: n for n, (src, _) in enumerate(s)}
    assert 'type="text/babel"' in dict(s)["extra/tareas.jsx"]
    assert i["sidebar.jsx"] < i["extra/tareas.jsx"] < i["app.jsx"] and i["extra/minecraft.jsx"] < i["extra/tareas.jsx"]
    assert "window.luneTareas = channel.objects.tareas || null;" in html
    canal = [c for c in re.findall(r"<script>(.*?)</script>", html, re.S) if "new QWebChannel" in c][0]
    assert canal.index("luneTareas") < canal.index("lune-ready"), "antes de lune-ready"


def test_jsx_clasico_por_tokens_y_sin_emojis():
    src = JSX.read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|export)\s", src, re.M)
    cuerpo = re.sub(r"^\s*/\*.*?\*/", "", src, count=1, flags=re.S).strip()
    assert cuerpo.startswith("(function () {") and cuerpo.rstrip().endswith("})();")
    assert "Object.assign(window, { TareasPanel, LuneTareas });" in src
    for prohibido in ("dangerouslySetInnerHTML", "innerHTML", "eval(", "new Function"):
        assert prohibido not in src
    assert "rgba(" not in src and not re.search(r"var\(--[a-z]+-\d+-rgb\)", src)
    assert not re.search(r"#(?:00E5FF|1E55FF|FFE000)\b", src, re.I)
    assert not re.search(r"[\U0001F300-\U0001FAFF☀-➿]", src), "sin emojis"
    barra = (KIT / "sidebar.jsx").read_text(encoding="utf-8")
    assert "ルネ</span> · ASISTENTE PERSONAL" in barra, "el subtítulo de Diego sigue igual"
    app = (KIT / "app.jsx").read_text(encoding="utf-8")
    assert "'tareas'" in re.search(r"const VISTAS_APP = \[(.*?)\];", app, re.S).group(1)


def test_paridad_de_ranuras_y_senales_con_el_js():
    meta = PuenteTareas.staticMetaObject
    ranuras, senales = set(), set()
    for i in range(meta.methodOffset(), meta.methodCount()):
        m = meta.method(i)
        nombre = bytes(m.name()).decode()
        if nombre.startswith("_"):
            continue
        (senales if m.methodType() == m.MethodType.Signal else ranuras).add(nombre)
    src = JSX.read_text(encoding="utf-8")
    assert set(re.findall(r"pedir\('([a-z_]+)'", src)) <= ranuras
    assert set(re.findall(r"conectar\('([a-z_]+)'", src)) <= senales
    js = (RAIZ / "tests" / "js" / "tareas_web.test.mjs").read_text(encoding="utf-8")
    lista = lambda n: set(re.findall(r"'([a-z_]+)'", re.search(rf"const {n} = \[(.*?)\];", js, re.S).group(1)))  # noqa: E731
    assert lista("RANURAS") == ranuras == {"estado", "agregar", "completar", "al_mi_dia", "quitar"}
    assert lista("SENALES") == senales == {"cambio"}


def test_sandbox_de_la_web_de_tareas():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node no está instalado")
    r = subprocess.run([node, "--test", "--test-reporter=tap", "tests/js/tareas_web.test.mjs"], cwd=RAIZ,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    salida = (r.stdout or "")[-6000:] + "\n" + (r.stderr or "")[-3000:]
    c = {k: int(v) for k, v in re.findall(r"^# (pass|fail|skipped|cancelled|todo) (\d+)\s*$", r.stdout or "", re.M)}
    assert r.returncode == 0 and c.get("fail", 1) == 0, f"fallaron tests de tareas_web:\n{salida}"
    assert c.get("pass", 0) >= 15, salida
    assert c.get("skipped", 0) == 0, salida


# ── patata ──────────────────────────────────────────────────────────────────────

def _cmd(p, linea):
    antes = len(p.out.getvalue())
    p.comando(linea)
    return p.out.getvalue()[antes:]


def test_patata_tareas(patata_c78, tmp_path):
    memoria = MemoriaManager(path=tmp_path / "memoria.json")
    p = patata_c78(memoria=memoria)
    assert "No tienes tareas pendientes" in _cmd(p, "/tareas")
    assert "Anotada en Mi día: Comprar pan" in _cmd(p, "/tareas   Comprar pan  ")
    Tareas(memoria).agregar("Leer un libro", mi_dia=False)
    assert "Anotada en Mi día: Llamar al banco" in _cmd(p, "/tareas Llamar al banco")
    lista = _cmd(p, "/tareas")
    lineas = [x.strip() for x in lista.splitlines()]
    assert "Mi día" in lineas and "Otras pendientes" in lineas
    assert lineas.index("1. Llamar al banco") < lineas.index("2. Comprar pan") < lineas.index("Otras pendientes") \
        < lineas.index("3. Leer un libro"), lista
    assert "/tareas hecha N" in lista
    r = _cmd(p, "/tareas hecha 2")
    assert "Hecha: Comprar pan" in r and "Te quedan 2" in r
    assert "No hay tarea 9" in _cmd(p, "/tareas hecha 9")
    assert "Quitada: Leer un libro" in _cmd(p, "/tareas quita 2")
    assert [t["texto"] for t in Tareas(memoria).pendientes()] == ["Llamar al banco"]
    assert "¡No te queda ninguna!" in _cmd(p, "/tareas hecha 1")
    assert "Anotada en Mi día: hecha la cama" in _cmd(p, "/tareas hecha la cama"), "sin número es texto"
    ayuda = _cmd(p, "/ayuda")
    assert "/tareas [texto] · /tareas hecha N · /tareas quita N" in ayuda


def test_patata_tareas_con_una_memoria_que_no_las_guarda(patata_c78):
    p = patata_c78()
    assert "no están disponibles" in _cmd(p, "/tareas")
    assert "Comando desconocido" not in _cmd(p, "/tareas algo")


def test_patata_y_la_app_comparten_tareas(qapp, patata_c78, tmp_path):
    ruta = tmp_path / "memoria.json"
    app = MemoriaManager(path=ruta)
    puente = PuenteTareas(app, sondeo_ms=0)
    cambios = cap(puente.cambio)
    p = patata_c78(memoria=MemoriaManager(path=ruta))            # otro proceso, su propio MemoriaManager
    _cmd(p, "/tareas desde la terminal")
    puente._sondear()
    procesar(qapp)
    assert cambios and [t["texto"] for t in j(cambios[-1])["mi_dia"]["pendientes"]] == ["desde la terminal"]
    assert j(puente.agregar("desde la ventana"))["ok"]
    assert "desde la ventana" in _cmd(p, "/tareas") and "desde la terminal" in _cmd(p, "/tareas")
    puente.cerrar()


def teardown_module(_):
    app = QCoreApplication.instance()
    if app is not None:
        app.processEvents()
