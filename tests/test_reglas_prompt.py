"""
Tests de las reglas de herramientas del system prompt (lune_core/reglas_prompt.py).

Lo crítico: solo aparecen las herramientas con handler, registradas y del modo;
el ejemplo usa el formato único <|CALL …|> y el Ejecutor lo entiende tal cual;
y el formato antiguo (ABRIR_URL:/TOOL:) no se enseña nunca.
"""
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
    return {linea[2:].split("(", 1)[0] for linea in texto.splitlines()
            if linea.startswith("- ")}


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
    assert "- temporizador(segundos: entero 1-90000, texto?: texto ≤60):" in texto
    assert "alarma(hora: HH:MM, dias?: letras lmxjvsd" in texto
    assert "dar_de_comer(comida: batido|pastel)" in texto


def test_sin_formato_antiguo(reg):
    texto = reglas_herramientas(reg, "vrm", TODAS)
    for viejo in ("ABRIR_URL", "ABRIR_BUSQUEDA", "TOOL:"):
        assert viejo not in texto


def test_un_solo_ejemplo_y_se_entiende(reg, tmp_path):
    texto = reglas_herramientas(reg, "patata", TODAS)
    assert texto.count("<|CALL ") == 1
    ej = A.Ejecutor(reg, H.Sesion(reg), {n: (lambda a, c: "ok") for n in TODAS})
    limpio, llamadas = ej.procesar(texto)
    assert len(llamadas) == 1 and llamadas[0].valida
    assert llamadas[0].herramienta == "temporizador"
    assert "<|CALL" not in limpio


@pytest.mark.parametrize("nombre", sorted(TODAS))
def test_el_ejemplo_de_cada_herramienta_es_valido(reg, nombre):
    """Sea cual sea la única disponible, su ejemplo pasa por el Ejecutor."""
    texto = reglas_herramientas(reg, None, {nombre})
    ej = A.Ejecutor(reg, H.Sesion(reg), {nombre: lambda a, c: "ok"})
    _, llamadas = ej.procesar(texto)
    assert [ll.herramienta for ll in llamadas] == [nombre]
    assert llamadas[0].valida, llamadas[0].error


def test_marca_pide_permiso(reg):
    texto = reglas_herramientas(reg, "vrm", TODAS)
    lineas = {l[2:].split("(", 1)[0]: l for l in texto.splitlines() if l.startswith("- ")}
    assert lineas["lanzar_app"].endswith("(pide permiso)")
    assert lineas["minecraft_orden"].endswith("(pide permiso)")
    assert not lineas["temporizador"].endswith("(pide permiso)")
    assert not lineas["comentar_pantalla"].endswith("(pide permiso)")
    nube = reglas_herramientas(reg, "vrm", TODAS, ctx={"proveedor": "openrouter"})
    assert "- comentar_pantalla(): Mirar la pantalla y comentarla (pide permiso)" in nube
    local = reglas_herramientas(reg, "vrm", TODAS, ctx={"proveedor": "ollama"})
    assert "- comentar_pantalla(): Mirar la pantalla y comentarla\n" in local + "\n"


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
    assert len(a) < 2200                            # modelos locales pequeños
    assert "<<<INICIO" in a                         # recuerda la regla anti-inyección
