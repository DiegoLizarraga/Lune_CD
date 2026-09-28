"""
Tests de ui/mmd_qt.ControlMMD (offscreen): el reproductor de bailes con el
ServiciosEscritorio de verdad, la Biblioteca de verdad en una carpeta temporal
(ffmpeg falso) y mascotas y canción falsas.

- VRM → prioridad «mmd» + payload `cargar` exacto; eventos cargando/listo/sonando/t;
- animada (D1) → `tipo:"audio"` con el bpm y la fase analizados;
- sprites (D1) → canción por el Mezclador (falsa) + bailar/pulso a 2 Hz;
- sin mascota → despachador.ejecutar("mascota") y arranca al llegar;
- `al_terminar` × 4; ceder (juego) → pausa y reanudar → sigue; parar → reanuda la
  sentada; error → aviso; mascota None → para; detener idempotente;
- herramientas: listar_bailes, mascota_bailar{cancion} → MMD o respaldo, parar_baile.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bailes_falsos as bf  # noqa: E402
from nucleo import bailes as nbl  # noqa: E402


class MascotaFalsa:
    def __init__(self, render="vrm", con_mmd=True):
        self.render = render
        self.ordenes, self.bailes, self.pulsos = [], [], []
        self.despertares = 0
        self.acepta = True
        if con_mmd:
            self.mmd = self._mmd

    def _mmd(self, orden, datos=None):
        self.ordenes.append((orden, json.loads(json.dumps(datos)) if datos is not None else None))
        return self.acepta

    def bailar(self, on, opciones=None):
        self.bailes.append((on, opciones))

    def pulso(self, bpm, fase, energia):
        self.pulsos.append((bpm, fase, energia))

    def despertar(self):
        self.despertares += 1
        return True

    def cargas(self):
        return [d for o, d in self.ordenes if o == "cargar"]


class CancionFalsa:
    def __init__(self):
        self.cargadas, self.reproducciones, self.pausas, self.vols = [], [], [], []
        self.pos = 0.0
        self.terminado = False
        self.liberada = 0
        self.duracion = 0.0
        self.ok = (True, "")
        self.error = ""
        self._id = None

    def cargar(self, ruta, al_listo):
        self.cargadas.append(Path(ruta))
        self.duracion = 42.0
        al_listo(*self.ok)

    def reproducir(self, vol):
        self.reproducciones.append(round(vol, 4))
        self.terminado = False
        self.pos = 0.0
        return True

    def pausar(self, on):
        self.pausas.append(on)

    def volumen(self, v):
        self.vols.append(round(v, 4))

    def posicion(self):
        return None if self.terminado else self.pos

    def parar(self):
        pass

    def liberar(self):
        self.liberada += 1


class DespachadorFalso:
    def __init__(self, al_ejecutar=None):
        self.ejecutados = []
        self.al_ejecutar = al_ejecutar

    def tiene(self, id_):
        return id_ == "mascota"

    def ejecutar(self, id_, arg="", **kw):
        self.ejecutados.append(id_)
        if self.al_ejecutar:
            self.al_ejecutar()
        return True


class AsientoFalso:
    def __init__(self):
        self.cedidas, self.reanudadas = [], []

    def ceder(self, c):
        self.cedidas.append(c.por)

    def reanudar(self, c):
        self.reanudadas.append(c.valor)


class Anfitrion:
    def __init__(self):
        self.avisos = []
        self.alternadas = 0

    def aviso(self, texto):
        self.avisos.append(texto)

    def alternar_mascota(self):
        self.alternadas += 1
        return True


@pytest.fixture
def m(qapp, tmp_path):
    from ui.escritorio import ServiciosEscritorio
    from ui.mmd_qt import ControlMMD
    carpeta = tmp_path / "bailes"
    bf.hacer_baile(carpeta, "Alfa", cara=bf.vmd([], [("あ", 5)]))
    bf.hacer_baile(carpeta, "Beta", vrma_datos=bf.vrma(3.0), audio=("tema.ogg", bf.OGG))
    bf.hacer_baile(carpeta, "Gamma", audio=None)
    cfg = bf.ConfigFalsa()
    esc = ServiciosEscritorio(cfg)
    ej = bf.EjecutarFalso(pcm=bf.clics(120, primero=0.1))
    bib = nbl.Biblioteca(carpeta, tmp_path / "cache", config=cfg, ffmpeg="ffm", ejecutar=ej)
    cancion = CancionFalsa()
    anf = Anfitrion()
    en_ui = []
    ctl = ControlMMD(esc, cfg, biblioteca=bib, cancion=lambda: cancion, anfitrion=anf,
                     en_ui=lambda fn: (en_ui.append(1), fn())[1], hilo=False,
                     rng=__import__("random").Random(2))
    esc.registrar("mmd", ctl, ("mmd",))
    esc.iniciar()
    ctl.estados, ctl.bibl, ctl.imp = [], [], []
    ctl.estado_cambio.connect(lambda s: ctl.estados.append(json.loads(s)))
    ctl.biblioteca_cambio.connect(lambda s: ctl.bibl.append(json.loads(s)))
    ctl.importado.connect(lambda s: ctl.imp.append(json.loads(s)))

    class X:
        pass
    x = X()
    x.esc, x.cfg, x.ctl, x.bib, x.ej, x.cancion, x.anf, x.dir, x.en_ui = esc, cfg, ctl, bib, ej, cancion, anf, carpeta, en_ui
    x.ids = {b.titulo: b.id for b in bib.escanear()}
    yield x
    esc.cerrar()
    ctl.deleteLater()


def bus(x):
    return x.esc.estado.actual()


def con_mascota(x, render="vrm", con_mmd=True):
    mas = MascotaFalsa(render, con_mmd)
    x.esc.set_mascota(mas)
    return mas


def ev(x, fase, id_=None, **kw):
    x.esc._on_evento_js("mmd", {"fase": fase, "id": id_ if id_ is not None else x.ctl.estado()["id"], **kw})


# ── VRM ──────────────────────────────────────────────────────────────────────────

def test_vrm_prioridad_y_payload_exacto(m):
    mas = con_mascota(m)
    ok, texto = m.ctl.reproducir(m.ids["Alfa"])
    assert ok and texto == "¡A bailar «Alfa»!"
    assert bus(m).bailando == "mmd" and mas.despertares == 1
    assert mas.cargas() == [{
        "id": m.ids["Alfa"], "tipo": "vmd", "motion": ["/bailes/Alfa/baile.vmd"], "cara": ["/bailes/Alfa/labios.vmd"],
        "audio": "/bailes/Alfa/cancion.mp3", "offsetMs": 0, "enSitio": True, "brazoGrados": 35.0, "volumen": 0.25,
        "bucle": False, "autoplay": True, "titulo": "Alfa"}]
    e = m.ctl.estado()
    assert e["fase"] == "cargando" and e["modo"] == "vrm" and e["titulo"] == "Alfa" and not e["sin_esqueleto"]
    assert m.ctl._t_vigia.isActive()
    ev(m, "cargando")
    ev(m, "listo", total=95.5)
    assert m.ctl.estado()["fase"] == "listo" and not m.ctl._t_vigia.isActive()
    ev(m, "sonando")
    ev(m, "t", t=12.5, total=200.0)
    e = m.ctl.estados[-1]
    assert e["fase"] == "sonando" and e["t"] == 12.5 and e["total"] == 200.0
    ev(m, "fin", id_="0" * 12)                             # de otro baile: se ignora
    m.esc._on_evento_js("otra_cosa", {"fase": "fin"})
    assert m.ctl.activo and bus(m).bailando == "mmd"
    assert m.ctl.reproducir(m.ids["Alfa"]) == (True, "Ya estoy bailando «Alfa».")
    assert len(mas.cargas()) == 1


def test_vrma_y_meta_del_baile_en_el_payload(m):
    mas = con_mascota(m)
    m.bib.guardar_meta(m.ids["Beta"], {"offset_ms": -120, "brazo_a_grados": 41, "en_el_sitio": False})
    m.cfg.set("baile", "al_terminar", "repetir")
    m.ctl.reproducir(m.ids["Beta"])
    p = mas.cargas()[-1]
    assert p["tipo"] == "vrma" and p["motion"] == ["/bailes/Beta/baile.vrma"] and p["cara"] == []
    assert p["audio"] == "/bailes/Beta/tema.ogg" and p["offsetMs"] == -120 and p["brazoGrados"] == 41.0
    assert p["enSitio"] is False and p["bucle"] is True


@pytest.mark.parametrize("modo", ["parar", "siguiente", "repetir", "aleatorio"])
def test_fin_segun_al_terminar(m, modo):
    mas = con_mascota(m)
    m.ctl.set_al_terminar(modo)
    m.ctl.reproducir(m.ids["Alfa"])
    ev(m, "sonando")
    ev(m, "fin")
    if modo == "parar":
        assert mas.ordenes[-1] == ("parar", None) and not m.ctl.activo and bus(m).bailando == ""
        assert m.ctl.estado()["fase"] == "parado"
        return
    cargas = mas.cargas()
    assert len(cargas) == 2 and bus(m).bailando == "mmd" and m.ctl.activo
    if modo == "siguiente":
        assert cargas[-1]["id"] == m.ids["Beta"]
    elif modo == "repetir":
        assert cargas[0]["bucle"] is True and cargas[-1]["id"] == m.ids["Alfa"]
    else:
        assert cargas[-1]["id"] != m.ids["Alfa"]


def test_evento_parado_y_error_de_la_pagina(m):
    mas = con_mascota(m)
    m.ctl.reproducir(m.ids["Alfa"])
    ev(m, "parado")                                         # la página salió sola al reposo
    assert not m.ctl.activo and bus(m).bailando == "" and ("parar", None) not in mas.ordenes
    m.ctl.reproducir(m.ids["Alfa"])
    ev(m, "error", mensaje="el VMD <b>no</b> se pudo leer\x00")
    assert m.anf.avisos and "se pudo leer" in m.anf.avisos[-1] and "\x00" not in m.anf.avisos[-1]
    e = m.ctl.estado()
    assert e["fase"] == "error" and e["id"] == m.ids["Alfa"] and "se pudo leer" in e["error"]
    assert bus(m).bailando == ""
    n = len(m.anf.avisos)
    m.ctl.reproducir(m.ids["Alfa"])
    ev(m, "error", mensaje="recarga")                       # la página recargó: para sin avisar
    assert not m.ctl.activo and len(m.anf.avisos) == n and m.ctl.estado()["fase"] == "parado"


def test_vigia_sin_respuesta_y_mascota_que_no_acepta(m):
    mas = con_mascota(m)
    m.ctl.reproducir(m.ids["Alfa"])
    m.ctl._vigia_vencido()
    assert not m.ctl.activo and "no respondió" in m.anf.avisos[-1] and bus(m).bailando == ""
    mas.acepta = False
    ok, texto = m.ctl.reproducir(m.ids["Alfa"])
    assert not ok and "no aceptó" in texto and bus(m).bailando == ""


# ── Mascotas sin esqueleto (D1) ─────────────────────────────────────────────────

def test_animada_tipo_audio_con_bpm_y_fase(m):
    mas = con_mascota(m, "animado")
    ok, texto = m.ctl.reproducir(m.ids["Alfa"])
    assert ok and "no tiene esqueleto" in texto
    p = mas.cargas()[-1]
    assert set(p) == {"id", "tipo", "audio", "bpm", "fase0", "offsetMs", "volumen", "bucle", "autoplay", "titulo"}
    assert p["tipo"] == "audio" and p["audio"] == "/bailes/Alfa/cancion.mp3"
    assert abs(p["bpm"] - 120) <= 2 and abs(((p["fase0"] - 0.8) + 0.5) % 1 - 0.5) <= 0.06
    assert m.ej.de_tipo("s16le"), "el pulso se analizó con ffmpeg"
    e = m.ctl.estado()
    assert e["modo"] == "animado" and e["sin_esqueleto"] and not e["analizando"]
    ok, texto = m.ctl.reproducir(m.ids["Gamma"])            # sin canción no hay equivalente
    assert not ok and "sin canción" in texto and bus(m).bailando == ""


def test_animada_con_m4a_se_convierte_antes(m):
    bf.escribir(m.dir / "Delta" / "baile.vmd", bf.vmd())
    bf.escribir(m.dir / "Delta" / "tema.m4a", bf.M4A)
    id_ = [b.id for b in m.bib.escanear() if b.titulo == "Delta"][0]
    mas = con_mascota(m, "animado")
    assert m.ctl.reproducir(id_)[0]
    assert mas.cargas()[-1]["audio"] == f"/bailes_cache/{id_}.ogg" and m.ej.de_tipo("libopus")


def test_sprites_cancion_por_el_mezclador_y_pulso_a_2_hz(m):
    import pytest as _p
    mas = con_mascota(m, "sprites", con_mmd=False)
    ok, texto = m.ctl.reproducir(m.ids["Alfa"])
    assert ok and "no tiene esqueleto" in texto and bus(m).bailando == "mmd"
    assert m.cancion.cargadas == [m.dir / "Alfa" / "cancion.mp3"] and m.cancion.reproducciones == [0.25]
    on, opts = mas.bailes[-1]
    assert on is True and set(opts) == {"estilo", "cambiar", "cambiarS", "particulas"}
    assert m.ctl._t_pulso.interval() == 500 and m.ctl._t_pulso.isActive()
    p = m.ctl._pulso
    m.cancion.pos = 0.25
    m.ctl._tic_pulso()
    bpm, fase, energia = mas.pulsos[-1]
    assert bpm == p["bpm"] and fase == _p.approx(nbl.fase_en(0.25, p["bpm"], p["fase0"])) and energia == 0.7
    e = m.ctl.estado()
    assert e["modo"] == "sprites" and e["fase"] == "sonando" and e["total"] == 42.0 and e["sin_esqueleto"]
    m.esc.estado.actualizar(hablando=True)                   # la voz de Lune baja la canción
    assert m.cancion.vols[-1] == _p.approx(0.25 * 0.35)
    m.cancion.terminado = True
    m.ctl._tic_pulso()                                       # acabó; al_terminar = parar
    assert mas.bailes[-1] == (False, None) and not m.ctl.activo and bus(m).bailando == ""
    assert m.cancion.liberada >= 1 and not m.ctl._t_pulso.isActive()


def test_sprites_repetir_y_siguiente_solo_con_cancion(m):
    mas = con_mascota(m, "sprites", con_mmd=False)
    m.ctl.set_al_terminar("repetir")
    m.ctl.reproducir(m.ids["Alfa"])
    m.cancion.terminado = True
    m.ctl._tic_pulso()
    assert m.cancion.reproducciones == [0.25, 0.25] and m.ctl.activo      # otra vez, sin recargar
    m.ctl.set_al_terminar("siguiente")
    m.ctl.reproducir(m.ids["Beta"])
    m.cancion.terminado = True
    m.ctl._tic_pulso()
    assert m.cancion.cargadas[-1] == m.dir / "Alfa" / "cancion.mp3"         # Gamma (sin canción) se salta


def test_sprites_error_al_cargar_la_cancion(m):
    con_mascota(m, "sprites", con_mmd=False)
    m.cancion.ok = (False, "ffmpeg no pudo leer cancion.mp3")
    ok, texto = m.ctl.reproducir(m.ids["Alfa"])
    assert not ok and "ffmpeg" in texto and "ffmpeg" in m.anf.avisos[-1] and bus(m).bailando == ""


# ── Sin mascota ──────────────────────────────────────────────────────────────────

def test_sin_mascota_la_saca_y_arranca_al_llegar(m):
    desp = DespachadorFalso()
    m.esc.registrar("despachador", desp)
    ok, _ = m.ctl.reproducir(m.ids["Alfa"])
    assert ok and desp.ejecutados == ["mascota"] and m.ctl.estado()["pendiente"]
    assert bus(m).bailando == "mmd" and m.ctl._t_mascota.isActive()
    mas = con_mascota(m)
    assert mas.cargas() and mas.cargas()[0]["id"] == m.ids["Alfa"] and mas.despertares == 1
    assert not m.ctl.estado()["pendiente"] and not m.ctl._t_mascota.isActive()


def test_sin_mascota_sale_en_el_acto_o_no_llega(m):
    nueva = MascotaFalsa("vrm")
    desp = DespachadorFalso(al_ejecutar=lambda: m.esc.set_mascota(nueva))
    m.esc.registrar("despachador", desp)
    assert m.ctl.reproducir(m.ids["Beta"])[0]
    assert nueva.cargas()[0]["id"] == m.ids["Beta"] and not m.ctl._t_mascota.isActive()
    m.esc.set_mascota(None)                                  # se cierra la mascota: para
    assert not m.ctl.activo and bus(m).bailando == ""
    desp.al_ejecutar = None
    m.ctl.reproducir(m.ids["Beta"])
    m.ctl._mascota_no_llego()
    assert not m.ctl.activo and "mascota" in m.anf.avisos[-1] and bus(m).bailando == ""


def test_sin_despachador_usa_el_anfitrion(m):
    m.ctl.reproducir(m.ids["Alfa"])
    assert m.anf.alternadas == 1 and m.ctl.estado()["pendiente"]


# ── Tabla de prioridades ─────────────────────────────────────────────────────────

def test_juego_pausa_y_al_salir_sigue(m):
    mas = con_mascota(m)
    m.ctl.reproducir(m.ids["Alfa"])
    ev(m, "sonando")
    assert m.esc.prioridad.iniciar("juego")
    assert mas.ordenes[-1] == ("pausa", {"on": True}) and bus(m).bailando == ""
    e = m.ctl.estado()
    assert e["pausado"] and e["cedida"] and e["fase"] == "pausado"
    ok, texto = m.ctl.reproducir(m.ids["Beta"])              # durante el juego no se cambia
    assert not ok and "juego" in texto
    m.esc.prioridad.terminar("juego")
    assert mas.ordenes[-1] == ("pausa", {"on": False}) and bus(m).bailando == "mmd"
    assert m.ctl.estado()["fase"] == "sonando"


def test_pausa_de_la_persona_sobrevive_a_la_alarma(m):
    mas = con_mascota(m)
    m.ctl.reproducir(m.ids["Alfa"])
    ev(m, "sonando")
    assert m.ctl.pausa() is True and mas.ordenes[-1] == ("pausa", {"on": True})
    m.esc.prioridad.iniciar("alarma")
    m.esc.prioridad.terminar("alarma")
    assert mas.ordenes[-1] == ("pausa", {"on": True}) and m.ctl.estado()["pausado"]
    assert m.ctl.reproducir() == (True, "Sigo bailando.")
    assert mas.ordenes[-1] == ("pausa", {"on": False})


def test_parar_reanuda_la_sentada(m):
    a = AsientoFalso()
    m.esc.registrar("asiento", a, ("sentada",))
    con_mascota(m)
    assert m.esc.prioridad.iniciar("sentada", "barra")
    m.ctl.reproducir(m.ids["Alfa"])
    assert a.cedidas == ["mmd"] and bus(m).sentada == ""
    assert m.ctl.parar() is True
    assert a.reanudadas == ["barra"] and bus(m).sentada == "barra" and bus(m).bailando == ""
    assert m.ctl.parar() is False


def test_parar_durante_el_juego_no_vuelve_al_acabar(m):
    mas = con_mascota(m)
    m.ctl.reproducir(m.ids["Alfa"])
    m.esc.prioridad.iniciar("juego")
    m.ctl.parar()
    n = len(mas.ordenes)
    m.esc.prioridad.terminar("juego")
    assert bus(m).bailando == "" and len(mas.ordenes) == n and not m.ctl.activo


def test_no_empieza_con_alarma(m):
    mas = con_mascota(m)
    m.esc.prioridad.iniciar("alarma")
    ok, texto = m.ctl.reproducir(m.ids["Alfa"])
    assert (ok, texto) == (False, "Ahora no puedo bailar: hay una alarma sonando.")
    assert mas.cargas() == [] and m.ctl.ultimo_motivo == "alarma"


def test_detener_idempotente_y_cambio_de_mascota(m):
    mas = con_mascota(m)
    m.ctl.reproducir(m.ids["Alfa"])
    otra = con_mascota(m)                                    # otra mascota: el baile acaba
    assert not m.ctl.activo and bus(m).bailando == "" and otra.cargas() == []
    m.ctl.reproducir(m.ids["Alfa"])
    m.ctl.detener()
    m.ctl.detener()
    assert not m.ctl.activo and otra.ordenes[-1] == ("parar", None) and bus(m).bailando == ""


# ── Órdenes y ajustes ────────────────────────────────────────────────────────────

def test_volumen_al_terminar_y_en_el_sitio(m):
    mas = con_mascota(m)
    m.ctl.reproducir(m.ids["Alfa"])
    m.ctl.volumen(0.6)
    assert m.cfg.get("baile", "volumen") == 0.6 and mas.ordenes[-1] == ("volumen", {"volumen": 0.6})
    m.ctl.volumen(float("nan"))
    assert m.cfg.get("baile", "volumen") == 0.6
    assert m.ctl.set_al_terminar("repetir") and mas.ordenes[-1] == ("bucle", {"bucle": True})
    assert m.ctl.set_al_terminar("otra") is False and m.cfg.get("baile", "al_terminar") == "repetir"
    m.ctl.set_en_el_sitio(False)
    assert mas.ordenes[-1] == ("en_sitio", {"enSitio": False}) and m.cfg.get("baile", "en_el_sitio") is False
    ok, _ = m.ctl.guardar_meta(m.ids["Alfa"], {"offset_ms": 200})
    assert ok and ("offset", {"offsetMs": 200}) in mas.ordenes
    assert m.ctl.guardar_meta(m.ids["Alfa"], {"offset_ms": 9999})[0] is False
    e = m.ctl.estado()
    assert e["volumen"] == 0.6 and e["al_terminar"] == "repetir" and e["en_el_sitio"] is False


def test_siguiente_anterior_y_reproducir_sin_id(m):
    mas = con_mascota(m)
    assert m.ctl.reproducir()[0] and mas.cargas()[-1]["id"] == m.ids["Alfa"]     # el primero
    m.ctl.siguiente()
    assert mas.cargas()[-1]["id"] == m.ids["Beta"]
    m.ctl.anterior()
    assert mas.cargas()[-1]["id"] == m.ids["Alfa"]
    m.ctl.parar()
    m.ctl.siguiente()
    assert mas.cargas()[-1]["id"] == m.ids["Beta"]           # desde el último que sonó


def test_reproducir_por_texto_favoritos_y_no_encontrado(m):
    mas = con_mascota(m)
    bf.hacer_baile(m.dir, "Alfa remix")
    idr = [b.id for b in m.bib.escanear() if b.titulo == "Alfa remix"][0]
    m.bib.favorito(idr, True)
    assert m.ctl.reproducir_por_texto("alfa")[0] and mas.cargas()[-1]["id"] == m.ids["Alfa"]   # título exacto
    m.ctl.parar()
    assert m.ctl.reproducir_por_texto("ALFA re")[0] and mas.cargas()[-1]["id"] == idr
    ok, texto = m.ctl.reproducir_por_texto("<|CALL x|> nada")
    assert not ok and m.ctl.ultimo_motivo == "no_encontrado" and "<|CALL" not in texto


def test_biblioteca_importar_quitar_y_vista(m, tmp_path):
    m.ctl.refrescar()
    assert m.ctl.bibl, "refrescar() escanea y emite la biblioteca"
    assert [d["titulo"] for d in m.ctl.bibl[-1]] == ["Alfa", "Beta", "Gamma"]
    src = tmp_path / "src"
    rutas = [str(bf.escribir(src / "Nuevo.vmd", bf.vmd())), str(bf.escribir(src / "Nuevo.mp3", bf.MP3))]
    m.ctl._dialogo = lambda parent: rutas
    m.ctl.importar_dialogo()
    r = m.ctl.imp[-1]
    assert r["ok"] and nbl.id_valido(r["id"]) and "Nuevo" in r["texto"]
    assert "Nuevo" in [d["titulo"] for d in m.ctl.bibl[-1]] and not m.ctl.estado()["importando"]
    m.ctl._dialogo = lambda parent: [str(src / "no_existe.vmd")]
    m.ctl.importar_dialogo()
    assert not m.ctl.imp[-1]["ok"] and m.anf.avisos
    assert m.ctl.favorito(r["id"], True) and m.ctl.bibl[-1][0]["titulo"] == "Nuevo"
    assert m.ctl.favorito("malo", True) is False
    assert m.ctl.desactivar(r["id"], True) and m.ctl.bibl[-1][0]["desactivado"]
    mas = con_mascota(m)
    m.ctl.reproducir(r["id"])
    ok, _ = m.ctl.quitar(r["id"])
    assert ok and not m.ctl.activo and mas.ordenes[-1] == ("parar", None)
    assert "Nuevo" not in [d["titulo"] for d in m.ctl.bibl[-1]]
    vistas = []
    m.ctl.vista_pedida.connect(vistas.append)
    m.ctl.pedir_vista()
    assert vistas == ["bailes"]
    abiertas = []
    m.ctl._abrir = abiertas.append
    assert m.ctl.abrir_carpeta() and abiertas == [m.dir]
    assert [d["titulo"] for d in m.ctl.lista("gam")] == ["Gamma"]


def test_estado_json_estable(m):
    con_mascota(m)
    m.ctl.reproducir(m.ids["Alfa"])
    e = m.ctl.estados[-1]
    assert set(e) >= {"fase", "id", "titulo", "autor", "t", "total", "modo", "al_terminar", "volumen",
                      "en_el_sitio", "error", "analizando"}
    n = len(m.ctl.estados)
    m.ctl._emitir_estado()
    assert len(m.ctl.estados) == n                           # sin cambios no se repite


# ── Herramientas del modelo ──────────────────────────────────────────────────────

class DetectorFalso:
    def __init__(self):
        self.on_cambio = self.on_pulso = self.on_sesiones = None
        self.disponible = True

    def iniciar(self):
        pass

    def detener(self):
        pass

    def forzar_pulso(self, on):
        pass

    def silenciar_hasta_silencio(self):
        pass

    def reanudar_auto(self):
        pass

    def pedir_sondeo(self):
        pass


@pytest.fixture
def con_baile(m):
    from ui.baile_qt import ControlBaile
    det = DetectorFalso()
    b = ControlBaile(m.esc, m.cfg, detector=det, en_ui=lambda fn: fn())
    m.esc.registrar("baile", b, ("baile",))
    m.baile, m.det = b, det
    yield m
    b.deleteLater()


def test_listar_bailes(m):
    h = m.ctl.herramientas()
    assert set(h) == {"listar_bailes"}
    r = h["listar_bailes"]({}, None)
    assert r.startswith("Tus bailes (3): ") and "«Alfa»" in r and "«Beta»" in r
    assert h["listar_bailes"]({"texto": "beta"}, {"origen": "usuario"}) == "Tus bailes con «beta» (1): «Beta»."


def test_mascota_bailar_con_cancion_usa_el_mmd_o_el_respaldo(con_baile):
    m = con_baile
    mas = con_mascota(m)
    h = m.baile.herramientas()
    assert h["mascota_bailar"]({"cancion": "beta"}, {}) == "¡A bailar «Beta»!"
    assert bus(m).bailando == "mmd" and mas.cargas()[-1]["id"] == m.ids["Beta"]
    assert h["parar_baile"]({}, None) == "Vale, dejo de bailar."
    assert not m.ctl.activo and bus(m).bailando == "" and mas.ordenes[-1] == ("parar", None)
    r = h["mascota_bailar"]({"cancion": "no existe", "segundos": 10}, {})
    assert r == "¡A bailar! 10 s. No encontré «no existe» en tus bailes: bailo a mi manera."
    assert m.baile.bailando and bus(m).bailando == "manual" and not m.ctl.activo
    m.baile.parar()
    m.esc.prioridad.iniciar("alarma")
    r = h["mascota_bailar"]({"cancion": "alfa"}, {})
    assert r == (False, "Ahora no puedo bailar: hay una alarma sonando.")


def test_mmd_le_quita_el_sitio_al_baile_automatico_y_vuelve(con_baile):
    m = con_baile
    mas = con_mascota(m)
    m.det.on_cambio(True, "Spotify")                         # suena música: baila sola
    assert m.baile.bailando and bus(m).bailando == "musica"
    m.ctl.reproducir(m.ids["Alfa"])
    assert not m.baile.bailando and bus(m).bailando == "mmd" and mas.bailes[-1] == (False, None)
    m.ctl.parar()                                            # la música sigue: vuelve a bailar sola
    assert m.baile.bailando and bus(m).bailando == "musica"
    m.ctl.reproducir(m.ids["Alfa"])
    h = m.baile.herramientas()
    assert h["parar_baile"]({}, None) == "Vale, dejo de bailar."
    assert not m.baile.bailando and not m.ctl.activo and bus(m).bailando == ""   # y no vuelve sola


# ── Mascota escondida (revisión 7-10, BM2) y sprites que se esconden (BM8/RR6) ─────

from PyQt6.QtCore import QObject, pyqtSignal  # noqa: E402


class MascotaQueCalla(QObject):
    """Como ui/companion.py: ESCONDIDA no lee su cola de eventos (la página sigue, pero a
    Python no llega nada hasta que se la ve). Visible, contesta al «cargar» en el acto."""
    visibilidad = pyqtSignal(bool)
    render = "vrm"

    def __init__(self, esc, visible=False):
        super().__init__()
        self.esc, self.vis, self.ordenes, self.cola = esc, visible, [], []
        self.responde = True

    def isVisible(self):
        return self.vis

    def mmd(self, orden, datos=None):
        self.ordenes.append((orden, datos))
        if orden == "cargar" and self.responde:
            for fase in ("cargando", "listo", "sonando"):
                self._evento({"fase": fase, "id": datos["id"]})
        return True

    def _evento(self, d):
        self.cola.append(d)
        if self.vis:
            self._vaciar()

    def _vaciar(self):
        cola, self.cola = self.cola, []
        for d in cola:
            self.esc._on_evento_js("mmd", d)

    def show(self):
        self.vis = True
        self.visibilidad.emit(True)
        self._vaciar()

    def hide(self):
        self.vis = False
        self.visibilidad.emit(False)

    def despertar(self):
        return True

    def cargas(self):
        return [d for o, d in self.ordenes if o == "cargar"]


class AnfitrionQueSaca(Anfitrion):
    """alternar_mascota como el de verdad: si está escondida, la enseña (si puede)."""
    def __init__(self, mascota=None):
        super().__init__()
        self.mascota = mascota

    def alternar_mascota(self):
        self.alternadas += 1
        if self.mascota is not None:
            (self.mascota.hide if self.mascota.isVisible() else self.mascota.show)()
        return True


@pytest.fixture
def vigia_corto(monkeypatch):
    from ui import mmd_qt
    monkeypatch.setattr(mmd_qt, "VIGIA_PRIMERA_MS", 60)
    monkeypatch.setattr(mmd_qt, "VIGIA_CARGA_MS", 60)


def esperar(ms):
    from PyQt6.QtTest import QTest
    QTest.qWait(ms)


def test_mascota_escondida_se_saca_para_bailar_y_no_falla(m, vigia_corto):
    mas = MascotaQueCalla(m.esc)
    m.esc.set_mascota(mas)
    m.ctl.anfitrion = AnfitrionQueSaca(mas)
    ok, _ = m.ctl.reproducir(m.ids["Alfa"])
    assert ok and m.ctl.anfitrion.alternadas == 1 and mas.isVisible(), "se saca como la acción «mascota»"
    assert mas.cargas()[0]["id"] == m.ids["Alfa"] and m.ctl.estado()["fase"] == "sonando"
    esperar(200)
    assert m.ctl.activo and not m.ctl.anfitrion.avisos and bus(m).bailando == "mmd"
    mas.hide()                                        # ▶ con el baile puesto y escondida: se saca otra vez
    assert m.ctl.reproducir() == (True, "Ya estoy bailando «Alfa».") and mas.isVisible()


def test_escondida_que_no_se_puede_sacar_avisa_y_el_vigia_espera_a_verla(m, vigia_corto):
    mas = MascotaQueCalla(m.esc)
    m.esc.set_mascota(mas)
    m.ctl.anfitrion = AnfitrionQueSaca(None)          # no sabe sacarla
    ok, _ = m.ctl.reproducir(m.ids["Alfa"])
    assert ok and m.ctl.anfitrion.avisos == ["La mascota está escondida: bailaré cuando la saques."]
    assert mas.cargas() and not m.ctl._t_vigia.isActive(), "el vigía no cuenta escondida"
    esperar(250)
    assert m.ctl.activo and m.ctl.estado()["fase"] == "cargando" and len(m.ctl.anfitrion.avisos) == 1
    mas.show()                                        # al verla llega lo que tenía en la cola
    assert m.ctl.estado()["fase"] == "sonando" and not m.ctl._t_vigia.isActive()
    # y visible, el vigía sigue valiendo: una que no contesta falla
    m.ctl.parar()
    mas.responde = False
    m.ctl.reproducir(m.ids["Beta"])
    assert m.ctl._t_vigia.isActive()
    esperar(250)
    assert not m.ctl.activo and "no respondió" in m.ctl.anfitrion.avisos[-1]


def test_siguiente_con_la_mascota_escondida_espera_a_que_se_vea(m, vigia_corto):
    mas = MascotaQueCalla(m.esc, visible=True)
    m.esc.set_mascota(mas)
    m.ctl.anfitrion = AnfitrionQueSaca(mas)
    m.ctl.reproducir(m.ids["Alfa"])
    mas.hide()
    ok, _ = m.ctl.siguiente()
    assert ok and m.ctl.anfitrion.alternadas == 0 and not mas.isVisible(), "a mitad, no la saca"
    assert mas.cargas()[-1]["id"] == m.ids["Beta"] and not m.ctl._t_vigia.isActive()
    esperar(250)
    assert m.ctl.activo and m.ctl.estado()["fase"] == "cargando"
    mas.show()
    assert m.ctl.estado()["fase"] == "sonando" and m.ctl.estado()["id"] == m.ids["Beta"]
    # escondida con el vigía en marcha (visible, sin respuesta aún): se para y vuelve entero al verla
    mas.responde = False
    m.ctl.siguiente()
    assert m.ctl._t_vigia.isActive()
    mas.hide()
    assert not m.ctl._t_vigia.isActive()
    m.ctl._vigia_vencido()                            # (si vence igual) escondida no cuenta
    assert m.ctl.activo
    mas.show()
    assert m.ctl._t_vigia.isActive() and m.ctl._t_vigia.interval() == 60


class SpritesFalsos(QObject):
    """AvatarOverlay mínimo: visibilidad, isVisible, cerrado, bailar y pulso."""
    visibilidad = pyqtSignal(bool)
    render = "sprites"

    def __init__(self):
        super().__init__()
        self.vis, self.cerrado, self.bailes, self.pulsos = True, False, [], 0

    def isVisible(self):
        return self.vis and not self.cerrado

    def bailar(self, on, opciones=None):
        self.bailes.append(on)

    def pulso(self, *a):
        self.pulsos += 1

    def hide(self):
        self.vis = False
        self.visibilidad.emit(False)

    def show(self):
        self.vis = True
        self.visibilidad.emit(True)

    def close(self):
        self.cerrado = True
        self.visibilidad.emit(False)


def test_sprites_escondidos_pausan_la_cancion_y_al_volver_sigue(m, caplog):
    s = SpritesFalsos()
    m.esc.set_mascota(s)
    assert m.ctl.reproducir(m.ids["Alfa"])[0] and m.ctl.estado()["fase"] == "sonando"
    assert m.cancion.reproducciones == [0.25] and s.bailes == [True] and m.ctl._t_pulso.isActive()
    s.hide()
    e = m.ctl.estado()
    assert m.cancion.pausas == [True] and s.bailes[-1] is False and not m.ctl._t_pulso.isActive()
    assert e["fase"] == "pausado" and e["pausado"] and not bus(m).visible
    n = s.pulsos
    m.ctl._tic_pulso()                                # ni pulsos a la mascota escondida
    assert s.pulsos == n
    s.show()
    assert m.cancion.pausas == [True, False] and s.bailes[-1] is True and m.ctl._t_pulso.isActive()
    assert m.ctl.estado()["fase"] == "sonando"
    # la pausa de la persona manda: al volver a verla sigue en pausa
    m.ctl.pausa(True)
    s.hide()
    s.show()
    assert m.ctl.estado()["fase"] == "pausado" and m.cancion.pausas[-1] is True
    m.ctl.pausa(False)
    # «Cerrar mascota»: en pausa; y cuando se borra, el baile acaba sin tocarla (ni un error)
    s.close()
    assert m.cancion.pausas[-1] is True and m.ctl.estado()["fase"] == "pausado"
    from PyQt6 import sip
    with caplog.at_level("ERROR"):
        sip.delete(s)
    assert not m.ctl.activo and bus(m).bailando == ""
    assert not [r for r in caplog.records if "falló" in r.getMessage()]


def test_sprites_escondidos_al_empezar_no_suenan_hasta_verla(m):
    s = SpritesFalsos()
    s.vis = False
    m.esc.set_mascota(s)
    m.ctl.siguiente()                                 # sin baile puesto: como ▶ … pero no sabe sacarla
    assert m.ctl.activo and m.cancion.cargadas and m.cancion.reproducciones == []
    assert m.ctl.estado()["fase"] == "pausado"
    s.show()
    assert m.cancion.reproducciones == [0.25] and m.ctl.estado()["fase"] == "sonando"


# ── La biblioteca no congela el hilo de Qt (revisión 7-10, BM4/RR3) ─────────────────

def _rapido(fn, tope=0.05):
    import time
    t0 = time.perf_counter()
    r = fn()
    dt = time.perf_counter() - t0
    assert dt <= tope, f"{dt * 1000:.0f} ms en el hilo de Qt"
    return r


def test_lista_favorito_meta_y_por_texto_no_esperan_al_escaneo(m, monkeypatch):
    """rv710_bailes_bloqueo: refrescar() escanea en su hilo (aquí, un VMD nuevo que tarda 1 s en
    leerse); la lista, buscar, ★, la meta y «pon X» del hilo de Qt usan la foto: ≤ 50 ms."""
    import threading
    import time
    con_mascota(m)
    bf.hacer_baile(m.dir, "Nuevo")
    real = nbl.info_vmd

    def lento(p, **kw):
        if "Nuevo" in str(p):
            time.sleep(1.0)
        return real(p, **kw)
    monkeypatch.setattr(nbl, "info_vmd", lento)
    hilo = threading.Thread(target=m.bib.escanear)
    hilo.start()
    time.sleep(0.1)
    assert [d["titulo"] for d in _rapido(lambda: m.ctl.lista(""))] == ["Alfa", "Beta", "Gamma"]   # la de antes
    assert [d["titulo"] for d in _rapido(lambda: m.ctl.lista("gam"))] == ["Gamma"]
    assert _rapido(lambda: m.ctl.favorito(m.ids["Beta"], True)) is True
    assert _rapido(lambda: m.ctl.guardar_meta(m.ids["Gamma"], {"titulo": "Gamma 2"}))[0]
    assert _rapido(lambda: m.ctl.reproducir_por_texto("alfa"))[0]
    assert hilo.is_alive(), "el escaneo seguía en marcha"
    hilo.join(10)
    titulos = [d["titulo"] for d in m.ctl.lista("")]
    assert titulos[0] == "Beta" and "Nuevo" in titulos and "Gamma 2" in titulos, titulos   # nada se pierde


def test_lista_no_espera_a_un_importar_con_ffmpeg_lento(m, tmp_path):
    """r910_lock: importar un .m4a (copia + ffmpeg, hasta 120 s) ya no retiene el cerrojo."""
    import threading
    import time
    src = tmp_path / "src"
    rutas = [bf.escribir(src / "Lento.vmd", bf.vmd()), bf.escribir(src / "Lento.m4a", bf.M4A)]
    empezo = threading.Event()

    def ffmpeg_lento(cmd, **kw):
        empezo.set()
        time.sleep(1.5)
        return m.ej(cmd, **kw)
    m.bib._ejecutar = ffmpeg_lento
    res = {}
    hilo = threading.Thread(target=lambda: res.update(r=m.bib.importar(rutas)))
    hilo.start()
    assert empezo.wait(5)
    assert len(_rapido(lambda: m.ctl.lista(""))) == 3
    assert _rapido(lambda: m.ctl.favorito(m.ids["Alfa"], True)) is True
    assert _rapido(lambda: m.ctl.lista("alfa"))[0]["favorito"] is True
    hilo.join(10)
    assert res["r"][0] and "Lento" in [d["titulo"] for d in m.ctl.lista("")]


def test_salir_con_el_dialogo_de_importar_abierto_no_importa(m, tmp_path):
    """«Salir» (o un cambio de interfaz) mientras el diálogo modal está abierto: al cerrarse,
    el reproductor ya está detenido y no se importa nada."""
    rutas = [str(bf.escribir(tmp_path / "src" / "Nuevo.vmd", bf.vmd()))]

    def dialogo(parent):
        m.esc.detener()
        return rutas
    m.ctl._dialogo = dialogo
    m.ctl.importar_dialogo()
    assert m.ctl.imp == [] and not m.ctl.estado()["importando"] and not (m.dir / "Nuevo").exists()


def test_dialogo_de_archivos_si_su_ventana_se_borra_con_el_abierto(qapp, monkeypatch):
    from PyQt6 import sip
    from PyQt6.QtWidgets import QFileDialog, QWidget
    from ui import mmd_qt
    ventana = QWidget()

    def exec_y_se_borra(self):
        assert self.parent() is ventana
        sip.delete(ventana)                        # la ventana (y con ella el diálogo) se va
        return 1
    monkeypatch.setattr(QFileDialog, "exec", exec_y_se_borra)
    assert mmd_qt.dialogo_archivos(ventana) == []
    monkeypatch.setattr(QFileDialog, "exec", lambda self: 1)
    monkeypatch.setattr(QFileDialog, "selectedFiles", lambda self: ["C:/x/a.vmd", "C:/x/a.mp3"])
    assert mmd_qt.dialogo_archivos(None) == ["C:/x/a.vmd", "C:/x/a.mp3"]
    monkeypatch.setattr(QFileDialog, "exec", lambda self: 0)
    assert mmd_qt.dialogo_archivos(None) == []


def test_detener_mata_el_ffmpeg_que_sigue_convirtiendo(m):
    """El ffmpeg de convertir/pulso/canción va por nucleo.bailes.ejecutar_proceso: detener el
    reproductor (y salir de Lune: atexit) lo mata en vez de dejarlo solo hasta 120 s."""
    import threading
    import time
    res = {}
    lento = [sys.executable, "-c", "import time; time.sleep(30)"]
    hilo = threading.Thread(target=lambda: res.update(r=nbl.ejecutar_proceso(lento, capture_output=True, timeout=60)))
    hilo.start()
    for _ in range(100):
        if nbl._PROCESOS:
            break
        time.sleep(0.05)
    assert nbl._PROCESOS
    t0 = time.monotonic()
    m.ctl.detener()
    hilo.join(10)
    assert not hilo.is_alive() and time.monotonic() - t0 < 5
    assert res["r"].returncode != 0 and not nbl._PROCESOS


def test_con_un_juego_delante_no_saca_a_la_escondida(m):
    mas = MascotaQueCalla(m.esc, visible=True)
    m.esc.set_mascota(mas)
    m.ctl.anfitrion = AnfitrionQueSaca(mas)
    m.ctl.reproducir(m.ids["Alfa"])
    assert m.esc.prioridad.iniciar("juego")
    mas.hide()                                        # el modo juego la esconde
    assert m.ctl.reproducir()[0] and m.ctl.anfitrion.alternadas == 0 and not mas.isVisible()
    ok, texto = m.ctl.reproducir(m.ids["Beta"])
    assert not ok and "juego" in texto and m.ctl.anfitrion.alternadas == 0
