"""
Tests de la presencia de Discord (servicios/discord_presencia.py).

- Qué se publica: la tabla ESTADOS, el juego (null), los detalles por modo, el
  modelo solo si se pide, el botón solo con https, el recorte en bytes y la
  PRIVACIDAD (nada del estado que no sea la clave llega al JSON de la tubería).
- Cuándo: la máquina se prueba con `hilo=False` y un reloj falso (antirrebote de
  1.5 s, 4 s entre envíos, coalescencia, sin repetidos, reintentos 15/30/60,
  4000 sin reintentos, mutex ocupado, apagar → null).
- Con el hilo de verdad: sin Application ID no hay hilo (D1) y en cuanto aparece
  conecta; `cerrar()` borra la actividad en ≤1 s.
"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from servicios import discord_ipc as di  # noqa: E402
from servicios import discord_presencia as dp  # noqa: E402
from discord_falso import (ID, ID2, ConfigFalsa, DiscordFalso, FabricaClientes,  # noqa: E402
                           MutexFalso, Reloj)

INICIO = 1_700_000_000_000


# ── Qué se publica ─────────────────────────────────────────────────────────────

def test_la_tabla_de_estados_completa_y_en_orden():
    assert dp.ESTADOS == (
        ("alarma", "Con una alarma sonando"),
        ("grande", "En pantalla grande"),
        ("salvapantallas", "Durmiendo en el salvapantallas"),
        ("llamada", "En una llamada"),
        ("arrastrando", "Paseando por la pantalla"),
        ("bailando", "Bailando ♪"),
        ("comiendo", "Merendando"),
        ("siesta", "Echando una siesta sentada"),
        ("durmiendo", "Durmiendo (-_-) zzZ"),
        ("sentada_barra", "Sentada en la barra de tareas"),
        ("sentada_ventana", "Sentada en una ventana"),
        ("pensando", "Pensando…"),
        ("hablando", "Hablando"),
        ("escritorio", "En el escritorio"),
        ("charlando", "Charlando"),
        ("terminal", "En la terminal"),
    )


@pytest.mark.parametrize("est, modo, render, clave", [
    ({"juego": True, "alarma": True, "bailando": "musica"}, "normal", "vrm", None),
    ({"alarma": True, "grande": True}, "normal", "vrm", "alarma"),
    ({"grande": True, "salvapantallas": True}, "normal", "vrm", "grande"),
    ({"salvapantallas": True, "llamada": True}, "normal", "", "salvapantallas"),
    ({"llamada": True, "arrastrando": True}, "normal", "vrm", "llamada"),
    ({"arrastrando": True, "bailando": "musica"}, "normal", "vrm", "arrastrando"),
    ({"bailando": "mmd", "comiendo": True}, "normal", "vrm", "bailando"),
    ({"comiendo": True, "durmiendo": True, "sentada": "barra"}, "normal", "vrm", "comiendo"),
    ({"durmiendo": True, "sentada": "barra"}, "normal", "vrm", "siesta"),
    ({"durmiendo": True, "sentada": "ventana"}, "normal", "animado", "siesta"),
    ({"durmiendo": True}, "normal", "vrm", "durmiendo"),
    ({"sentada": "barra", "pensando": True}, "normal", "vrm", "sentada_barra"),
    ({"sentada": "ventana", "hablando": True}, "normal", "sprites", "sentada_ventana"),
    ({"pensando": True, "hablando": True}, "normal", "vrm", "pensando"),
    ({"hablando": True}, "br", "", "hablando"),
    ({}, "normal", "vrm", "escritorio"),
    ({}, "br", "sprites", "escritorio"),
    ({}, "normal", "", "charlando"),
    ({}, "patata", "", "terminal"),
    ({"pensando": True}, "patata", "", "pensando"),
    ({"juego": True}, "patata", "", None),
])
def test_clave_por_prioridad(est, modo, render, clave):
    assert dp.clave_estado(est, modo=modo, render=render) == clave


def test_tambien_acepta_el_estado_del_bus():
    from nucleo.estado_asistente import EstadoAsistente
    assert dp.clave_estado(EstadoAsistente(render="vrm", visible=True, bailando="musica"),
                           modo="normal", render="vrm") == "bailando"
    assert dp.clave_estado(EstadoAsistente(juego=True), modo="normal", render="") is None


def _act(foto, config=None):
    return dp.actividad_de(foto, config=config or ConfigFalsa(), inicio_ms=INICIO)


@pytest.mark.parametrize("foto, details, pequena", [
    ({"modo": "normal", "render": "vrm", "visible": True}, "Lune CD · Escritorio · 3D", "vrm"),
    ({"modo": "normal", "render": "animado", "visible": True}, "Lune CD · Escritorio · animación", "animado"),
    ({"modo": "br", "render": "sprites", "visible": True}, "Lune CD · Escritorio · sprites", "sprites"),
    ({"modo": "br", "render": "carita", "visible": True}, "Lune CD · Escritorio · sprites", "sprites"),
    ({"modo": "normal", "render": "vrm", "visible": False}, "Lune CD · Ventana", "web"),
    ({"modo": "normal", "render": "", "visible": False}, "Lune CD · Ventana", "web"),
    ({"modo": "br", "render": "", "visible": False}, "Lune CD · Ventana", "nativo"),
    ({"modo": "patata"}, "Lune CD · Terminal", "patata"),
])
def test_detalles_e_imagen_pequena_por_modo(foto, details, pequena):
    a = _act(foto)
    assert a["details"] == details
    assert a["assets"]["small_image"] == pequena
    assert a["assets"]["large_image"] == "lune"
    assert a["assets"]["large_text"] == "Lune CD"
    assert a["timestamps"] == {"start": INICIO}
    assert "buttons" not in a


def test_con_un_juego_la_actividad_es_null():
    assert _act({"modo": "normal", "render": "vrm", "visible": True, "juego": True}) is None
    assert dp.construir_actividad(None, modo="normal", render="vrm", inicio_ms=0, config={}) is None


def test_el_modelo_solo_con_mostrar_modelo_y_en_vrm():
    foto = {"modo": "normal", "render": "vrm", "visible": True, "modelo": "C:\\Modelos\\Aria.vrm"}
    assert _act(foto)["assets"]["large_text"] == "Lune CD"
    cfg = ConfigFalsa(mostrar_modelo=True)
    assert _act(foto, cfg)["assets"]["large_text"] == "Lune CD · Aria"
    assert _act(dict(foto, render="animado"), cfg)["assets"]["large_text"] == "Lune CD"


@pytest.mark.parametrize("url, sale", [
    ("https://lune.example.com/descarga", True),
    ("http://lune.example.com", False),
    ("javascript:alert(1)", False),
    ("https://", False),
    ("https://lune example.com", False),
    ("ftp://lune.example.com", False),
    ("https://lune.example.com/" + "a" * 600, False),
    ("", False),
])
def test_boton_solo_con_https_valida(url, sale):
    a = _act({"modo": "normal"}, ConfigFalsa(boton_url=url))
    if sale:
        assert a["buttons"] == [{"label": "Conoce a Lune", "url": url}]
    else:
        assert "buttons" not in a


def test_cabe_recorta_en_bytes_sin_partir_acentos():
    t = dp.cabe("ñ" * 100, 128)
    assert t == "ñ" * 64 and len(t.encode("utf-8")) == 128
    t = dp.cabe("a" + "é" * 100, 128)
    assert len(t.encode("utf-8")) <= 128 and t.encode("utf-8").decode("utf-8") == t
    assert dp.cabe("Hola", 128) == "Hola"
    assert len(dp.cabe("", 128)) == 2 and len(dp.cabe("x", 128)) == 2
    assert len(dp.cabe("áé", 3).encode("utf-8")) <= 3


def test_textos_largos_se_recortan_a_128_bytes():
    cfg = ConfigFalsa(mostrar_modelo=True)
    a = _act({"modo": "normal", "render": "vrm", "visible": True, "modelo": "ñ" * 200 + ".vrm"}, cfg)
    for texto in (a["details"], a["state"], a["assets"]["large_text"], a["assets"]["small_text"]):
        assert 2 <= len(texto) and len(texto.encode("utf-8")) <= 128


# ── La máquina (sin hilo, reloj falso) ─────────────────────────────────────────

class Foto:
    """estado_fn que se puede cambiar desde el test."""

    def __init__(self, **campos):
        self.d = {"modo": "normal", "render": "vrm", "visible": True}
        self.d.update(campos)
        self.llamadas = 0

    def __call__(self):
        self.llamadas += 1
        return dict(self.d)

    def poner(self, **campos):
        base = {"modo": self.d["modo"], "render": self.d.get("render", ""), "visible": self.d.get("visible")}
        base.update(campos)
        self.d = base


def _presencia(config=None, foto=None, fabrica=None, mutex=None, reloj=None, **kw):
    reloj = reloj or Reloj()
    fabrica = fabrica or FabricaClientes("ok")
    mutex = mutex or MutexFalso()
    p = dp.Presencia(config or ConfigFalsa(activo=True, client_id=ID), foto or Foto(),
                     cliente=fabrica, mutex=mutex, reloj=reloj, hilo=False, pid=4321, inicio_ms=INICIO, **kw)
    return p, fabrica, mutex, reloj


def _estados(enviadas):
    return [None if a is None else a["state"] for a, _pid in enviadas]


def test_al_conectar_publica_enseguida_con_el_pid():
    p, fab, mutex, reloj = _presencia()
    p.habilitar(True)
    assert p.paso() == pytest.approx(dp.TIC_S)
    assert mutex.nombres == ["Local\\LuneDiscordRPC"]
    assert fab.enviadas() == [(fab.ultimo.enviadas[0][0], 4321)]
    assert _estados(fab.enviadas()) == ["En el escritorio"]
    e = p.estado()
    assert e["conectado"] is True and e["usuario"] == "Diego"
    assert e["publicando"] == {"details": "Lune CD · Escritorio · 3D", "state": "En el escritorio"}


def test_antirrebote_de_1_5_s():
    foto = Foto()
    p, fab, _m, reloj = _presencia(foto=foto)
    p.habilitar(True)
    p.paso()                                      # t=0: primera publicación
    reloj.t = 10.0
    foto.poner(hablando=True)
    p.actualizar()
    p.paso()
    reloj.t = 11.4
    p.paso()
    assert _estados(fab.enviadas()) == ["En el escritorio"]
    reloj.t = 11.5
    p.paso()
    assert _estados(fab.enviadas()) == ["En el escritorio", "Hablando"]


def test_al_menos_4_s_entre_envios():
    foto = Foto()
    p, fab, _m, reloj = _presencia(foto=foto)
    p.habilitar(True)
    p.paso()                                      # t=0
    reloj.t = 0.5
    foto.poner(hablando=True)
    p.actualizar()
    for t in (0.5, 2.0, 3.9):
        reloj.t = t
        p.paso()
    assert len(fab.enviadas()) == 1
    reloj.t = 4.0
    p.paso()
    assert _estados(fab.enviadas()) == ["En el escritorio", "Hablando"]


def test_coalescencia_solo_sale_el_ultimo():
    foto = Foto()
    p, fab, _m, reloj = _presencia(foto=foto)
    p.habilitar(True)
    p.paso()
    for t, campos in ((1.0, {"pensando": True}), (1.5, {"hablando": True}), (2.0, {"bailando": "musica"})):
        reloj.t = t
        foto.poner(**campos)
        p.actualizar()
        p.paso()
    reloj.t = 4.0
    p.paso()
    assert _estados(fab.enviadas()) == ["En el escritorio", "Bailando ♪"]


def test_un_estado_que_no_para_de_cambiar_sale_igual():
    foto = Foto()
    p, fab, _m, reloj = _presencia(foto=foto)
    p.habilitar(True)
    p.paso()
    t = 5.0
    alterna = [{"pensando": True}, {"hablando": True}]
    while t < 16.5:                                # cambia cada segundo: el antirrebote nunca vence
        reloj.t = t
        foto.poner(**alterna[int(t) % 2])
        p.actualizar()
        p.paso()
        t += 1.0
    assert len(fab.enviadas()) >= 2


def test_no_reenvia_lo_identico():
    foto = Foto()
    p, fab, _m, reloj = _presencia(foto=foto)
    p.habilitar(True)
    p.paso()
    reloj.t = 5.0
    foto.poner(hablando=True)
    p.actualizar()
    p.paso()
    reloj.t = 5.5
    foto.poner()                                   # vuelve a lo publicado antes de enviarse
    p.actualizar()
    p.paso()
    for t in (8.0, 20.0, 60.0):                    # sondeos sin cambios
        reloj.t = t
        p.paso()
    assert len(fab.enviadas()) == 1


def test_el_juego_se_salta_el_antirrebote():
    foto = Foto()
    p, fab, _m, reloj = _presencia(foto=foto)
    p.habilitar(True)
    p.paso()
    reloj.t = 10.0
    foto.poner(juego=True)
    p.actualizar()
    p.paso()
    assert _estados(fab.enviadas()) == ["En el escritorio", None]
    assert p.estado()["publicando"] is None


def test_sin_llamar_a_actualizar_el_sondeo_ve_el_cambio():
    foto = Foto()
    p, fab, _m, reloj = _presencia(foto=foto)
    p.habilitar(True)
    p.paso()
    reloj.t = 10.0
    foto.poner(pensando=True)                     # patata: nadie avisa
    p.paso()
    reloj.t = 11.6
    p.paso()
    assert _estados(fab.enviadas())[-1] == "Pensando…"


def test_atiende_la_tuberia_en_cada_paso():
    p, fab, _m, reloj = _presencia()
    p.habilitar(True)
    for i in range(5):
        reloj.t = i * 0.1
        p.paso()
    assert fab.ultimo.atendidas == 5


def test_sin_discord_reintenta_a_los_15_30_y_cada_60_s():
    p, fab, _m, reloj = _presencia(fabrica=FabricaClientes("sin_discord"))
    p.habilitar(True)
    esperas = []
    for t in (0.0, 14.9, 15.0, 44.9, 45.0, 104.9, 105.0, 165.0):
        reloj.t = t
        esperas.append(p.paso())
    assert len(fab.clientes) == 5                 # t = 0, 15, 45, 105, 165
    assert esperas[0] == pytest.approx(15.0)
    assert esperas[2] == pytest.approx(30.0)
    assert esperas[4] == pytest.approx(60.0)
    assert esperas[6] == pytest.approx(60.0)
    assert p.estado()["error"] == "Discord no está abierto."


def test_id_rechazado_4000_no_reintenta_hasta_que_cambie():
    cfg = ConfigFalsa(activo=True, client_id=ID)
    p, fab, _m, reloj = _presencia(config=cfg, fabrica=FabricaClientes("4000", "ok"))
    p.habilitar(True)
    assert p.paso() is None                       # esperar sin sondear
    for t in (100.0, 1000.0, 10000.0):
        reloj.t = t
        assert p.paso() is None
    assert len(fab.clientes) == 1
    assert p.estado()["error"] == dp.TXT_RECHAZADO
    cfg.set("discord", "client_id", ID2)
    p.actualizar()
    p.paso()
    assert len(fab.clientes) == 2 and fab.ultimo.client_id == ID2
    assert p.estado()["conectado"] is True


def test_close_4000_en_mitad_de_la_sesion_tampoco_reintenta():
    p, fab, _m, reloj = _presencia()
    p.habilitar(True)
    p.paso()
    fab.ultimo.caer(codigo=4000)
    reloj.t = 1.0
    assert p.paso() is None
    reloj.t = 500.0
    p.paso()
    assert len(fab.clientes) == 1


def test_si_discord_se_cierra_reintenta_a_los_15_s():
    p, fab, _m, reloj = _presencia()
    p.habilitar(True)
    p.paso()
    fab.ultimo.caer()
    reloj.t = 3.0
    assert p.paso() == pytest.approx(15.0)
    assert p.estado()["conectado"] is False
    reloj.t = 17.9
    p.paso()
    assert len(fab.clientes) == 1
    reloj.t = 18.0
    p.paso()
    assert len(fab.clientes) == 2 and p.estado()["conectado"] is True
    assert len(fab.ultimo.enviadas) == 1          # vuelve a publicar al reconectar


def test_mutex_ocupado_no_conecta_y_dice_que_otra_lune_publica():
    mutex = MutexFalso(libre=False)
    p, fab, _m, reloj = _presencia(mutex=mutex)
    p.habilitar(True)
    # Mirar el mutex no cuesta nada: cada 5 s, sin alargar la espera (tras un cambio de
    # interfaz el hilo de la ventana vieja lo suelta enseguida: antes eran 15 s de «otra Lune»).
    assert dp.REINTENTO_OTRA_LUNE_S == 5.0
    assert p.paso() == pytest.approx(5.0)
    assert fab.clientes == []
    assert p.estado()["error"] == dp.TXT_OTRA_LUNE
    reloj.t = 5.0
    assert p.paso() == pytest.approx(5.0)           # sigue ocupado: otros 5 s, no 30
    mutex.libre = True                              # la otra se cerró
    reloj.t = 10.0
    p.paso()
    assert len(fab.clientes) == 1 and p.estado()["conectado"] is True


def test_apagar_borra_la_actividad_y_suelta_el_mutex():
    p, fab, mutex, reloj = _presencia()
    p.habilitar(True)
    p.paso()
    p.habilitar(False)
    assert p.paso() is None
    c = fab.ultimo
    assert c.cerrado is True                        # cerrar(limpiar=True): null + OP_CLOSE
    assert c.enviadas[-1] == (None, "cierre")
    assert mutex.liberado == 1
    e = p.estado()
    assert e["activo"] is False and e["conectado"] is False


def test_cambiar_el_id_reconecta_con_el_nuevo():
    cfg = ConfigFalsa(activo=True, client_id=ID)
    p, fab, _m, reloj = _presencia(config=cfg)
    p.habilitar(True)
    p.paso()
    cfg.set("discord", "client_id", ID2)
    reloj.t = 1.0
    p.actualizar()
    p.paso()
    assert [c.client_id for c in fab.clientes] == [ID, ID2]
    assert fab.clientes[0].cerrado is True


def test_client_id_mal_escrito_no_conecta():
    p, fab, _m, _r = _presencia(config=ConfigFalsa(activo=True, client_id="mi-app"))
    p.habilitar(True)
    assert p.paso() is None
    assert fab.clientes == []
    assert p.estado()["error"] == di.TXT_ID_NO_VALIDO


def test_on_estado_avisa_de_los_cambios():
    vistos = []
    p, fab, _m, reloj = _presencia()
    p.on_estado = vistos.append
    p.habilitar(True)
    p.paso()
    assert vistos[-1]["conectado"] is True
    assert vistos[-1]["publicando"]["state"] == "En el escritorio"
    n = len(vistos)
    reloj.t = 1.0
    p.paso()                                        # nada cambió: no avisa otra vez
    assert len(vistos) == n


# ── Privacidad, de punta a punta por la tubería ────────────────────────────────

SECRETOS = ("Banco Santander — Mi cuenta", "Spotify.exe", "Spotify", "Aria", "Tomar la pastilla",
            "DiegoB", "mi contraseña es 1234", "Valorant", "VALORANT-Win64-Shipping.exe")


def test_privacidad_nada_personal_llega_al_json_enviado():
    falso = DiscordFalso()
    reloj = Reloj()

    def cliente(cid):
        return di.ClienteIPC(cid, abrir=lambda n: falso if n == 0 else None, reloj=reloj, dormir=reloj.dormir)

    foto = Foto(titulo_ventana=SECRETOS[0], app_musica=SECRETOS[1], musica=SECRETOS[2],
                personaje=SECRETOS[3], alarma_texto=SECRETOS[4], usuario_pc=SECRETOS[5],
                texto=SECRETOS[6], juego_nombre=SECRETOS[7], proceso=SECRETOS[8],
                modelo="Aria.vrm", bailando="musica", emocion="happy")
    extra = {k: v for k, v in foto.d.items() if k not in ("modo", "render", "visible", "bailando")}
    p = dp.Presencia(ConfigFalsa(activo=True, client_id=ID), foto, cliente=cliente, mutex=MutexFalso(),
                     reloj=reloj, hilo=False, pid=11, inicio_ms=INICIO)
    p.habilitar(True)
    p.paso()
    for t, campos in ((10.0, {"alarma": True}), (20.0, {"sentada": "ventana"}), (30.0, {"pensando": True})):
        reloj.t = t
        foto.poner(**dict(extra, **campos))
        p.actualizar()
        p.paso()
        reloj.t = t + 2.0
        p.paso()
    enviado = falso.bytes_escritos.decode("utf-8", errors="replace")
    assert "Bailando" in enviado and "alarma sonando" in enviado and "Sentada en una ventana" in enviado
    for secreto in SECRETOS:
        assert secreto not in enviado, secreto
    assert "happy" not in enviado


# ── Con el hilo de verdad ──────────────────────────────────────────────────────

def _esperar(cond, s=3.0):
    fin = time.monotonic() + s
    while time.monotonic() < fin:
        if cond():
            return True
        time.sleep(0.01)
    return cond()


def test_sin_client_id_no_hay_hilo_ni_intentos_y_con_id_conecta_sin_reiniciar():
    cfg = ConfigFalsa(activo=True, client_id="")
    fab = FabricaClientes("ok")
    p = dp.Presencia(cfg, Foto(), cliente=fab, mutex=MutexFalso(), pid=1, inicio_ms=INICIO)
    try:
        p.habilitar(True)
        p.actualizar()
        assert p._hilo is None
        assert fab.clientes == []
        e = p.estado()
        assert e["activo"] is True and e["sin_id"] is True and e["error"] == ""
        cfg.set("discord", "client_id", ID)          # Diego pega el Application ID en la tarjeta
        p.actualizar()
        assert _esperar(lambda: p.estado()["conectado"])
        assert p._hilo is not None and p._hilo.name == "LuneDiscordRPC" and p._hilo.daemon
        assert _esperar(lambda: len(fab.enviadas()) == 1)
    finally:
        p.cerrar()


def test_id_mal_escrito_no_arranca_hilo_y_lo_dice():
    fab = FabricaClientes("ok")
    p = dp.Presencia(ConfigFalsa(activo=True, client_id="mi-app"), Foto(), cliente=fab, mutex=MutexFalso())
    p.habilitar(True)
    assert p._hilo is None and fab.clientes == []
    assert p.estado()["error"] == di.TXT_ID_NO_VALIDO
    p.cerrar()


def test_apagada_no_arranca_ningun_hilo():
    fab = FabricaClientes("ok")
    p = dp.Presencia(ConfigFalsa(activo=False, client_id=ID), Foto(), cliente=fab, mutex=MutexFalso())
    p.habilitar(False)
    p.actualizar()
    assert p._hilo is None and fab.clientes == []
    p.cerrar()


def test_cerrar_borra_la_actividad_en_menos_de_1_s():
    falso = DiscordFalso()

    def cliente(cid):
        return di.ClienteIPC(cid, abrir=lambda n: falso if n == 0 else None)

    p = dp.Presencia(ConfigFalsa(activo=True, client_id=ID), Foto(), cliente=cliente,
                     mutex=MutexFalso(), pid=321, inicio_ms=INICIO)
    p.habilitar(True)
    assert _esperar(lambda: len(falso.actividades()) == 1)
    t0 = time.monotonic()
    p.cerrar(timeout=1.0)
    dt = time.monotonic() - t0
    assert dt < 1.0
    assert falso.actividades()[-1] is None
    assert falso.recibidas[-1][0] == di.OP_CLOSE and falso.cerrada is True
    assert p.estado()["activo"] is False
    # se puede volver a habilitar
    falso2 = DiscordFalso()
    p2_abrir = {"t": falso2}
    p._fab_cliente = lambda cid: di.ClienteIPC(cid, abrir=lambda n: p2_abrir["t"] if n == 0 else None)
    p.habilitar(True)
    try:
        assert _esperar(lambda: len(falso2.actividades()) == 1)
    finally:
        p.cerrar()


def test_el_hilo_no_bloquea_a_quien_llama():
    """habilitar/actualizar vuelven al momento aunque Discord tarde en responder."""
    falso = DiscordFalso(ready=False)                # no contesta: conectar esperaría 5 s

    def cliente(cid):
        return di.ClienteIPC(cid, abrir=lambda n: falso if n == 0 else None)

    p = dp.Presencia(ConfigFalsa(activo=True, client_id=ID), Foto(), cliente=cliente, mutex=MutexFalso())
    t0 = time.monotonic()
    p.habilitar(True)
    p.actualizar()
    p.estado()
    assert time.monotonic() - t0 < 0.2
    t0 = time.monotonic()
    p.cerrar(timeout=1.0)                             # cancela la espera del handshake
    assert time.monotonic() - t0 < 1.0
