"""
Tests del catálogo de herramientas (lune_core/catalogo_herramientas.py).

Lo crítico: están todas las herramientas del plan (§2.5) con su riesgo y sus
esquemas; ningún argumento se llama `nombre`/`app` salvo en lanzar_app (la
Política busca DENY_APPS ahí); la validación es estricta con rangos, patrones y
enums; y la aprobación dinámica es fail-closed con la nube.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lune_core import catalogo_herramientas as C  # noqa: E402
from lune_core import herramientas as H  # noqa: E402

NUEVAS_PLAN = {
    "temporizador", "alarma", "cancelar_alarma", "listar_alarmas",
    "asistente_bailar", "parar_baile", "asistente_dormir", "asistente_despertar",
    "asistente_pantalla_grande", "asistente_sentarse", "asistente_tamano",
    "dar_de_comer", "cambiar_voz", "comentar_pantalla",
    "minecraft_estado", "minecraft_orden", "minecraft_bot",
    "listar_bailes",                     # cortes 9/10 (reproductor de bailes)
}
EXISTENTES = {"sistema_info", "buscar_web", "abrir_url", "lanzar_app"}


def validar(nombre, args):
    return C.validar(args, C.ESQUEMAS[nombre])[0]


# ── Contenido del catálogo ───────────────────────────────────────────────────────

def test_estan_todas_las_herramientas_del_plan():
    assert set(C.NUEVAS) == NUEVAS_PLAN
    assert set(C.EXISTENTES) == EXISTENTES
    assert set(C.CATALOGO) == NUEVAS_PLAN | EXISTENTES
    assert set(C.ESQUEMAS) == set(C.CATALOGO)


def test_existentes_coinciden_con_registro_por_defecto():
    """El catálogo no puede contradecir a la Política que ya existe."""
    reg = H.registro_por_defecto()
    for nombre in EXISTENTES:
        d, h = reg.get(nombre), C.CATALOGO[nombre]
        assert (d.riesgo, d.requiere_aprobacion, d.coste) == \
               (h.riesgo, h.requiere_aprobacion, h.coste), nombre


@pytest.mark.parametrize("nombre,riesgo,aprobacion,coste", [
    ("temporizador", H.Riesgo.ESCRITURA, False, 1),
    ("alarma", H.Riesgo.ESCRITURA, False, 1),
    ("cancelar_alarma", H.Riesgo.ESCRITURA, False, 1),
    ("listar_alarmas", H.Riesgo.LECTURA, False, 0),
    ("asistente_bailar", H.Riesgo.ESCRITURA, False, 0),
    ("parar_baile", H.Riesgo.ESCRITURA, False, 0),
    ("listar_bailes", H.Riesgo.LECTURA, False, 0),
    ("asistente_dormir", H.Riesgo.ESCRITURA, False, 0),
    ("asistente_despertar", H.Riesgo.ESCRITURA, False, 0),
    ("asistente_pantalla_grande", H.Riesgo.ESCRITURA, False, 0),
    ("asistente_sentarse", H.Riesgo.ESCRITURA, False, 0),
    ("asistente_tamano", H.Riesgo.ESCRITURA, False, 0),
    ("dar_de_comer", H.Riesgo.ESCRITURA, False, 0),
    ("cambiar_voz", H.Riesgo.ESCRITURA, False, 1),
    ("comentar_pantalla", H.Riesgo.LECTURA, False, 1),
    ("minecraft_estado", H.Riesgo.LECTURA, False, 0),
    ("minecraft_orden", H.Riesgo.ESCRITURA, True, 1),
    ("minecraft_bot", H.Riesgo.ESCRITURA, False, 1),
])
def test_riesgo_aprobacion_y_coste_del_plan(nombre, riesgo, aprobacion, coste):
    h = C.CATALOGO[nombre]
    assert (h.riesgo, h.requiere_aprobacion, h.coste) == (riesgo, aprobacion, coste)


def test_ningun_argumento_se_llama_nombre_ni_app_salvo_lanzar_app():
    for nombre, esquema in C.ESQUEMAS.items():
        vigilados = set(esquema) & set(C.ARGS_VIGILADOS)
        if nombre == "lanzar_app":
            assert vigilados == {"app"}
        else:
            assert not vigilados, f"{nombre} usa {vigilados}"


def test_cada_herramienta_esta_completa_y_su_ejemplo_es_valido():
    for nombre, h in C.CATALOGO.items():
        assert h.descripcion and h.handler and h.modos <= C.TODOS, nombre
        assert h.modos, nombre
        C.validar(dict(h.ejemplo), h.args)          # no lanza
        for clave, arg in h.args.items():
            assert arg.tipo in ("int", "float", "bool", "str"), (nombre, clave)
            if arg.tipo == "str" and arg.enum is None:
                assert arg.maxlen, f"{nombre}.{clave} necesita maxlen"


def test_registrar_extras_no_pisa_las_existentes():
    reg = H.registro_por_defecto()
    original = reg.get("lanzar_app")
    C.registrar_extras(reg)
    assert reg.get("lanzar_app") is original
    assert set(reg.nombres()) == NUEVAS_PLAN | EXISTENTES
    d = reg.get("minecraft_orden")
    assert d.requiere_aprobacion and d.riesgo == H.Riesgo.ESCRITURA


def test_registro_completo():
    assert set(C.registro_completo().nombres()) == NUEVAS_PLAN | EXISTENTES


# ── Modos ────────────────────────────────────────────────────────────────────────

def test_modos():
    cat = C.CATALOGO
    assert cat["asistente_dormir"].disponible_en("vrm")          # vrm es una asistente
    assert cat["asistente_dormir"].disponible_en("asistente")
    assert not cat["asistente_dormir"].disponible_en("patata")
    assert cat["asistente_sentarse"].disponible_en("vrm")
    assert cat["asistente_sentarse"].disponible_en("asistente")     # cortes 7/8: animada y sprites se apoyan
    assert not cat["asistente_sentarse"].disponible_en("normal")  # sin asistente a la vista, no
    assert not cat["asistente_sentarse"].disponible_en("patata")
    assert not cat["asistente_tamano"].disponible_en("asistente")   # el tamaño sigue siendo solo de la 3D
    assert cat["dar_de_comer"].disponible_en("patata") and cat["dar_de_comer"].disponible_en("normal")
    assert cat["asistente_bailar"].disponible_en("normal")
    assert cat["asistente_bailar"].disponible_en("br")
    # Cortes 9/10: en patata también (el título baila al ritmo de la canción de tu biblioteca).
    assert cat["asistente_bailar"].disponible_en("patata") and cat["parar_baile"].disponible_en("patata")
    assert all(cat["listar_bailes"].disponible_en(m) for m in C.MODOS)
    assert cat["temporizador"].disponible_en("patata")
    assert cat["temporizador"].disponible_en(None)            # sin modo, sin filtro


def test_disponibles_en_filtra_por_handler_modo_y_registro():
    reg = H.registro_basico()                                 # sin las nuevas
    con = {"temporizador", "sistema_info", "asistente_dormir"}
    assert C.disponibles_en("patata", con, reg) == ["sistema_info"]
    reg_c = C.registro_completo()
    assert C.disponibles_en("patata", con, reg_c) == ["sistema_info", "temporizador"]
    assert C.disponibles_en("vrm", con, reg_c) == ["sistema_info", "temporizador",
                                                  "asistente_dormir"]


# ── Validación ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("valor,esperado", [(1, 1), (90000, 90000), ("300", 300), (3.0, 3)])
def test_temporizador_rango_valido(valor, esperado):
    assert validar("temporizador", {"segundos": valor})["segundos"] == esperado


@pytest.mark.parametrize("valor", [0, 90001, -5, 3.5, "tres", True, [1], float("nan")])
def test_temporizador_rango_invalido(valor):
    with pytest.raises(C.ArgumentosInvalidos):
        validar("temporizador", {"segundos": valor})


def test_requerido_y_null():
    with pytest.raises(C.ArgumentosInvalidos):
        validar("temporizador", {})
    with pytest.raises(C.ArgumentosInvalidos):
        validar("temporizador", {"segundos": None})
    with pytest.raises(C.ArgumentosInvalidos):
        validar("abrir_url", {"url": "   "})


def test_defectos():
    assert validar("asistente_bailar", {}) == {"segundos": 30}
    assert validar("buscar_web", {"consulta": "gatos"}) == {"consulta": "gatos",
                                                            "sitio": "google"}
    assert validar("temporizador", {"segundos": 5})["texto"] == ""


def test_argumentos_desconocidos_se_descartan():
    limpio, ignorados = C.validar({"app": "paint", "nombre": "cmd", "x": 1},
                                  C.ESQUEMAS["lanzar_app"])
    assert limpio == {"app": "paint"}
    assert ignorados == ["nombre", "x"]


def test_args_no_objeto():
    with pytest.raises(C.ArgumentosInvalidos):
        C.validar(["a"], C.ESQUEMAS["temporizador"])


@pytest.mark.parametrize("hora", ["07:30", "7:30", "23:59", "00:00"])
def test_alarma_hora_valida(hora):
    assert validar("alarma", {"hora": hora})["hora"] == hora


@pytest.mark.parametrize("hora", ["24:00", "7:60", "HH:MM", "0730", "07:30:00"])
def test_alarma_hora_invalida(hora):
    with pytest.raises(C.ArgumentosInvalidos):
        validar("alarma", {"hora": hora})


def test_alarma_dias():
    assert validar("alarma", {"hora": "08:00", "dias": "lmxjv"})["dias"] == "lmxjv"
    assert validar("alarma", {"hora": "08:00"})["dias"] == ""
    with pytest.raises(C.ArgumentosInvalidos):
        validar("alarma", {"hora": "08:00", "dias": "lunes"})


def test_enum_sin_mayusculas_ni_tildes():
    assert validar("asistente_tamano", {"tamano": "Pequeño"})["tamano"] == "pequeno"
    assert validar("buscar_web", {"consulta": "x", "sitio": "YouTube"})["sitio"] == "youtube"
    with pytest.raises(C.ArgumentosInvalidos):
        validar("dar_de_comer", {"comida": "pizza"})


def test_texto_libre_se_recorta_pero_url_se_rechaza():
    assert len(validar("temporizador", {"segundos": 5, "texto": "a" * 200})["texto"]) == 60
    with pytest.raises(C.ArgumentosInvalidos):
        validar("abrir_url", {"url": "https://x.com/" + "a" * 600})


def test_caracteres_de_control_fuera():
    assert validar("temporizador", {"segundos": 5, "texto": "té\nya\x00"})["texto"] == "té ya"


@pytest.mark.parametrize("app", ['paint" & del /q', "..\\cmd", "a/b", "x" * 61])
def test_lanzar_app_patron(app):
    with pytest.raises(C.ArgumentosInvalidos):
        validar("lanzar_app", {"app": app})


def test_abrir_url_sin_espacios():
    with pytest.raises(C.ArgumentosInvalidos):
        validar("abrir_url", {"url": "https://x.com y más"})


def test_bool():
    assert validar("asistente_pantalla_grande", {"activar": "true"})["activar"] is True
    assert validar("asistente_pantalla_grande", {"activar": "no"})["activar"] is False
    assert validar("asistente_pantalla_grande", {"activar": 1})["activar"] is True
    with pytest.raises(C.ArgumentosInvalidos):
        validar("asistente_pantalla_grande", {"activar": "quizá"})


def test_cambiar_voz_patron():
    assert validar("cambiar_voz", {"voz": "es-MX-DaliaNeural"})["voz"] == "es-MX-DaliaNeural"
    assert validar("cambiar_voz", {"voz": "ef_dora"})["voz"] == "ef_dora"
    with pytest.raises(C.ArgumentosInvalidos):
        validar("cambiar_voz", {"voz": "../../voz"})


def test_float_generico():
    esquema = {"x": C.Arg("float", requerido=True, min=0, max=1)}
    assert C.validar({"x": "0.5"}, esquema)[0] == {"x": 0.5}
    for malo in (float("inf"), 2, "1e3", False):
        with pytest.raises(C.ArgumentosInvalidos):
            C.validar({"x": malo}, esquema)


def test_numero_como_texto_en_str():
    assert validar("cancelar_alarma", {"id": 7})["id"] == "7"


# ── Aprobación dinámica ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("ctx,nube", [
    ({"proveedor": "openrouter"}, True),
    ({"proveedor": "ollama"}, False),
    ({"proveedor": "ollama", "url": "http://192.168.1.50:11434"}, False),
    ({"proveedor": "ollama", "url": "http://127.0.0.1:11434"}, False),
    ({"proveedor": "ollama", "url": "https://ollama.ejemplo.com"}, True),
    ({"proveedor": "compat", "base_url": "http://localhost:1234/v1"}, False),
    ({"proveedor": "compat", "base_url": "https://api.groq.com/openai/v1"}, True),
    ({"proveedor": "compat"}, True),
    ({"proveedor": "desconocido"}, True),
    ({}, True),
    (None, True),
    ({"proveedor": "openrouter", "nube": False}, False),
    ({"proveedor": "ollama", "nube": True}, True),
])
def test_es_nube(ctx, nube):
    assert C.es_nube(ctx) is nube


def test_es_nube_con_objeto():
    class Ctx:
        proveedor = "ollama"
    assert C.es_nube(Ctx()) is False


def test_aprobacion_dinamica():
    assert C.aprobacion_dinamica("comentar_pantalla", {"proveedor": "openrouter"})
    assert not C.aprobacion_dinamica("comentar_pantalla", {"proveedor": "ollama"})
    assert C.aprobacion_dinamica("minecraft_bot", {}, {"accion": "conectar"})
    assert not C.aprobacion_dinamica("minecraft_bot", {}, {"accion": "desconectar"})
    for n in ("abrir_url", "buscar_web"):
        assert not C.aprobacion_dinamica(n, {"origen": "usuario"})
        assert not C.aprobacion_dinamica(n, None)
        assert C.aprobacion_dinamica(n, {"origen": "no_confiable"})
    assert not C.aprobacion_dinamica("temporizador", {"origen": "no_confiable"})


# ── Presentación ─────────────────────────────────────────────────────────────────

def test_resumen():
    assert "paint" in C.resumen("lanzar_app", {"app": "paint"})
    assert C.resumen("temporizador", {"segundos": 300, "texto": ""}) == \
        "Poner un temporizador de 300 s"
    assert "nube" in C.resumen("comentar_pantalla", {}, {"proveedor": "openrouter"})
    assert "nube" not in C.resumen("comentar_pantalla", {}, {"proveedor": "ollama"})
    assert C.resumen("no_existe", {}) == "Acción «no_existe»"
    # Llaves en los valores no rompen la plantilla.
    assert "{x}" in C.resumen("minecraft_orden", {"orden": "{x}"})


def test_firma():
    assert C.firma(C.CATALOGO["temporizador"]) == \
        "temporizador(segundos: entero 1-90000, texto?: texto ≤60)"
    assert C.firma(C.CATALOGO["sistema_info"]) == "sistema_info()"
    assert "sitio?: google|youtube" in C.firma(C.CATALOGO["buscar_web"])
