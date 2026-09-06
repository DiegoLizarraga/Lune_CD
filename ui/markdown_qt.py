"""
markdown_qt.py — Convierte el markdown que escupen los modelos al subconjunto
de HTML que entiende el rich text de Qt.

No usamos una librería de markdown a propósito: Qt solo soporta un HTML4 muy
recortado (nada de <table>, ni CSS moderno), así que un conversor completo
generaría etiquetas que se verían como basura literal en pantalla. Esto cubre
lo que un asistente usa de verdad: negritas, cursivas, código, listas, títulos,
enlaces y citas.

Los bloques de código NO se convierten aquí — se separan con `dividir_bloques()`
para que chat_widgets.py los pinte en un widget propio con botón de copiar.
"""
import html
import re
from typing import List, Tuple

# (tipo, contenido, lenguaje) — tipo es "texto" o "codigo"
Bloque = Tuple[str, str, str]

_CERCA = re.compile(r"^[ \t]*```([\w+#-]*)[ \t]*$", re.MULTILINE)


def dividir_bloques(texto: str) -> List[Bloque]:
    """
    Separa el texto en bloques normales y bloques de código con ```.

    Una cerca sin cerrar (habitual mientras el modelo escribe) se trata como
    código hasta el final: así el bloque se ve bien ya durante el streaming.
    """
    if not texto:
        return []

    bloques: List[Bloque] = []
    pos = 0
    while True:
        apertura = _CERCA.search(texto, pos)
        if not apertura:
            resto = texto[pos:]
            if resto.strip():
                bloques.append(("texto", resto, ""))
            break

        previo = texto[pos:apertura.start()]
        if previo.strip():
            bloques.append(("texto", previo, ""))

        lenguaje = apertura.group(1) or ""
        cierre = _CERCA.search(texto, apertura.end())
        if cierre:
            codigo = texto[apertura.end():cierre.start()]
            pos = cierre.end()
        else:
            codigo = texto[apertura.end():]
            pos = len(texto)

        bloques.append(("codigo", codigo.strip("\n"), lenguaje))
        if pos >= len(texto):
            break

    return bloques or [("texto", texto, "")]


# ── Conversión de un bloque de texto a HTML de Qt ─────────────────────────────

def _inline(texto: str, color_codigo: str, color_enlace: str) -> str:
    """Formato dentro de una línea. El texto ya debe venir escapado."""
    # El código en línea se aparta primero para que su contenido no se
    # reinterprete (si no, `**` dentro de `código` saldría en negrita).
    apartados: List[str] = []

    def _guardar(m):
        apartados.append(m.group(1))
        return f"\x00{len(apartados) - 1}\x00"

    texto = re.sub(r"`([^`]+)`", _guardar, texto)

    # Enlaces [texto](url) — solo http(s), como en tools.py
    texto = re.sub(
        r"\[([^\]]+)\]\((https?://[^\s)]+)\)",
        rf'<a href="\2" style="color:{color_enlace};">\1</a>',
        texto,
    )
    # URLs sueltas
    texto = re.sub(
        r"(?<!href=\")(?<!>)(https?://[^\s<]+)",
        rf'<a href="\1" style="color:{color_enlace};">\1</a>',
        texto,
    )

    texto = re.sub(r"\*\*\*(.+?)\*\*\*", r"<b><i>\1</i></b>", texto)
    texto = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", texto)
    texto = re.sub(r"__(.+?)__", r"<b>\1</b>", texto)
    texto = re.sub(r"~~(.+?)~~", r"<s>\1</s>", texto)
    # Cursiva: se exige que no sea parte de ** para no romper las negritas
    texto = re.sub(r"(?<![\*\w])\*(?!\s)([^\*\n]+?)(?<!\s)\*(?![\*\w])", r"<i>\1</i>", texto)
    texto = re.sub(r"(?<![_\w])_(?!\s)([^_\n]+?)(?<!\s)_(?![_\w])", r"<i>\1</i>", texto)

    # Devolver el código en línea con su propio estilo
    def _restaurar(m):
        contenido = apartados[int(m.group(1))]
        return (f'<code style="background:{color_codigo};'
                f'font-family:Consolas,monospace;">&nbsp;{contenido}&nbsp;</code>')

    return re.sub(r"\x00(\d+)\x00", _restaurar, texto)


def a_html(texto: str, color_texto: str = "#EAF1FF",
           color_codigo: str = "#1B2440", color_enlace: str = "#00E5FF",
           color_tenue: str = "#97A6C4") -> str:
    """Convierte un bloque de texto markdown al HTML que Qt sabe pintar."""
    if not texto:
        return ""

    lineas = html.escape(texto).split("\n")
    salida: List[str] = []
    lista_abierta = None   # "ul" | "ol" | None

    def _cerrar_lista():
        nonlocal lista_abierta
        if lista_abierta:
            salida.append(f"</{lista_abierta}>")
            lista_abierta = None

    for linea in lineas:
        desnuda = linea.strip()

        if not desnuda:
            _cerrar_lista()
            salida.append("<br>")
            continue

        # Regla horizontal
        if re.fullmatch(r"(\*\s*){3,}|(-\s*){3,}|(_\s*){3,}", desnuda):
            _cerrar_lista()
            salida.append(f'<hr style="border:1px solid {color_codigo};">')
            continue

        # Títulos
        if m := re.match(r"^(#{1,6})\s+(.*)$", desnuda):
            _cerrar_lista()
            nivel = len(m.group(1))
            tam = {1: 17, 2: 15, 3: 14}.get(nivel, 13)
            salida.append(
                f'<div style="font-size:{tam}px;font-weight:bold;color:{color_texto};">'
                f'{_inline(m.group(2), color_codigo, color_enlace)}</div>'
            )
            continue

        # Cita
        if m := re.match(r"^&gt;\s?(.*)$", desnuda):
            _cerrar_lista()
            salida.append(
                f'<div style="color:{color_tenue};">| '
                f'{_inline(m.group(1), color_codigo, color_enlace)}</div>'
            )
            continue

        # Lista con viñetas
        if m := re.match(r"^[-*+]\s+(.*)$", desnuda):
            if lista_abierta != "ul":
                _cerrar_lista()
                salida.append("<ul>")
                lista_abierta = "ul"
            salida.append(f"<li>{_inline(m.group(1), color_codigo, color_enlace)}</li>")
            continue

        # Lista numerada
        if m := re.match(r"^\d+[.)]\s+(.*)$", desnuda):
            if lista_abierta != "ol":
                _cerrar_lista()
                salida.append("<ol>")
                lista_abierta = "ol"
            salida.append(f"<li>{_inline(m.group(1), color_codigo, color_enlace)}</li>")
            continue

        _cerrar_lista()
        salida.append(f"{_inline(linea, color_codigo, color_enlace)}<br>")

    _cerrar_lista()

    # Los <br> del final solo dejan hueco vacío en la burbuja
    while salida and salida[-1] == "<br>":
        salida.pop()

    return "".join(salida)


def tiene_formato(texto: str) -> bool:
    """¿Merece la pena renderizar, o es texto plano y nos ahorramos el trabajo?"""
    if not texto:
        return False
    marcas = ("**", "```", "`", "* ", "- ", "# ", "> ", "](", "1. ", "__", "~~")
    return any(m in texto for m in marcas)
