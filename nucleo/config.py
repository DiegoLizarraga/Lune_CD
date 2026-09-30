"""
config.py — Preferencias locales de Lune CD (config.json).

Regla de la casa: aquí SOLO viven claves que algún módulo lee de verdad.
Antes había 14 que no leía nadie (`ui`, `behavior`, `paths` enteras): daban
la falsa impresión de ser configurables y editarlas no hacía nada. Si añades
una clave nueva, añade también el código que la usa — o no la añadas.

Excepción temporal (serie 10.3+, funciones portadas de Mate-Engine): sus
claves se declaran TODAS desde el primer corte aunque el código que las lee
llegue en cortes posteriores. `_merge_defaults` poda lo que no está aquí, así
que sin esto cualquier arranque borraría lo que la interfaz nueva guarde
mientras se desarrolla. Cada corte que las use debe cablearlas de verdad.

Varios escritores (la app, patata, el tema con guardado diferido, el bot):
- La escritura es atómica: archivo temporal en la misma carpeta + os.replace.
  Un corte de luz a media escritura deja el archivo viejo o el nuevo, nunca
  medio JSON.
- `set`, `set_feature` y `save` no escriben el dict entero a ciegas: si el
  archivo cambió desde la última vez que esta instancia lo leyó o lo escribió,
  lo recargan (fusionado con los valores por defecto), aplican SOLO las claves
  que cambió esta instancia y guardan. Gana el último por clave, no por archivo.
  "Cambió" = otro identificador de archivo, mtime o tamaño (cada os.replace crea
  un archivo nuevo, así que dos escrituras en el mismo tic de reloj se notan).
- Entre procesos, la lectura-fusión-escritura va dentro de un mutex con nombre
  de Windows (best effort: si no se consigue en 2 s, se sigue sin él).
- Un config.json corrupto NO se pisa con los valores por defecto: se aparta
  como config.json.corrupto-AAAAMMDD-HHMMSS y se avisa en el log.

La ruta por defecto se ancla a la raíz del repo (no al directorio de trabajo),
para que la app, patata y el bot usen el mismo archivo aunque se lancen desde
otra carpeta. Una ruta relativa también se ancla a la raíz.

Las APIs, modelos y personalidad viven en datos.json (ver datos.py).
"""
import copy
import hashlib
import json
import logging
import os
import shutil
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from nucleo import nombres_antiguos

RAIZ = Path(__file__).resolve().parent.parent
RUTA_CONFIG = RAIZ / "config.json"

_log = logging.getLogger("lune.config")

# Reintentos: lectura de un archivo a medio sustituir y os.replace contra un
# lector que lo tiene abierto (en Windows falla con PermissionError).
_REINTENTOS_LECTURA = 3
_PAUSA_LECTURA_S = 0.05
_REINTENTOS_REEMPLAZO = 20
_PAUSA_REEMPLAZO_S = 0.025
_ESPERA_MUTEX_MS = 2000

_FALTA = object()


def _anclar(config_path) -> Path:
    """Ruta absoluta del config: vacía → RAIZ/config.json; relativa → bajo RAIZ."""
    if config_path is None or str(config_path) == "":
        return RUTA_CONFIG
    p = Path(config_path).expanduser()
    if not p.is_absolute():
        p = RAIZ / p
    return p.resolve()


# ── Exclusión mutua ────────────────────────────────────────────────────────────
# Dentro del proceso: un RLock por archivo (varias instancias de Config sobre el
# mismo config.json comparten el lock). Entre procesos: mutex con nombre.

_LOCKS: Dict[str, threading.RLock] = {}
_LOCKS_GUARDIA = threading.Lock()


def _lock_de(ruta: Path) -> threading.RLock:
    clave = os.path.normcase(str(ruta))
    with _LOCKS_GUARDIA:
        return _LOCKS.setdefault(clave, threading.RLock())


_kernel32 = None
_kernel32_cargado = False


def _k32():
    """kernel32 con las firmas del mutex, cargado una vez. None fuera de Windows."""
    global _kernel32, _kernel32_cargado
    if _kernel32_cargado:
        return _kernel32
    _kernel32_cargado = True
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        k.CreateMutexW.restype = wintypes.HANDLE
        k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k.WaitForSingleObject.restype = wintypes.DWORD
        k.ReleaseMutex.argtypes = [wintypes.HANDLE]
        k.ReleaseMutex.restype = wintypes.BOOL
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.CloseHandle.restype = wintypes.BOOL
        _kernel32 = k
    except Exception:
        _kernel32 = None
    return _kernel32


class _MutexProcesos:
    """Mutex con nombre entre procesos (app, patata, bot) para leer-fusionar-escribir.

    Se toma y se suelta en el mismo hilo y en la misma llamada. Best effort: si
    no hay kernel32 o no se consigue en `_ESPERA_MUTEX_MS`, se sigue sin él (el
    lock de hilo sigue protegiendo dentro del proceso). Un mutex abandonado por un
    proceso que murió se toma igual (WAIT_ABANDONED).
    """

    def __init__(self, ruta: Path):
        digest = hashlib.sha1(os.path.normcase(str(ruta)).encode("utf-8")).hexdigest()[:16]
        self.nombre = "Local\\Lune_CD_config_" + digest
        self._h = None

    def __enter__(self):
        k = _k32()
        if k is None:
            return self
        try:
            h = k.CreateMutexW(None, False, self.nombre)
            if not h:
                return self
            r = k.WaitForSingleObject(h, _ESPERA_MUTEX_MS)
            if r in (0x0, 0x80):                     # WAIT_OBJECT_0 · WAIT_ABANDONED
                self._h = h
            else:
                _log.warning("config: otro proceso retiene el mutex de %s; sigo sin él", self.nombre)
                k.CloseHandle(h)
        except Exception:
            self._h = None
        return self

    def __exit__(self, *_exc):
        h, self._h = self._h, None
        if h:
            k = _k32()
            try:
                k.ReleaseMutex(h)
            finally:
                k.CloseHandle(h)
        return False


# ── Comparación y fusión de cambios ────────────────────────────────────────────

def _igual(a: Any, b: Any) -> bool:
    """Igualdad estricta de valores JSON (True ≠ 1, 1 ≠ 1.0), también anidados."""
    try:
        return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)
    except Exception:
        return a == b


Cambio = Tuple[Tuple[str, ...], Any]


def _diferencias(base: Dict, actual: Dict) -> List[Cambio]:
    """Qué cambió esta instancia respecto a lo último sincronizado con el disco.

    Por clave dentro de cada sección (("avatar", "companion_x"), valor) y por
    clave de primer nivel si no es una sección (("x",), valor). Las claves
    borradas en memoria se ignoran (al recargar volverían con su valor por defecto).
    """
    cambios: List[Cambio] = []
    for sec, val in actual.items():
        b = base.get(sec, _FALTA)
        if isinstance(val, dict) and isinstance(b, dict):
            for k, v in val.items():
                if k not in b or not _igual(b[k], v):
                    cambios.append(((sec, k), copy.deepcopy(v)))
        elif b is _FALTA or not _igual(b, val):
            cambios.append(((sec,), copy.deepcopy(val)))
    return cambios


def _aplicar_cambios(destino: Dict, cambios: List[Cambio]) -> None:
    for ruta, v in cambios:
        if len(ruta) == 1:
            destino[ruta[0]] = copy.deepcopy(v)
            continue
        sec = destino.get(ruta[0])
        if not isinstance(sec, dict):
            sec = destino[ruta[0]] = {}
        sec[ruta[1]] = copy.deepcopy(v)


class Config:
    """Gestor de preferencias y toggles de rendimiento."""

    DEFAULT_CONFIG = {
        # Activa/desactiva funciones para ajustar rendimiento y consumo.
        "features": {
            "respuestas_predeterminadas": True,  # respuestas instantáneas sin IA
            "animaciones_video": True,           # caras .mp4 (cuesta CPU/GPU)
            "fondo_estrellas": True,             # splash animado al iniciar
            "voz_auto": False,                   # leer en voz alta cada respuesta
            "efectos_hover": True,               # microanimaciones en la UI
            "streaming_tokens": True,            # mostrar respuesta letra por letra
            "minimizar_a_bandeja": True,         # al cerrar, ocultar en la bandeja
            "acciones_ia": True,                 # dejar que la IA abra webs y lance apps
            "markdown": True,                    # formatear negritas, listas y código
            "guardar_conversaciones": True,      # historial de chats en disco
            "contador_tokens": True,             # mostrar tokens y costo por respuesta
            "emociones": True,                   # la IA emite <|ACT|> y la cara reacciona
            "voz_streaming": False,              # hablar por frases mientras escribe (vs. al final)
            "sonido_tecleo": False,              # tecleo suave mientras la burbuja escribe (P08)
        },
        # Interfaz principal: "web" = piel Shibuya Punk (QWebEngineView), "nativo"
        # = la interfaz PyQt clásica.
        "interfaz": {
            "modo": "web",
            "en_barra_tareas": True,             # la ventana principal sale en la barra de tareas
            "fundido_ms": 180,                   # fundido al cambiar de interfaz en caliente (0 = sin fundido)
        },
        # Avatar/expresiones: permite cambiar el "modelo" visual de Lune.
        "avatar": {
            "pack": "default",                   # carpeta lune_face/ por defecto
            "render": "animado",                 # animado (video anime) · vrm (avatar 3D) · sprites (ligero, bajos recursos)
            "vrm_archivo": "",                   # .vrm por defecto; vacío = el 1º en modelo_vrm/ (cada personaje puede traer el suyo)
            "vrm_tamano": "normal",              # pequeno · normal · grande (tamaño de la asistente 3D)
            "vrm_escala": 1.0,                   # ajuste fino con la rueda del ratón sobre la asistente (0.6–1.5)
            "vrm_fantasma_auto": True,           # los clics pasan al escritorio donde no hay avatar
            "vrm_encuadre": "retrato",           # retrato (cara y torso) · cuerpo (entera)
            "dormir_min": 10,                    # la asistente 3D se duerme tras N min sin tocarla ni hablarle (0 = nunca)
            "click_through": False,              # modo fantasma: los clics la atraviesan
            "comentarios_cada_min": 0,           # companion comenta la pantalla cada N min (0 = off)
            "overlay_x": None, "overlay_y": None,      # posición de la asistente clásica
            "companion_x": None, "companion_y": None,  # posición del companion animado
            # ── Serie 10.3+ (funciones de Mate-Engine) ──
            "siempre_encima": True,              # la asistente se queda por encima de las ventanas (P11)
            "fps_max": 60,                       # 15–144; en reposo = min(fps_max, 30) (P11)
            "seguir_cursor": True,               # cabeza/ojos/torso siguen al ratón (P14)
            "peso_cabeza": 1.0,                  # 0–1: cuánto gira la cabeza hacia el cursor (P14)
            "peso_torso": 1.0,                   # 0–1: cuánto gira el torso (P14)
            "peso_ojos": 1.0,                    # 0–1: cuánto miran los ojos (P14)
            "sentarse_ventanas": False,          # sentarse en ventanas ajenas; aviso anticheat, como en ME (P03)
            "sentarse_barra": True,              # sentarse en la barra de tareas al soltarla encima (P03)
            "sentarse_offset_px": 0,             # ajuste vertical del asiento en px (P03)
            "microexpresiones": True,            # sonrisas y entrecerrar ojos al azar en reposo (P02)
            "mareo": True,                       # se marea si la zarandeas (P02)
            "sonidos": False,                    # sonidos al arrastrar y soltar (P02)
            "pack_sonidos": "default",           # carpeta de sonidos de reacción (P08)
            "volumen_sfx": 0.7,                  # 0–1: volumen de los efectos de la asistente
        },
        # Optimizador estilo Stacer: qué categorías limpiar por defecto.
        "optimizador": {
            "categorias_activas": [
                "temp_usuario", "temp_windows", "miniaturas", "cache_navegadores",
            ],
            "confirmar_antes_de_limpiar": True,
        },
        # Historial de conversaciones (ver conversaciones.py).
        "chat": {
            "max_sesiones": 50,                  # cuántas conversaciones se conservan
            "restaurar_ultima": True,            # reabrir la última al arrancar
            "aburrimiento_min": 10,              # tras N min sin escribirle, Lune se aburre y te dice algo (0 = nunca)
        },
        # Adjuntos: documentos e imágenes (ver adjuntos.py).
        "adjuntos": {
            "max_caracteres": 20000,             # texto máximo por documento
        },
        # Bot de Telegram (telegram-bot-or/, lo lanza servicios/telegram_worker.py).
        "telegram": {
            # /pc <orden> desde tu Telegram: la orden llega a Lune y TODO lo que haga
            # se aprueba en el PC. Necesita apis.telegram_admin_id (datos.json) y
            # reiniciar el bot para aplicarse. Apagado por defecto.
            "ordenes_pc": False,
        },
        # Red de Lune: rol de este dispositivo y descubrimiento en la LAN.
        "red": {
            "rol": "hibrido",              # host · interaccion · hibrido (ver descubrimiento.py)
            "nombre": "",                  # nombre visible; vacío = nombre del equipo
            "anunciar": True,              # anunciarse por mDNS para que otros lo vean
        },
        # Notas + RAG (memoria larga sobre documentos markdown, ver lune_core/rag.py).
        "notas": {
            "activo": False,               # apagado por defecto: requiere embeddings
            "carpeta": "notas",            # dónde están las notas .md
            "modelo_embeddings": "nomic-embed-text",
            "top_k": 3,                    # cuántos trozos se inyectan por mensaje
        },
        # Voz de entrada (Whisper) y de salida (edge-tts / Kokoro local).
        "voz": {
            "modelo_whisper": "base",            # tiny · base · small · medium · large-v3
            "idioma": "es",
            # ── Dispositivos (por NOMBRE; vacío = el del sistema). Ver voz_entrada.py ──
            "dispositivo_entrada": "",           # micrófono para dictar y para la llamada
            "dispositivo_salida": "",            # por dónde suena Lune (pygame/SDL; el mezclador lo busca en WASAPI)
            "llamada_umbral": 0.015,             # energía RMS mínima para «estás hablando»
            # ── Salida (ver voice.py y lune_core/voz/kokoro_backend.py) ──
            "motor_salida": "auto",              # auto · edge · gtts · kokoro
            "kokoro_carpeta": "modelos_voz",     # dónde están los pesos .onnx / .bin
            "kokoro_voz": "ef_dora",             # ef_dora · em_alex · em_santa
            "kokoro_velocidad": 1.0,             # 1.0 = normal
            # ── Voz de edge-tts elegible (P08) ──
            "edge_voz": "es-MX-DaliaNeural",     # ShortName de la voz de edge-tts
            "edge_rate": "+0%",                  # velocidad (-50%…+50%)
            "edge_pitch": "+0Hz",                # tono (-50Hz…+50Hz)
            "edge_volumen": "+0%",               # volumen relativo
            "gtts_tld": "com.mx",                # acento de gTTS (dominio de Google: com.mx, es, com…)
            # ── Conversión de voz opcional (experimental) ──
            "rvc_activo": False,
            "rvc_modelo": "",                    # ruta a un .pth entrenado
            "rvc_transpose": 0,                  # semitonos
            "rvc_index_rate": 0.5,
        },
        # Actualizaciones por git (ver actualizador.py).
        "actualizaciones": {
            "rama": "master",
            "comprobar_al_iniciar": False,
        },
        # ══ Secciones de la serie 10.3+ (funciones de Mate-Engine) ══════════════
        # Salvapantallas: Lune ocupa la pantalla tras un rato sin tocar nada (P05).
        "salvapantallas": {
            "activo": False,                     # apagado por defecto
            "paso": 0,                           # índice del tiempo de espera (tabla de 11 pasos de ME)
            "clic_sale_de_todo": True,           # un clic cierra el salvapantallas estés donde estés
            "fondo_oscuro": True,                # oscurecer el escritorio detrás de Lune
            "reloj": True,                       # mostrar la hora
        },
        # Alarmas y temporizadores (la lista vive en alarmas.json, no aquí) (P06).
        "alarmas": {
            "activo": True,                      # el programador de alarmas está encendido
            "bloqueo_s": 5,                      # s en los que un clic no apaga una alarma recién sonada
            "pantalla_grande": True,             # al sonar, Lune se pone en pantalla grande
            "decir_texto": True,                 # decir el texto de la alarma en voz alta
            "recuperar_min": 10,                 # si el PC estuvo suspendido, sonar las perdidas de hace ≤ N min
            "posponer_min": 5,                   # minutos de «posponer»
            "volumen": 0.8,                      # volumen del sonido de la alarma (0–1)
            "sonido": "azar",                    # azar · alarma_1 · alarma_2 · alarma_3
        },
        # Baile con la música del PC y reproductor de bailes (bailes/) (P04).
        "baile": {
            "auto": True,                        # bailar sola cuando suena música en una app permitida
            "umbral": 0.05,                      # pico de audio mínimo (0–1) para contar como música
            "apps": ["Spotify", "MusicBee", "foobar2000", "vlc", "AppleMusic"],  # apps que cuentan como música
            "cambiar": False,                    # cambiar de baile procedural cada `cambiar_s`
            "cambiar_s": 15,                     # s entre cambios de baile
            "volumen": 0.25,                     # volumen del audio de los bailes MMD/VRMA
            "al_terminar": "parar",              # al acabar un baile: parar · siguiente · repetir · aleatorio
            "en_el_sitio": True,                 # bailar sin desplazarse por la ventana
            "particulas": True,                  # notas/partículas mientras baila
            "favoritos": [],                     # ids de bailes favoritos
            "desactivados": [],                  # ids de bailes que no salen al azar
        },
        # Modo juego: qué hacer cuando hay un juego en primer plano (P11).
        "juego": {
            "activo": True,                      # detectar juegos
            "accion": "ocultar",                 # ocultar · fondo · nada
            "fps": 0,                            # fps de la asistente durante el juego (0 = pausada)
            "apps": [],                          # .exe que siempre cuentan como juego
            "rutas_juego": True,                 # contar como juego lo que corre desde steamapps\common y similares
            "incluir_videos": True,              # un vídeo a pantalla completa también cuenta (QUNS_BUSY)
            "prioridad_baja": True,              # bajar la prioridad del proceso de Lune
            "recortar_ram": True,                # recortar el working set al entrar
            "silenciar": True,                   # callar la voz y los efectos
        },
        # Arranque con Windows y mantenimiento (P12).
        "sistema": {
            "autoinicio": False,                 # arrancar con Windows
            "autoinicio_como": "bandeja",        # bandeja · asistente · ventana
            "autoinicio_retraso_s": 20,          # esperar antes de cargar lo pesado
            "recorte_ram_auto": False,           # recortar RAM periódicamente
        },
        # Presencia en Discord (Rich Presence por IPC propio) (P12).
        "discord": {
            "activo": False,                     # apagado por defecto
            "client_id": "",                     # Application ID de discord.com/developers (no es secreto;
                                                 # vacío = no publica nada hasta pegarlo: D1)
            "mostrar_modelo": False,             # enseñar el nombre del modelo VRM
            "boton_url": "",                     # enlace opcional del botón
        },
        # Integración con Minecraft (lector de latest.log y bot) (P13).
        "minecraft": {
            "reaccionar": False,                 # reaccionar a lo que pasa en la partida
            "ruta_log": "",                      # latest.log; vacío = .minecraft/logs por defecto
            "udp_mate_engine": False,            # reservada (sin usar): el UDP 32145 del mod de Mate-Engine
            "voz_reacciones": False,             # decir las reacciones en voz alta
            "comentar_con_ia": False,            # reservada (sin usar): el texto del juego nunca va al modelo
            "auto_con_juego": True,              # empezar a leer el log al detectar Minecraft abierto
            "decir_en_juego": True,              # en modo juego y con el bot conectado, lo dice el bot en el chat
            "resumen_al_salir": True,            # al salir del modo juego, «Mientras jugabas: …»
            "pensar_en_juego": False,            # el cerebro autónomo del bot sigue en modo juego (más GPU)
            "reaccionar_otros": False,           # reaccionar también a muertes y logros de otros jugadores
        },
        # Comida: batido y pastel con el clic central; el catálogo es fijo (nucleo/comida.CATALOGO)
        # y `catalogo_extra` queda reservado (se ignora) (P07, corte 8).
        "comida": {
            "activa": True,                      # clic central → comida
            "catalogo_extra": [],                # comidas añadidas por el usuario
        },
        # Tema de color de la interfaz y de la asistente en escritorio (P10).
        "tema": {
            "preset": "cian",                    # cian · y los demás presets de nucleo/tema.py
            "hue": 0.0,                          # desplazamiento de tono (grados)
            "saturacion": 1.0,                   # multiplicador de saturación
            "tenir_pop": False,                  # teñir también el amarillo de acento
            "tenir_fondo": False,                # teñir también los fondos
        },
        # Efectos visuales de la piel web (antes en localStorage) (P10).
        "efectos": {
            "fondo": True,                       # fondo animado
            "barrido": True,                     # barrido al cambiar de pantalla
            "micro": True,                       # microinteracciones
        },
        # Botones del menú radial de la asistente en escritorio (P10).
        "menu_radial": {
            "principal": ["ajustes", "chat", "comentar", "expresiones", "bailar",   # clic derecho
                          "alarma", "voz", "dormir", "tamano", "bajar"],
            "secundario": ["comer_batido", "comer_pastel", "guardar_comida"],     # clic central
        },
        # Sonidos de los menús (P10).
        "menu": {
            "sonidos": True,                     # sonar al abrir, cerrar y pulsar
            "volumen": 0.6,                      # 0–1
        },
        # Atajos globales con RegisterHotKey (sin hooks de teclado) (P10).
        "atajos": {
            "activo": True,                      # registrar los atajos al arrancar
            "pausar_en_juegos": True,            # no responder a los atajos en modo juego
            "sonido": False,                     # sonido al usar un atajo
            "lista": [                           # combos guardados con atajos_globales.normalizar()
                {"id": "mostrar_lune",    "combo": "ctrl+alt+shift+l"},
                {"id": "asistente",       "combo": "ctrl+alt+shift+m"},
                {"id": "menu_radial",     "combo": "ctrl+alt+shift+space"},
                {"id": "comentar",        "combo": "ctrl+alt+shift+c"},
                {"id": "voz",             "combo": "ctrl+alt+shift+v"},
                {"id": "llamada",         "combo": "ctrl+alt+shift+k"},
                {"id": "fantasma",        "combo": "ctrl+alt+shift+g"},
                {"id": "dormir",          "combo": "ctrl+alt+shift+z"},
                {"id": "pantalla_grande", "combo": "ctrl+alt+shift+b"},
                {"id": "baile_pausa",     "combo": "ctrl+alt+shift+period"},
            ],
        },
        # Acciones del menú de la bandeja (la misma lista que el radial y los atajos) (P10).
        "bandeja": {
            "acciones": ["asistente", "comentar", "voz", "llamada", "dormir", "pantalla_grande",   # en este orden
                         "bailar", "temporizador_rapido", "comida", "modo_juego_forzar",
                         "discord", "minecraft"],
        },
        # Modo patata (terminal) (P10).
        "patata": {
            "tema": "cian",                      # paleta ANSI truecolor
            "caritas": "clasico",                # clasico · kaomoji
            "prompt": "tú > ",                   # texto del prompt
        },
        # Bienvenida (11, nucleo/bienvenida.py): las tres preguntas de Lune cuando aún no te
        # conoce (tu nombre, cómo eres y cómo quieres que sea contigo). Sin migración: un
        # config.json viejo la recibe sin hacer y solo empieza con la memoria vacía de ti.
        "bienvenida": {
            "hecha": False,                      # terminada o saltada (con memoria ya no se pregunta)
            "paso": 0,                           # 0 = sin empezar · 1 nombre · 2 cómo eres · 3 cómo la quieres
            "reintento_nombre": False,           # ya se repitió la pregunta del nombre una vez
            "pedida": False,                     # esta ronda la pediste con /conocernos (ya te conozco)
        },
        # Versión del esquema de config.json: cada migración única de _migrar() sube uno.
        # Un config.json sin esta sección viene de antes de las migraciones (10.3).
        # 1 (serie 10.3+): baile.umbral · 2 (11): nombres del modo asistente en escritorio.
        "esquema": {
            "version": 2,
        },
    }

    def __init__(self, config_path: str = "config.json"):
        self.config_path = _anclar(config_path)
        self._lock = _lock_de(self.config_path)
        self._firma: Optional[tuple] = None   # (id, mtime_ns, tamaño) de lo último leído/escrito
        self._base: Dict[str, Any] = {}       # copia de lo último sincronizado con el disco
        with self._lock, _MutexProcesos(self.config_path):
            self.config = self._load_or_create()

    # ── Disco ──────────────────────────────────────────────────────────────────
    def _firma_disco(self) -> Optional[tuple]:
        try:
            st = os.stat(self.config_path)
        except OSError:
            return None
        return (st.st_ino, st.st_mtime_ns, st.st_size)

    def _leer_disco(self):
        """→ (estado, valor, firma). estado: ok · falta · corrupto · error.

        La firma sale del MISMO handle que se lee: si otro escritor sustituye el
        archivo entre medias, la firma sigue correspondiendo a lo leído.
        """
        try:
            with open(self.config_path, "rb") as f:
                st = os.fstat(f.fileno())
                crudo = f.read()
        except FileNotFoundError:
            return "falta", None, None
        except OSError as e:
            return "error", str(e), None
        firma = (st.st_ino, st.st_mtime_ns, st.st_size)
        try:
            data = json.loads(crudo.decode("utf-8-sig"))   # tolera el BOM de algunos editores
        except ValueError as e:                            # JSON o UTF-8 inválidos
            return "corrupto", str(e), firma
        if not isinstance(data, dict):
            return "corrupto", "no es un objeto JSON", firma
        return "ok", data, firma

    def _leer_con_reintento(self):
        """Como _leer_disco, pero reintenta un momento si falla (archivo a medio sustituir)."""
        resultado = self._leer_disco()
        for _ in range(_REINTENTOS_LECTURA - 1):
            if resultado[0] not in ("corrupto", "error"):
                break
            time.sleep(_PAUSA_LECTURA_S)
            resultado = self._leer_disco()
        return resultado

    def _apartar_corrupto(self, motivo: str) -> bool:
        """Renombra el config.json roto a config.json.corrupto-<fecha>. True si quedó a salvo."""
        fecha = datetime.now().strftime("%Y%m%d-%H%M%S")
        destino = self.config_path.with_name(f"{self.config_path.name}.corrupto-{fecha}")
        n = 1
        while destino.exists():
            destino = self.config_path.with_name(f"{self.config_path.name}.corrupto-{fecha}-{n}")
            n += 1
        try:
            os.replace(self.config_path, destino)
        except OSError:
            try:
                shutil.copyfile(self.config_path, destino)
            except OSError as e:
                _log.error("config.json está corrupto (%s) y no pude apartarlo (%s): "
                           "no lo sobrescribo.", motivo, e)
                return False
        _log.warning("config.json estaba corrupto (%s): lo aparto como %s y sigo con los "
                     "valores por defecto.", motivo, destino.name)
        return True

    def _escribir(self, data: Dict) -> bool:
        """Escritura atómica: temporal en la misma carpeta + os.replace. True si se guardó."""
        carpeta = self.config_path.parent
        tmp = None
        try:
            carpeta.mkdir(parents=True, exist_ok=True)
            texto = json.dumps(data, indent=4, ensure_ascii=False)
            fd, tmp = tempfile.mkstemp(prefix=f".{self.config_path.name}.", suffix=".tmp", dir=str(carpeta))
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(texto)
                f.flush()
                os.fsync(f.fileno())
            for intento in range(_REINTENTOS_REEMPLAZO):
                try:
                    os.replace(tmp, self.config_path)
                    break
                except PermissionError:
                    # Windows: otro proceso lo tiene abierto para leer justo ahora.
                    if intento == _REINTENTOS_REEMPLAZO - 1:
                        raise
                    time.sleep(_PAUSA_REEMPLAZO_S)
            tmp = None
        except Exception as e:
            _log.error("Error guardando config: %s", e)
            return False
        finally:
            if tmp is not None:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
        self._firma = self._firma_disco()
        self._base = copy.deepcopy(data)
        return True

    def _load_or_create(self) -> Dict[str, Any]:
        estado, valor, firma = self._leer_con_reintento()
        if estado == "ok":
            merged = self._merge_defaults(valor, self.DEFAULT_CONFIG)
            self._migrar(valor, merged)
            self._firma = firma
            self._base = copy.deepcopy(merged)
            # Persistir si el esquema cambió (secciones nuevas o claves podadas)
            if merged != valor:
                self._escribir(merged)
            return merged
        # copy() era superficial: las secciones anidadas quedaban compartidas
        # con DEFAULT_CONFIG y set_feature() mutaba los valores por defecto.
        inicial = copy.deepcopy(self.DEFAULT_CONFIG)
        if estado == "error":
            # Existe pero no se puede leer (bloqueado, permisos): no se toca.
            _log.warning("No pude leer %s (%s): uso los valores por defecto sin sobrescribirlo.",
                         self.config_path.name, valor)
            self._base = copy.deepcopy(inicial)
            return inicial
        if estado == "corrupto" and not self._apartar_corrupto(valor):
            self._base = copy.deepcopy(inicial)
            return inicial
        self._escribir(inicial)
        return inicial

    def _reemplazar_en_sitio(self, fresco: Dict) -> None:
        """Cambia el contenido de self.config por `fresco` conservando los dict
        (quien guardó una referencia a self.config o a una sección la sigue viendo).

        Nunca deja una sección vacía ni a medias: get()/feature() leen sin el
        lock desde otros hilos (la voz, el worker de la IA). Primero se quitan
        las claves que ya no están y luego se escribe cada valor en su sitio, así
        que un lector ve el valor viejo o el nuevo, jamás el de por defecto.
        """
        for k in [k for k in self.config if k not in fresco]:
            del self.config[k]
        for k, v in fresco.items():
            actual = self.config.get(k)
            if isinstance(actual, dict) and isinstance(v, dict):
                for clave in [c for c in actual if c not in v]:
                    del actual[clave]
                actual.update(v)
            else:
                self.config[k] = v

    def _sincronizar(self, forzar: Tuple[Tuple[str, str], ...] = ()) -> None:
        """Trae lo que otros escribieron y reaplica encima lo que cambió esta instancia.

        `forzar`: claves (sección, clave) que se reaplican aunque su valor en
        memoria no haya cambiado (un set() explícito siempre gana, aunque ponga el
        mismo valor que ya tenía esta instancia).
        """
        firma = self._firma_disco()
        if firma is None or firma == self._firma:
            return
        cambios = _diferencias(self._base, self.config)
        vistos = {ruta for ruta, _ in cambios}
        for sec, clave in forzar:
            if (sec, clave) not in vistos and isinstance(self.config.get(sec), dict) and clave in self.config[sec]:
                cambios.append(((sec, clave), copy.deepcopy(self.config[sec][clave])))
        estado, valor, firma_leida = self._leer_con_reintento()
        if estado == "ok":
            fresco = self._merge_defaults(valor, self.DEFAULT_CONFIG)
            _aplicar_cambios(fresco, cambios)
            self._reemplazar_en_sitio(fresco)
            self._firma = firma_leida
            self._base = self._merge_defaults(valor, self.DEFAULT_CONFIG)
        elif estado == "corrupto":
            # Otro escritor (o una edición a mano) lo dejó roto: se aparta y se guarda lo nuestro.
            self._apartar_corrupto(valor)
        # "falta" o "error": se guarda lo que hay en memoria (mejor que perder el cambio).

    def _guardar(self, forzar: Tuple[Tuple[str, str], ...] = ()) -> None:
        with self._lock, _MutexProcesos(self.config_path):
            self._sincronizar(forzar)
            self._escribir(self.config)

    def _save_config(self, data: dict):
        """Compatibilidad: escribe `data` tal cual (atómico). Preferir save()/set()."""
        with self._lock, _MutexProcesos(self.config_path):
            self._escribir(data)

    def save(self):
        """Guarda los cambios de esta instancia sin pisar los de otros escritores."""
        self._guardar()

    def recargar(self) -> bool:
        """Relee el archivo si otro lo cambió, conservando lo no guardado de esta
        instancia. True si había cambios en disco."""
        with self._lock, _MutexProcesos(self.config_path):
            firma = self._firma_disco()
            if firma is None or firma == self._firma:
                return False
            self._sincronizar()
            return True

    # ── Acceso cómodo a features ───────────────────────────────────────────────
    def feature(self, nombre: str, default: bool = True) -> bool:
        """Devuelve si una función está activada (sección 'features')."""
        return bool(self.config.get("features", {}).get(nombre, default))

    def set_feature(self, nombre: str, valor: bool):
        with self._lock:
            sec = self.config.get("features")
            if not isinstance(sec, dict):
                sec = self.config["features"] = {}
            sec[nombre] = bool(valor)
            self._guardar(forzar=(("features", nombre),))

    def get(self, seccion: str, clave: str, default=None):
        return self.config.get(seccion, {}).get(clave, default)

    def set(self, seccion: str, clave: str, valor):
        """Cambia UNA clave y guarda. Si otro escritor cambió el archivo desde la
        última lectura, se recarga y solo se aplica este cambio (y los demás no
        guardados de esta instancia): gana el último por clave, no por archivo."""
        with self._lock:
            sec = self.config.get(seccion)
            if not isinstance(sec, dict):
                sec = self.config[seccion] = {}
            sec[clave] = valor
            self._guardar(forzar=((seccion, clave),))

    # ── Migraciones únicas ─────────────────────────────────────────────────────
    @staticmethod
    def _version_esquema(crudo: Dict) -> int:
        sec = crudo.get("esquema") if isinstance(crudo, dict) else None
        v = sec.get("version") if isinstance(sec, dict) else None
        return v if isinstance(v, int) and not isinstance(v, bool) else 0

    def _migrar(self, crudo: Dict, merged: Dict) -> None:
        """Cambios de valores por defecto que tienen que llegar a los config.json viejos
        (_merge_defaults solo añade claves nuevas: un valor ya escrito se queda). Se miran
        en lo LEÍDO (`crudo`) y se aplican una sola vez sobre `merged`."""
        version = self._version_esquema(crudo)
        if version < 1:
            # 10.3 escribía baile.umbral = 0.2 (el defecto de entonces) y el detector de
            # música ya usa 0.05 (D1). Solo se cambia si sigue en el defecto viejo: un valor
            # que eligió la persona se respeta.
            baile = merged.get("baile")
            umbral = baile.get("umbral") if isinstance(baile, dict) else None
            if isinstance(umbral, (int, float)) and not isinstance(umbral, bool) and abs(umbral - 0.2) < 1e-9:
                baile["umbral"] = self.DEFAULT_CONFIG["baile"]["umbral"]
                _log.info("config: baile.umbral 0.2 (defecto de la 10.3) → %s", baile["umbral"])
        if version < 2:
            # 11: el modo «asistente en escritorio» dejó atrás su nombre de antes. Los ids
            # de acción y el modo de autoinicio guardados con él pasan al de ahora
            # (nucleo/nombres_antiguos); lo demás no se toca.
            tocado = self._migrar_nombres_antiguos(merged)
            if tocado:
                _log.info("config: nombres del modo asistente en escritorio al día en %s",
                          ", ".join(tocado))
        if version < self.DEFAULT_CONFIG["esquema"]["version"]:
            sec = merged.get("esquema")
            if not isinstance(sec, dict):
                sec = merged["esquema"] = {}
            sec["version"] = self.DEFAULT_CONFIG["esquema"]["version"]

    # Listas de ids de acción (nucleo/acciones_ui) que guarda config.json.
    _LISTAS_DE_ACCIONES = (("bandeja", "acciones"), ("menu_radial", "principal"),
                           ("menu_radial", "secundario"))

    @classmethod
    def _migrar_nombres_antiguos(cls, merged: Dict) -> List[str]:
        """Ids de acción (atajos, bandeja, menú radial) y sistema.autoinicio_como con los
        nombres de ahora. Las listas se sustituyen por otras nuevas: `merged` comparte las
        suyas con lo leído y así se nota el cambio al comparar. Devuelve qué se tocó."""
        tocado: List[str] = []
        atajos = merged.get("atajos")
        if isinstance(atajos, dict):
            lista, cambio = nombres_antiguos.migrar_atajos(atajos.get("lista"))
            if cambio:
                atajos["lista"] = lista
                tocado.append("atajos.lista")
        for sec, clave in cls._LISTAS_DE_ACCIONES:
            seccion = merged.get(sec)
            if not isinstance(seccion, dict):
                continue
            lista, cambio = nombres_antiguos.migrar_lista_acciones(seccion.get(clave))
            if cambio:
                seccion[clave] = lista
                tocado.append(f"{sec}.{clave}")
        sistema = merged.get("sistema")
        if isinstance(sistema, dict):
            como = sistema.get("autoinicio_como")
            nuevo = nombres_antiguos.como_autoinicio(como)
            if nuevo != como:
                sistema["autoinicio_como"] = nuevo
                tocado.append("sistema.autoinicio_como")
        return tocado

    # ── Fusión con los valores por defecto ─────────────────────────────────────
    def _merge_defaults(self, loaded: Dict, default: Dict) -> Dict:
        """
        Conserva lo que el usuario configuró y añade las claves nuevas.

        PODA las claves que ya no existen en DEFAULT_CONFIG: así las secciones
        muertas desaparecen solas del config.json de quien viene de una versión
        anterior, en vez de quedarse ahí engañando.
        """
        result = copy.deepcopy(default)
        for key, value in loaded.items():
            if key not in default:
                continue  # clave obsoleta → se descarta
            if isinstance(default[key], dict) and isinstance(value, dict):
                result[key] = self._merge_defaults(value, default[key])
            else:
                result[key] = value
        return result
