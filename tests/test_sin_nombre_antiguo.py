"""
Guardia de la 11: el nombre viejo del modo «asistente en escritorio» no vuelve al repo.

Diego pidió quitarlo de todo Lune, código e interfaz, porque suena ofensivo. Este test
recorre TODOS los archivos de texto del repo (los versionados y los nuevos que .gitignore
no ignora; sin ui_web/vendor ni node_modules) y falla si la palabra aparece, en cualquier
mayúscula y también en inglés, fuera de la lista blanca: nucleo/nombres_antiguos.py (el
único que la necesita, para traducir lo que la gente ya tiene guardado con ella) y sus
tests. También mira los nombres de archivos y carpetas.

- Texto: UTF-8, o UTF-16/UTF-32 si llevan BOM.
- Binarios (un byte 0 al principio: imágenes, vídeos, audio, fuentes, o texto en UTF-16 sin
  BOM): no se saltan, se busca en los bytes tal cual (metadatos de un PNG o el título de un
  WebM) y en UTF-16/UTF-32 (LE y BE).
- Carpetas: además de las rutas que lista git, se recorre el árbol (sin .git, node_modules,
  __pycache__, ui_web/vendor ni lo que .gitignore ignora entero), así que también salen las
  carpetas vacías o con solo archivos ignorados (git mv deja atrás carpetas vacías).

La palabra se construye aquí a trozos para que este archivo no la contenga.
Si el test falla: di «asistente en escritorio» (el modo, en etiquetas y menús) o «la
asistente» / «sácame al escritorio» (en prosa, con la voz de Lune), o, si es un dato
guardado con el nombre viejo, tradúcelo en nucleo/nombres_antiguos.py.
"""
import os
import re
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent

# La raíz común del español y del inglés, a trozos (las dos formas y sus plurales).
_RAIZ_PALABRA = "mas" + "cot"
PATRON = re.compile(re.escape(_RAIZ_PALABRA), re.IGNORECASE)

# Los únicos archivos que pueden escribirla (rutas relativas a la raíz, con «/»).
LISTA_BLANCA = frozenset({
    "nucleo/nombres_antiguos.py",
    "tests/test_nombres_antiguos.py",
})

# Lo que no es nuestro: bibliotecas de terceros (y, al recorrer carpetas, lo de git y Python).
_CARPETAS_FUERA = ("ui_web/vendor/",)
_SEGMENTOS_FUERA = ("node_modules",)
_CARPETAS_NUNCA = frozenset({".git", "node_modules", "__pycache__"})

_TROZO_BINARIO = 8192
_BOMS_32 = (b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")         # antes que los de 16: empiezan igual
_BOMS_16 = (b"\xff\xfe", b"\xfe\xff")


def _letra(c: str) -> bytes:
    return b"[" + c.lower().encode() + c.upper().encode() + b"]"


# La palabra en bytes, sin distinguir mayúsculas: tal cual (ASCII, UTF-8, Latin-1…) y en
# UTF-16/UTF-32 de los dos órdenes.
PATRONES_BYTES = tuple((forma, re.compile(b"".join(antes + _letra(c) + despues for c in _RAIZ_PALABRA)))
                       for forma, antes, despues in (
                           ("bytes", b"", b""),
                           ("UTF-16LE", b"", b"\x00"), ("UTF-16BE", b"\x00", b""),
                           ("UTF-32LE", b"", b"\x00" * 3), ("UTF-32BE", b"\x00" * 3, b"")))


def _archivos_del_repo() -> list:
    """Versionados + nuevos no ignorados, sin los de terceros. Salta el test sin git."""
    try:
        r = subprocess.run(
            ["git", "-c", "core.quotepath=off", "ls-files", "-z", "--cached", "--others",
             "--exclude-standard"],
            cwd=RAIZ, capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as e:
        pytest.skip(f"sin git para listar los archivos del repo: {e}")
    if r.returncode != 0:
        pytest.skip("no es un repositorio git: " + r.stderr.decode("utf-8", "replace").strip())
    rutas = set()
    for crudo in r.stdout.split(b"\0"):
        if not crudo:
            continue
        ruta = crudo.decode("utf-8", "surrogateescape").replace("\\", "/")
        if ruta.startswith(_CARPETAS_FUERA):
            continue
        if any(seg in _SEGMENTOS_FUERA for seg in ruta.split("/")):
            continue
        rutas.add(ruta)
    return sorted(rutas)


def _leer(archivo: Path):
    """(texto, crudo): el texto (None si es binario) y los bytes; (None, None) si no se
    deja leer."""
    try:
        crudo = archivo.read_bytes()
    except OSError:
        return None, None
    if crudo.startswith(_BOMS_32):
        return crudo.decode("utf-32", "replace"), crudo
    if crudo.startswith(_BOMS_16):
        return crudo.decode("utf-16", "replace"), crudo
    if b"\0" in crudo[:_TROZO_BINARIO]:
        return None, crudo                                            # binario
    return crudo.decode("utf-8", "replace"), crudo


def _texto(archivo: Path):
    """El contenido como texto, o None si es binario o no se deja leer."""
    return _leer(archivo)[0]


def _en_bytes(crudo: bytes) -> list:
    """Las formas en que la palabra está en unos bytes («bytes», «UTF-16LE»…)."""
    return [forma for forma, patron in PATRONES_BYTES if patron.search(crudo or b"")]


def _en_archivo(archivo: Path) -> list:
    """Dónde sale la palabra en un archivo: «n: línea» si es texto, «binario (formas)» si no."""
    texto, crudo = _leer(archivo)
    if texto is not None:
        if not PATRON.search(texto):
            return []
        return [f"{n}: {linea.strip()[:160]}"
                for n, linea in enumerate(texto.splitlines(), 1) if PATRON.search(linea)]
    formas = _en_bytes(crudo) if crudo is not None else []
    return [f"dentro del binario ({', '.join(formas)})"] if formas else []


def _carpetas_ignoradas() -> frozenset:
    """Las carpetas que .gitignore ignora enteras (rutas relativas con «/», sin la del final)."""
    try:
        r = subprocess.run(
            ["git", "-c", "core.quotepath=off", "ls-files", "-z", "--others", "--ignored",
             "--exclude-standard", "--directory"],
            cwd=RAIZ, capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return frozenset()
    if r.returncode != 0:
        return frozenset()
    return frozenset(c.decode("utf-8", "surrogateescape").replace("\\", "/").rstrip("/")
                     for c in r.stdout.split(b"\0") if c.endswith(b"/"))


def _carpetas_con_la_palabra(raiz: Path, ignoradas=frozenset()) -> list:
    """Carpetas bajo `raiz` con la palabra en su nombre, estén o no en git (vacías, o con
    solo archivos ignorados). Sin .git, node_modules, __pycache__, ui_web/vendor ni las
    `ignoradas` (rutas relativas a `raiz`, con «/»)."""
    fuera = {c.rstrip("/") for c in _CARPETAS_FUERA} | set(ignoradas)
    malas = []
    for actual, carpetas, _archivos in os.walk(raiz):
        rel = Path(actual).relative_to(raiz).as_posix()
        rel = "" if rel == "." else rel
        quedan = []
        for c in sorted(carpetas):
            ruta = f"{rel}/{c}" if rel else c
            if c in _CARPETAS_NUNCA or ruta in fuera:
                continue
            if PATRON.search(c):
                malas.append(ruta)
            quedan.append(c)
        carpetas[:] = quedan
    return sorted(malas)


def _apariciones() -> list:
    encontradas = []
    for ruta in _archivos_del_repo():
        if PATRON.search(ruta):
            encontradas.append(f"{ruta}: el propio nombre del archivo o de su carpeta")
        if ruta in LISTA_BLANCA:
            continue
        archivo = RAIZ / ruta
        if not archivo.is_file():                  # borrado en la copia de trabajo, o un submódulo
            continue
        encontradas.extend(f"{ruta}:{donde}" for donde in _en_archivo(archivo))
    for carpeta in _carpetas_con_la_palabra(RAIZ, _carpetas_ignoradas()):
        encontradas.append(f"{carpeta}/: carpeta con el nombre viejo (aunque git no la vea)")
    return encontradas


def test_el_patron_pilla_todas_las_formas():
    for forma in ("a", "as", "A", "AS", "", "s"):
        palabra = _RAIZ_PALABRA + forma
        for variante in (palabra, palabra.upper(), palabra.capitalize()):
            assert PATRON.search(f"x_{variante}_y"), variante
    assert not PATRON.search("asistente en escritorio")


def test_lee_texto_en_cualquier_codificacion_y_busca_en_binarios(tmp_path):
    palabra = _RAIZ_PALABRA + "a"
    casos = {
        "utf8.txt": f"hola {palabra}\n".encode("utf-8"),
        "utf16_bom.txt": f"hola {palabra}\n".encode("utf-16"),
        "utf16le_sin_bom.txt": f"hola {palabra.upper()}\n".encode("utf-16-le"),
        "utf16be_sin_bom.txt": f"hola {palabra}\n".encode("utf-16-be"),
        "utf32_bom.txt": f"hola {palabra}\n".encode("utf-32"),
        "utf32le_sin_bom.txt": f"hola {palabra}\n".encode("utf-32-le"),
        "con_nul.js": ("const s = '\x00';\n// la " + palabra.capitalize() + "\n").encode("utf-8"),
        "imagen.png": b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR" + b"\x00" * 20
                      + b"tEXtComment\x00mi " + palabra.encode() + b"\x00",
    }
    for nombre, datos in casos.items():
        (tmp_path / nombre).write_bytes(datos)
        assert _en_archivo(tmp_path / nombre), f"{nombre}: no la ve"
    # UTF-32 con BOM se lee como texto (y no como UTF-16 mal leído).
    assert _texto(tmp_path / "utf32_bom.txt") == f"hola {palabra}\n"
    assert _en_archivo(tmp_path / "utf32_bom.txt") == [f"1: hola {palabra}"]
    assert "UTF-16LE" in _en_bytes(casos["utf16le_sin_bom.txt"])
    # Sin la palabra, nada.
    (tmp_path / "limpio.bin").write_bytes(b"\x00\x01asistente\x00" + "asistente".encode("utf-16-le"))
    assert _en_archivo(tmp_path / "limpio.bin") == []
    assert _en_archivo(tmp_path / "no_existe.txt") == []


def test_ve_las_carpetas_que_git_no_lista(tmp_path):
    palabra = _RAIZ_PALABRA
    (tmp_path / "ui_web" / "assets" / palabra / "anime").mkdir(parents=True)     # vacía (git mv)
    (tmp_path / "otra" / (palabra.upper() + "s")).mkdir(parents=True)
    for fuera in (".git/" + palabra, "node_modules/" + palabra, "ui_web/vendor/" + palabra,
                  "x/__pycache__/" + palabra, "ignorada/" + palabra):
        (tmp_path / fuera).mkdir(parents=True)
    assert _carpetas_con_la_palabra(tmp_path, frozenset({"ignorada"})) == [
        "otra/" + palabra.upper() + "s", "ui_web/assets/" + palabra]


def test_la_lista_blanca_no_se_queda_vieja():
    """Sus archivos existen y de verdad la necesitan (si ya no, fuera de la lista)."""
    for ruta in LISTA_BLANCA:
        archivo = RAIZ / ruta
        assert archivo.is_file(), f"{ruta} ya no existe: quítalo de LISTA_BLANCA"
        assert PATRON.search(_texto(archivo) or ""), f"{ruta} ya no la usa: quítalo de LISTA_BLANCA"


def test_la_palabra_vieja_no_aparece_fuera_de_la_lista_blanca():
    encontradas = _apariciones()
    muestra = "\n".join(encontradas[:60])
    resto = f"\n… y {len(encontradas) - 60} más" if len(encontradas) > 60 else ""
    assert not encontradas, (
        f"El nombre viejo del modo asistente en escritorio sigue en {len(encontradas)} sitio(s). "
        "Solo puede estar en nucleo/nombres_antiguos.py y sus tests:\n" + muestra + resto)
