"""
patata.py — Modo PATATA: Lune en la terminal, sin nada más.

Sin Qt, sin animaciones, sin imágenes, sin mascota: solo texto. Sirve para:
  · usar a Lune desde una consola porque te gusta así, o
  · rescatarla cuando la interfaz no abre (PyQt6 roto, equipo muy justo…).

Conserva lo que importa: el MISMO cerebro (Ollama u OpenRouter), la MISMA
memoria (memoria.json) y la MISMA personalidad (personajes de datos.json). Las
emociones que el modelo marca con <|ACT|> se muestran como caritas de teclado.

    python patata.py            (o doble clic en lune_patata.bat)

Comandos:  /ayuda  /memoria  /olvida <texto>  /nube  /local  /personaje <nombre>
           /limpiar  /salir
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from nucleo import datos, personajes                      # noqa: E402
from nucleo.memoria import MemoriaManager                 # noqa: E402
from lune_core import marcadores                          # noqa: E402
from lune_core.prompt import GRAMATICA_EMOCIONES          # noqa: E402
from servicios.ai_manager import AIManager                # noqa: E402

# Emoción canónica → carita de teclado (esto ES la mascota en modo patata).
CARITAS = {
    "happy": ":D", "sad": ":(", "angry": ">:(", "think": ":/", "surprised": ":O",
    "awkward": "^^'", "question": ":?", "curious": "o_O", "neutral": ":|",
    "nervous": "^^;", "wave": "o/", "dismiss": "-_-",
    "laughing": "xD", "bored": "-.-",
}

# Colores ANSI (Windows 10+ los soporta al activar VT). Con --sin-color van vacíos.
def _colores(activar: bool):
    if not activar:
        return {k: "" for k in ("cyan", "yellow", "dim", "bold", "red", "reset")}
    if os.name == "nt":
        os.system("")          # activa el procesamiento de secuencias VT en la consola
    return {"cyan": "\033[96m", "yellow": "\033[93m", "dim": "\033[90m",
            "bold": "\033[1m", "red": "\033[91m", "reset": "\033[0m"}


class Patata:
    def __init__(self, color: bool = True):
        self.c = _colores(color)
        self.ai = AIManager()
        self.memoria = MemoriaManager()
        self.provider = "ollama" if datos.ollama_model() else "openrouter"
        self.tools = None
        try:                                   # opcional: "abre youtube", "estado del pc"
            from servicios.tools import ToolManager
            self.tools = ToolManager()
        except Exception:
            pass

    # ── Prompt: igual que la app (personalidad + memoria + emociones) ────────────
    def _system_prompt(self) -> str:
        base = personajes.build_system_prompt(personajes.get_activo())
        try:
            ctx = self.memoria.obtener_contexto_para_prompt()
        except Exception:
            ctx = ""
        if ctx:
            base += "\n\nCONTEXTO DE MEMORIA DEL USUARIO:\n" + ctx
        return base + "\n\n" + GRAMATICA_EMOCIONES

    # ── Salida por consola (stream con los marcadores <|…|> ocultos) ────────────
    def _imprimir_stream(self):
        c = self.c
        estado = {"buf": "", "dentro": False}

        def on_token(t: str):
            s = estado["buf"] + t
            out = ""
            while s:
                if estado["dentro"]:
                    j = s.find("|>")
                    if j < 0:
                        break                      # marcador a medias: esperar
                    estado["dentro"] = False
                    s = s[j + 2:]
                    continue
                i = s.find("<|")
                if i < 0:
                    if s.endswith("<"):            # podría empezar "<|" en el próximo token
                        out += s[:-1]; s = "<"
                        break
                    out += s; s = ""
                else:
                    out += s[:i]; estado["dentro"] = True; s = s[i + 2:]
            estado["buf"] = s
            if out:
                sys.stdout.write(out); sys.stdout.flush()
        return on_token

    def _carita(self, control) -> str:
        acts = [v for k, v in control if k == "act"]
        if not acts:
            return CARITAS["neutral"]
        return CARITAS.get(str(acts[-1].get("emotion", "neutral")), CARITAS["neutral"])

    # ── Un turno ─────────────────────────────────────────────────────────────────
    def responder(self, texto: str):
        c = self.c
        # memoria por comando ("recuerda que…")
        try:
            r = self.memoria.procesar_mensaje_usuario(texto)
        except Exception:
            r = None
        if r:
            print(f"{c['cyan']}Lune {c['yellow']}:D{c['reset']}  {r}\n"); return
        # herramienta directa ("abre youtube", "estado del pc")
        if self.tools is not None:
            try:
                tr = self.tools.detectar_y_ejecutar(texto)
            except Exception:
                tr = None
            if tr:
                cara = ":D" if tr.ok else ">:("
                print(f"{c['cyan']}Lune {c['yellow']}{cara}{c['reset']}  {tr.mensaje}\n"); return

        sys.stdout.write(f"{c['cyan']}Lune{c['reset']}  "); sys.stdout.flush()
        on_token = self._imprimir_stream()
        try:
            respuesta = asyncio.run(self.ai.chat(texto, self._system_prompt(),
                                                 provider=self.provider, on_token=on_token))
        except Exception as e:
            print(f"\n{c['red']}(no pude responder: {e}){c['reset']}\n"); return
        hablable, control = marcadores.separar(respuesta or "")
        print(f"  {c['yellow']}{self._carita(control)}{c['reset']}\n")
        try:
            self.memoria.procesar_respuesta_lune(respuesta or "")
        except Exception:
            pass

    # ── Comandos ─────────────────────────────────────────────────────────────────
    def comando(self, linea: str) -> bool:
        """Devuelve True si hay que salir."""
        c = self.c
        partes = linea.strip().split(maxsplit=1)
        cmd, arg = partes[0].lower(), (partes[1] if len(partes) > 1 else "")
        if cmd == "/salir":
            return True
        if cmd == "/ayuda":
            print(__doc__.split("Comandos:")[1] if "Comandos:" in __doc__ else "")
        elif cmd == "/memoria":
            print(self.memoria._cmd_listar(), "\n")
        elif cmd == "/olvida":
            print(self.memoria._cmd_olvida(arg) if arg else "¿Olvidar qué? /olvida <texto o id>", "\n")
        elif cmd == "/nube":
            self.provider = "openrouter"; print("Ahora respondo desde la nube (OpenRouter).\n")
        elif cmd == "/local":
            self.provider = "ollama"; print(f"Ahora respondo en local ({datos.ollama_model() or 'sin modelo'}).\n")
        elif cmd == "/personaje":
            if arg:
                try:
                    personajes.set_activo(arg); print(f"Personaje activo: {arg}\n")
                except Exception as e:
                    print(f"No pude cambiar de personaje: {e}\n")
            else:
                print("Personajes:", ", ".join(p.get("nombre", "") for p in personajes.listar()), "\n")
        elif cmd == "/limpiar":
            self.ai.clear_history(); os.system("cls" if os.name == "nt" else "clear")
        else:
            print(f"{c['dim']}Comando desconocido. /ayuda{c['reset']}\n")
        return False

    # ── Bucle ────────────────────────────────────────────────────────────────────
    def correr(self) -> int:
        c = self.c
        nombre = personajes.get_activo().get("nombre", "Lune")
        modo = f"local · {datos.ollama_model()}" if self.provider == "ollama" else "nube · OpenRouter"
        print(f"{c['bold']}{c['cyan']}月 {nombre} — modo patata{c['reset']} {c['dim']}({modo}){c['reset']}")
        print(f"{c['dim']}Solo texto. Caritas en vez de mascota. /ayuda para los comandos, /salir para irte.{c['reset']}\n")
        print(f"{c['cyan']}Lune {c['yellow']}o/{c['reset']}  Lune en línea. Dime qué necesitas.\n")
        while True:
            try:
                linea = input(f"{c['bold']}tú >{c['reset']} ").strip()
            except (EOFError, KeyboardInterrupt):
                print(); break
            if not linea:
                continue
            if linea.startswith("/"):
                if self.comando(linea):
                    break
                continue
            self.responder(linea)
        print(f"{c['cyan']}Lune {c['yellow']}o/{c['reset']}  Hasta luego.")
        return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    return Patata(color="--sin-color" not in argv).correr()


if __name__ == "__main__":
    raise SystemExit(main())
