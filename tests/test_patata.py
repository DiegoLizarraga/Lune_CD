"""
Tests del modo patata (patata.py) con el Ejecutor del corte 2.

Consola de verdad (nucleo/consola.ConsolaAsincrona) con stdin, stdout y API de
Windows falsos; modelo, memoria y voz simulados; datos.json en una carpeta
temporal. Se comprueba que un <|CALL|> que pide permiso se pregunta por la
consola («¿Lo hago? [s/N]»), que la siguiente línea es la respuesta, que sin
respuesta caduca, que el formato antiguo no ejecuta nada y los comandos nuevos.
"""
import io
import queue
import shutil
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import patata  # noqa: E402
from nucleo import datos  # noqa: E402
from nucleo.config import Config  # noqa: E402
from nucleo.consola import ConsolaAsincrona  # noqa: E402
from servicios.tools import ToolManager  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent


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
        self.parpadeos.append(veces)
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


class ProvFalso:
    cancel_flag = False
    url = "http://localhost:11434"


class AIFalsa:
    def __init__(self, texto="Hola <|ACT {\"emotion\":\"happy\"}|>"):
        self.texto = texto
        self.system = ""
        self.providers = {"ollama": ProvFalso(), "openrouter": ProvFalso()}
        self.limpiado = 0
        self.recargas = 0
        self.liberado = 0

    async def chat(self, message, system_prompt="", provider=None, on_token=None, imagenes=None):
        self.system = system_prompt
        for i in range(0, len(self.texto), 5):
            if on_token:
                on_token(self.texto[i:i + 5])
        return self.texto

    def clear_history(self):
        self.limpiado += 1

    def reload_provider(self):
        self.recargas += 1

    def descargar_modelo(self):
        self.liberado += 1
        return True

    def probar_compat(self):
        return {"ok": True, "mensaje": "Responde", "modelos": ["m1", {"id": "m2"}], "ms": 12}


class MemFalsa:
    def __init__(self):
        self.guardado = []

    def procesar_mensaje_usuario(self, t):
        return None

    def obtener_contexto_para_prompt(self):
        return ""

    def procesar_respuesta_lune(self, t):
        self.guardado.append(t)


class TimerFalso:
    def __init__(self, fn):
        self.fn = fn
        self.cancelado = False

    def cancel(self):
        self.cancelado = True


def esperar(cond, t=3.0):
    fin = time.monotonic() + t
    while time.monotonic() < fin:
        if cond():
            return True
        time.sleep(0.01)
    return cond()


@pytest.fixture(autouse=True)
def _sin_red_de_voces(tmp_path, monkeypatch):
    """/voces no descarga la lista de edge-tts ni escribe la caché del repo."""
    from servicios import voces
    monkeypatch.setattr(voces, "RUTA_CACHE", tmp_path / "cache" / "voces_edge.json")
    monkeypatch.setattr(voces, "_ultimo_fallo", None)

    def sin_red(cargar=None):
        raise OSError("sin red en los tests")
    monkeypatch.setattr(voces, "_descargar", sin_red)
    yield
    voces.esperar_actualizacion(5)


@pytest.fixture
def datos_tmp(monkeypatch, tmp_path):
    ruta = tmp_path / "datos.json"
    shutil.copyfile(RAIZ / "datos.example.json", ruta)
    monkeypatch.setattr(datos, "_PATH", ruta)
    datos.invalidar()
    yield ruta
    datos.invalidar()


@pytest.fixture
def crear(tmp_path, datos_tmp):
    """Patata con consola de prueba; al acabar suelta el hilo lector."""
    creadas = []

    def _crear(texto="Hola", *, tools=None, voice=None, **kw):
        entrada = EntradaBloqueante()
        out = io.StringIO()
        consola = ConsolaAsincrona("tú > ", stdout=out, stdin=entrada, api=ApiFalsa(), ansi=False)
        cfg = Config(str(tmp_path / "config.json"))
        tm = tools if tools is not None else ToolManager()
        timers = []
        # Cortes 5/6 aparte (sus hilos: alarmas.json, audio, inactividad): tests/test_anfitriones_c56.py
        for pieza in ("alarmas", "baile", "salvapantallas"):
            kw.setdefault(pieza, None)
        p = patata.Patata(color=False, consola=consola, config=cfg, ai=AIFalsa(texto),
                          memoria=MemFalsa(), voice=voice, tools=tm, audit_path=None,
                          programar=lambda s, fn: timers.append(TimerFalso(fn)) or timers[-1],
                          **kw)
        p.entrada, p.out, p.timers = entrada, out, timers
        creadas.append(p)
        return p

    yield _crear
    for p in creadas:
        p.entrada.put(None)
        p.cerrar()


def _tm_con_lanzar():
    tm = ToolManager()
    lanzadas = []
    tm.registrar_handler("lanzar_app", lambda a, c: lanzadas.append((a["app"], c.get("origen")))
                         or f"Abriendo {a['app']}")
    return tm, lanzadas


# ── Un turno con acciones ────────────────────────────────────────────────────────

def test_call_que_pide_permiso_se_aprueba_con_la_siguiente_linea(crear):
    tm, lanzadas = _tm_con_lanzar()
    p = crear('Te la abro <|ACT {"emotion":"happy"}|> <|CALL ["lanzar_app", {"app": "calc"}]|>',
              tools=tm)
    p.responder("hola")
    salida = p.out.getvalue()
    assert "CALL" not in salida and "Te la abro" in salida and ":D" in salida
    assert "Abrir la aplicación «calc»" in salida and "Contesta s o n" in salida
    assert lanzadas == [] and p.consola.reclamada          # esperando al humano
    assert p.ejecutor.pendientes()[0]["herramienta"] == "lanzar_app"

    p.entrada.put("s\n")                                   # la siguiente línea responde
    assert esperar(lambda: lanzadas == [("calc", "usuario")])
    assert esperar(lambda: "✓ Abriendo calc" in p.out.getvalue())
    assert not p.consola.reclamada and not p._reclamos
    assert p.ai.system and "<|CALL" in p.ai.system and "ABRIR_URL" not in p.ai.system


def test_cualquier_otra_respuesta_es_no(crear):
    tm, lanzadas = _tm_con_lanzar()
    p = crear('Vale. <|CALL ["lanzar_app", {"app": "calc"}]|>', tools=tm)
    p.responder("hola")
    p.entrada.put("abre la calculadora ya\n")
    assert esperar(lambda: "No lo hice" in p.out.getvalue())
    assert lanzadas == []


def test_sin_respuesta_caduca_y_la_linea_vuelve_al_chat(crear):
    tm, lanzadas = _tm_con_lanzar()
    p = crear('Vale. <|CALL ["lanzar_app", {"app": "calc"}]|>', tools=tm)
    p.responder("hola")
    assert p.consola.reclamada and len(p.timers) == 1
    p.timers[0].fn()                                       # pasan los 60 s
    assert esperar(lambda: "Nadie respondió" in p.out.getvalue())
    assert esperar(lambda: not p.consola.reclamada)
    assert lanzadas == [] and not p._reclamos


def test_el_formato_antiguo_no_ejecuta_nada(crear, monkeypatch):
    tm = ToolManager()
    abiertas = []
    monkeypatch.setattr("servicios.tools.webbrowser.open", lambda u, *a, **k: abiertas.append(u))
    p = crear("Te la abro.\nABRIR_URL:https://malo.example\nTOOL:lanzar_app:calc", tools=tm)
    p.responder("hola")
    time.sleep(0.05)
    assert abiertas == [] and not p.consola.reclamada
    assert p.memoria.guardado and "ABRIR_URL" not in p.memoria.guardado[0]


def test_lectura_va_sola_y_el_resultado_se_avisa(crear):
    tm = ToolManager()
    tm.registrar_handler("sistema_info", lambda a, c: "CPU 3% | RAM 40%")
    p = crear('Mira: <|CALL ["sistema_info", {}]|>', tools=tm)
    p.responder("hola")
    assert "✓ CPU 3% | RAM 40%" in p.out.getvalue() and not p.consola.reclamada


def test_sin_acciones_ia_no_se_ofrecen_ni_se_ejecutan(crear):
    tm, lanzadas = _tm_con_lanzar()
    p = crear('Vale. <|CALL ["lanzar_app", {"app": "calc"}]|>', tools=tm)
    p.config.set_feature("acciones_ia", False)
    p.responder("hola")
    assert "<|CALL" not in p.ai.system and not p.consola.reclamada and lanzadas == []
    assert "CALL" not in p.out.getvalue()


def test_respuesta_sin_streaming_se_imprime_igual(crear):
    p = crear("")
    p.ai.texto = "Proveedor 'x' no disponible"

    async def sin_tokens(message, system_prompt="", provider=None, on_token=None, imagenes=None):
        return p.ai.texto
    p.ai.chat = sin_tokens
    p.responder("hola")
    assert "Proveedor 'x' no disponible" in p.out.getvalue()


def test_la_voz_habla_por_tramos_si_esta_activada(crear):
    class VozFalsa:
        _enabled = True
        tramos = None

        def speak_segmentos(self, segmentos, **kw):
            self.tramos = list(segmentos)
            return True

        def cancelar(self):
            pass
    v = VozFalsa()
    p = crear('Hola <|ACT {"emotion":"happy"}|> ¿qué tal?', voice=v)
    p.responder("hola")
    assert v.tramos and any("qué tal" in t for _, t in v.tramos)


def test_nuevo_repone_el_presupuesto_y_cancela_lo_pendiente(crear):
    tm, lanzadas = _tm_con_lanzar()
    p = crear('Vale. <|CALL ["lanzar_app", {"app": "calc"}]|>', tools=tm)
    p.responder("hola")
    assert p.consola.reclamada
    p.comando("/nuevo")
    assert esperar(lambda: not p.consola.reclamada)
    assert p.ejecutor.pendientes() == [] and p.ejecutor.sesion.gastado == 0
    assert p.ai.limpiado == 1 and lanzadas == []


# ── Comandos ─────────────────────────────────────────────────────────────────────

def _cmd(p, linea):
    antes = len(p.out.getvalue())
    assert p.comando(linea) is False
    return p.out.getvalue()[antes:]


def test_ayuda_lista_los_comandos_nuevos(crear):
    p = crear()
    texto = _cmd(p, "/ayuda")
    for c in ("/voces", "/voz", "/proveedor", "/modelo", "/estado", "/temp", "/ctx",
              "/liberar", "/compat", "/nuevo", "/herramientas"):
        assert c in texto, c


def test_voces_y_voz(crear):
    p = crear()
    assert "es-MX-DaliaNeural" in _cmd(p, "/voces mexico")
    assert "No hay motor de voz" in _cmd(p, "/voz on")
    assert "Voz desactivada" in _cmd(p, "/voz")
    assert "No conozco la voz" in _cmd(p, "/voz es-XX-InventadaNeural")


def test_proveedor_y_modelo(crear):
    p = crear()
    assert "compat" in _cmd(p, "/proveedor compat") and p.provider in ("ollama", "openrouter")
    assert "Ahora respondo" in _cmd(p, "/proveedor nube") and p.provider == "openrouter"
    assert "No conozco" in _cmd(p, "/proveedor marte")
    _cmd(p, "/local")
    assert p.provider == "ollama"
    assert "Modelo de ollama: qwen2.5:7b" in _cmd(p, "/modelo qwen2.5:7b")
    assert datos.ollama_model() == "qwen2.5:7b" and p.ai.recargas >= 1
    assert "no es válido" in _cmd(p, "/modelo con espacios")


def test_temp_ctx_y_preset(crear):
    p = crear()
    assert "Temperatura: 0.3" in _cmd(p, "/temp 0,3")
    assert datos.parametros_muestreo()["temperatura"] == 0.3
    assert datos.preset_muestreo() == "personalizado"
    assert "va de 0" in _cmd(p, "/temp 5")
    assert "Preset preciso" in _cmd(p, "/temp preciso")
    assert datos.parametros_muestreo()["top_k"] == 40
    assert "16384 tokens" in _cmd(p, "/ctx 16k") and datos.ollama_num_ctx() == 16384
    assert "entre" in _cmd(p, "/ctx 12")


def test_compat_configurar_probar_y_apagar(crear):
    p = crear()
    assert "sin configurar" in _cmd(p, "/compat")
    assert "no válida" in _cmd(p, "/compat url file:///c:/x")
    assert "no válida" in _cmd(p, "/compat url http://user:clave@host/v1")
    assert "Úsala con /proveedor compat" in _cmd(p, "/compat url http://localhost:1234/v1/chat/completions")
    assert datos.compat_url() == "http://localhost:1234/v1"
    _cmd(p, "/compat modelo qwen-7b")
    assert datos.compat_model() == "qwen-7b"
    texto = _cmd(p, "/compat")
    assert "✓ Responde (12 ms)" in texto and "m1, m2" in texto
    p.ai.providers["compat"] = ProvFalso()
    _cmd(p, "/proveedor compat")
    assert p.provider == "compat"
    assert "apagada" in _cmd(p, "/compat off") and p.provider != "compat"
    assert datos.compat_url() == ""


def test_estado_liberar_y_herramientas(crear):
    tm, _ = _tm_con_lanzar()
    tm.conectar_voz(None, None)
    p = crear(tools=tm)
    estado = _cmd(p, "/estado")
    assert "Proveedor:" in estado and "temperatura" in estado and "gastado 0/20" in estado
    assert "salió de la memoria" in _cmd(p, "/liberar") and p.ai.liberado == 1
    herramientas = _cmd(p, "/herramientas")
    assert "lanzar_app" in herramientas and "(te pido permiso)" in herramientas
    assert "cambiar_voz" in herramientas


def test_helpers():
    assert patata.leer_ctx("8k") == 8192 and patata.leer_ctx("4096") == 4096
    assert patata.leer_ctx("100") is None and patata.leer_ctx("mucho") is None
    assert patata.url_compat_valida(" https://api.groq.com/openai/v1/ ") == "https://api.groq.com/openai/v1"
    assert patata.url_compat_valida("ftp://x") is None
    assert patata.url_compat_valida("http://a b") is None
    rlo = chr(0x202E)
    assert patata.una_linea("abre\nesto" + rlo + "exe.txt") == "abre ⏎ estoexe.txt"
    assert patata.una_linea("x" * 300, 10).endswith("…")


def test_caritas_siguen_igual():
    assert patata.CARITAS["happy"] == ":D" and patata.CARITAS["neutral"] == ":|"


def test_patata_no_importa_qt():
    import subprocess
    codigo = ("import sys; import patata; "
              "print(any(m.startswith('PyQt') for m in sys.modules))")
    r = subprocess.run([sys.executable, "-c", codigo], cwd=str(RAIZ), capture_output=True,
                       text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().endswith("False")


# ── Revisión cortes 2+3 (G3, G6, lo pedido con palabras, Ctrl+C tardío) ────────────

def test_personaje_inexistente_no_se_guarda_y_da_la_lista(crear):
    """G3: «/personaje Luen» se guardaba sin validar y luego la voz, las frases… del
    «activo» fallaban. Ahora no se toca nada y se responde con la lista."""
    p = crear()
    antes = datos.get_bot().get("personaje_default")
    salida = _cmd(p, "/personaje Luen")
    assert "No existe el personaje «Luen»" in salida and "Personajes: Lune" in salida
    datos.invalidar()
    assert datos.get_bot().get("personaje_default") == antes
    assert "Personaje activo: Lune" in _cmd(p, "/personaje lune")      # con su nombre guardado
    datos.invalidar()
    assert datos.get_bot()["personaje_default"] == "Lune"
    assert "Velocidad: +10%" in _cmd(p, "/voz velocidad 10")            # la voz ya lo encuentra


def test_set_activo_valida_en_todos_los_modos(datos_tmp):
    from nucleo import personajes
    with pytest.raises(ValueError, match="No existe el personaje"):
        personajes.set_activo("Nadie")
    with pytest.raises(ValueError):
        personajes.set_activo("   ")
    assert personajes.set_activo("LUNE") == "Lune"


def test_comandos_y_respuestas_s_n_cuentan_como_actividad(crear):
    """G6: la pausa del sueño se mide desde tu última línea (mensaje, comando o
    «s/n») o el fin de la última respuesta, lo más reciente."""
    reloj = {"t": 1000.0}
    tm, lanzadas = _tm_con_lanzar()
    p = crear('Va <|CALL ["lanzar_app", {"app": "calc"}]|>', tools=tm, reloj_sueno=lambda: reloj["t"])
    p.config.set("avatar", "dormir_min", 10)
    reloj["t"] += 11 * 60
    _cmd(p, "/estado")                                # un comando a los 11 min
    reloj["t"] += 5 * 60
    p.responder("hola")                               # 5 min después: no se había dormido
    assert "dormida" not in p.out.getvalue()
    reloj["t"] += 9 * 60
    p.entrada.put("s\n")                              # contestar «s» también cuenta
    assert esperar(lambda: lanzadas == [("calc", "usuario")])
    reloj["t"] += 9 * 60
    p.responder("otra")
    assert "dormida" not in p.out.getvalue()
    reloj["t"] += 11 * 60                             # ahora sí: 11 min sin nada
    p.responder("¿sigues?")
    assert "Lune se quedó dormida hace 1 min" in p.out.getvalue()


def test_la_pausa_cuenta_desde_el_fin_de_la_respuesta(crear):
    reloj = {"t": 1000.0}

    class AILenta(AIFalsa):
        async def chat(self, *a, **k):
            reloj["t"] += 8 * 60                      # una respuesta larguísima (8 min)
            return await super().chat(*a, **k)

    p = crear(reloj_sueno=lambda: reloj["t"])
    p.ai = AILenta("Hola")
    p.config.set("avatar", "dormir_min", 10)
    p.responder("cuéntame algo largo")
    reloj["t"] += 5 * 60                              # 13 min desde tu mensaje, 5 desde el final
    p.responder("gracias")
    assert "dormida" not in p.out.getvalue()


def test_lo_pedido_con_palabras_va_por_el_ejecutor(crear):
    """«lanza calc» ya no se ejecuta por su cuenta: va al Ejecutor (pregunta) y el
    modelo ni se entera."""
    tm, lanzadas = _tm_con_lanzar()
    p = crear("no debería hablar", tools=tm)
    p.responder("lanza calc")
    assert p.ai.system == "" and "no debería hablar" not in p.out.getvalue()
    assert lanzadas == [] and p.consola.reclamada
    p.entrada.put("s\n")
    assert esperar(lambda: lanzadas == [("calc", "usuario")])
    assert esperar(lambda: "✓ Abriendo calc" in p.out.getvalue())


def test_ctrl_c_fuera_del_stream_vuelve_al_prompt(crear):
    """Ctrl+C durante la voz, la memoria o las acciones (fuera de asyncio.run) salía
    con traceback; ahora corta eso y sigue."""
    import threading
    p = crear("Hola")
    llamadas = []

    def hablar(_texto):
        llamadas.append(1)
        if len(llamadas) == 1:
            raise KeyboardInterrupt
    p._hablar = hablar
    fin = {}
    h = threading.Thread(target=lambda: fin.setdefault("r", p.correr()), daemon=True)
    h.start()
    p.entrada.put("hola\n")
    assert esperar(lambda: "(interrumpido)" in p.out.getvalue())
    p.entrada.put("otra vez\n")
    assert esperar(lambda: len(llamadas) == 2)
    p.entrada.put("/salir\n")
    h.join(5)
    assert fin.get("r") == 0 and "Hasta luego" in p.out.getvalue()


def test_main_sale_sin_traceback_con_ctrl_c_al_arrancar(monkeypatch):
    def revienta(*a, **k):
        raise KeyboardInterrupt
    monkeypatch.setattr(patata, "Patata", revienta)
    sueltas = []
    inst = type("Inst", (), {"adquirir": lambda self: True, "escuchar": lambda self, fn: True,
                             "liberar": lambda self: sueltas.append(1)})()
    assert patata.main([], instancia=inst) == 130
    assert sueltas == [1]                                   # el mutex de instancia se suelta igual


# ── Revisión 4-5-6: título base desde el arranque y todo el ocio a la vez ──────────

def test_correr_pone_el_titulo_normal_al_empezar(crear):
    # MO6: sin haber chateado, al quitarse la última capa vuelve el título de patata
    # (no se queda «(-_-) zzZ 23:41»).
    import threading
    p = crear()
    t = p.consola._api.titulos
    hilo = threading.Thread(target=p.correr, daemon=True)
    hilo.start()
    assert esperar(lambda: bool(t))
    base = t[0]
    assert base.startswith("Lune ") and base.endswith("· patata")
    p.consola.titulo_capa("salvapantallas", "(-_-) zzZ 23:41", 10)
    p.consola.titulo_capa("salvapantallas", None, 10)
    assert t[-2:] == ["(-_-) zzZ 23:41", base]
    p.entrada.put("/salir\n")
    hilo.join(5)
    assert not hilo.is_alive()


def test_la_aprobacion_no_se_come_el_enter_de_una_alarma_que_suena(crear):
    # MO5 (lado patata): aunque la alarma reclamara con la misma prioridad (detrás),
    # el Enter en vacío con una alarma sonando no responde «no» a la aprobación.
    from types import SimpleNamespace
    tm, lanzadas = _tm_con_lanzar()
    p = crear('Vale. <|CALL ["lanzar_app", {"app": "calc"}]|>', tools=tm)
    p.alarmas = SimpleNamespace(aviso=SimpleNamespace(sonando=object()))
    p.responder("hola")
    alarma = []
    p.consola.reclamar(alarma.append, prompt="⏰ Enter apaga > ")
    p.entrada.put("\n")
    assert esperar(lambda: alarma == [""])
    assert p.ejecutor.pendientes() and lanzadas == [] and p._reclamos
    p.alarmas.aviso.sonando = None
    p.entrada.put("s\n")
    assert esperar(lambda: lanzadas == [("calc", "usuario")])


class _Mez:
    def cargar_wav(self, ruta):
        return b""

    def reproducir(self, *a, **k):
        return 1

    def detener(self, sid):
        pass

    def detener_canal(self, canal):
        pass


class _Mutex:
    es_dueno = True

    def adquirir(self):
        return True

    def liberar(self):
        pass


class _ApiInactiva:
    """GetLastInputInfo y compañía de mentira (servicios/win_entrada)."""

    def __init__(self):
        self.ultima = self.t = 1_000_000

    def inactivo(self, s):
        self.t = self.ultima + int(s * 1000)

    def tick(self):
        return self.t

    def ultima_entrada(self):
        return self.ultima

    def cursor(self):
        return (0, 0)

    def boton_izquierdo(self):
        return False

    def hay_xinput(self):
        return False

    def estado_mando(self, i):
        return None

    def estado_ejecucion(self):
        return 0


class _Juego:
    INTERVALO_S = 3600
    activo = False

    def detectando(self):
        return True

    def evaluar(self):
        return True, self.activo, "prueba"


class _Musica:
    on_cambio = on_pulso = on_sesiones = None

    def iniciar(self):
        pass

    def detener(self):
        pass

    def forzar_pulso(self, on):
        pass

    def pedir_sondeo(self):
        pass

    def reanudar_auto(self):
        pass

    def silenciar_hasta_silencio(self):
        pass


def test_alarma_baile_salvapantallas_juego_y_aprobacion_conviven(tmp_path, datos_tmp):
    """Todo el ocio de patata a la vez: capas del título (alarma 60 > juego 50 >
    baile 20 > salvapantallas 10 > el normal) y reclamos de la consola (el Enter es
    de la alarma aunque haya un «¿Lo hago?» pendiente; «s» responde a la aprobación;
    el Enter en vacío que queda para el baile)."""
    from nucleo.alarmas import Almacen, Disparo
    from servicios.alarmas_patata import AlarmasTerminal
    from servicios.baile_terminal import BaileTerminal
    from servicios.salvapantallas_terminal import SalvapantallasTerminal

    reloj = [100.0]
    entrada, out, api = EntradaBloqueante(), io.StringIO(), ApiFalsa()
    consola = ConsolaAsincrona("tú > ", stdout=out, stdin=entrada, api=api, ansi=True)
    cfg = Config(str(tmp_path / "config.json"))
    cfg.set("salvapantallas", "activo", True)
    tm, lanzadas = _tm_con_lanzar()
    alarmas = AlarmasTerminal(consola, cfg, almacen=Almacen(tmp_path / "alarmas.json"), mutex=_Mutex(),
                              mezclador=_Mez(), reloj=lambda: reloj[0], lanzar_sonido=lambda f: f())
    juego = _Juego()
    timers = []
    p = patata.Patata(color=False, consola=consola, config=cfg,
                      ai=AIFalsa('Vale. <|CALL ["lanzar_app", {"app": "calc"}]|>'), memoria=MemFalsa(),
                      voice=None, tools=tm, audit_path=None,
                      programar=lambda s, fn: timers.append(TimerFalso(fn)) or timers[-1],
                      juego=juego, prioridad=lambda baja: None, alarmas=alarmas, baile=None, salvapantallas=None)
    p.baile = BaileTerminal(consola, cfg, detector=_Musica(), en_juego=p._en_juego)
    api_in = _ApiInactiva()
    p.salvapantallas = SalvapantallasTerminal(consola, cfg, api=api_in, en_juego=p._en_juego,
                                              reloj=lambda: reloj[0])
    try:
        p._poner_titulo()                                   # como correr() al empezar
        base = api.titulos[-1]
        p.responder("hola")                                 # «¿Lo hago? [s/N]» pendiente
        assert consola.reclamada and p.ejecutor.pendientes()
        # Salvapantallas (10) y baile a mano (20; su línea viva reclama con -10).
        reloj[0] += 40
        api_in.inactivo(40)
        assert p.salvapantallas.tic() is True and consola.capa_titulo() == "salvapantallas"
        p.comando("/bailar 60")
        assert p.baile.bailando and consola.capa_titulo() == "baile"
        # Suena una alarma (60): encima de todo.
        alarmas.aviso.disparar(Disparo("a1", "pizza", "alarma", 0.0, "07:30", 0.0))
        assert consola.capa_titulo() == "alarma" and api.titulos[-1] == "⏰ pizza"
        # Enter en el bloqueo: lo consume la alarma («espera»), no la aprobación.
        entrada.put("\n")
        assert esperar(lambda: "(espera" in out.getvalue())
        assert alarmas.aviso.sonando is not None and p.ejecutor.pendientes() and lanzadas == []
        # Enter pasado el bloqueo: apaga la alarma; la aprobación y el baile siguen.
        reloj[0] += 6
        entrada.put("\n")
        assert esperar(lambda: alarmas.aviso.sonando is None)
        assert esperar(lambda: consola.capa_titulo() == "baile")
        assert p.ejecutor.pendientes() and lanzadas == [] and p.baile.bailando
        # «s» es para la aprobación.
        entrada.put("s\n")
        assert esperar(lambda: lanzadas == [("calc", "usuario")])
        assert p.baile.bailando
        # El Enter en vacío que queda para el baile: para.
        entrada.put("\n")
        assert esperar(lambda: not p.baile.bailando)
        assert esperar(lambda: consola.capa_titulo() == "salvapantallas")
        # Modo juego (50): el salvapantallas se quita; una alarma sigue por encima.
        juego.activo = True
        assert p._tic_juego() is True and consola.capa_titulo() == "juego"
        assert p.salvapantallas.tic() is False and consola.capa_titulo() == "juego"
        assert "baile" not in consola._capas and "salvapantallas" not in consola._capas
        alarmas.aviso.disparar(Disparo("a2", "cita", "alarma", 0.0, "08:00", 0.0))
        assert consola.capa_titulo() == "alarma"
        reloj[0] += 6
        entrada.put("\n")
        assert esperar(lambda: alarmas.aviso.sonando is None)
        assert esperar(lambda: consola.capa_titulo() == "juego")
        juego.activo = False
        assert p._tic_juego() is True
        assert consola.capa_titulo() is None and api.titulos[-1] == base
        assert not consola.reclamada                       # nada se queda esperando una línea
    finally:
        entrada.put(None)
        p.cerrar()
