"""
Tests de nucleo/packs_sonido.py: packs de sonidos de reacción de la asistente.

Sin red ni audio. Se prueba el pack por defecto de verdad (sonidos/default, que
apunta a los WAV de ui_web/assets/sfx) y packs hechos en tmp_path: validación de
pack.json y de cada ruta (extensiones, «..», absolutas, unidades, nombres de
dispositivo, base no permitida), el mapeo en ciclo y reemplazar de Mate-Engine,
el orden del listado, las URLs para la web y el archivo al azar para el mezclador.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo import packs_sonido as ps  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent


def _wav(ruta: Path, n: int = 8) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(b"RIFF" + b"\0" * n)
    return ruta


def _pack(carpeta: Path, datos, archivos=()) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    for a in archivos:
        _wav(carpeta / a)
    texto = datos if isinstance(datos, str) else json.dumps(datos, ensure_ascii=False)
    (carpeta / "pack.json").write_text(texto, encoding="utf-8")
    return carpeta


# ── Pack por defecto ──────────────────────────────────────────────────────────

def test_pack_por_defecto_valido_y_apunta_a_los_sfx():
    d = ps.pack_por_defecto()
    assert d is not None and d.valido, d and d.errores
    assert d.id == "default" and d.base == ps.DIR_SFX
    assert not d.avisos, d.avisos                    # todos sus archivos existen
    assert set(d.eventos) == set(ps.EVENTOS), "pack.json documenta todos los eventos"
    for ev, lista in list(d.eventos.items()) + list(d.capas.items()):
        for ruta in lista:
            assert ruta.parent == ps.DIR_SFX.resolve() and ruta.suffix == ".wav", (ev, ruta)
    assert [p.name for p in d.eventos["beber"]] == ["trago_1.wav", "trago_2.wav", "trago_3.wav"]
    assert ps.REACCIONES <= set(ps.EVENTOS)


def test_rutas_ancladas_a_la_raiz(monkeypatch, tmp_path):
    from nucleo import rutas
    monkeypatch.chdir(tmp_path)                      # otro cwd no cambia nada
    assert ps.CARPETA_SONIDOS == rutas.DATOS / "sonidos"          # los del usuario
    assert ps.CARPETA_SONIDOS_APP == RAIZ / "sonidos"             # el de Lune
    assert ps.DIR_SFX == RAIZ / "ui_web" / "assets" / "sfx"
    assert [p.id for p in ps.listar_packs()][:1] == ["default"]
    assert ps.obtener_pack("default") is not None


def test_packs_del_usuario_y_default_de_lune(monkeypatch, tmp_path):
    """Instalada son dos carpetas: el default que trae Lune (solo lectura) y los packs del
    usuario. Sin carpeta explícita se juntan; un «default» del usuario no tapa al de Lune."""
    app, usuario = tmp_path / "app", tmp_path / "usuario"
    _pack(app / "default", {"base": "ui_web/assets/sfx", "eventos": {"beber": ["trago_1.wav"]}})
    _pack(usuario / "gata", {"nombre": "Gata", "eventos": {"beber": ["a.wav"]}}, ["a.wav"])
    _pack(usuario / "default", {"nombre": "Falso", "eventos": {"beber": ["a.wav"]}}, ["a.wav"])
    monkeypatch.setattr(ps, "CARPETA_SONIDOS_APP", app)
    monkeypatch.setattr(ps, "CARPETA_SONIDOS", usuario)
    packs = ps.listar_packs()
    assert [p.id for p in packs] == ["default", "gata"]
    assert packs[0].carpeta == app / "default" and packs[0].nombre != "Falso"
    assert ps.obtener_pack("gata").carpeta == usuario / "gata"
    assert ps.obtener_pack("default").carpeta == app / "default"
    assert ps.pack_por_defecto().carpeta == app / "default"
    # el pack del usuario completa con el default de Lune, no con su «default»
    assert ps._defecto_para(ps.obtener_pack("gata")).carpeta == app / "default"
    # con carpeta explícita, solo esa (como siempre)
    assert [p.id for p in ps.listar_packs(usuario)] == ["default", "gata"]
    assert ps.listar_packs(tmp_path / "vacia") == []


# ── Validación ────────────────────────────────────────────────────────────────

def test_pack_valido_con_ogg_y_wav_en_subcarpetas(tmp_path):
    c = _pack(tmp_path / "gata", {
        "nombre": "  Gata\u202e\n mala  ", "autor": "Diego", "mapeo": "reemplazar", "volumen": 1.7,
        "eventos": {"caricia": ["voz/miau_1.ogg", "voz/miau_2.wav"], "beber": "glup.ogg"},
        "capas": {"caricia": ["ronroneo.wav"]},
    }, ["voz/miau_1.ogg", "voz/miau_2.wav", "glup.ogg", "ronroneo.wav"])
    p = ps.cargar_pack(c)
    assert p.valido and not p.avisos, (p.errores, p.avisos)
    assert p.nombre == "Gata mala"                   # sin control ni bidi, una línea
    assert p.mapeo == "reemplazar" and p.volumen == 1.0
    assert [r.name for r in p.eventos["caricia"]] == ["miau_1.ogg", "miau_2.wav"]
    assert [r.name for r in p.eventos["beber"]] == ["glup.ogg"]
    assert [r.name for r in p.capas["caricia"]] == ["ronroneo.wav"]
    resumen = p.a_dict()
    assert resumen["eventos"] == {"caricia": 2, "beber": 1} and resumen["valido"] is True


@pytest.mark.parametrize("ref", [
    "../fuera.wav", "voz/../../fuera.wav", "/abs.wav", "C:/x.wav", "C:x.wav", "a\\b.wav",
    "x.mp3", "x.exe", "x.wav.exe", "NUL.wav", "com1.ogg", "voz//a.wav", "./a.wav", "a.wav:ads",
    "no_existe.wav", "nombre.wav ", "con\x07trol.wav", "", 5, None,
])
def test_rutas_peligrosas_o_invalidas_se_descartan(tmp_path, ref):
    _wav(tmp_path / "fuera.wav")
    c = _pack(tmp_path / "p", {"eventos": {"beber": ["bien.wav", ref]}}, ["bien.wav", "x.mp3", "x.exe", "x.wav.exe"])
    p = ps.cargar_pack(c)
    assert p.valido
    assert [r.name for r in p.eventos["beber"]] == ["bien.wav"], ref
    assert p.avisos, f"{ref!r} debería dejar un aviso"


def test_archivo_demasiado_grande_se_descarta(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "TAM_MAX_ARCHIVO", 16)
    c = _pack(tmp_path / "p", {"eventos": {"beber": ["chico.wav", "grande.wav"]}}, ["chico.wav"])
    _wav(c / "grande.wav", n=64)
    p = ps.cargar_pack(c)
    assert [r.name for r in p.eventos["beber"]] == ["chico.wav"]
    assert any("MB" in a for a in p.avisos)


@pytest.mark.parametrize("datos,motivo", [
    ("{no es json", "no se puede leer"),
    ("[1, 2]", "objeto JSON"),
    ({"eventos": {"beber": ["nada.mp3"]}}, "ningún archivo"),
    ({"eventos": {}}, "ningún archivo"),
    ({"base": "C:/Users", "eventos": {"beber": ["a.wav"]}}, "base"),
    ({"base": "../../ui_web/assets/sfx", "eventos": {"beber": ["blip.wav"]}}, "base"),
    ({"base": ["ui_web/assets/sfx"], "eventos": {"beber": ["blip.wav"]}}, "base"),
])
def test_pack_invalido(tmp_path, datos, motivo):
    c = _pack(tmp_path / "roto", datos, ["a.wav"])
    p = ps.cargar_pack(c)
    assert not p.valido
    assert any(motivo in e for e in p.errores), p.errores
    assert ps.listar_packs(tmp_path) == []
    assert [x.id for x in ps.listar_packs(tmp_path, incluir_invalidos=True)] == ["roto"]
    assert ps.obtener_pack("roto", tmp_path) is None


def test_pack_json_demasiado_grande(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "TAM_MAX_JSON", 50)
    c = _pack(tmp_path / "p", {"nombre": "x" * 80, "eventos": {"beber": ["a.wav"]}}, ["a.wav"])
    assert any("KB" in e for e in ps.cargar_pack(c).errores)


def test_valores_raros_se_corrigen_con_aviso(tmp_path):
    c = _pack(tmp_path / "p", {
        "mapeo": "aleatorio", "volumen": "alto", "nombre": 7,
        "eventos": {"beber": ["a.wav"], "Mal-Nombre": ["a.wav"], "comer": {"x": 1}},
        "capas": ["a.wav"],
    }, ["a.wav"])
    p = ps.cargar_pack(c)
    assert p.valido
    assert p.mapeo == "ciclo" and p.volumen == 1.0 and p.nombre == "p"
    assert set(p.eventos) == {"beber"} and p.capas == {}
    assert len(p.avisos) == 5, p.avisos


def test_limites_de_eventos_y_archivos(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "MAX_EVENTOS", 2)
    monkeypatch.setattr(ps, "MAX_ARCHIVOS_EVENTO", 3)
    c = _pack(tmp_path / "p", {"eventos": {"a": ["x.wav"] * 5, "b": ["x.wav"], "c": ["x.wav"]}}, ["x.wav"])
    p = ps.cargar_pack(c)
    assert list(p.eventos) == ["a", "b"] and len(p.eventos["a"]) == 3


def test_base_permitida_la_puede_usar_cualquier_pack(tmp_path):
    c = _pack(tmp_path / "remix", {"base": "ui_web/assets/sfx", "eventos": {"beber": ["blip.wav"]}})
    p = ps.cargar_pack(c)
    assert p.valido and p.eventos["beber"] == [(ps.DIR_SFX / "blip.wav").resolve()]


# ── Listado ───────────────────────────────────────────────────────────────────

def test_listar_default_primero_y_por_nombre(tmp_path):
    _pack(tmp_path / "zeta", {"nombre": "Abeja", "eventos": {"beber": ["a.wav"]}}, ["a.wav"])
    _pack(tmp_path / "alfa", {"nombre": "Zorro", "eventos": {"beber": ["a.wav"]}}, ["a.wav"])
    _pack(tmp_path / "default", {"base": "ui_web/assets/sfx", "eventos": {"beber": ["trago_1.wav"]}})
    _pack(tmp_path / ".oculto", {"eventos": {"beber": ["a.wav"]}}, ["a.wav"])
    _pack(tmp_path / "_borrador", {"eventos": {"beber": ["a.wav"]}}, ["a.wav"])
    (tmp_path / "sin_pack").mkdir()
    (tmp_path / "suelto.json").write_text("{}", encoding="utf-8")
    assert [p.id for p in ps.listar_packs(tmp_path)] == ["default", "zeta", "alfa"]
    assert ps.listar_packs(tmp_path / "no_existe") == []


@pytest.mark.parametrize("id_malo", ["..", "../sonidos", "a/b", "a\\b", "C:", ".oculto", "", " x", None])
def test_obtener_pack_no_sale_de_la_carpeta(tmp_path, id_malo):
    _pack(tmp_path / "bien", {"eventos": {"beber": ["a.wav"]}}, ["a.wav"])
    assert ps.obtener_pack(id_malo, tmp_path / "bien") is None
    assert ps.obtener_pack("bien", tmp_path) is not None


# ── Mapeo y resolución ────────────────────────────────────────────────────────

def test_mapear_como_mevoicepack():
    assert ps.mapear([1, 2, 3], ["a", "b"], "ciclo") == ["a", "b", "a"]
    assert ps.mapear([1, 2, 3, 4, 5], ["a", "b"], "ciclo") == ["a", "b", "a", "b", "a"]
    assert ps.mapear([1], ["a", "b", "c"], "ciclo") == ["a", "b", "c"]
    assert ps.mapear([], ["a"], "ciclo") == ["a"]
    assert ps.mapear([1, 2, 3], ["a", "b"], "reemplazar") == ["a", "b"]
    assert ps.mapear([1, 2], [], "reemplazar") == [1, 2]


def test_resolver_ciclo_reemplazar_y_respaldo(tmp_path):
    ciclo = ps.cargar_pack(_pack(tmp_path / "ciclo", {
        "eventos": {"beber": ["g1.ogg", "g2.ogg"], "caricia": ["miau.ogg"]},
        "capas": {"caricia": ["ronroneo.wav"]},
    }, ["g1.ogg", "g2.ogg", "miau.ogg", "ronroneo.wav"]))
    nombres = lambda l: [p.name for p in l]  # noqa: E731
    # Sin «default» al lado: el de sonidos/ (3 tragos).
    assert nombres(ps.resolver(ciclo, "beber")) == ["g1.ogg", "g2.ogg", "g1.ogg"]
    assert nombres(ps.resolver(ciclo, "comer")) == ["mordisco_1.wav", "mordisco_2.wav", "mordisco_3.wav"]
    assert nombres(ps.resolver(ciclo, "caricia")) == ["miau.ogg"]
    assert nombres(ps.resolver(ciclo, "caricia", capas=True)) == ["ronroneo.wav"]
    assert ps.resolver(ciclo, "inventado") == []
    reemplazo = ps.cargar_pack(_pack(tmp_path / "reemplazo", {
        "mapeo": "reemplazar", "eventos": {"beber": ["g1.ogg"]}}, ["g1.ogg"]))
    assert nombres(ps.resolver(reemplazo, "beber")) == ["g1.ogg"]
    # Por id (en sonidos/) y con un pack que no existe: el de por defecto.
    assert nombres(ps.resolver("default", "tecleo")) == ["blip.wav"]
    assert nombres(ps.resolver("no_existe_este_pack", "beber")) == ["trago_1.wav", "trago_2.wav", "trago_3.wav"]
    # Un «default» en la misma carpeta de packs manda sobre el de sonidos/.
    _pack(tmp_path / "default", {"base": "ui_web/assets/sfx", "eventos": {"beber": ["blip.wav"] * 4}})
    assert nombres(ps.resolver(ciclo, "beber")) == ["g1.ogg", "g2.ogg", "g1.ogg", "g2.ogg"]


def test_archivo_al_azar(tmp_path):
    p = ps.cargar_pack(_pack(tmp_path / "p", {"eventos": {"beber": ["a.wav", "b.wav"]}}, ["a.wav", "b.wav"]))
    assert ps.archivo_al_azar(p, "beber", azar=lambda: 0.0).name == "a.wav"
    assert ps.archivo_al_azar(p, "beber", azar=lambda: 0.999).name == "a.wav"   # ciclo: a, b, a
    assert ps.archivo_al_azar(p, "beber", azar=lambda: 0.5).name == "b.wav"
    assert ps.archivo_al_azar(p, "beber", azar=lambda: 7.0).name == "a.wav"     # acotado
    assert ps.archivo_al_azar(p, "caricia") is None


# ── Web ───────────────────────────────────────────────────────────────────────

def test_pack_para_web_urls_y_mapeo(tmp_path):
    _pack(tmp_path / "default", {"base": "ui_web/assets/sfx",
                                 "eventos": {"beber": ["trago_1.wav", "trago_2.wav", "trago_3.wav"],
                                             "tecleo": ["blip.wav"]}})
    p = ps.cargar_pack(_pack(tmp_path / "mi gata", {
        "nombre": "Gata", "volumen": 0.5,
        "eventos": {"beber": ["voz/glup ñ.ogg"]}, "capas": {"caricia": ["r.wav"]},
    }, ["voz/glup ñ.ogg", "r.wav"]))
    web = ps.pack_para_web(p)
    assert web["id"] == "mi gata" and web["nombre"] == "Gata" and web["volumen"] == 0.5
    assert web["resuelto"] is True and web["mapeo"] == "ciclo"
    assert web["eventos"]["beber"] == ["/sonidos/mi%20gata/voz/glup%20%C3%B1.ogg"] * 3
    assert web["eventos"]["tecleo"] == ["/assets/sfx/blip.wav"]
    assert web["capas"] == {"caricia": ["/sonidos/mi%20gata/r.wav"]}
    json.dumps(web)                                   # serializable para runJavaScript
    otro = ps.pack_para_web(p, prefijo="packs")
    assert otro["eventos"]["beber"][0].startswith("/packs/mi%20gata/")


def test_pack_para_web_del_default_real():
    web = ps.pack_para_web("default")
    assert web["eventos"]["arrastre_inicio"] == ["/assets/sfx/drag_start.wav"]
    assert web["eventos"]["caricia"] == []
    assert ps.pack_para_web("no_existe_este_pack") is None


def test_url_web_fuera_de_las_carpetas_servidas(tmp_path):
    fuera = _wav(tmp_path / "x.wav")
    assert ps.url_web(fuera) is None
    assert ps.url_web(ps.DIR_SFX / "blip.wav") == "/assets/sfx/blip.wav"
