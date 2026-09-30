"""
Cambio de modo de interfaz en caliente, integración (fase 2): la nativa
(main.LuneCDWindow), el puente web (ui/web_bridge.py), las órdenes de Telegram que
se quedarían sin respuesta, el gancho del corte 4 y los Ajustes de la nativa.

Con dobles: nada de ventanas reales, ni Telegram, ni datos.json / config.json /
chats/ reales (carpetas temporales).
"""
import json
import shutil
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

try:
    # QtWebEngine tiene que importarse ANTES de crear la QApplication (fixture qapp).
    import PyQt6.QtWebEngineWidgets  # noqa: F401
except ImportError:
    pass

import ui.cambio_interfaz as ci
from test_cambio_interfaz import (ControladorFalso, HiloFalso, SenalFalsa,  # noqa: F401
                                  _puente_falso, _ventana_web_falsa, ws)
from test_settings_voz_compat import panel  # noqa: F401  (fixture)

RAIZ = Path(__file__).resolve().parent.parent


# ── La web: órdenes de Telegram y corte 4 ─────────────────────────────────────────
def test_ventana_web_contesta_las_ordenes_cortadas_y_desmonta_el_corte_4(qapp, ws, monkeypatch):
    monkeypatch.setattr(ws, "QApplication", types.SimpleNamespace(
        instance=lambda: types.SimpleNamespace(quit=lambda: None)))
    b, _prov, hechos, _ = _puente_falso(qapp)
    worker, tg = b._worker, b._tg_worker
    tg.stop = lambda: hechos.append("tg.stop")
    b._turno = {"remoto": "o1"}                            # orden respondiéndose ahora…
    b._ultima_orden_tg = "o2"                              # …y otra esperando tu permiso
    b.acciones = types.SimpleNamespace(cerrar=lambda: hechos.append("acciones.cerrar"),
                                       pendientes=lambda: [{"id": "p1", "remoto": True}])
    b._responder_telegram = lambda oid, texto: hechos.append(("tg", oid, texto))
    yo, _ = _ventana_web_falsa(ws, b, hechos)
    yo._avisar_ordenes_cortadas = ws.VentanaWeb._avisar_ordenes_cortadas
    yo._servicios_c4 = types.SimpleNamespace(desmontar=lambda: hechos.append("c4.desmontar"))
    yo.cerrar_para_cambio()
    from servicios.telegram_worker import AVISO_TG_DETENIDA
    avisos = [h for h in hechos if isinstance(h, tuple)]
    assert avisos == [("tg", "o1", AVISO_TG_DETENIDA), ("tg", "o2", AVISO_TG_DETENIDA)]
    i = hechos.index
    assert i(avisos[-1]) < i("acciones.cerrar") and i(avisos[-1]) < i("tg.stop")
    assert i("c4.desmontar") < i("tray.hide") and yo._servicios_c4 is None
    for h in (worker, tg):
        h.terminar()


def test_ordenes_cortadas():
    assert ci.ordenes_cortadas({"remoto": "a"}, True, [], "a") == ["a"]
    assert ci.ordenes_cortadas({"remoto": "a"}, False, [], "a") == []        # ya respondió
    assert ci.ordenes_cortadas({}, False, [{"remoto": True}], "b") == ["b"]
    assert ci.ordenes_cortadas({"remoto": "a"}, True, [{"remoto": True}], "a") == ["a"]
    assert ci.ordenes_cortadas(None, True, [{"x": 1}], "") == []


def test_desmontar_servicios_c4_es_tolerante():
    hechos = []
    con = types.SimpleNamespace(_servicios_c4=types.SimpleNamespace(desmontar=lambda: hechos.append(1)))
    roto = types.SimpleNamespace(_servicios_c4=types.SimpleNamespace(desmontar=lambda: 1 / 0))
    sin = types.SimpleNamespace()
    ci.desmontar_servicios_c4(con, roto, sin, None)
    assert hechos == [1] and con._servicios_c4 is None and roto._servicios_c4 is None


def test_detener_bot_desconecta_las_ordenes():
    tg = HiloFalso()
    tg.orden_recibida = SenalFalsa()
    assert ci.detener_bot(tg, espera_ms=1) is True and tg.orden_recibida.desconectada
    tg.terminar()


# ── La nativa (main.LuneCDWindow) ─────────────────────────────────────────────────
@pytest.fixture
def main_mod():
    import main
    return main


def _nativa_falsa(main_mod, hechos, carpeta):
    from nucleo.conversaciones import GestorConversaciones
    from ui.escritorio import ServiciosEscritorio
    esc = ServiciosEscritorio(None)
    atajos = ControladorFalso()
    esc.registrar("atajos", atajos)
    esc.iniciar()
    prov = types.SimpleNamespace(cancel_flag=False)
    tg = HiloFalso()
    tg.responder_orden = lambda oid, texto: hechos.append(("tg", oid, texto)) or True
    tg.stop = lambda: hechos.append("tg.stop")
    ov = types.SimpleNamespace(cerrado=False, isVisible=lambda: True, visibilidad=SenalFalsa(),
                               close=lambda: hechos.append("asistente.close"), deleteLater=lambda: None)
    boton = types.SimpleNamespace(hide=lambda: None, show=lambda: None, setEnabled=lambda v: None)
    yo = types.SimpleNamespace(
        _gen=1, ai_worker=HiloFalso(), ai_manager=types.SimpleNamespace(providers={"ollama": prov}),
        current_provider="ollama", _turno={"remoto": "o1", "proveedor": "ollama"},
        _ultima_orden_tg="o2", _esperando_corte=False, _typing_indicator=None, _current_bubble=None,
        _seguidor=None, _voz_stream=None, _timers_plan=[], stop_btn=boton, send_btn=boton,
        input_field=boton, _set_status=lambda *a: None,
        acciones=types.SimpleNamespace(cerrar=lambda: hechos.append("acciones.cerrar"),
                                       pendientes=lambda: [{"remoto": True}]),
        voice=types.SimpleNamespace(cancelar=lambda: hechos.append("voz.cancelar"),
                                    al_hablar=print, on_error=print, _enabled=True, available=True),
        _grabadora=None, _transcriptor=None, _sondeo_prov=None,
        _timer_estado=types.SimpleNamespace(stop=lambda: hechos.append("timer.stop")),
        lune_face=types.SimpleNamespace(_player=types.SimpleNamespace(stop=lambda: hechos.append("video.stop"))),
        chats=GestorConversaciones(directorio=carpeta / "chats"),
        notas=types.SimpleNamespace(cerrar=lambda: hechos.append("notas.cerrar")),
        red=types.SimpleNamespace(detener=lambda: hechos.append("red.detener")),
        _overlay=ov, _tg_worker=tg, escritorio=esc,
        _hub_cliente=types.SimpleNamespace(detener=lambda: hechos.append("hub_cliente.detener")),
        _hub_en_hilo=types.SimpleNamespace(detener=lambda: hechos.append("hub.detener")),
        tray=types.SimpleNamespace(contextMenu=lambda: None, hide=lambda: hechos.append("tray.hide"),
                                   deleteLater=lambda: None),
        _servicios_c4=types.SimpleNamespace(desmontar=lambda: hechos.append("c4.desmontar")),
        hide=lambda: hechos.append("hide"), close=lambda: hechos.append("close"),
        MODO_INTERFAZ="nativo", _relevada=False, _servicios_listos=True)
    W = main_mod.LuneCDWindow
    for n in ("cerrar_para_cambio", "_cortar_respuesta", "_worker_vivo", "_cancelar_worker",
              "_cancelar_plan", "_asistente_viva", "_responder_telegram", "_asistente_a_la_vista",
              "estado_para_cambio", "aplicar_estado", "iniciar_servicios", "cambio_fallido",
              "closeEvent"):
        setattr(yo, n, types.MethodType(getattr(W, n), yo))
    return yo, prov, atajos


def test_nativa_cerrar_para_cambio_suelta_todo_sin_salir(qapp, main_mod, monkeypatch, tmp_path):
    salidas = []
    monkeypatch.setattr(main_mod, "QApplication", types.SimpleNamespace(quit=lambda: salidas.append(1)))
    hechos = []
    yo, prov, atajos = _nativa_falsa(main_mod, hechos, tmp_path)
    worker, tg = yo.ai_worker, yo._tg_worker
    en_marcha = yo.cerrar_para_cambio()
    assert en_marcha == {"asistente_fuera": True, "telegram": True}
    # Órdenes de Telegram: la que se respondía (o1) y la que esperaba permiso (o2).
    from servicios.telegram_worker import AVISO_TG_DETENIDA
    avisos = [h for h in hechos if isinstance(h, tuple)]
    assert sorted(avisos) == [("tg", "o1", AVISO_TG_DETENIDA), ("tg", "o2", AVISO_TG_DETENIDA)]
    assert max(hechos.index(a) for a in avisos) < hechos.index("tg.stop")
    # IA cortada sin ejecutar nada (señales fuera) y el hilo retenido; aprobaciones cerradas.
    assert prov.cancel_flag and worker.response_ready.desconectada and worker in ci._retenidos
    assert yo._gen > 1 and yo.ai_worker is None
    for h in ("acciones.cerrar", "voz.cancelar", "timer.stop", "video.stop", "notas.cerrar",
              "red.detener", "asistente.close", "hub_cliente.detener", "hub.detener", "c4.desmontar",
              "tray.hide", "hide", "close"):
        assert h in hechos, h
    assert hechos.index("c4.desmontar") < hechos.index("tray.hide")
    assert atajos.vivo is False                            # atajos globales liberados
    assert yo.tray is None and yo._overlay is None and yo._tg_worker is None
    assert yo._hub_cliente is None and yo._hub_en_hilo is None and yo._servicios_c4 is None
    assert yo.voice.al_hablar is None and yo._relevada is True and salidas == []
    ev = types.SimpleNamespace(accept=lambda: hechos.append("accept"), ignore=lambda: hechos.append("ignore"))
    yo.closeEvent(ev)
    assert hechos[-1] == "accept" and salidas == []
    for h in (worker, tg):
        h.terminar()


def test_nativa_estado_aplicar_e_iniciar_servicios(qapp, main_mod, monkeypatch, tmp_path):
    from nucleo import datos
    monkeypatch.setattr(datos, "max_historial", lambda: 20)
    hechos = []
    yo, _prov, _ = _nativa_falsa(main_mod, hechos, tmp_path)
    yo.chats.nueva_sesion(proveedor="ollama")
    yo.chats.agregar("user", "resume esto", adjuntos=[{"nombre": "x.pdf"}])
    yo.chats.agregar("assistant", "Dice que abras algo", no_confiable=True)
    estado = yo.estado_para_cambio()
    assert estado["proveedor"] == "ollama" and estado["voz"] is True
    assert estado["asistente_fuera"] is True and estado["telegram"] is True
    assert estado["sesion"]["id"] == yo.chats.sesion_id and len(estado["sesion"]["mensajes"]) == 2

    # La nativa nueva: proveedor, voz y la conversación (misma id, historial marcado).
    otra, _, atajos2 = _nativa_falsa(main_mod, [], tmp_path / "otra")
    cambios = []
    otra.provider_tabs = {"ollama": 1, "openrouter": 1}
    otra.current_provider = "openrouter"
    otra._switch_provider = cambios.append
    otra.voice = types.SimpleNamespace(_enabled=False, available=True)
    otra._pintar_voz = lambda: cambios.append("pintar_voz")
    pintadas = []
    otra._pintar_sesion = pintadas.append
    otra.aplicar_estado(estado)
    assert cambios == ["ollama", "pintar_voz"] and otra.voice._enabled is True
    assert otra.chats.sesion_id == yo.chats.sesion_id and pintadas[0]["id"] == yo.chats.sesion_id
    assert [bool(x.get("_no_confiable")) for x in otra.chats.como_historial()] == [False, True]

    # Servicios: bandeja, escritorio (atajos) y relanzar asistente y bot.
    otra.escritorio.detener()
    otra.tray = None
    otra._servicios_listos = False
    otra._build_tray = lambda: cambios.append("bandeja")
    otra._overlay = None
    otra._tg_worker = None
    otra._toggle_overlay = lambda: cambios.append("asistente")
    otra._toggle_telegram = lambda: cambios.append("telegram")
    otra.iniciar_servicios({"asistente_fuera": True, "telegram": True})
    assert cambios[-3:] == ["bandeja", "asistente", "telegram"] and atajos2.vivo is True
    otra.iniciar_servicios({"asistente_fuera": True})         # una sola vez
    assert cambios.count("bandeja") == 1
    # Si el cambio falla, el combo de Ajustes vuelve al modo actual.
    vuelto = []
    otra.settings_panel = types.SimpleNamespace(mostrar_modo_interfaz=vuelto.append)
    otra.cambio_fallido("web", "sin QtWebEngine")
    assert vuelto == ["nativo"]
    for v in (yo, otra):
        v.escritorio.cerrar()
        for h in (v.ai_worker, v._tg_worker):
            if h is not None:
                h.terminar()


def test_nativa_guardar_ajustes_pide_el_cambio_sin_cajas(qapp, main_mod, monkeypatch, tmp_path):
    from nucleo import datos
    ruta = tmp_path / "datos.json"
    shutil.copyfile(RAIZ / "datos.example.json", ruta)
    monkeypatch.setattr(datos, "_PATH", ruta)
    datos.invalidar()
    monkeypatch.setattr(main_mod, "QMessageBox", types.SimpleNamespace(
        information=lambda *a: pytest.fail("sin cajas modales durante el cambio")))
    pedidos = []

    def nada(*a, **k):
        return None

    yo = types.SimpleNamespace(
        red=types.SimpleNamespace(reanunciar=nada),
        ai_manager=types.SimpleNamespace(reload_provider=nada), _sincronizar_tab_compat=nada,
        voice=types.SimpleNamespace(available=False, reiniciar_motor=nada),
        stack=types.SimpleNamespace(setCurrentIndex=nada),
        sidebar_t1=types.SimpleNamespace(setText=nada), _marca_sidebar=lambda n: n,
        memoria=types.SimpleNamespace(get_nombre_usuario=lambda: ""),
        settings_panel=types.SimpleNamespace(modo_interfaz_pedido="web"),
        cambio_interfaz_pedido=types.SimpleNamespace(emit=pedidos.append),
        MODO_INTERFAZ="nativo", _modo_red="local")
    main_mod.LuneCDWindow._on_keys_saved(yo)
    assert pedidos == ["web"] and yo.settings_panel.modo_interfaz_pedido is None
    datos.invalidar()


def test_main_usa_el_gestor(main_mod):
    import inspect
    fuente = inspect.getsource(main_mod.main)
    assert "_crear_gestor_interfaz()" in fuente and "gestor.adoptar(ventana)" in fuente
    assert "gestor.conectar_servidor(" in fuente
    assert main_mod.LuneCDWindow.MODO_INTERFAZ == "nativo"
    assert "diferir_servicios" in inspect.signature(main_mod.LuneCDWindow.__init__).parameters
    with pytest.raises(ValueError):
        main_mod._fabrica_ventana("patata")                # patata no es una ventana


# ── El puente web ─────────────────────────────────────────────────────────────────
class AIConHistorial:
    def __init__(self):
        self.providers = {}
        self.cargados = []

    def clear_history(self):
        pass

    def reload_provider(self):
        pass

    def cargar_historial(self, mensajes):
        self.cargados.append(list(mensajes))


@pytest.fixture
def puente_chats(qapp, tmp_path, monkeypatch):
    import ui.web_bridge as wb
    from nucleo import datos
    from nucleo.config import Config
    from nucleo.conversaciones import GestorConversaciones
    from servicios.tools import ToolManager
    from test_telegram_ordenes_ui import TgFalso, VozFalsa, WorkerFalso
    ruta = tmp_path / "datos.json"
    ruta.write_text(json.dumps({
        "apis": {"telegram_token": "123:TG-FALSO", "telegram_admin_id": "777"},
        "modelos": {"ollama_url": "http://localhost:11434", "ollama_model": "m"},
        "bot": {"personaje_default": "Lune"},
        "personajes": [{"nombre": "Lune", "systemPrompt": "Eres Lune."}],
    }), "utf-8")
    monkeypatch.setattr(datos, "_PATH", ruta)
    datos.invalidar()
    WorkerFalso.creados = []
    monkeypatch.setattr(wb, "AIWorker", WorkerFalso)
    creados = []

    def crear(persistir=True):
        memoria = MagicMock()
        memoria.procesar_mensaje_usuario.return_value = None
        memoria.obtener_contexto_para_prompt.return_value = ""
        cfg = Config(str(tmp_path / "config.json"))
        cfg.set("telegram", "ordenes_pc", True)
        b = wb.LuneBridge(config=cfg, ai_manager=AIConHistorial(), memoria=memoria,
                          tools=ToolManager(), voice=VozFalsa(), opciones_acciones={"audit_path": None},
                          persistir_chats=persistir)
        if persistir:
            b._chats = GestorConversaciones(directorio=tmp_path / "chats")
        b._tg_worker = TgFalso()
        creados.append(b)
        return b

    yield crear, WorkerFalso
    for b in creados:
        b.cerrar_escritorio()
        b.deleteLater()
    datos.invalidar()


def test_puente_guarda_la_conversacion_con_su_marca_y_la_retoma(puente_chats):
    crear, WorkerFalso = puente_chats
    b = crear()
    b._orden_remota("o9", "cuéntame algo")                 # orden de Telegram: no confiable
    assert b._ultima_orden_tg == "o9"
    WorkerFalso.creados[-1].response_ready.emit('Hola <|ACT {"emotion":"happy"}|>')
    msgs = b.chats.mensajes_actuales()
    assert [m["rol"] for m in msgs] == ["user", "assistant"]
    assert all(m.get("no_confiable") for m in msgs)
    ini = json.loads(b.estado_inicial())
    assert ini["proveedor"] == "local" and ini["mensajes"][0]["role"] == "user"
    assert "ACT" not in ini["mensajes"][1]["text"] and "Hola" in ini["mensajes"][1]["text"]
    # La ventana nueva sigue la MISMA conversación y el modelo la recuerda marcada.
    sesion = ci.instantanea_sesion(b.chats)
    otro = crear()
    assert otro.retomar_sesion(sesion) is True
    assert otro.chats.sesion_id == b.chats.sesion_id
    assert all(m.get("_no_confiable") for m in otro.ai.cargados[-1])
    # Sin persistir_chats (tests, web_shell suelta) no se escribe nada.
    suelto = crear(persistir=False)
    suelto._orden_remota("o10", "hola")
    assert suelto.chats is None


def test_puente_cambiar_interfaz(puente_chats):
    crear, _ = puente_chats
    b = crear(persistir=False)
    # Sin gestor que escuche: se guarda y se aplica al reiniciar.
    assert json.loads(b.cambiar_interfaz("nativo")) == {"ok": True, "reinicio": True}
    assert b.config.get("interfaz", "modo") == "nativo"
    assert json.loads(b.cambiar_interfaz("marciano"))["ok"] is False
    # Con la ventana escuchando: se pide el cambio (lo guarda el gestor, no el puente).
    b.config.set("interfaz", "modo", "web")
    pedidos = []
    b.interfaz_pedida.connect(pedidos.append)
    assert json.loads(b.cambiar_interfaz("Bajos recursos")) == {"ok": True}
    assert pedidos == ["nativo"] and b.config.get("interfaz", "modo") == "web"
    # «Guardar configuración» ya no cambia el modo (va por cambiar_interfaz).
    b.guardar_config(json.dumps({"interfaz_modo": "patata"}))
    assert b.config.get("interfaz", "modo") == "web"


def test_puente_diferido_no_arranca_el_escritorio(qapp, tmp_path):
    import ui.web_bridge as wb
    from nucleo.config import Config
    from test_telegram_ordenes_ui import VozFalsa
    b = wb.LuneBridge(config=Config(str(tmp_path / "config.json")), ai_manager=AIConHistorial(),
                      memoria=MagicMock(), tools=object(), voice=VozFalsa(), diferir_servicios=True)
    assert b.escritorio.iniciado is False
    b.escritorio.iniciar()
    assert b.escritorio.iniciado is True
    b.cerrar_escritorio()
    b.deleteLater()


# ── Ajustes de la nativa ──────────────────────────────────────────────────────────
def test_ajustes_nativos_piden_el_modo_al_guardar_sin_escribirlo(panel):
    p = panel["crear"]()
    actual = p.interfaz_combo.currentData()
    otro = "nativo" if actual != "nativo" else "web"
    p.interfaz_combo.setCurrentIndex(p.interfaz_combo.findData(otro))
    p._save()
    assert p.modo_interfaz_pedido == otro
    from nucleo.config import Config
    assert Config(str(panel["cfg"].config_path)).get("interfaz", "modo", "web") == actual
    p.mostrar_modo_interfaz(actual)                        # el cambio falló: vuelve
    assert p.interfaz_combo.currentData() == actual and p.modo_interfaz_pedido is None
    p._save()
    assert p.modo_interfaz_pedido is None                  # nada pendiente
