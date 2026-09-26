"""Tests del catálogo de voces (servicios/voces.py), la voz del personaje
(nucleo/personajes.py) y la validación de voces de Kokoro. Sin red: la lista
online se sustituye por una función falsa y el reloj es un número."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from servicios import voces  # noqa: E402
from nucleo import personajes  # noqa: E402
from lune_core.voz import kokoro_backend  # noqa: E402

DIA = 24 * 3600


@pytest.fixture(autouse=True)
def _aislar(tmp_path, monkeypatch):
    """Caché en una carpeta temporal, sin fallos de red previos y SIN red: si
    algo intenta descargar la lista de verdad (cargar=None), falla como sin conexión."""
    monkeypatch.setattr(voces, "RUTA_CACHE", tmp_path / "cache" / "voces_edge.json")
    monkeypatch.setattr(voces, "_ultimo_fallo", None)
    real = voces._descargar

    def sin_red(cargar=None):
        if cargar is None:
            raise OSError("sin red en los tests")
        return real(cargar)

    monkeypatch.setattr(voces, "_descargar", sin_red)
    yield
    voces.esperar_actualizacion(5)


class Cfg:
    """Config falsa con la misma firma que nucleo.config.Config.get."""
    def __init__(self, **voz):
        self.d = {"voz": voz}

    def get(self, seccion, clave, default=None):
        return self.d.get(seccion, {}).get(clave, default)


def _crudas():
    """Respuesta tipo edge_tts.list_voices(): españolas, multilingües y otras."""
    return [
        {"ShortName": "es-MX-DaliaNeural", "Locale": "es-MX", "Gender": "Female"},
        {"ShortName": "es-AR-TomasNeural", "Locale": "es-AR", "Gender": "Male"},
        {"ShortName": "es-XX-NuevaNeural", "Locale": "es-XX", "Gender": "Female"},
        {"ShortName": "en-US-AvaMultilingualNeural", "Locale": "en-US", "Gender": "Female"},
        {"ShortName": "en-US-GuyNeural", "Locale": "en-US", "Gender": "Male"},
        {"ShortName": "fr-FR-DeniseNeural", "Locale": "fr-FR", "Gender": "Female"},
        {"basura": True},
    ]


# ── Listas embebidas ────────────────────────────────────────────────────────────

def test_45_espanolas_y_12_multilingues():
    assert len(voces.VOCES_EDGE_ES) == 45
    assert len(voces.MULTILINGUES) == 12
    ids = [v.id for v in voces.VOCES_EDGE]
    assert len(ids) == len(set(ids)), "ids repetidos"
    assert all(v.id.startswith("es-") for v in voces.VOCES_EDGE_ES)
    assert all(v.id.endswith("MultilingualNeural") and v.multilingue for v in voces.MULTILINGUES)
    assert all(voces.es_id_edge(i) for i in ids)
    assert all(v.genero in ("F", "M") for v in voces.VOCES_EDGE)
    # Cada región tiene nombre de país en español (no se queda en el código).
    assert all(len(v.pais) > 2 for v in voces.VOCES_EDGE), [v for v in voces.VOCES_EDGE if len(v.pais) <= 2]
    assert voces.VOZ_POR_DEFECTO in ids


def test_nombre_y_pais_de_una_voz():
    dalia = next(v for v in voces.VOCES_EDGE_ES if v.id == "es-MX-DaliaNeural")
    assert (dalia.nombre, dalia.pais, dalia.genero, dalia.locale) == ("Dalia", "México", "F", "es-MX")
    ava = next(v for v in voces.MULTILINGUES if v.id == "en-US-AvaMultilingualNeural")
    assert ava.nombre == "Ava"


def test_kokoro_voces_se_calculan_al_pedirlas():
    k = voces.KOKORO_VOCES
    assert "ef_dora" in k and "af_heart" in k and "bm_george" in k


# ── Validación ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("valor,ok", [
    ("+0%", True), ("-10%", True), ("+150%", True),
    ("10%", False), ("+10", False), ("+10Hz", False), ("+1.5%", False), (10, False), (None, False),
])
def test_validar_rate_y_volumen(valor, ok):
    assert voces.validar_rate(valor) is ok
    assert voces.validar_volumen(valor) is ok


@pytest.mark.parametrize("valor,ok", [
    ("+0Hz", True), ("-20Hz", True), ("+5hz", False), ("5Hz", False), ("+5%", False), (5, False),
])
def test_validar_pitch(valor, ok):
    assert voces.validar_pitch(valor) is ok


def test_normalizar_acepta_numeros_y_acota():
    assert voces.normalizar_rate(10) == "+10%"
    assert voces.normalizar_rate("-15") == "-15%"
    assert voces.normalizar_rate(" +20 % ") == "+20%"
    assert voces.normalizar_rate(999) == "+200%"
    assert voces.normalizar_rate("rápido") is None
    assert voces.normalizar_rate(True) is None
    assert voces.normalizar_pitch("-5Hz") == "-5Hz"
    assert voces.normalizar_pitch(-500) == "-100Hz"
    assert voces.normalizar_volumen(0) == "+0%"
    assert voces.porcentaje("+25%") == 25 and voces.porcentaje("mal") == 0


# ── Lista online con caché (TTL con reloj falso) ─────────────────────────────────

def test_listar_edge_descarga_filtra_y_respeta_ttl(tmp_path):
    cache = tmp_path / "v.json"
    llamadas = []

    def cargar():
        llamadas.append(1)
        return _crudas()

    t0 = 1_000_000.0
    lista = voces.listar_edge(cache, cargar=cargar, reloj=lambda: t0, esperar=True)
    ids = {v["id"] for v in lista}
    assert ids == {"es-MX-DaliaNeural", "es-AR-TomasNeural", "es-XX-NuevaNeural",
                   "en-US-AvaMultilingualNeural"}
    assert len(llamadas) == 1
    assert json.loads(cache.read_text(encoding="utf-8"))["ts"] == t0

    # A los 6 días la caché vale: ni red ni hilo.
    assert voces.listar_edge(cache, cargar=cargar, reloj=lambda: t0 + 6 * DIA, esperar=True) == lista
    assert len(llamadas) == 1

    # A los 8 días caduca y se vuelve a pedir.
    voces.listar_edge(cache, cargar=cargar, reloj=lambda: t0 + 8 * DIA, esperar=True)
    assert len(llamadas) == 2
    # La voz nueva de la caché cuenta como conocida.
    assert "es-XX-NuevaNeural" in voces.ids_edge(cache)


def test_listar_edge_en_hilo_devuelve_ya_la_estatica(tmp_path):
    import threading
    cache = tmp_path / "v.json"
    puede_seguir = threading.Event()
    recibidas = []

    def cargar_lenta():
        puede_seguir.wait(5)
        return _crudas()

    lista = voces.listar_edge(cache, cargar=cargar_lenta, al_actualizar=recibidas.append)
    assert len(lista) == 57                   # no esperó a la red
    assert not cache.exists()
    puede_seguir.set()
    assert voces.esperar_actualizacion(5)
    assert cache.exists()
    assert recibidas and {v["id"] for v in recibidas[0]} >= {"es-XX-NuevaNeural"}


def test_sin_red_usa_la_estatica_y_no_reintenta_enseguida(tmp_path):
    cache = tmp_path / "v.json"
    llamadas = []

    def falla():
        llamadas.append(1)
        raise OSError("sin red")

    reloj = [5000.0]
    lista = voces.listar_edge(cache, cargar=falla, reloj=lambda: reloj[0], esperar=True)
    assert len(lista) == 57 and len(llamadas) == 1
    reloj[0] += 60
    voces.listar_edge(cache, cargar=falla, reloj=lambda: reloj[0], esperar=True)
    assert len(llamadas) == 1                 # dentro de los 10 min de espera
    reloj[0] += voces.REINTENTO_S
    voces.listar_edge(cache, cargar=falla, reloj=lambda: reloj[0], esperar=True)
    assert len(llamadas) == 2


def test_cache_rota_o_lista_vacia_no_rompen(tmp_path):
    cache = tmp_path / "v.json"
    cache.write_text("{no es json", encoding="utf-8")
    assert len(voces.listar_edge(cache, cargar=lambda: [], reloj=lambda: 1.0, esperar=True)) == 57
    # Una respuesta sin voces en español no pisa nada.
    assert cache.read_text(encoding="utf-8") == "{no es json"


def test_buscar_y_texto_para_patata():
    mex = voces.buscar_edge("mexico")
    assert {v["id"] for v in mex} == {"es-MX-DaliaNeural", "es-MX-JorgeNeural"}
    assert all(v["genero"] == "F" for v in voces.buscar_edge("mujer"))
    assert len(voces.buscar_edge("multi")) == 12
    texto = voces.texto_voces("mexico", actual="es-MX-DaliaNeural", voces=voces.voces_estaticas())
    assert "*es-MX-DaliaNeural (F)" in texto and "es-MX-JorgeNeural (M)" in texto
    assert "No hay voces" in voces.texto_voces("zzz", voces=voces.voces_estaticas())


# ── resolver_voz: personaje > config > por defecto ───────────────────────────────

def test_resolver_sin_nada_da_los_valores_por_defecto():
    p = voces.resolver_voz(None, None)
    assert p == voces.ParamsVoz("auto", "es-MX-DaliaNeural", "+0%", "+0Hz", "+0%", "com.mx")


def test_resolver_config_sobre_defecto():
    cfg = Cfg(edge_voz="es-ES-ElviraNeural", edge_rate="-10%", edge_pitch="+5Hz",
              edge_volumen="+20%", gtts_tld="es")
    p = voces.resolver_voz(cfg, {"nombre": "Lune"})
    assert (p.id, p.rate, p.pitch, p.volumen, p.tld) == ("es-ES-ElviraNeural", "-10%", "+5Hz", "+20%", "es")


def test_resolver_personaje_sobre_config_campo_a_campo():
    cfg = Cfg(edge_voz="es-ES-ElviraNeural", edge_rate="-10%", edge_pitch="+5Hz")
    pers = {"nombre": "Aria", "voz": {"id": "es-AR-ElenaNeural", "rate": 15}}
    p = voces.resolver_voz(cfg, pers)
    assert p.id == "es-AR-ElenaNeural"        # del personaje
    assert p.rate == "+15%"                   # del personaje (número normalizado)
    assert p.pitch == "+5Hz"                  # el personaje no lo trae: de config
    assert p.motor == "edge"                  # deducido del id (config en auto)


def test_resolver_valores_invalidos_caen_al_siguiente():
    cfg = Cfg(edge_voz="Dalia", edge_rate="+10%", edge_pitch="+5%", gtts_tld="fr")
    pers = {"voz": {"id": "no-es-una-voz", "rate": "rapidito", "tld": "xx"}}
    p = voces.resolver_voz(cfg, pers)
    assert p.id == voces.VOZ_POR_DEFECTO      # ni el del personaje ni el de config valen
    assert p.rate == "+10%"                   # el de config sí
    assert p.pitch == "+0Hz" and p.tld == "com.mx"


def test_resolver_forma_corta_y_motores():
    assert voces.resolver_voz(None, {"voz": "es-CL-CatalinaNeural"}).id == "es-CL-CatalinaNeural"
    # gTTS no tiene voces: id vacío y cuenta el acento.
    g = voces.resolver_voz(Cfg(gtts_tld="us"), {"voz": {"motor": "gtts"}})
    assert (g.motor, g.id, g.tld) == ("gtts", "", "us")
    # Motor global kokoro con voz de edge en el personaje: manda el global y la
    # voz de edge (inválida para Kokoro) cae a la de config.
    k = voces.resolver_voz(Cfg(motor_salida="kokoro", kokoro_voz="em_alex"), {"voz": {"id": "es-AR-ElenaNeural"}})
    assert (k.motor, k.id) == ("kokoro", "em_alex")
    # Un motor fijado en el personaje manda sobre el global.
    e = voces.resolver_voz(Cfg(motor_salida="kokoro"), {"voz": {"motor": "edge", "id": "es-AR-ElenaNeural"}})
    assert (e.motor, e.id) == ("edge", "es-AR-ElenaNeural")
    # Forzar edge (respaldo cuando Kokoro no está) da una voz de edge.
    assert voces.resolver_voz(Cfg(edge_voz="es-PE-CamilaNeural"), {"voz": {"id": "af_heart"}},
                              motor="edge").id == "es-PE-CamilaNeural"


def test_params_desde_lo_que_manda_la_interfaz():
    base = voces.ParamsVoz("edge", "es-MX-DaliaNeural", "+0%", "+0Hz", "+0%", "com.mx")
    p = voces.params_desde('{"id": "es-UY-ValentinaNeural", "rate": -20, "pitch": "+3Hz"}', base)
    assert (p.id, p.rate, p.pitch, p.volumen) == ("es-UY-ValentinaNeural", "-20%", "+3Hz", "+0%")
    assert voces.params_desde({"id": "inventada"}, base).id == "es-MX-DaliaNeural"
    assert voces.params_desde("no es json", base) == base
    assert voces.params_desde({"motor": "gtts", "tld": "es"}, base).tld == "es"
    # También con las claves planas de config que usa la tarjeta de ajustes.
    plano = voces.params_desde({"motor_salida": "edge", "edge_voz": "es-DO-RamonaNeural",
                                "edge_rate": "+10%", "edge_pitch": "-5Hz", "gtts_tld": "us",
                                "texto": "hola"}, base)
    assert (plano.motor, plano.id, plano.rate, plano.pitch, plano.tld) == (
        "edge", "es-DO-RamonaNeural", "+10%", "-5Hz", "us")


# ── Voz del personaje (nucleo/personajes.py) ─────────────────────────────────────

def test_voz_de_limpia_y_admite_forma_corta():
    assert personajes.voz_de(None) == {}
    assert personajes.voz_de({"nombre": "x"}) == {}
    assert personajes.voz_de({"voz": " es-AR-ElenaNeural "}) == {"id": "es-AR-ElenaNeural"}
    v = personajes.voz_de({"voz": {"motor": "edge", "id": "es-AR-ElenaNeural", "rate": -10,
                                   "pitch": "", "tld": True, "otra": "x", "id_extra": 3}})
    assert v == {"motor": "edge", "id": "es-AR-ElenaNeural", "rate": -10}


@pytest.fixture
def almacen(monkeypatch):
    """datos.json en memoria, con Aria como personaje activo."""
    datos = {"bot": {"personaje_default": "Aria"},
             "personajes": [{"nombre": "Lune", "systemPrompt": "x"},
                            {"nombre": "Aria", "systemPrompt": "y", "voz": {"rate": "-5%"}}]}
    monkeypatch.setattr(personajes, "_load", lambda: json.loads(json.dumps(datos)))
    monkeypatch.setattr(personajes, "_save", lambda d: datos.update(json.loads(json.dumps(d))))
    return datos


def _aria(datos):
    return next(p for p in datos["personajes"] if p["nombre"] == "Aria")


def test_set_voz_guarda_y_quita(almacen):
    assert personajes.set_voz("aria", {"id": "es-CU-BelkysNeural", "basura": 1})
    assert _aria(almacen)["voz"] == {"id": "es-CU-BelkysNeural"}
    assert personajes.set_voz("Aria", None)
    assert "voz" not in _aria(almacen)
    assert not personajes.set_voz("Nadie", {"id": "es-CU-BelkysNeural"})


# ── Herramienta cambiar_voz ──────────────────────────────────────────────────────

def test_herramienta_cambiar_voz_valida_y_guarda_en_el_activo(almacen):
    refrescos = []

    class VozFalsa:
        def invalidar_params(self):
            refrescos.append(1)

    msg = voces.herramienta_cambiar_voz({"voz": "es-ar-elenaneural"}, {"voice": VozFalsa()})
    assert "es-AR-ElenaNeural" in msg and "Argentina" in msg
    # Se guarda en el personaje activo (Aria), con el id canónico y sin perder la velocidad.
    assert _aria(almacen)["voz"] == {"rate": "-5%", "motor": "edge", "id": "es-AR-ElenaNeural"}
    assert "voz" not in almacen["personajes"][0]
    assert refrescos == [1]


@pytest.mark.parametrize("args", [{"voz": "es-XX-InventadaNeural"}, {"voz": ""}, {}, {"voz": 42}, None])
def test_herramienta_rechaza_lo_que_no_esta_en_la_lista(almacen, args):
    antes = json.dumps(almacen, sort_keys=True)
    with pytest.raises(ValueError):
        voces.herramienta_cambiar_voz(args, None)
    assert json.dumps(almacen, sort_keys=True) == antes


def test_herramienta_acepta_ids_de_la_cache(almacen, tmp_path):
    voces.listar_edge(cargar=_crudas, reloj=lambda: 1.0, esperar=True)   # a la caché del fixture
    voces.herramienta_cambiar_voz({"voz": "es-XX-NuevaNeural"}, None)
    assert _aria(almacen)["voz"]["id"] == "es-XX-NuevaNeural"


def test_comando_voz_de_patata(almacen):
    class VozFalsa:
        _enabled = False
        engine_name = "edge-tts"
        def __init__(self):
            self.pruebas, self.canceladas, self.reinicios = [], 0, 0
        def probar_voz(self, params, texto):
            self.pruebas.append(texto); return True
        def cancelar(self):
            self.canceladas += 1
        def reiniciar_motor(self):
            self.reinicios += 1; return "gTTS"
        def invalidar_params(self):
            pass

    v = VozFalsa()
    assert voces.comando_voz("on", None, v) == "Voz activada." and v._enabled
    assert voces.comando_voz("off", None, v) == "Voz desactivada." and not v._enabled and v.canceladas == 1
    assert voces.comando_voz("prueba hola", None, v) == "Probando la voz…" and v.pruebas == ["hola"]
    assert "Motor desconocido" in voces.comando_voz("motor turbo", None, v)
    assert voces.comando_voz("motor gtts", None, v) == "Motor de voz: gTTS." and v.reinicios == 1
    assert _aria(almacen)["voz"]["motor"] == "gtts"
    assert voces.comando_voz("velocidad -10", None, v) == "Velocidad: -10%."
    assert voces.comando_voz("tono 7", None, v) == "Tono: +7Hz."
    assert voces.comando_voz("es-PE-AlexNeural", None, v).startswith("Listo")
    assert _aria(almacen)["voz"] == {"rate": "-10%", "motor": "edge", "pitch": "+7Hz", "id": "es-PE-AlexNeural"}
    assert "No conozco la voz" in voces.comando_voz("es-XX-NadaNeural", None, v)
    assert "desactivada" in voces.comando_voz("", None, v)


def test_catalogo_es_json(almacen):
    c = voces.catalogo(Cfg(edge_voz="es-ES-ElviraNeural"))
    json.dumps(c)
    assert len(c["edge"]) == 45 and len(c["multilingues"]) == 12
    assert c["personaje"] == "Aria" and c["personaje_voz"] == {"rate": "-5%"}
    assert c["actual"]["id"] == "es-ES-ElviraNeural" and c["actual"]["rate"] == "-5%"
    assert set(c["gtts_tld"]) >= {"com.mx", "es", "us"}
    assert "disponible" in c["kokoro"]


# ── Kokoro: voces inglesas y validación contra lo instalado ──────────────────────

def test_kokoro_voces_en_y_validacion_sin_instalar(tmp_path):
    assert set(kokoro_backend.VOCES_ES) <= set(kokoro_backend.VOCES)
    assert kokoro_backend.VOCES_EN and all(k[0] in "ab" and k[1] in "fm" and k[2] == "_"
                                           for k in kokoro_backend.VOCES_EN)
    vacia = str(tmp_path / "sin_pesos")
    assert kokoro_backend.voces_instaladas(vacia) == []
    assert kokoro_backend.validar_voz("af_heart", vacia) == "af_heart"     # en la lista
    assert kokoro_backend.validar_voz("zz_nada", vacia) == kokoro_backend.VOZ_POR_DEFECTO


def test_kokoro_valida_contra_lo_instalado(tmp_path):
    np = pytest.importorskip("numpy")
    carpeta = tmp_path / "pesos"
    carpeta.mkdir()
    ruta = carpeta / kokoro_backend.ARCHIVO_VOCES
    with open(ruta, "wb") as f:                       # voices-v1.0.bin es un .npz
        np.savez(f, ef_dora=np.zeros(3), af_heart=np.zeros(3), ff_siwis=np.zeros(3))
    inst = kokoro_backend.voces_instaladas(str(carpeta))
    assert inst == ["af_heart", "ef_dora", "ff_siwis"]
    assert kokoro_backend.validar_voz("af_heart", str(carpeta)) == "af_heart"
    assert kokoro_backend.validar_voz("bm_george", str(carpeta)) == "ef_dora"  # conocida pero no instalada
    assert kokoro_backend.validar_voz("ff_siwis", str(carpeta)) == "ff_siwis"  # instalada aunque no esté en VOCES
    assert kokoro_backend.validar_voz("x", instaladas=["af_heart"]) == "af_heart"


def test_kokoro_sintetizar_usa_voz_valida_e_idioma_del_texto(monkeypatch):
    pytest.importorskip("numpy")
    pedidas = []

    class KokoroFalso:
        def get_voices(self):
            return ["af_heart", "ef_dora"]

        def create(self, texto, voice, speed, lang):
            pedidas.append((voice, speed, lang))
            return [0.0, 0.1, -0.1], 24000

    monkeypatch.setattr(kokoro_backend, "cargar", lambda carpeta=None: KokoroFalso())
    for voz in ("af_heart", "bm_george"):
        ruta = kokoro_backend.sintetizar("hola", voz=voz, velocidad=1.2, idioma="es")
        assert ruta and Path(ruta).exists()
        Path(ruta).unlink()
    assert pedidas == [("af_heart", 1.2, "es"), ("ef_dora", 1.2, "es")]


def test_kokoro_idioma_y_rutas_ancladas():
    assert kokoro_backend.idioma_fonemas("es") == "es"
    assert kokoro_backend.idioma_fonemas("en", "bf_emma") == "en-gb"
    assert kokoro_backend.idioma_fonemas("en", "af_heart") == "en-us"
    assert kokoro_backend.idioma_fonemas("auto") == "es"
    onnx, _ = kokoro_backend._rutas("modelos_voz")
    assert onnx.is_absolute() and onnx.parent == kokoro_backend.RAIZ / "modelos_voz"


def test_numeros_no_finitos_no_revientan():
    """G7: «/voz velocidad inf» (o un rate "inf%" en datos.json) lanzaba OverflowError."""
    for malo in ("inf", "-inf%", "nan", "NaNHz", "1e999", float("inf"), float("nan"), 10 ** 400):
        assert voces.normalizar_rate(malo) is None, malo
        assert voces.normalizar_pitch(malo) is None, malo
        assert voces.normalizar_volumen(malo) is None, malo
    assert "Pon un número" in voces.comando_voz("velocidad inf")
    p = voces.resolver_voz(None, {"voz": {"id": "es-MX-DaliaNeural", "rate": "inf%", "pitch": "nan"}})
    assert (p.rate, p.pitch) == (voces.RATE_POR_DEFECTO, voces.PITCH_POR_DEFECTO)
    # La ayuda de /voz dice el rango de verdad (lo de fuera se recorta).
    assert "-90…+200" in voces.comando_voz.__doc__ and "-100…+100" in voces.comando_voz.__doc__
    assert voces.normalizar_rate("500") == "+200%" and voces.normalizar_pitch(-300) == "-100Hz"
