"""
Tests de las reglas de herramientas del system prompt (lune_core/reglas_prompt.py).

Lo crítico: solo aparecen las herramientas con handler, registradas y del modo;
cada una se enseña con la forma de su llamada (<|CALL ["x", {…}]|>, no x(…): la
prueba real con qwen2.5:7b vio al modelo copiar la firma como <|x(arg=…)|>); los
ejemplos son pocos, neutros y el Ejecutor los entiende tal cual; y el formato
antiguo (ABRIR_URL:/TOOL:) no se enseña nunca.
"""
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lune_core import acciones as A  # noqa: E402
from lune_core import catalogo_herramientas as C  # noqa: E402
from lune_core import herramientas as H  # noqa: E402
from lune_core.reglas_prompt import reglas_herramientas  # noqa: E402

TODAS = set(C.CATALOGO)


@pytest.fixture
def reg():
    return C.registro_completo()


def listadas(texto):
    return {re.match(r'- <\|CALL \["([^"]+)"', linea).group(1) for linea in texto.splitlines()
            if linea.startswith("- ")}


def lineas_por_nombre(texto):
    return {re.match(r'- <\|CALL \["([^"]+)"', l).group(1): l
            for l in texto.splitlines() if l.startswith("- ")}


def test_solo_las_del_modo(reg):
    patata = listadas(reglas_herramientas(reg, "patata", TODAS))
    assert "temporizador" in patata and "sistema_info" in patata
    # Cortes 9/10: bailar sí (el título baila al ritmo de la canción); las demás de la mascota, no.
    assert {n for n in patata if n.startswith("mascota_")} == {"mascota_bailar"}
    assert {"listar_bailes", "parar_baile"} <= patata
    assert "comentar_pantalla" not in patata

    vrm = listadas(reglas_herramientas(reg, "vrm", TODAS))
    assert {"mascota_sentarse", "mascota_dormir", "comentar_pantalla"} <= vrm

    mascota = listadas(reglas_herramientas(reg, "mascota", TODAS))
    assert "mascota_dormir" in mascota and "mascota_sentarse" in mascota   # cortes 7/8
    assert "mascota_tamano" not in mascota

    normal = listadas(reglas_herramientas(reg, "normal", TODAS))
    assert "mascota_bailar" in normal and "mascota_dormir" not in normal


@pytest.mark.parametrize("modo", C.MODOS)
def test_cada_listada_vale_en_su_modo(reg, modo):
    for n in listadas(reglas_herramientas(reg, modo, TODAS)):
        assert C.CATALOGO[n].disponible_en(modo)


def test_solo_las_que_tienen_handler(reg):
    texto = reglas_herramientas(reg, "patata", {"temporizador", "sistema_info"})
    assert listadas(texto) == {"temporizador", "sistema_info"}


def test_lo_no_registrado_no_se_ofrece():
    texto = reglas_herramientas(H.registro_basico(), "patata",
                                {"temporizador", "sistema_info"})
    assert listadas(texto) == {"sistema_info"}


def test_nombres_fuera_del_catalogo_se_ignoran(reg):
    assert reglas_herramientas(reg, "patata", {"formatear_disco"}) == ""


def test_sin_herramientas_vacio(reg):
    assert reglas_herramientas(reg, "patata", set()) == ""
    assert reglas_herramientas(reg, "patata", {"mascota_dormir"}) == ""


def test_argumentos_en_la_lista(reg):
    texto = reglas_herramientas(reg, "patata", TODAS)
    assert '- <|CALL ["temporizador", {"segundos": N, "texto": "…"}]|> Poner un temporizador' in texto
    assert '<|CALL ["alarma", {"hora": "HH:MM", "dias": "", "texto": "…", "fecha": "AAAA-MM-DD"}]|>' in texto
    assert '<|CALL ["dar_de_comer", {"comida": "batido|pastel"}]|>' in texto


def test_firmas_con_la_forma_de_la_llamada(reg):
    """Ninguna firma `nombre(arg: tipo)`: el modelo la copiaba como <|nombre(arg=…)|>."""
    texto = reglas_herramientas(reg, "vrm", TODAS)
    for linea in texto.splitlines():
        if linea.startswith("- "):
            assert linea.startswith('- <|CALL ["'), linea
            assert not re.match(r"- \w+\(", linea)


def _rellenar(marca):
    """La firma con valores del tipo, como los escribiría el modelo."""
    t = marca.replace(": N", ": 5").replace(": true|false", ": true")
    t = re.sub(r'"([a-z]+)\|[a-z|]+"', r'"\1"', t)          # enum → la primera opción
    return (t.replace('"HH:MM"', '"07:30"').replace('"AAAA-MM-DD"', '"2026-01-01"')
             .replace('"https://…"', '"https://example.org"').replace('"…"', '"x"'))


@pytest.mark.parametrize("nombre", sorted(TODAS))
def test_la_firma_rellenada_es_una_llamada_valida(reg, nombre):
    texto = reglas_herramientas(reg, None, {nombre})
    linea = lineas_por_nombre(texto)[nombre]
    marca = re.search(r"<\|CALL .*?\|>", linea).group(0)
    ej = A.Ejecutor(reg, H.Sesion(reg), {nombre: lambda a, c: "ok"})
    _, llamadas = ej.procesar(_rellenar(marca))
    assert [ll.herramienta for ll in llamadas] == [nombre]
    assert llamadas[0].valida, (marca, llamadas[0].error)


def test_sin_formato_antiguo(reg):
    texto = reglas_herramientas(reg, "vrm", TODAS)
    for viejo in ("ABRIR_URL", "ABRIR_BUSQUEDA", "TOOL:"):
        assert viejo not in texto


def _ejemplos(texto):
    return [l for l in texto.splitlines() if l.startswith("«")]


def test_dos_ejemplos_y_uno_sin_accion_y_se_entienden(reg):
    texto = reglas_herramientas(reg, "patata", TODAS)
    ejemplos = _ejemplos(texto)
    assert len(ejemplos) == 3
    ej = A.Ejecutor(reg, H.Sesion(reg), {n: (lambda a, c: "ok") for n in TODAS})
    hechas = []
    for linea in ejemplos:
        respuesta = linea.split(" → ", 1)[1]
        assert respuesta.startswith("<|ACT {")                 # la cara, al principio
        limpio, llamadas = ej.procesar(respuesta)
        assert all(ll.valida for ll in llamadas) and "<|CALL" not in limpio
        hechas += [ll.herramienta for ll in llamadas]
    assert hechas == ["abrir_url", "temporizador"]            # el tercero: sin acción
    assert "sin marca" in ejemplos[-1]


def test_los_ejemplos_son_neutros(reg):
    """Prueba real: el modelo copió «sacar la pizza» del único ejemplo."""
    for modo in C.MODOS:
        texto = reglas_herramientas(reg, modo, TODAS)
        assert "pizza" not in texto
    # Un cuarto de hora son 900 s: enseña a pasar palabras a número.
    assert '["temporizador", {"segundos": 900}]' in reglas_herramientas(reg, "normal", TODAS)


def test_sin_emociones_los_ejemplos_no_llevan_act(reg):
    texto = reglas_herramientas(reg, "normal", TODAS, con_emociones=False)
    assert "<|ACT" not in texto and len(_ejemplos(texto)) == 3


def test_anti_ejemplos_de_las_marcas_inventadas(reg):
    texto = reglas_herramientas(reg, "normal", TODAS)
    assert "<|OPEN_URL" in texto and "<|nombre(…)|>" in texto and "|<…>|" in texto


@pytest.mark.parametrize("nombre", sorted(TODAS))
def test_los_ejemplos_solo_de_lo_disponible(reg, nombre):
    """Sea cual sea la única disponible, los ejemplos con acción son de ella (o no hay)."""
    texto = reglas_herramientas(reg, None, {nombre})
    ej = A.Ejecutor(reg, H.Sesion(reg), {nombre: lambda a, c: "ok"})
    for linea in _ejemplos(texto):
        _, llamadas = ej.procesar(linea.split(" → ", 1)[1])
        assert all(ll.herramienta == nombre and ll.valida for ll in llamadas)


def test_marca_pide_permiso(reg):
    texto = reglas_herramientas(reg, "vrm", TODAS)
    lineas = lineas_por_nombre(texto)
    assert lineas["lanzar_app"].endswith("(pide permiso)")
    assert lineas["minecraft_orden"].endswith("(pide permiso)")
    assert not lineas["temporizador"].endswith("(pide permiso)")
    assert not lineas["comentar_pantalla"].endswith("(pide permiso)")
    nube = reglas_herramientas(reg, "vrm", TODAS, ctx={"proveedor": "openrouter"})
    assert ('- <|CALL ["comentar_pantalla", {}]|> Mirar la pantalla y comentarla (pide permiso)'
            in nube)
    local = reglas_herramientas(reg, "vrm", TODAS, ctx={"proveedor": "ollama"})
    assert '- <|CALL ["comentar_pantalla", {}]|> Mirar la pantalla y comentarla\n' in local + "\n"


def test_comentar_pantalla_sin_handler_no_se_ofrece(reg):
    """Nadie registra un handler «comentar_pantalla» (el comentario va por la mascota,
    sin herramienta): con los handlers reales no aparece en ningún modo."""
    sin = TODAS - {"comentar_pantalla"}
    for modo in C.MODOS:
        assert "comentar_pantalla" not in reglas_herramientas(reg, modo, sin)


def test_bailes_de_la_biblioteca(reg):
    """Prueba real: el modelo se inventaba canciones y nunca listaba los bailes."""
    lineas = lineas_por_nombre(reglas_herramientas(reg, "mascota", TODAS))
    assert "listar_bailes" in lineas["mascota_bailar"] and "omítela" in lineas["mascota_bailar"]
    assert "preguntan" in lineas["listar_bailes"]


def test_solo_lectura(reg):
    texto = reglas_herramientas(reg, "vrm", TODAS, solo_lectura=True)
    assert listadas(texto) == {"sistema_info", "listar_alarmas", "comentar_pantalla",
                               "minecraft_estado", "listar_bailes"}


def test_titulo(reg):
    assert reglas_herramientas(reg, "patata", TODAS).startswith("## Herramientas\n")
    sin = reglas_herramientas(reg, "patata", TODAS, con_titulo=False)
    assert "## Herramientas" not in sin
    # Encaja con construir_system_prompt, que pone su propio título.
    from lune_core.prompt import construir_system_prompt
    sp = construir_system_prompt("Eres Lune.", herramientas=sin)
    assert sp.count("## Herramientas") == 1 and "<|CALL" in sp


def test_estable_y_corta(reg):
    a = reglas_herramientas(reg, "vrm", set(sorted(TODAS)))
    b = reglas_herramientas(reg, "vrm", list(reversed(sorted(TODAS))))
    assert a == b                                   # no depende del orden del set
    # Presupuesto (modelos locales pequeños). Subió de 2200 a 3300 con TODO el catálogo
    # en vrm (22 herramientas; con los handlers reales, ~3000) por las firmas con forma
    # de llamada, los dos ejemplos + uno sin acción y los anti-ejemplos: la prueba real
    # pasó de acertar solo con temporizador a acertar también NASA y alarma. Se compensa
    # en parte con la gramática de emociones más corta (sin DELAY) y, sobre todo, el
    # prompt ya es ESTABLE: con la caché de prefijo se evalúa una vez por conversación.
    assert len(a) < 3300
    assert "<<<INICIO" in a                         # recuerda la regla anti-inyección
    assert not re.search(r"\d{4}-\d{2}-\d{2}|\d{1,2}:\d{2}", a)   # ni fechas ni horas: caché
