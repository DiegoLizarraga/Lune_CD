"""
Tests de nucleo/nombres_antiguos.py: lo guardado con los nombres de antes de la 11 sigue
funcionando con los de ahora (modo «asistente en escritorio»).

Este archivo y nucleo/nombres_antiguos.py son los ÚNICOS del repo que pueden escribir la
palabra vieja («mascota»): tests/test_sin_nombre_antiguo.py lo vigila.

Qué se comprueba:
- las tablas: cada nombre viejo lleva la palabra vieja, el nuevo no, y el nuevo existe
  (acción de la interfaz, herramienta del catálogo, modo de autoinicio, tipo del hub);
- config.json (esquema 2): atajos, bandeja, menú radial y autoinicio_como pasan al nombre
  de ahora una sola vez, sin tocar nada más; con los dos nombres gana el nuevo; un umbral
  de baile elegido después de la migración 1 se respeta; una segunda carga no reescribe;
- datos.json: personajes[].frases_mascota → frases_asistente al cargar (sin escribir el
  archivo) y al guardar; si están las dos, gana la nueva y se conserva lo que no choca;
  personajes.py y las frases de lune_core/frases_asistente la ven;
- marcadores: <|mascota_bailar(…)|>, <|CALL ["mascota_dormir", {}]|>… → herramienta de ahora;
- un id viejo que vuelve a config.json DESPUÉS de la migración (esquema ya en 2) se entiende
  al leerlo: bandeja, radial, Despachador y atajos siguen funcionando;
- bailes/LEEME.txt (fuera de git): el que escribió Lune antes de la 11 se reescribe; el de la
  persona no se toca.
"""
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lune_core import marcadores as M  # noqa: E402
from lune_core import protocolo  # noqa: E402
from lune_core.catalogo_herramientas import CATALOGO  # noqa: E402
from lune_core.frases_asistente import frases_de_personaje  # noqa: E402
from nucleo import acciones_ui, arranque, datos, personajes  # noqa: E402
from nucleo import bailes as nbl  # noqa: E402
from nucleo import nombres_antiguos as NA  # noqa: E402
from nucleo.config import Config  # noqa: E402

VIEJA = "mascota"
TABLAS = {
    "ACCIONES": NA.ACCIONES, "COMOS_AUTOINICIO": NA.COMOS_AUTOINICIO,
    "HERRAMIENTAS": NA.HERRAMIENTAS, "CLAVES_PERSONAJE": NA.CLAVES_PERSONAJE,
    "TIPOS_EVENTO": NA.TIPOS_EVENTO,
}


def leer(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


# ── Tablas ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("nombre", sorted(TABLAS))
def test_cada_nombre_viejo_pasa_a_su_nuevo(nombre):
    tabla = TABLAS[nombre]
    assert tabla, nombre
    for viejo, nuevo in tabla.items():
        assert VIEJA in viejo.lower(), (nombre, viejo)
        assert VIEJA not in nuevo.lower() and NA.NUEVA in nuevo, (nombre, nuevo)
        assert nuevo == viejo.replace(VIEJA, NA.NUEVA), (nombre, viejo, nuevo)
    assert NA.VIEJA == VIEJA and NA.NUEVA == "asistente"


def test_los_nombres_nuevos_existen_y_los_viejos_ya_no():
    for viejo, nuevo in NA.ACCIONES.items():
        assert nuevo in acciones_ui.ACCIONES and viejo not in acciones_ui.ACCIONES
    for viejo, nuevo in NA.HERRAMIENTAS.items():
        assert nuevo in CATALOGO and viejo not in CATALOGO
    for viejo, nuevo in NA.COMOS_AUTOINICIO.items():
        assert nuevo in arranque.COMOS and viejo not in arranque.COMOS
    tipos = {t.value for t in protocolo.Tipo}
    for viejo, nuevo in NA.TIPOS_EVENTO.items():
        assert nuevo in tipos and viejo not in tipos
    assert NA.CLAVES_PERSONAJE == {"frases_mascota": "frases_asistente"}


def test_todas_las_herramientas_de_la_asistente_tienen_su_nombre_viejo():
    # Las seis que había en la 10.9; una herramienta nueva de la 11 en adelante no lo necesita.
    assert set(NA.HERRAMIENTAS.values()) == {
        "asistente_bailar", "asistente_despertar", "asistente_dormir",
        "asistente_pantalla_grande", "asistente_sentarse", "asistente_tamano"}


def test_valores_sueltos():
    assert NA.accion("mascota") == "asistente" and NA.accion("cerrar_mascota") == "cerrar_asistente"
    assert NA.accion("voz") == "voz" and NA.accion(None) is None and NA.accion(3) == 3
    assert NA.como_autoinicio("mascota") == "asistente"
    assert NA.como_autoinicio("  Mascota ") == "asistente"          # como lo compara arranque
    assert NA.como_autoinicio("ventana") == "ventana" and NA.como_autoinicio(None) is None
    assert arranque.como({"sistema": {"autoinicio_como": NA.como_autoinicio("MASCOTA")}}) == "asistente"
    assert NA.herramienta("mascota_bailar") == "asistente_bailar"
    assert NA.herramienta("abrir_url") == "abrir_url"
    assert NA.tipo_evento("mascota:accion") == "asistente:accion"
    assert protocolo.es_tipo_conocido(NA.tipo_evento("mascota:accion"))
    assert NA.tipo_evento("input:text") == "input:text"


def test_listas_de_acciones_sin_tocar_la_de_entrada():
    entrada = ["voz", "mascota", "dormir", "cerrar_mascota"]
    copia = list(entrada)
    nueva, cambio = NA.migrar_lista_acciones(entrada)
    assert cambio and nueva == ["voz", "asistente", "dormir", "cerrar_asistente"]
    assert entrada == copia, "la lista de entrada no se toca"
    # con los dos nombres gana el nuevo, y no quedan repetidos
    assert NA.migrar_lista_acciones(["mascota", "asistente", "voz"]) == (["asistente", "voz"], True)
    assert NA.migrar_lista_acciones(["mascota", "mascota", 7]) == (["asistente", 7], True)
    # idempotente y sin cambios → la MISMA lista
    assert NA.migrar_lista_acciones(nueva) == (nueva, False)
    assert NA.migrar_lista_acciones(nueva)[0] is nueva
    assert NA.migrar_lista_acciones(None) == (None, False)
    assert NA.migrar_lista_acciones("mascota") == ("mascota", False)


def test_atajos_conservan_su_combo():
    entrada = [{"id": "mostrar_lune", "combo": "ctrl+alt+shift+l"},
               {"id": "mascota", "combo": "ctrl+alt+shift+p"}, "basura", {"combo": "x"}]
    copia = copy.deepcopy(entrada)
    nueva, cambio = NA.migrar_atajos(entrada)
    assert cambio and nueva == [{"id": "mostrar_lune", "combo": "ctrl+alt+shift+l"},
                                {"id": "asistente", "combo": "ctrl+alt+shift+p"}, "basura", {"combo": "x"}]
    assert entrada == copia, "ni la lista ni sus entradas se tocan"
    assert NA.migrar_atajos(nueva) == (nueva, False)
    # con los dos, gana la entrada nueva (su combo)
    dos = [{"id": "mascota", "combo": "ctrl+alt+shift+p"}, {"id": "asistente", "combo": "ctrl+alt+shift+m"}]
    assert NA.migrar_atajos(dos) == ([{"id": "asistente", "combo": "ctrl+alt+shift+m"}], True)
    assert NA.migrar_atajos({"id": "mascota"}) == ({"id": "mascota"}, False)


# ── config.json ────────────────────────────────────────────────────────────────

def _config_10_9(version=1, **cambios) -> dict:
    """Un config.json como lo dejaba la 10.9 (esquema 1) con los nombres de antes."""
    d = {
        "features": {"voz_auto": True, "markdown": False},
        "avatar": {"render": "vrm", "vrm_tamano": "grande", "overlay_x": 40},
        "baile": {"auto": True, "umbral": 0.2},         # elegido DESPUÉS de la migración 1
        "atajos": {"activo": True, "lista": [
            {"id": "mostrar_lune", "combo": "ctrl+alt+shift+l"},
            {"id": "mascota", "combo": "ctrl+alt+shift+p"},          # combo cambiado a mano
            {"id": "voz", "combo": "ctrl+alt+shift+v"},
        ]},
        "bandeja": {"acciones": ["voz", "mascota", "dormir", "minecraft"]},
        "menu_radial": {"principal": ["chat", "cerrar_mascota", "dormir"],
                        "secundario": ["comer_batido", "mascota"]},
        "sistema": {"autoinicio": True, "autoinicio_como": "mascota", "autoinicio_retraso_s": 45},
        "esquema": {"version": version},
    }
    for ruta, valor in cambios.items():
        sec, clave = ruta.split("__")
        d[sec][clave] = valor
    return d


def _como_nuevo(d: dict) -> dict:
    """El mismo config con los nombres de ahora y el esquema de ahora."""
    n = copy.deepcopy(d)
    n["atajos"]["lista"] = [{**e, "id": NA.accion(e["id"])} for e in n["atajos"]["lista"]]
    for sec, clave in (("bandeja", "acciones"), ("menu_radial", "principal"), ("menu_radial", "secundario")):
        n[sec][clave] = [NA.accion(x) for x in n[sec][clave]]
    n["sistema"]["autoinicio_como"] = NA.como_autoinicio(n["sistema"]["autoinicio_como"])
    n["esquema"] = {"version": Config.DEFAULT_CONFIG["esquema"]["version"]}
    return n


def test_el_esquema_sube_a_2():
    assert Config.DEFAULT_CONFIG["esquema"]["version"] == 2
    # Los valores por defecto ya nacen con los nombres de ahora.
    texto = json.dumps(Config.DEFAULT_CONFIG, ensure_ascii=False).lower()
    assert VIEJA not in texto


def test_config_de_la_10_9_pasa_a_los_nombres_de_ahora(tmp_path):
    viejo = tmp_path / "viejo" / "config.json"
    nuevo = tmp_path / "nuevo" / "config.json"
    for ruta, d in ((viejo, _config_10_9()), (nuevo, _como_nuevo(_config_10_9()))):
        ruta.parent.mkdir()
        ruta.write_text(json.dumps(d), encoding="utf-8")

    c = Config(config_path=str(viejo))
    assert c.get("atajos", "lista")[1] == {"id": "asistente", "combo": "ctrl+alt+shift+p"}
    assert c.get("bandeja", "acciones") == ["voz", "asistente", "dormir", "minecraft"]
    assert c.get("menu_radial", "principal") == ["chat", "cerrar_asistente", "dormir"]
    assert c.get("menu_radial", "secundario") == ["comer_batido", "asistente"]
    assert c.get("sistema", "autoinicio_como") == "asistente"
    assert arranque.como(c) == "asistente"
    # Sin tocar nada más: queda IGUAL que el mismo config escrito ya con los nombres de ahora.
    assert c.config == Config(config_path=str(nuevo)).config
    assert leer(viejo) == leer(nuevo)
    assert leer(viejo)["esquema"]["version"] == 2
    assert leer(viejo)["baile"]["umbral"] == 0.2, "la migración 1 no se repite"
    assert VIEJA not in viejo.read_text(encoding="utf-8").lower()


def test_la_migracion_es_de_una_vez_e_idempotente(tmp_path):
    ruta = tmp_path / "config.json"
    ruta.write_text(json.dumps(_config_10_9()), encoding="utf-8")
    Config(config_path=str(ruta))
    migrado = ruta.read_bytes()
    antes = ruta.stat().st_mtime_ns
    c = Config(config_path=str(ruta))                  # segunda carga: nada que hacer
    assert ruta.read_bytes() == migrado and ruta.stat().st_mtime_ns == antes
    # Aplicada otra vez sobre lo ya migrado, no cambia nada.
    otra = copy.deepcopy(c.config)
    assert Config._migrar_nombres_antiguos(otra) == [] and otra == c.config
    # Y un ajuste guardado después se conserva.
    c.set("bandeja", "acciones", ["asistente", "voz"])
    assert Config(config_path=str(ruta)).get("bandeja", "acciones") == ["asistente", "voz"]


def test_config_sin_esquema_hace_las_dos_migraciones(tmp_path):
    ruta = tmp_path / "config.json"
    d = _config_10_9()
    del d["esquema"]                                   # de antes de la 10.3+: umbral 0.2 de serie
    ruta.write_text(json.dumps(d), encoding="utf-8")
    c = Config(config_path=str(ruta))
    assert c.get("baile", "umbral") == 0.05
    assert c.get("bandeja", "acciones") == ["voz", "asistente", "dormir", "minecraft"]
    assert c.get("sistema", "autoinicio_como") == "asistente"
    assert leer(ruta)["esquema"]["version"] == 2


def test_config_con_los_dos_nombres_gana_el_nuevo(tmp_path):
    ruta = tmp_path / "config.json"
    d = _config_10_9(bandeja__acciones=["mascota", "voz", "asistente"],
                     sistema__autoinicio_como="Mascota")
    d["atajos"]["lista"].append({"id": "asistente", "combo": "ctrl+alt+shift+m"})
    ruta.write_text(json.dumps(d), encoding="utf-8")
    c = Config(config_path=str(ruta))
    assert c.get("bandeja", "acciones") == ["voz", "asistente"]
    ids = [e["id"] for e in c.get("atajos", "lista")]
    assert ids == ["mostrar_lune", "voz", "asistente"]
    assert c.get("atajos", "lista")[-1]["combo"] == "ctrl+alt+shift+m"
    assert c.get("sistema", "autoinicio_como") == "asistente"


def test_config_con_valores_raros_no_falla(tmp_path):
    ruta = tmp_path / "config.json"
    d = _config_10_9(bandeja__acciones="mascota", sistema__autoinicio_como=None)
    d["atajos"]["lista"] = {"id": "mascota"}
    d["menu_radial"] = "roto"
    ruta.write_text(json.dumps(d), encoding="utf-8")
    c = Config(config_path=str(ruta))                  # no revienta; lo raro se queda como está
    assert c.get("bandeja", "acciones") == "mascota"
    assert c.get("atajos", "lista") == {"id": "mascota"}
    assert leer(ruta)["esquema"]["version"] == 2


def test_config_nuevo_nace_con_el_esquema_de_ahora(tmp_path):
    ruta = tmp_path / "config.json"
    c = Config(config_path=str(ruta))
    assert leer(ruta)["esquema"]["version"] == 2
    assert "asistente" in c.get("bandeja", "acciones")
    assert {"id": "asistente", "combo": "ctrl+alt+shift+m"} in c.get("atajos", "lista")


# ── Un id viejo que vuelve después de la migración ────────────────────────────

def _config_migrado_con_ids_viejos(tmp_path) -> Config:
    """Un config.json con el esquema YA en 2 y los ids de antes (un Lune de la 10.x que
    seguía abierto guardó su copia, o uno restaurado a mano): la migración no se repite."""
    d = _como_nuevo(_config_10_9())
    d["bandeja"]["acciones"] = ["voz", "mascota", "dormir"]
    d["menu_radial"]["principal"] = ["chat", "cerrar_mascota", "mascota"]
    d["atajos"]["lista"] = [{"id": "mostrar_lune", "combo": "ctrl+alt+shift+l"},
                            {"id": "mascota", "combo": "ctrl+alt+shift+p"}]
    ruta = tmp_path / "config.json"
    ruta.write_text(json.dumps(d), encoding="utf-8")
    c = Config(config_path=str(ruta))
    assert c.get("bandeja", "acciones") == ["voz", "mascota", "dormir"], "la migración es de una vez"
    return c


def test_id_viejo_despues_de_la_migracion_sigue_en_la_bandeja_y_el_radial(tmp_path):
    c = _config_migrado_con_ids_viejos(tmp_path)
    assert acciones_ui.validar_lista(c.get("bandeja", "acciones"), uso=acciones_ui.USO_BANDEJA) == [
        "voz", "asistente", "dormir"]
    assert acciones_ui.validar_lista(["mascota", "asistente", "cerrar_mascota"]) == [
        "asistente", "cerrar_asistente"], "sin repetidos: el viejo y el nuevo son la misma acción"
    assert acciones_ui.en_modo("mascota", "normal") and not acciones_ui.en_modo("mascota", "patata")

    hechas = []
    desp = acciones_ui.Despachador()
    desp.registrar("asistente", lambda: hechas.append("asistente"), marcado=lambda: True)
    desp.registrar("cerrar_asistente", lambda: hechas.append("cerrar"))
    desp.registrar("chat", lambda: None)
    assert desp.tiene("mascota") and desp.tiene("cerrar_mascota")
    assert desp.ejecutar("mascota") and desp.ejecutar("cerrar_mascota")
    assert hechas == ["asistente", "cerrar"]
    assert desp.marcado("mascota") is True
    ctx = acciones_ui.Contexto(modo="normal", render="vrm", asistente_visible=True)
    radial = acciones_ui.items_radial(desp, None, ctx, c.get("menu_radial", "principal"))
    assert [i.id for i in radial] == ["chat", "cerrar_asistente", "asistente"]
    assert radial[2].etiqueta == "Guardar a la asistente"
    menu = acciones_ui.menu_bandeja(desp, None, ctx, c.get("bandeja", "acciones"), ())
    rapidas = [m for m in menu if m.etiqueta == "Lune"][0]
    assert [h.id for h in rapidas.hijos] == ["asistente"], "el botón de la bandeja no desaparece"
    # Lo que no es un nombre viejo ni está en el catálogo se sigue descartando.
    assert acciones_ui.validar_lista(["mascota_volar", "voz"]) == ["voz"]
    assert not desp.tiene("mascota_volar") and not desp.ejecutar("mascota_volar")


def test_id_viejo_despues_de_la_migracion_sigue_en_los_atajos(tmp_path, qapp):
    pytest.importorskip("PyQt6.QtWidgets")
    from ui.atajos_qt import GestorAtajosQt

    class GestorFalso:
        def __init__(self):
            self.activos = {}

        def activo(self):
            return True

        def iniciar(self):
            return True

        def detener(self):
            pass

        def registrar(self, id_, combo):
            self.activos[id_] = combo

        def quitar(self, id_):
            self.activos.pop(id_, None)

        def quitar_todos(self):
            self.activos.clear()

    c = _config_migrado_con_ids_viejos(tmp_path)
    g = GestorFalso()
    desp = acciones_ui.Despachador()
    desp.registrar("asistente", lambda: None)
    desp.registrar("mostrar_lune", lambda: None)
    q = GestorAtajosQt(c, disponible=lambda i: desp.tiene(i) and acciones_ui.en_modo(i, "normal"), gestor=g)
    try:
        assert q.lista() == [("mostrar_lune", "ctrl+alt+shift+l"), ("asistente", "ctrl+alt+shift+p")]
        q.iniciar()
        assert g.activos.get("asistente") == "ctrl+alt+shift+p", "el atajo no desaparece"
        # Cambiar su combinación sustituye a la entrada vieja (no deja dos).
        assert q.cambiar("asistente", "ctrl+alt+shift+k") is None
        ids = [e["id"] for e in c.get("atajos", "lista")]
        assert ids == ["mostrar_lune", "asistente"]
        assert q.lista()[1] == ("asistente", "ctrl+alt+shift+k")
        assert VIEJA not in json.dumps(c.get("atajos", "lista"))
    finally:
        q.detener()


# ── bailes/LEEME.txt ──────────────────────────────────────────────────────────

# El LEEME que escribía la 10.9 (su comienzo; el resto era como el de ahora).
LEEME_10_9 = (
    "BAILES DE LUNE\n"
    "==============\n"
    "\n"
    "Aquí van tus bailes: un movimiento (MMD o VRM Animation) y, si quieres, su canción.\n"
    "Lune los baila en la mascota 3D (VRM). En la animada y en los sprites no hay\n"
    "esqueleto: suena la canción y Lune baila a su manera, al ritmo de la canción.\n"
    "\n"
    "FORMATOS\n"
)


def test_leeme_viejo_se_reconoce():
    assert NA.texto_viejo("la MASCOTA 3D") and not NA.texto_viejo("la asistente") and not NA.texto_viejo(None)
    assert NA.leeme_viejo(LEEME_10_9)
    assert NA.leeme_viejo("\ufeff" + LEEME_10_9.replace("\n", "\r\n")), "con BOM y saltos de Windows"
    assert not NA.leeme_viejo(nbl.TEXTO_LEEME), "el de ahora no"
    assert not NA.leeme_viejo("Mis notas: mi mascota baila genial\n"), "uno de la persona no"
    assert not NA.leeme_viejo(None)
    assert nbl.TEXTO_LEEME.startswith(NA.CABECERA_LEEME_BAILES), "la cabecera sigue siendo la del LEEME"


@pytest.mark.parametrize("viejo", [LEEME_10_9, "\ufeff" + LEEME_10_9.replace("\n", "\r\n")])
def test_el_leeme_de_la_10_9_se_reescribe(tmp_path, viejo):
    carpeta = tmp_path / "bailes"
    carpeta.mkdir()
    (carpeta / nbl.LEEME).write_bytes(viejo.encode("utf-8"))
    (carpeta / "Senbonzakura").mkdir()
    b = nbl.Biblioteca(carpeta, tmp_path / "cache")
    assert b.asegurar_carpeta() is True
    texto = (carpeta / nbl.LEEME).read_text(encoding="utf-8")
    assert texto == nbl.TEXTO_LEEME and VIEJA not in texto.lower()
    assert (carpeta / "Senbonzakura").is_dir(), "lo demás de la carpeta no se toca"
    # Ya al día: una segunda vez no lo vuelve a escribir.
    antes = (carpeta / nbl.LEEME).stat().st_mtime_ns
    assert b.asegurar_carpeta() is True
    assert (carpeta / nbl.LEEME).stat().st_mtime_ns == antes


def test_un_leeme_de_la_persona_no_se_toca(tmp_path):
    carpeta = tmp_path / "bailes"
    carpeta.mkdir()
    propio = "Mis bailes para la mascota de mi hermana\n"
    (carpeta / nbl.LEEME).write_text(propio, encoding="utf-8")
    assert nbl.Biblioteca(carpeta, tmp_path / "cache").asegurar_carpeta() is True
    assert (carpeta / nbl.LEEME).read_text(encoding="utf-8") == propio


# ── datos.json ─────────────────────────────────────────────────────────────────

@pytest.fixture
def datos_tmp(monkeypatch, tmp_path):
    """datos.json en una carpeta temporal (la caché se limpia al entrar y al salir)."""
    ruta = tmp_path / "datos.json"
    monkeypatch.setattr(datos, "_PATH", ruta)
    datos.invalidar()
    yield ruta
    datos.invalidar()


def _escribir(ruta: Path, d: dict) -> None:
    ruta.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def _datos_10_9(**frases) -> dict:
    lune = {"nombre": "Lune", "systemPrompt": "Eres Lune.", "avatar_pack": "default",
            "voz": {"motor": "edge", "id": "es-MX-DaliaNeural"}}
    lune.update(frases)
    lune["vrm"] = "lune.vrm"
    return {"apis": {"openrouter_key": ""}, "bot": {"personaje_default": "Lune"},
            "personajes": [lune, {"nombre": "Aria", "frases_minecraft": {"muerte": ["Au."]}}]}


def test_datos_viejos_se_leen_con_la_clave_nueva_sin_escribir(datos_tmp):
    _escribir(datos_tmp, _datos_10_9(frases_mascota={"caricia": ["Jeje~"]}))
    en_disco = datos_tmp.read_bytes()
    lune = datos.cargar()["personajes"][0]
    assert lune["frases_asistente"] == {"caricia": ["Jeje~"]} and "frases_mascota" not in lune
    # misma posición entre las claves del personaje
    assert list(lune) == ["nombre", "systemPrompt", "avatar_pack", "voz", "frases_asistente", "vrm"]
    assert datos.get_personajes()[0]["frases_asistente"] == {"caricia": ["Jeje~"]}
    assert datos.get_personaje("lune")["frases_asistente"] == {"caricia": ["Jeje~"]}
    assert datos_tmp.read_bytes() == en_disco, "leer no escribe datos.json"


def test_al_guardar_solo_queda_la_clave_nueva(datos_tmp):
    _escribir(datos_tmp, _datos_10_9(frases_mascota={"caricia": ["Jeje~"], "mareo": ["Uy"]}))
    d = datos.cargar()
    d["apis"]["openrouter_key"] = "sk-prueba"
    datos.guardar(d)
    guardado = leer(datos_tmp)
    lune = guardado["personajes"][0]
    assert lune["frases_asistente"] == {"caricia": ["Jeje~"], "mareo": ["Uy"]}
    assert "frases_mascota" not in lune
    assert guardado["apis"]["openrouter_key"] == "sk-prueba"
    assert guardado["personajes"][1] == {"nombre": "Aria", "frases_minecraft": {"muerte": ["Au."]}}
    assert VIEJA not in datos_tmp.read_text(encoding="utf-8").lower()


def test_guardar_un_dict_con_la_clave_vieja_la_traduce(datos_tmp):
    d = _datos_10_9(frases_mascota={"dormir": ["zz"]})
    datos.guardar(d)
    assert d["personajes"][0]["frases_asistente"] == {"dormir": ["zz"]}, "el dict del que llama también"
    assert leer(datos_tmp)["personajes"][0]["frases_asistente"] == {"dormir": ["zz"]}
    assert VIEJA not in datos_tmp.read_text(encoding="utf-8").lower()


def test_con_las_dos_claves_gana_la_nueva_y_se_conserva_lo_demas(datos_tmp):
    _escribir(datos_tmp, _datos_10_9(
        frases_asistente={"caricia": ["nueva"], "soltar": {"p": 0.9}},
        frases_mascota={"caricia": ["vieja"], "mareo": ["Uy"], " Soltar ": ["vieja"],
                        "dormir": {"frases": ["zz"], "p": 0.5}}))
    lune = datos.cargar()["personajes"][0]
    assert lune["frases_asistente"] == {"caricia": ["nueva"], "soltar": {"p": 0.9},
                                        "mareo": ["Uy"], "dormir": {"frases": ["zz"], "p": 0.5}}
    assert "frases_mascota" not in lune


@pytest.mark.parametrize("nueva, vieja, queda", [
    (None, {"caricia": ["Jeje"]}, {"caricia": ["Jeje"]}),      # la nueva no vale: no se pierde la vieja
    ({"caricia": ["a"]}, ["basura"], {"caricia": ["a"]}),
    ([], "basura", []),                                         # ninguna vale: la nueva
])
def test_con_las_dos_claves_y_una_rota(nueva, vieja, queda):
    p = {"nombre": "Lune", "frases_asistente": nueva, "frases_mascota": vieja}
    assert NA.migrar_personaje(p) is True
    assert p == {"nombre": "Lune", "frases_asistente": queda}
    assert NA.migrar_personaje(p) is False, "idempotente"


def test_datos_raros_no_fallan(datos_tmp):
    for raro in ({"personajes": "no"}, {"personajes": [None, 3, "x", {"nombre": "Lune"}]}, {}):
        _escribir(datos_tmp, raro)
        datos.invalidar()
        assert datos.cargar() == raro
        assert NA.migrar_datos(raro) is False
    assert NA.migrar_datos(None) is False and NA.migrar_datos([]) is False


def test_personajes_y_las_frases_ven_la_clave_nueva(datos_tmp):
    _escribir(datos_tmp, _datos_10_9(frases_mascota={"caricia": ["Jeje~"]}))
    activo = personajes.get_activo()
    assert activo["frases_asistente"] == {"caricia": ["Jeje~"]}
    assert all("frases_mascota" not in p for p in personajes.listar())
    assert frases_de_personaje(activo)["caricia"][0] == ["Jeje~"]
    # guardar_personaje con la clave vieja (una card o una UI de antes) → la nueva en disco
    personajes.guardar_personaje({"nombre": "Nyx", "frases_mascota": {"mareo": ["Ay"]}})
    nyx = personajes.get("Nyx")
    assert nyx["frases_asistente"] == {"mareo": ["Ay"]} and "frases_mascota" not in nyx
    assert VIEJA not in datos_tmp.read_text(encoding="utf-8").lower()


def test_la_plantilla_trae_la_clave_nueva():
    plantilla = Path(datos._EJEMPLO)
    texto = plantilla.read_text(encoding="utf-8")
    assert VIEJA not in texto.lower()
    lune = json.loads(texto)["personajes"][0]
    assert "frases_asistente" in lune


# ── Lo que escribe el modelo (lune_core/marcadores) ────────────────────────────

def test_los_alias_salen_de_la_tabla():
    assert M.ALIAS_ANTIGUOS is NA.HERRAMIENTAS


@pytest.mark.parametrize("escrito, nombre", [
    ("mascota_bailar", "asistente_bailar"),
    ("MASCOTA_DORMIR", "asistente_dormir"),
    ("mascota-despertar", "asistente_despertar"),
    ("Mascota Tamano", "asistente_tamano"),
    ("mascota_pantalla_grande", "asistente_pantalla_grande"),
    ("mascota_sentarse", "asistente_sentarse"),
])
def test_nombre_de_herramienta_viejo(escrito, nombre):
    assert M.nombre_herramienta(escrito) == nombre


def test_lo_viejo_que_no_es_herramienta_no_se_inventa():
    assert M.nombre_herramienta("mascota") is None
    assert M.nombre_herramienta("mascota_volar") is None


def test_marcas_con_el_nombre_viejo_se_ejecutan_con_el_nuevo():
    _, control = M.separar("¡Vamos! <|mascota_bailar(segundos=60)|> ya")
    assert control == [("call", ["asistente_bailar", {"segundos": 60}])]
    _, control = M.separar('Buenas noches <|CALL ["mascota_dormir", {}]|>')
    assert control == [("call", ["asistente_dormir", {}])]
    _, control = M.separar('<|CALL {"name": "mascota_sentarse", "arguments": {"sitio": "barra"}}|>')
    assert control == [("call", ["asistente_sentarse", {"sitio": "barra"}])]
    _, control = M.separar('<|mascota_tamano {"tamano": "grande"}|>')
    assert control == [("call", ["asistente_tamano", {"tamano": "grande"}])]


def test_el_historial_se_guarda_con_el_nombre_nuevo():
    limpio = M.normalizar('Ya me despierto <|CALL ["mascota_despertar", {}]|>')
    assert "asistente_despertar" in limpio and VIEJA not in limpio.lower()
    assert M.limpiar_para_mostrar("Hola <|mascota_bailar|>") == "Hola "
