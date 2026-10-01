"""
Ningún texto de la app le dice al usuario «pip install …» por su cuenta: lo dice
nucleo/rutas.como_instalar(), que desde el código da la orden de pip y en la Lune
instalada (Setup.exe, sin Python ni pip) dice que eso no viene incluido.

LA REGLA (la que aplica este test)
----------------------------------
Se recorre el código de la app: los .py de nucleo/, servicios/, ui/ y lune_core/,
main.py y patata.py, y los .js/.jsx/.mjs de ui_web/ salvo ui_web/vendor/ (librerías
de terceros). Falla si «pip install» (o «pip3 install») aparece en:

- Python: cualquier cadena del código (también las f-strings), MENOS los docstrings,
  que no llegan al usuario. Excepción: el docstring del módulo patata.py SÍ cuenta,
  porque /ayuda se construye con él. Los comentarios no cuentan.
- JS/JSX: el texto sin comentarios (/* … */, {/* … */} y // …).

Permitido: nucleo/rutas.py (como_instalar, el único que escribe la orden). El flujo
de git del actualizador llama a pip con una lista (["-m", "pip", "install", …]) y no
es un texto para el usuario, así que no choca con la regla.
"""
import ast
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

PERMITIDOS = {"nucleo/rutas.py"}
CARPETAS_PY = ("nucleo", "servicios", "ui", "lune_core")
SUELTOS_PY = ("main.py", "patata.py")
DOCSTRING_QUE_SE_ENSENA = {"patata.py"}           # patata.ayuda() lee su __doc__

_RE_PIP = re.compile(r"\bpip3?\s+install\b", re.IGNORECASE)
_RE_BLOQUE_JS = re.compile(r"/\*.*?\*/", re.DOTALL)
_RE_LINEA_JS = re.compile(r"(^|\s)//.*$", re.MULTILINE)


def _docstrings(arbol: ast.AST, *, con_el_del_modulo: bool = True) -> set:
    """id() de los nodos Constant que son docstrings (de clases y funciones, y el del
    módulo si `con_el_del_modulo`)."""
    ids = set()
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if isinstance(nodo, ast.Module) and not con_el_del_modulo:
            continue
        cuerpo = nodo.body
        if cuerpo and isinstance(cuerpo[0], ast.Expr) and isinstance(cuerpo[0].value, ast.Constant) \
                and isinstance(cuerpo[0].value.value, str):
            ids.add(id(cuerpo[0].value))
    return ids


def pips_en_python(codigo: str, *, docstring_modulo_cuenta: bool = False) -> list:
    """[(línea, texto)] de las cadenas con «pip install» que no son docstrings."""
    arbol = ast.parse(codigo)
    excluidos = _docstrings(arbol, con_el_del_modulo=not docstring_modulo_cuenta)
    hallados = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str) and id(nodo) not in excluidos:
            if _RE_PIP.search(nodo.value):
                hallados.append((getattr(nodo, "lineno", 0), nodo.value.strip()[:90]))
    return hallados


def pips_en_js(codigo: str) -> list:
    """[(línea, texto)] con «pip install» fuera de los comentarios."""
    sin_bloques = _RE_BLOQUE_JS.sub(lambda m: "\n" * m.group(0).count("\n"), codigo)
    limpio = _RE_LINEA_JS.sub(r"\1", sin_bloques)
    return [(n, linea.strip()[:90]) for n, linea in enumerate(limpio.splitlines(), 1) if _RE_PIP.search(linea)]


def _archivos_py():
    for carpeta in CARPETAS_PY:
        for ruta in sorted((RAIZ / carpeta).rglob("*.py")):
            if "__pycache__" not in ruta.parts:
                yield ruta
    for nombre in SUELTOS_PY:
        yield RAIZ / nombre


def _archivos_js():
    for ruta in sorted((RAIZ / "ui_web").rglob("*")):
        if ruta.suffix.lower() in (".js", ".jsx", ".mjs") and "vendor" not in ruta.relative_to(RAIZ / "ui_web").parts:
            yield ruta


def _rel(ruta: Path) -> str:
    return ruta.relative_to(RAIZ).as_posix()


# ── El detector (para que la regla sea la que dice el docstring) ────────────────

def test_el_detector_de_python_sigue_la_regla():
    codigo = '''"""Módulo: pip install algo (docstring: vale)."""
# pip install en un comentario: vale
def f(faltan):
    """pip install otra (docstring de función: vale)"""
    a = "Instálalo con:  pip install pypdf"
    b = f"    pip install {' '.join(faltan)}"
    c = ["-m", "pip", "install", "-r"]
    return a, b, c
'''
    hallados = pips_en_python(codigo)
    assert [n for n, _ in hallados] == [5, 6]
    assert [n for n, _ in pips_en_python(codigo, docstring_modulo_cuenta=True)] == [1, 5, 6]


def test_el_detector_de_js_ignora_los_comentarios():
    codigo = """// pip install nada
const a = 'hace falta: pip install kokoro-onnx';
/* pip install
   tampoco */
const url = 'https://ejemplo.mx/pip'; // pip install al final: comentario
<p>{/* pip install en JSX: comentario */}</p>
<code>pip install {faltan}</code>
"""
    assert [n for n, _ in pips_en_js(codigo)] == [2, 7]


# ── El código de la app ─────────────────────────────────────────────────────────

def test_ningun_texto_de_python_dice_pip_install_por_su_cuenta():
    problemas = []
    for ruta in _archivos_py():
        rel = _rel(ruta)
        if rel in PERMITIDOS:
            continue
        codigo = ruta.read_text(encoding="utf-8")
        for linea, texto in pips_en_python(codigo, docstring_modulo_cuenta=rel in DOCSTRING_QUE_SE_ENSENA):
            problemas.append(f"{rel}:{linea}  {texto!r}")
    assert not problemas, ("Usa nucleo/rutas.como_instalar(...) en vez de escribir «pip install»:\n  "
                           + "\n  ".join(problemas))


def test_ningun_texto_de_la_pagina_dice_pip_install():
    problemas = []
    for ruta in _archivos_js():
        for linea, texto in pips_en_js(ruta.read_text(encoding="utf-8", errors="replace")):
            problemas.append(f"{_rel(ruta)}:{linea}  {texto!r}")
    assert not problemas, ("La página no escribe «pip install»: usa el texto que manda el backend "
                           "(rutas.como_instalar) o la bandera «instalada»:\n  " + "\n  ".join(problemas))


def test_se_recorre_de_verdad_el_codigo():
    rels = {_rel(r) for r in _archivos_py()}
    assert {"main.py", "patata.py", "servicios/voz_entrada.py", "ui/web_bridge.py",
            "lune_core/voz/kokoro_backend.py"} <= rels
    assert any(_rel(r).endswith("settings.jsx") for r in _archivos_js())
    assert not any("/vendor/" in _rel(r) for r in _archivos_js())


# ── como_instalar: pip desde el código, el aviso instalada ──────────────────────

def test_como_instalar_desde_el_codigo_e_instalada(monkeypatch):
    from nucleo import rutas
    monkeypatch.setattr(rutas, "INSTALADA", False)
    assert rutas.como_instalar("faster-whisper", "sounddevice") == "pip install faster-whisper sounddevice"
    monkeypatch.setattr(rutas, "INSTALADA", True)
    assert rutas.como_instalar("faster-whisper") == rutas.AVISO_NO_INCLUIDO
    assert "pip" not in rutas.AVISO_NO_INCLUIDO.lower()


@pytest.mark.parametrize("modulo, llamada", [
    ("servicios.voz_entrada", lambda m: m.mensaje_instalacion()),
    ("lune_core.voz.kokoro_backend", lambda m: m.mensaje_instalacion()),
    ("lune_core.voz.rvc_backend", lambda m: m.mensaje_instalacion()),
])
def test_los_mensajes_de_instalar_siguen_a_rutas(monkeypatch, modulo, llamada):
    import importlib
    from nucleo import rutas
    m = importlib.import_module(modulo)
    monkeypatch.setattr(m, "dependencias_faltantes", lambda: ["paquete-falso"])
    monkeypatch.setattr(rutas, "INSTALADA", False)
    assert "pip install paquete-falso" in llamada(m)
    monkeypatch.setattr(rutas, "INSTALADA", True)
    texto = llamada(m)
    assert "pip install" not in texto and rutas.AVISO_NO_INCLUIDO in texto
