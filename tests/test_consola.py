"""
Tests de nucleo/consola: la consola de patata con un único despachador de
entrada, avisos que no rompen el prompt y el lock compartido con el streaming.
Todo con stdout, stdin, teclado y API de Windows falsos: sin consola real.
"""
import ctypes
import io
import queue
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo import consola as C  # noqa: E402
from nucleo.consola import BORRAR_LINEA, SUBIR_Y_BORRAR, ConsolaAsincrona  # noqa: E402


# ── Falsos ───────────────────────────────────────────────────────────────────────
class ApiFalsa:
    def __init__(self):
        self.titulos, self.parpadeos = [], []

    def habilitar_vt(self):
        return True

    def es_consola_entrada(self):
        return False

    def titulo(self, texto):
        self.titulos.append(texto)
        return True

    def parpadear(self, veces=3, hasta_foco=True):
        self.parpadeos.append((veces, hasta_foco))
        return True

    def leer_tecla(self):
        return ""


class EntradaBloqueante:
    """stdin cuyo readline() espera a que el test le dé una línea (None = fin)."""

    def __init__(self):
        self.q = queue.Queue()

    def put(self, s):
        self.q.put(s)

    def readline(self):
        s = self.q.get()
        return "" if s is None else s


def esperar(cond, t=3.0):
    fin = time.monotonic() + t
    while time.monotonic() < fin:
        if cond():
            return True
        time.sleep(0.005)
    return cond()


@pytest.fixture
def crear():
    """Fábrica de consolas de prueba; al acabar suelta los hilos lectores."""
    creadas = []

    def _crear(modo="lineas", prompt="tú > ", ancho=80, ansi=True):
        out = io.StringIO()
        api = ApiFalsa()
        if modo == "teclas":
            teclas = queue.Queue()
            c = ConsolaAsincrona(prompt, stdout=out, leer_tecla=teclas.get, api=api, ansi=ansi, ancho=ancho)
            c.entrada = teclas
            creadas.append(lambda: teclas.put(""))
        else:
            ent = EntradaBloqueante()
            c = ConsolaAsincrona(prompt, stdout=out, stdin=ent, api=api, ansi=ansi, ancho=ancho)
            c.entrada = ent
            creadas.append(lambda: ent.put(None))
        c.out, c.api_falsa = out, api
        return c
    yield _crear
    for soltar in creadas:
        soltar()


def teclear(c, texto):
    for ch in texto:
        c.entrada.put(ch)


def en_hilo(fn, *args):
    caja = {}

    def correr():
        try:
            caja["r"] = fn(*args)
        except BaseException as e:          # noqa: BLE001 - el test mira qué salió
            caja["e"] = e
    h = threading.Thread(target=correr, daemon=True)
    h.start()
    h.caja = caja
    return h


# ── aviso ────────────────────────────────────────────────────────────────────────
def test_aviso_sin_nada_en_pantalla_borra_la_linea_e_imprime(crear):
    c = crear()
    c.aviso("hola")
    assert c.out.getvalue() == "\r\033[2Khola\n"


def test_aviso_redibuja_el_prompt_con_lo_ya_escrito(crear):
    c = crear("teclas")
    h = en_hilo(c.leer_linea)
    assert esperar(lambda: c.out.getvalue().endswith("tú > "))
    teclear(c, "ho")
    assert esperar(lambda: c.out.getvalue().endswith("tú > ho"))
    pos = len(c.out.getvalue())
    c.aviso("⏰ Alarma: sacar la ropa")
    assert c.out.getvalue()[pos:] == BORRAR_LINEA + "⏰ Alarma: sacar la ropa\ntú > ho"
    teclear(c, "la\r")
    h.join(3)
    assert h.caja["r"] == "hola"
    assert c.out.getvalue().endswith("tú > hola\n")


def test_aviso_en_modo_lineas_redibuja_el_prompt(crear):
    c = crear("lineas")
    h = en_hilo(c.leer_linea)
    assert esperar(lambda: c.out.getvalue().endswith("tú > "))
    pos = len(c.out.getvalue())
    c.aviso("aviso")
    assert c.out.getvalue()[pos:] == BORRAR_LINEA + "aviso\ntú > "
    c.entrada.put("hola\n")
    h.join(3)
    assert h.caja["r"] == "hola"


def test_aviso_durante_el_streaming_repone_la_frase_a_medias(crear):
    c = crear()
    c.escribir("Lune  Hola, qu")
    pos = len(c.out.getvalue())
    c.aviso("⏰")
    assert c.out.getvalue()[pos:] == BORRAR_LINEA + "⏰\nLune  Hola, qu"
    c.escribir("é tal\n")
    assert c.out.getvalue().endswith("Lune  Hola, qué tal\n")
    pos = len(c.out.getvalue())
    c.aviso("otro")
    assert c.out.getvalue()[pos:] == BORRAR_LINEA + "otro\n"


def test_aviso_borra_todas_las_filas_de_una_linea_que_da_la_vuelta(crear):
    c = crear(ancho=10)
    c.escribir("a" * 25)                      # 3 filas de 10 columnas
    pos = len(c.out.getvalue())
    c.aviso("X")
    assert c.out.getvalue()[pos:] == BORRAR_LINEA + SUBIR_Y_BORRAR * 2 + "X\n" + "a" * 25


def test_prompt_con_colores_ocupa_lo_visible(crear):
    c = crear("teclas", prompt="\033[1mtú >\033[0m ", ancho=10)
    h = en_hilo(c.leer_linea)
    teclear(c, "abcd")                        # 5 + 4 = 9 columnas: una fila
    assert esperar(lambda: c.out.getvalue().endswith("abcd"))
    pos = len(c.out.getvalue())
    c.aviso("X")
    assert c.out.getvalue()[pos:].startswith(BORRAR_LINEA + "X\n")
    teclear(c, "ef")                          # 11 columnas: dos filas
    assert esperar(lambda: c.out.getvalue().endswith("ef"))
    pos = len(c.out.getvalue())
    c.aviso("Y")
    assert c.out.getvalue()[pos:].startswith(BORRAR_LINEA + SUBIR_Y_BORRAR + "Y\n")
    teclear(c, "\r")
    h.join(3)
    assert h.caja["r"] == "abcdef"


def test_sin_ansi_no_emite_secuencias(crear):
    c = crear(ansi=False)
    c.escribir("Lune  a medias")
    c.aviso("aviso")
    assert "\033" not in c.out.getvalue()
    assert c.out.getvalue() == "Lune  a medias\naviso\n"


def test_ancho_visible():
    assert C.ancho_visible("\033[1mtú >\033[0m ") == 5
    assert C.ancho_visible("日本") == 4
    assert C.ancho_visible("é") == 1                # e + tilde combinante
    assert C.ancho_visible("a\tb") == 9
    assert C.ancho_visible("\033]0;título\a") == 0


# ── Un solo despachador: reclamos y chat ─────────────────────────────────────────
def test_reclamar_desvia_solo_la_siguiente_linea(crear):
    c = crear()
    recibidas = []
    c.reclamar(recibidas.append)
    h = en_hilo(c.leer_linea)
    c.entrada.put("s\n")
    c.entrada.put("hola\n")
    h.join(3)
    assert recibidas == ["s"]
    assert h.caja["r"] == "hola"
    assert not c.reclamada


def test_reclamos_en_orden_de_llegada(crear):
    c = crear()
    a, b = [], []
    c.reclamar(a.append)
    c.reclamar(b.append)
    c.entrada.put("1\n")
    c.entrada.put("2\n")
    assert esperar(lambda: a == ["1"] and b == ["2"])


def test_reclamo_que_devuelve_false_deja_pasar_la_linea_y_sigue_esperando(crear):
    c = crear()
    vistas = []

    def solo_enter(linea):
        vistas.append(linea)
        return linea == ""                    # la alarma solo se apaga con Enter en vacío
    c.reclamar(solo_enter, prompt="Enter apaga > ")
    h = en_hilo(c.leer_linea)
    c.entrada.put("hola\n")
    h.join(3)
    assert h.caja["r"] == "hola"              # fue al chat
    assert c.reclamada
    c.entrada.put("\n")
    assert esperar(lambda: vistas == ["hola", ""])
    assert esperar(lambda: not c.reclamada)


def test_cancelar_un_reclamo(crear):
    c = crear()
    vistas = []
    cancelar = c.reclamar(vistas.append)
    cancelar()
    h = en_hilo(c.leer_linea)
    c.entrada.put("hola\n")
    h.join(3)
    assert h.caja["r"] == "hola" and vistas == []


def test_el_prompt_del_reclamo_sustituye_al_normal(crear):
    c = crear("teclas")
    h = en_hilo(c.leer_linea)
    assert esperar(lambda: c.out.getvalue().endswith("tú > "))
    vistas = []
    pos = len(c.out.getvalue())
    c.reclamar(vistas.append, prompt="alarma > ")
    assert c.out.getvalue()[pos:] == BORRAR_LINEA + "alarma > "
    teclear(c, "\r")
    assert esperar(lambda: vistas == [""])
    assert esperar(lambda: c.out.getvalue().endswith("alarma > \ntú > "))
    teclear(c, "hola\r")
    h.join(3)
    assert h.caja["r"] == "hola"


def test_preguntar_recibe_la_linea(crear):
    c = crear("teclas")
    h = en_hilo(c.preguntar, "¿Lo hago? (s/N) ", 5)
    assert esperar(lambda: c.out.getvalue().endswith("¿Lo hago? (s/N) "))
    teclear(c, "s\r")
    h.join(3)
    assert h.caja["r"] == "s"
    assert c.out.getvalue().endswith("¿Lo hago? (s/N) s\n")


def test_preguntar_caduca_y_la_linea_vuelve_al_chat(crear):
    c = crear()
    t0 = time.monotonic()
    assert c.preguntar("¿Seguro? ", timeout=0.3) is None
    assert time.monotonic() - t0 < 2
    assert not c.reclamada
    h = en_hilo(c.leer_linea)
    c.entrada.put("hola\n")
    h.join(3)
    assert h.caja["r"] == "hola"


def test_preguntar_desde_el_hilo_lector_es_error(crear):
    c = crear()
    errores = []

    def fn(linea):
        try:
            c.preguntar("x ")
        except RuntimeError as e:
            errores.append(e)
    c.reclamar(fn)
    c.entrada.put("a\n")
    assert esperar(lambda: len(errores) == 1)


def test_escribir_con_una_pregunta_en_pantalla_sale_encima(crear):
    c = crear("teclas")
    h = en_hilo(c.preguntar, "¿Lo hago? ", 5)
    assert esperar(lambda: c.out.getvalue().endswith("¿Lo hago? "))
    pos = len(c.out.getvalue())
    c.escribir("Lune  hola\n")
    assert c.out.getvalue()[pos:] == BORRAR_LINEA + "Lune  hola\n¿Lo hago? "
    teclear(c, "n\r")
    h.join(3)
    assert h.caja["r"] == "n"


# ── Teclado ──────────────────────────────────────────────────────────────────────
def test_lo_tecleado_sin_prompt_no_se_cruza_y_aparece_al_leerlo(crear):
    c = crear("teclas")
    c.iniciar()
    c.escribir("Lune  respondiendo…")
    teclear(c, "hi\r")                        # se escribe mientras Lune habla
    assert esperar(lambda: len(c._cola_chat) == 1)
    assert c.out.getvalue() == "Lune  respondiendo…"   # nada cruzado con su texto
    c.escribir("\n")
    assert c.leer_linea() == "hi"
    assert c.out.getvalue().endswith("\n" + BORRAR_LINEA + "tú > hi\n")


def test_retroceso_y_esc(crear):
    c = crear("teclas")
    h = en_hilo(c.leer_linea)
    teclear(c, "abc")
    assert esperar(lambda: c.out.getvalue().endswith("abc"))
    teclear(c, "\x08")
    assert esperar(lambda: c.out.getvalue().endswith(BORRAR_LINEA + "tú > ab"))
    teclear(c, "\x1b")
    assert esperar(lambda: c.out.getvalue().endswith(BORRAR_LINEA + "tú > "))
    teclear(c, "z\r")
    h.join(3)
    assert h.caja["r"] == "z"


def test_historial_con_flechas(crear):
    c = crear("teclas")
    h = en_hilo(c.leer_linea)
    teclear(c, "uno\r")
    h.join(3)
    h = en_hilo(c.leer_linea)
    c.entrada.put(C.TECLA_ARRIBA)
    assert esperar(lambda: c.out.getvalue().endswith("tú > uno"))
    c.entrada.put(C.TECLA_ABAJO)
    assert esperar(lambda: c.out.getvalue().endswith(BORRAR_LINEA + "tú > "))
    c.entrada.put(C.TECLA_ARRIBA)
    teclear(c, "s\r")
    h.join(3)
    assert h.caja["r"] == "unos"


def test_crlf_pegado_es_un_solo_enter(crear):
    c = crear("teclas")
    h = en_hilo(c.leer_linea)
    teclear(c, "a\r\n")
    h.join(3)
    assert h.caja["r"] == "a"
    time.sleep(0.05)
    assert len(c._cola_chat) == 0


# ── Fin de la entrada, Ctrl+C y el lock ──────────────────────────────────────────
def test_fin_de_la_entrada_lanza_eoferror(crear):
    c = ConsolaAsincrona("> ", stdout=io.StringIO(), stdin=io.StringIO("hola\n"), api=ApiFalsa(), ansi=True)
    assert c.leer_linea() == "hola"
    with pytest.raises(EOFError):
        c.leer_linea()
    assert c.preguntar("¿? ", timeout=1) is None


def test_ctrl_z_en_vacio_es_fin(crear):
    c = crear("teclas")
    teclear(c, "\x1a")
    with pytest.raises(EOFError):
        c.leer_linea()


def test_detener_suelta_a_quien_espera(crear):
    c = crear()
    h = en_hilo(c.leer_linea)
    assert esperar(lambda: c.out.getvalue().endswith("tú > "))
    c.detener()
    h.join(3)
    assert isinstance(h.caja.get("e"), EOFError)


def test_el_lock_es_reentrante_para_el_streaming(crear):
    c = crear()

    def on_token():
        with c.lock:                          # como hará el on_token de patata
            c.escribir("tok")
            c.aviso("dentro")
    h = en_hilo(on_token)
    h.join(3)
    assert not h.is_alive()


def test_el_aviso_espera_al_streaming(crear):
    """El aviso usa el MISMO lock que el streaming: no se mete a mitad de un token."""
    c = crear()
    with c.lock:
        c.escribir("Lune  hol")
        h = en_hilo(c.aviso, "⏰")
        time.sleep(0.1)
        assert "⏰" not in c.out.getvalue()
        c.escribir("a")
    h.join(3)
    assert c.out.getvalue().endswith(BORRAR_LINEA + "⏰\nLune  hola")


def test_imprimir_como_print(crear):
    c = crear()
    c.imprimir("a", 1, sep="-", end="!\n")
    assert c.out.getvalue() == "a-1!\n"


# ── Título y parpadeo ────────────────────────────────────────────────────────────
def test_titulo_y_parpadear_usan_la_api(crear):
    c = crear()
    assert c.titulo("Lune :D\x07\n")
    assert c.api_falsa.titulos == ["Lune :D"]            # sin caracteres de control
    assert c.parpadear(5, hasta_foco=False)
    assert c.api_falsa.parpadeos == [(5, False)]
    c.parpadear(campana=True)
    assert c.out.getvalue().endswith("\a")


# ── Título por capas (cortes 5 y 6) ──────────────────────────────────────────────
def test_titulo_por_capas_con_prioridad_y_repintado(crear):
    c = crear()
    t = c.api_falsa.titulos
    c.titulo("Lune :) · patata")
    c.titulo_capa("baile", "ヽ(^o^)ﾉ ♪ 120 BPM", 20)
    assert t[-1] == "ヽ(^o^)ﾉ ♪ 120 BPM" and c.capa_titulo() == "baile"
    c.titulo_capa("salvapantallas", "(-_-) zzZ 23:41", 10)       # por debajo: no se ve
    assert t[-1] == "ヽ(^o^)ﾉ ♪ 120 BPM"
    c.titulo_capa("juego", "Lune · modo juego", 50)
    assert t[-1] == "Lune · modo juego"
    n = len(t)
    c.titulo_capa("baile", "┏(^o^)┛ ♪ 120 BPM", 20)               # cambia una de debajo: no repinta
    c.titulo("Lune :D · patata")                                  # el normal se guarda para luego
    assert len(t) == n
    c.titulo_capa("alarma", "⏰ Sacar la ropa", 60)
    assert t[-1] == "⏰ Sacar la ropa"
    c.titulo_capa("alarma", None)
    assert t[-1] == "Lune · modo juego"
    c.titulo_capa("juego", None)
    assert t[-1] == "┏(^o^)┛ ♪ 120 BPM"                          # el último texto del baile
    c.titulo_capa("baile", None)
    assert t[-1] == "(-_-) zzZ 23:41"
    c.titulo_capa("salvapantallas", None)
    assert t[-1] == "Lune :D · patata" and c.capa_titulo() is None
    n = len(t)
    assert c.titulo_capa("no_existe", None) is False and len(t) == n


def test_titulo_capa_mismo_texto_no_repinta_y_empate_gana_la_ultima(crear):
    c = crear()
    t = c.api_falsa.titulos
    c.titulo_capa("a", "uno", 20)
    c.titulo_capa("a", "uno", 20)
    assert t == ["uno"]
    c.titulo_capa("b", "dos", 20)
    assert t[-1] == "dos"
    c.titulo_capa("a", "uno bis", 20)                  # cambiar el texto no la sube
    assert t[-1] == "dos"
    c.titulo_capa("b", None)
    assert t[-1] == "uno bis"


def test_quitar_la_ultima_capa_sin_titulo_normal_repinta_el_de_por_defecto(crear):
    # MO6: sin titulo() previo (patata recién arrancada), quitar el salvapantallas no
    # deja congelado «(-_-) zzZ 23:41».
    from nucleo.consola import TITULO_DEFECTO
    c = crear()
    t = c.api_falsa.titulos
    c.titulo_capa("salvapantallas", "(-_-) zzZ 23:41", 10)
    c.titulo_capa("salvapantallas", None, 10)
    assert t == ["(-_-) zzZ 23:41", TITULO_DEFECTO] and c.capa_titulo() is None
    c.titulo_capa("baile", "ヽ(^o^)ﾉ ♪ Spotify · 124 BPM", 20)
    c.titulo_capa("baile", None, 20)
    assert t[-1] == TITULO_DEFECTO
    c.titulo("Lune :D · patata")
    c.titulo_capa("alarma", "⏰ Pizza", 60)
    c.titulo_capa("alarma", None, 60)
    assert t[-1] == "Lune :D · patata"                          # con título normal, ese
    otra = ConsolaAsincrona("> ", stdout=io.StringIO(), stdin=io.StringIO(""), api=ApiFalsa(), ansi=False,
                            titulo_defecto="Lune · patata")
    otra.titulo_capa("x", "capa", 1)
    otra.titulo_capa("x", None, 1)
    assert otra._api.titulos == ["capa", "Lune · patata"]


# ── Reclamos con prioridad y prompt que cambia (cortes 5 y 6) ────────────────────
def test_reclamo_de_mas_prioridad_se_queda_antes_la_linea(crear):
    c = crear()
    baile, alarma = [], []
    c.reclamar(baile.append, prompt="♪ baile > ", prioridad=-10)
    c.reclamar(alarma.append, prompt="alarma > ")
    assert c._texto_prompt() == "alarma > "
    c.entrada.put("\n")
    assert esperar(lambda: alarma == [""])
    assert baile == [] and c._texto_prompt() == "♪ baile > "
    c.entrada.put("\n")
    assert esperar(lambda: baile == [""])


def test_cambiar_prompt_repinta_la_linea_viva_sin_perder_lo_tecleado(crear):
    c = crear("teclas")
    h = en_hilo(c.leer_linea)
    assert esperar(lambda: c.out.getvalue().endswith("tú > "))
    vistas = []
    cancelar = c.reclamar(lambda l: vistas.append(l) if l == "" else False,
                          prompt="♪ \\o/ 120 BPM ", prioridad=-10)
    assert esperar(lambda: c.out.getvalue().endswith("♪ \\o/ 120 BPM "))
    teclear(c, "ho")
    assert esperar(lambda: c.out.getvalue().endswith("♪ \\o/ 120 BPM ho"))
    pos = len(c.out.getvalue())
    assert cancelar.cambiar_prompt("♪ |o| 121 BPM ") is True
    assert c.out.getvalue()[pos:] == BORRAR_LINEA + "♪ |o| 121 BPM ho"
    pos = len(c.out.getvalue())
    cancelar.cambiar_prompt("♪ |o| 121 BPM ")                  # el mismo: no repinta
    assert c.out.getvalue()[pos:] == ""
    teclear(c, "la\r")                                         # con texto: sigue al chat
    h.join(3)
    assert h.caja["r"] == "hola" and vistas == [] and c.reclamada
    cancelar()
    assert cancelar.cambiar_prompt("otro") is False
    assert not c.reclamada


def test_cambiar_prompt_de_un_reclamo_que_no_se_ve_no_repinta(crear):
    c = crear("teclas")
    h = en_hilo(c.leer_linea)
    c.reclamar(lambda l: None, prompt="alarma > ")
    abajo = c.reclamar(lambda l: None, prompt="baile > ", prioridad=-10)
    assert esperar(lambda: c.out.getvalue().endswith("alarma > "))
    pos = len(c.out.getvalue())
    abajo.cambiar_prompt("baile 2 > ")
    assert c.out.getvalue()[pos:] == ""
    teclear(c, "\r")                                           # se lo queda la alarma…
    assert esperar(lambda: c.out.getvalue().endswith("baile 2 > "))   # …y se ve el del baile
    c.detener()
    h.join(3)


def test_ansi_y_columnas_publicos(crear):
    c = crear(ancho=57, ansi=True)
    assert c.ansi is True and c.columnas() == 57
    assert crear(ansi=False).ansi is False


# ── ApiConsolaWin32 con DLLs falsas ──────────────────────────────────────────────
class Kernel32Falso:
    def __init__(self, modo=0x3, consola=True, hwnd=1234, registros=()):
        self.modo, self.consola, self.hwnd = modo, consola, hwnd
        self.puesto, self.titulos = None, []
        self.registros = list(registros)

    def GetStdHandle(self, n):
        return 7 if n == C.STD_OUTPUT_HANDLE else 8

    def GetConsoleMode(self, h, ref):
        if not self.consola:
            return 0
        ref._obj.value = self.modo
        return 1

    def SetConsoleMode(self, h, modo):
        self.puesto = modo
        return 1

    def SetConsoleTitleW(self, t):
        self.titulos.append(t)
        return 1

    def GetConsoleWindow(self):
        return self.hwnd

    def ReadConsoleInputW(self, h, ref, n, leidos):
        if not self.registros:
            return 0
        tipo, abajo, vk, ch, rep = self.registros.pop(0)
        r = ref._obj
        r.EventType = tipo
        ke = r.Event.KeyEvent
        ke.bKeyDown, ke.wVirtualKeyCode, ke.uChar, ke.wRepeatCount = abajo, vk, ch, rep
        leidos._obj.value = 1
        return 1


class User32Falso:
    def __init__(self):
        self.info = None

    def FlashWindowEx(self, ref):
        i = ref._obj
        self.info = (i.cbSize, i.hwnd, i.dwFlags, i.uCount)
        return 0


solo_windows = pytest.mark.skipif(sys.platform != "win32", reason="API de consola de Windows")


@solo_windows
def test_api_habilita_vt():
    k = Kernel32Falso(modo=0x3)
    assert C.ApiConsolaWin32(k, User32Falso()).habilitar_vt()
    assert k.puesto == 0x3 | C.ENABLE_VIRTUAL_TERMINAL_PROCESSING
    k = Kernel32Falso(modo=0x7)                           # ya estaba
    assert C.ApiConsolaWin32(k, User32Falso()).habilitar_vt() and k.puesto is None
    k = Kernel32Falso(consola=False)                      # salida redirigida
    api = C.ApiConsolaWin32(k, User32Falso())
    assert not api.habilitar_vt() and not api.es_consola_entrada()


@solo_windows
def test_api_titulo_y_parpadeo():
    k, u = Kernel32Falso(hwnd=4321), User32Falso()
    api = C.ApiConsolaWin32(k, u)
    assert api.titulo("Lune ♪") and k.titulos == ["Lune ♪"]
    assert api.parpadear(3, hasta_foco=True)
    assert u.info[1] == 4321
    assert u.info[2] == C.FLASHW_ALL | C.FLASHW_TIMERNOFG
    assert u.info[0] == ctypes.sizeof(C.FLASHWINFO)
    assert not C.ApiConsolaWin32(Kernel32Falso(hwnd=0), User32Falso()).parpadear()


@solo_windows
def test_api_leer_tecla():
    alta, baja = "\ud83c", "\udf19"                       # 🌙 en dos mitades UTF-16
    k = Kernel32Falso(registros=[
        (2, 0, 0, "\x00", 1),                             # evento de ratón: se ignora
        (1, 0, 0x41, "a", 1),                             # soltar una tecla: se ignora
        (1, 1, 0x41, "a", 1),
        (1, 1, 0x10, "\x00", 1),                          # Mayús sola: nada
        (1, 1, C.VK_UP, "\x00", 1),
        (1, 1, 0, alta, 1), (1, 1, 0, baja, 1),
        (1, 1, 0x42, "b", 3),                             # tecla mantenida
        (1, 0, C.VK_MENU, "ñ", 1),                        # Alt+164 llega al soltar Alt
    ])
    api = C.ApiConsolaWin32(k, User32Falso())
    assert [api.leer_tecla() for _ in range(6)] == ["a", C.TECLA_ARRIBA, "🌙", "bbb", "ñ", ""]
