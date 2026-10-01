"""
/version y /actualizar en la terminal (servicios/actualizar_terminal.py y patata.py), sin red:
las búsquedas, descargas e instalaciones son funciones falsas y el trabajo corre en el mismo
hilo. También el aviso al iniciar de patata (una vez al día, nunca con un juego delante), la
ayuda (/ayuda es el docstring de patata.py) y la versión en el banner.
"""
import io
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import patata  # noqa: E402
from servicios import actualizador as A  # noqa: E402
from servicios.actualizar_terminal import ActualizacionesTerminal  # noqa: E402


class Cfg:
    def __init__(self, **act):
        self.d = {"actualizaciones": {"rama": "master", "comprobar_al_iniciar": True,
                                      "ultima_comprobacion": "", "omitir_version": "", **act}}

    def get(self, s, k, d=None):
        return self.d.get(s, {}).get(k, d)

    def set(self, s, k, v):
        self.d.setdefault(s, {})[k] = v


def rel(version="11.4", **extra):
    r = {"ok": True, "hay_novedades": True, "nueva": True, "omitida": False, "version": version,
         "notas": "Me actualizo sola.\n· y gasto menos", "pagina": A.URL_RELEASES,
         "asset": {"nombre": f"LuneCD-Setup-{version}.exe", "url": "u", "tamano": 100 * 1024 * 1024},
         "sha256": "a" * 64, "instalable": True, "mensaje": f"Hay una versión nueva de mí: la {version} (tengo la 11.3)."}
    r.update(extra)
    return r


def terminal(modo="instalada", busqueda=None, descarga=None, instalar_ok=True, en_juego=None, cfg=None, git=None):
    dichas, salidas, llamadas = [], [], []

    def buscar(m, rama=None):
        llamadas.append(("buscar", m, rama))
        return dict(busqueda if busqueda is not None else rel())

    def descargar(info, on_progreso=None, cancelar=None):
        llamadas.append(("descargar", info["version"]))
        total = info["asset"]["tamano"]
        for i in range(1, 11):
            on_progreso(total * i // 10, total)
        return descarga or {"ok": True, "ruta": "C:/x/LuneCD-Setup-11.4.exe"}

    def instalar(ruta, sha256=""):
        llamadas.append(("instalar", ruta, sha256))
        return instalar_ok

    def actualizar(rama, on_progreso=None):
        llamadas.append(("actualizar", rama))
        on_progreso("Trayendo cambios…")
        return git or {"ok": True, "actualizado": True, "requisitos_ok": True, "mensaje": "Actualizado a abc1234."}

    t = ActualizacionesTerminal(cfg or Cfg(), decir=dichas.append, salir=lambda: salidas.append(1),
                                en_juego=en_juego, modo=modo, lanzar=lambda fn: fn(),
                                funciones={"buscar": buscar, "descargar": descargar, "instalar": instalar,
                                           "actualizar": actualizar})
    return t, dichas, salidas, llamadas


def test_no_es_mio():
    t, *_ = terminal()
    assert t.comando("/voz on") is None and t.comando("") is None


def test_version(monkeypatch):
    from nucleo import rutas
    t, *_ = terminal(cfg=Cfg(ultima_comprobacion="2026-10-01T07:00:00Z", omitir_version="11.4"))
    texto = t.comando("/version")
    assert texto.startswith(f"Lune CD {A.version_actual()} · instalada")
    assert str(rutas.DATOS) in texto and "2026-10-01 07:00 UTC" in texto and "saltarte la 11.4" in texto
    t, *_ = terminal(modo="git", cfg=Cfg(comprobar_al_iniciar=False))
    texto = t.comando("/version")
    assert "desde el código (git)" in texto and "al abrirme: no" in texto


def test_buscar_hay_version_con_notas_y_apunta_la_comprobacion():
    cfg = Cfg()
    t, dichas, _, llamadas = terminal(cfg=cfg)
    assert t.comando("/actualizar") == "Busco en GitHub…"
    assert llamadas == [("buscar", "instalada", "master")]
    texto = dichas[-1]
    assert texto.startswith("Hay una versión nueva de mí: la 11.4") and "  Me actualizo sola." in texto
    assert "/actualizar instalar" in texto and "/actualizar omitir" in texto
    assert cfg.d["actualizaciones"]["ultima_comprobacion"].endswith("Z")


def test_buscar_al_dia_error_y_sin_sha():
    t, dichas, *_ = terminal(busqueda=rel("11.3", nueva=False, hay_novedades=False, mensaje="Estoy al día: tengo la 11.3."))
    t.comando("/actualizar buscar")
    assert dichas[-1] == "Estoy al día: tengo la 11.3."
    t, dichas, *_ = terminal(busqueda={"ok": False, "mensaje": "GitHub me pidió un respiro."})
    t.comando("/actualizar")
    assert dichas[-1] == "GitHub me pidió un respiro."
    t, dichas, *_ = terminal(busqueda=rel(instalable=False, sha256=""))
    t.comando("/actualizar")
    assert "falta su SHA-256" in dichas[-1]


def test_instalar_descarga_con_progreso_lanza_y_sale():
    t, dichas, salidas, llamadas = terminal()
    assert t.comando("/actualizar instalar").startswith("Voy: descargo")
    assert [x[0] for x in llamadas] == ["buscar", "descargar", "instalar"]
    assert llamadas[-1] == ("instalar", "C:/x/LuneCD-Setup-11.4.exe", "a" * 64)
    progreso = [d for d in dichas if d.startswith("Descargando…")]
    assert progreso and progreso[0].startswith("Descargando… 10 %") and len(progreso) <= 9   # una línea cada 10 %
    assert any("Abro el instalador y me cierro" in d for d in dichas)
    assert salidas == [1]


def test_instalar_reutiliza_lo_buscado_y_respeta_errores():
    t, dichas, salidas, llamadas = terminal()
    t.comando("/actualizar")
    t.comando("/actualizar instalar")
    assert [x[0] for x in llamadas] == ["buscar", "descargar", "instalar"]          # no busca dos veces
    t, dichas, salidas, llamadas = terminal(descarga={"ok": False, "mensaje": "El instalador descargado no coincide…"})
    t.comando("/actualizar instalar")
    assert dichas[-1].startswith("El instalador descargado no coincide") and salidas == []
    assert "instalar" not in [x[0] for x in llamadas]
    t, dichas, salidas, _ = terminal(instalar_ok=False)
    t.comando("/actualizar instalar")
    assert "No pude abrir el instalador" in dichas[-1] and salidas == []
    t, dichas, salidas, llamadas = terminal(busqueda=rel("11.3", nueva=False, hay_novedades=False))
    t.comando("/actualizar instalar")
    assert dichas[-1] == "Estoy al día: no hay nada que instalar." and salidas == []


def test_instalar_en_git_y_en_carpeta():
    t, dichas, salidas, llamadas = terminal(modo="git")
    assert t.comando("/actualizar instalar") == "Traigo los cambios con git…"
    assert llamadas == [("actualizar", "master")] and "Trayendo cambios…" in dichas
    assert "Ciérrame (/salir)" in dichas[-1] and salidas == []
    t, dichas, *_ = terminal(modo="git", git={"ok": False, "mensaje": "Tienes cambios sin guardar y no quiero pisártelos."})
    t.comando("/actualizar instalar")
    assert dichas[-1].startswith("Tienes cambios sin guardar")
    t, dichas, salidas, llamadas = terminal(modo="carpeta")
    assert "no se actualiza sola" in t.comando("/actualizar instalar") and llamadas == []


def test_buscar_en_git_lista_los_commits():
    git = {"ok": True, "hay_novedades": True, "commits": ["abc uno", "def dos"], "limpio": False,
           "modificados": ["main.py"], "mensaje": "Hay 2 cambio(s) nuevo(s) esperando."}
    t, dichas, *_ = terminal(modo="git", busqueda=git)
    assert t.comando("/actualizar") == "Miro el remoto de git…"
    assert "  · abc uno" in dichas[-1] and "sin guardar" in dichas[-1]


def test_omitir():
    cfg = Cfg()
    t, *_ = terminal(cfg=cfg)
    assert t.comando("/actualizar omitir").startswith("¿Cuál?")
    t.comando("/actualizar")
    assert t.comando("/actualizar omitir") == "Vale: no te aviso de la 11.4. Te digo cuando salga la siguiente."
    assert cfg.d["actualizaciones"]["omitir_version"] == "11.4"
    assert "11.5" in t.comando("/actualizar omitir v11.5") and cfg.d["actualizaciones"]["omitir_version"] == "11.5"
    assert "vuelvo a avisarte" in t.comando("/actualizar omitir ninguna") and cfg.d["actualizaciones"]["omitir_version"] == ""
    assert "no parece una versión" in t.comando("/actualizar omitir pepe")


def test_cancelar_y_uso():
    t, *_ = terminal()
    assert t.comando("/actualizar cancelar") == "No estoy descargando nada."
    assert t.comando("/actualizar algo").startswith("Uso: /actualizar")


def test_una_cosa_a_la_vez():
    trabajos = []
    t, dichas, *_ = terminal()
    t._lanzar = trabajos.append
    t.comando("/actualizar instalar")
    assert "Ya estoy descargando" in t.comando("/actualizar")
    assert t.comando("/actualizar cancelar") == "Corto la descarga…"
    trabajos.pop()()
    assert t.comando("/actualizar cancelar") == "No estoy descargando nada."


# ── Aviso al iniciar ───────────────────────────────────────────────────────────

def test_aviso_al_iniciar_una_vez_al_dia():
    cfg = Cfg()
    t, dichas, _, llamadas = terminal(cfg=cfg)
    assert t.iniciar_aviso(espera_s=0) is True
    assert dichas == ["Hay una versión nueva de mí (11.4). Escribe /actualizar para verla."]
    t2, dichas2, _, llamadas2 = terminal(cfg=cfg)
    assert t2.iniciar_aviso(espera_s=0) is False and dichas2 == [] and llamadas2 == []
    t3, *_ = terminal(cfg=Cfg(comprobar_al_iniciar=False))
    assert t3.iniciar_aviso(espera_s=0) is False


def test_aviso_al_iniciar_nunca_con_un_juego_delante():
    jugando = {"n": 0}

    def en_juego():
        jugando["n"] += 1
        return jugando["n"] <= 3                   # tres vistazos con partida, luego acaba
    cfg = Cfg()
    t, dichas, _, llamadas = terminal(cfg=cfg, en_juego=en_juego)
    esperas = []
    t._parar.wait = lambda s: esperas.append(s) or False
    t.iniciar_aviso(espera_s=45, reintento_s=60)
    assert esperas[0] == 45 and esperas.count(60) == 3          # esperó a que acabara la partida
    assert llamadas == [("buscar", "instalada", "master")] and len(dichas) == 1


def test_aviso_al_iniciar_se_para_al_salir():
    cfg = Cfg()
    t, dichas, _, llamadas = terminal(cfg=cfg, en_juego=lambda: True)
    hilo = {}
    t._lanzar = lambda fn: hilo.setdefault("h", threading.Thread(target=fn, daemon=True)).start()
    t.iniciar_aviso(espera_s=0, reintento_s=0.01)
    t.detener()
    hilo["h"].join(2)
    assert not hilo["h"].is_alive() and llamadas == [] and dichas == []


def test_sin_novedades_no_dice_nada():
    t, dichas, _, llamadas = terminal(busqueda=rel(hay_novedades=False, omitida=True))
    t.iniciar_aviso(espera_s=0)
    assert llamadas and dichas == []


# ── patata.py ──────────────────────────────────────────────────────────────────

def test_ayuda_y_banner():
    texto = patata.ayuda()
    assert "/version" in texto and "/actualizar [buscar|instalar|omitir" in texto
    from version import APP_VERSION
    assert patata._version_banner() == f"v{APP_VERSION} · "


class ActFalsa:
    def __init__(self):
        self.lineas, self.avisos, self.detenida = [], 0, False

    def comando(self, linea):
        self.lineas.append(linea)
        if linea.split()[0] in ("/version", "/actualizar"):
            return f"ok {linea}"
        return None

    def iniciar_aviso(self):
        self.avisos += 1
        return True

    def detener(self):
        self.detenida = True


@pytest.fixture
def patata_minima(tmp_path, monkeypatch):
    from test_patata import ApiFalsa, EntradaBloqueante, AIFalsa, MemFalsa
    from nucleo.config import Config
    from nucleo.consola import ConsolaAsincrona
    out = io.StringIO()
    consola = ConsolaAsincrona("tú > ", stdout=out, stdin=EntradaBloqueante(), api=ApiFalsa(), ansi=False)
    act = ActFalsa()
    p = patata.Patata(color=False, consola=consola, config=Config(str(tmp_path / "config.json")),
                      ai=AIFalsa("hola"), memoria=MemFalsa(), voice=None, tools=None, audit_path=None,
                      alarmas=None, baile=None, salvapantallas=None, comida=None, sistema=None,
                      bailes=None, minecraft=None, bienvenida=None, actualizaciones=act)
    yield p, act, out
    p.cerrar()


def test_patata_pasa_los_comandos_y_arranca_el_aviso(patata_minima):
    p, act, out = patata_minima
    assert p.comando("/version") is False and p.comando("/actualizar instalar") is False
    assert act.lineas == ["/version", "/actualizar instalar"]
    assert "ok /version" in out.getvalue() and "ok /actualizar instalar" in out.getvalue()
    assert p.iniciar_aviso_actualizacion() is True and act.avisos == 1
    p.cerrar()
    assert act.detenida


def test_patata_crea_las_de_verdad(tmp_path):
    from test_patata import ApiFalsa, EntradaBloqueante, AIFalsa, MemFalsa
    from nucleo.config import Config
    from nucleo.consola import ConsolaAsincrona
    consola = ConsolaAsincrona("tú > ", stdout=io.StringIO(), stdin=EntradaBloqueante(), api=ApiFalsa(), ansi=False)
    p = patata.Patata(color=False, consola=consola, config=Config(str(tmp_path / "config.json")),
                      ai=AIFalsa("hola"), memoria=MemFalsa(), voice=None, tools=None, audit_path=None,
                      alarmas=None, baile=None, salvapantallas=None, comida=None, sistema=None,
                      bailes=None, minecraft=None, bienvenida=None)
    try:
        assert isinstance(p.actualizaciones, ActualizacionesTerminal)
        assert p.actualizaciones.comando("/version").startswith("Lune CD ")
    finally:
        p.cerrar()


def test_main_arranca_el_aviso_antes_de_correr(monkeypatch):
    orden = []

    class P:
        def __init__(self, **k):
            pass

        def iniciar_aviso_actualizacion(self):
            orden.append("aviso")

        def correr(self):
            orden.append("correr")
            return 0
    monkeypatch.setattr(patata, "Patata", P)
    monkeypatch.setattr(patata, "_marcar_abierta", lambda: None)
    inst = type("Inst", (), {"adquirir": lambda self: True, "escuchar": lambda self, fn: True,
                             "liberar": lambda self: None})()
    assert patata.main([], instancia=inst) == 0 and orden == ["aviso", "correr"]
