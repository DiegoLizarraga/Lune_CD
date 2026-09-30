"""
ai_manager.py — Motor híbrido de Lune CD: nube (OpenRouter), local (Ollama) y
cualquier API compatible con OpenAI (proveedor 'compat': LM Studio, llama.cpp,
Groq, OpenAI, Together, Mistral…).

Cada proveedor mantiene su propio historial y su propia sesión HTTP. Lo de la
sesión por proveedor no es cosmético: `requests.Session` no es thread-safe y
aquí las llamadas salen desde un executor, así que compartir una sola sesión
entre proveedores era una carrera esperando a ocurrir. Las llamadas sueltas
(sondeos, listar modelos, liberar VRAM) usan una sesión de un solo uso por la
misma razón: pueden coincidir con un chat en curso.

El historial se recorta a `datos.max_historial()` turnos. Sin eso crecía sin
límite y con modelos locales acababa desbordando la ventana de contexto. Se
recorta POR BLOQUES (`BLOQUE_RECORTE` mensajes de golpe) y no de dos en dos: si
la ventana se desplazara en cada turno, el principio de la conversación cambiaría
siempre y la caché de prefijo de Ollama no serviría nunca (prueba real: 40 s
hasta el primer token con el historial lleno, en cada mensaje).

CACHÉ Y MENSAJE DEL USUARIO
`prefijo` (la hora, «[AAAA-MM-DD HH:MM] ») se guarda con el mensaje: el mismo
texto en el historial que el que se envió. `anexo` (adjuntos, notas: datos de
este mensaje) se envía al final del último mensaje y NO se guarda: el
historial no crece con documentos y el prefijo cacheado no cambia.

HISTORIAL NORMALIZADO
Lo que se guarda de cada respuesta es su versión normalizada
(lune_core.marcadores.normalizar): marcas válidas en su forma buena y sin la
basura que los modelos pequeños escriben (|<ACT …>|, <|OPEN_URL …|>…). Guardarla
cruda hacía que el modelo copiara sus propias marcas rotas en los turnos siguientes.

Visión: las imágenes se adjuntan SOLO al mensaje que se está enviando; en el
historial queda la versión de texto. Guardar el base64 turno tras turno haría
crecer el contexto sin parar y reenviaría la misma imagen en cada mensaje.

REINTENTOS SEGUROS (`AIProvider._post_con_reintentos`)
Hasta 3 reintentos, con esperas de 0.5, 1 y 2 s, ante ConnectionError,
Timeout, HTTP 5xx o 429. Nunca ante un error del cliente (400/401/402/403/404:
repetir no lo arregla y un 402 es dinero) y NUNCA después del primer token: el
texto ya se mostró (y quizá se habló), repetir lo duplicaría. Tampoco ante una
conexión RECHAZADA (el servidor no está escuchando: reintentar solo hacía
esperar 11 s en vez de 2) y nunca más allá de `TOPE_REINTENTOS_S` desde el
primer intento (un equipo apagado falla en ~10 s, no en ~24). Ollama no
reintenta el timeout de LECTURA (el suyo ya es de minutos para cubrir el
arranque en frío) ni un 500 (p. ej. sin memoria para el modelo: repetirlo no lo
arregla); sí 502/503/504.

HISTORIAL CON ORIGEN (taint)
Un turno 'no_confiable' (texto de terceros: adjuntos, Telegram, notas…) o
'remoto' (una orden desde Telegram con /pc: cualquier origen que no sea
'usuario', ver `es_no_confiable`) deja su
prompt y su respuesta MARCADOS en el historial (`MARCA_NO_CONFIABLE`, que nunca
se envía al proveedor), y los `<|CALL|>` de esa respuesta, neutralizados.
`contexto_contaminado(proveedor)` dice si la ventana enviada en el último turno
(o el historial actual) lleva algo marcado: el Ejecutor lo consulta al ejecutar
y, si es así, todo lo que no sea de LECTURA pide permiso a un humano. Un turno
`efimero` (el comentario de pantalla de la asistente) ni se guarda ni marca nada.
`clear_history()` quita las marcas con la conversación.

CLAVES
Los errores de red pueden llevar la cabecera `Authorization: Bearer <clave>`
(p. ej. requests.InvalidHeader con una clave pegada con un salto de línea).
Todo error que se muestra, se registra o vuelve como texto pasa antes por
`redactar_secretos`.

PARÁMETROS DE MUESTREO (`datos.parametros_muestreo()`)
Ollama los recibe en `options` con sus nombres nativos; OpenRouter con sus
campos (top_k, min_p, repetition_penalty…); 'compat' con los campos estándar
de OpenAI (temperature, top_p, max_tokens, seed) y los extendidos (top_k,
min_p, repeat_penalty) solo si el servidor es local (LM Studio, llama.cpp):
las nubes estrictas (OpenAI, Mistral) rechazan campos desconocidos con 400/422.
Por lo mismo, a los modelos de razonamiento de OpenAI no se les manda
temperature ni top_p, y a Mistral la semilla le llega como `random_seed`.
Lo que no está definido no se envía, así que sin ajustes nuevos las peticiones
a Ollama y OpenRouter son idénticas a las de antes.
"""
import asyncio
import ipaddress
import json
import re
import threading
import time
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

import requests
from urllib3.exceptions import ReadTimeoutError

from lune_core import marcadores
from nucleo import datos


_USER_AGENT = "LuneCD/8.5"

# Esperas antes de cada reintento (s). Su longitud es el número de reintentos.
ESPERAS_REINTENTO = (0.5, 1.0, 2.0)
# Tope al `Retry-After` de un 429/503: más que esto y el usuario ya se fue.
_RETRY_AFTER_MAX = 5.0
# Ningún reintento empieza si con su espera se pasaría de esto desde el primer
# intento: un servidor apagado o lento no debe multiplicar la espera.
TOPE_REINTENTOS_S = 10.0

# Marca interna del historial: la entrada salió de un turno con texto de
# terceros. Se guarda en el dict del historial, pero NUNCA se envía.
MARCA_NO_CONFIABLE = "_no_confiable"
ORIGEN_USUARIO = "usuario"

_CALL_EN_HISTORIAL = re.compile(r"<\|(\s*)(CALL)(?![A-Za-z0-9_])", re.IGNORECASE)

# Recorte del historial por bloques (mensajes; par, para no partir user/assistant).
BLOQUE_RECORTE = 10
# Mensajes de la conversación que ve un turno efímero (el comentario de pantalla de la
# asistente): los últimos, no todos (prueba real: 22 s con el historial entero y otro
# system prompt, sin caché).
VENTANA_EFIMERA = 4


def es_no_confiable(origen) -> bool:
    """None (no se dijo) = turno del usuario, como siempre; cualquier otro valor
    que no sea 'usuario' es de terceros."""
    return origen is not None and str(origen).strip().lower() != ORIGEN_USUARIO


def neutralizar_calls(texto: str) -> str:
    """`<|CALL …|>` → `< |CALL …|>`: el parser ya no lo ve como llamada."""
    return _CALL_EN_HISTORIAL.sub(r"< |\1\2", str(texto or ""))


def respuesta_para_historial(texto: str) -> str:
    """La respuesta tal como se guarda en el historial: normalizada (marcas buenas,
    sin basura). Si no queda nada (solo había marcas rotas), «…»."""
    try:
        limpio = marcadores.normalizar(texto)
    except Exception:
        limpio = str(texto or "")
    return limpio if limpio.strip() else "…"


# ── Claves fuera de los mensajes de error ─────────────────────────────────────
_PATRONES_SECRETO = (
    (re.compile(r"(?i)\b(bearer|basic)\s+[^\s'\",;)]+"), r"\1 ***"),
    (re.compile(r"(?i)(authorization['\"]?\s*[:=]\s*['\"]?)[^'\"\s,}]+(?:\s+[^'\"\s,}]+)?"), r"\1***"),
    (re.compile(r"(?i)\b(sk|pk|rk|gsk|xai)-[A-Za-z0-9_\-]{6,}"), r"\1-***"),
    (re.compile(r"(?i)([?&](?:api[_-]?key|key|token|access_token)=)[^&\s'\"]+"), r"\1***"),
    (re.compile(r"(?i)(://)[^/\s:@]+:[^/\s@]+@"), r"\1***@"),
)


def redactar_secretos(texto, secretos=(), formas: bool = True) -> str:
    """
    Quita claves de un texto: los valores exactos de `secretos` y, con `formas`
    (textos de error), lo que tenga forma de credencial (Bearer …, sk-…,
    ?key=…, usuario:clave@). Sin `formas` (la respuesta normal del modelo) solo
    se tocan los valores exactos: explicar «Authorization: Bearer <token>» es legítimo.
    """
    s = str(texto if texto is not None else "")
    for secreto in secretos or ():
        secreto = str(secreto or "").strip()
        if len(secreto) >= 4:
            s = s.replace(secreto, "***")
    if formas:
        for patron, cambio in _PATRONES_SECRETO:
            s = patron.sub(cambio, s)
    return s


def _conexion_rechazada(error: BaseException) -> bool:
    """¿El error viene de una conexión RECHAZADA (nadie escucha en ese puerto)?"""
    pila, vistos = [error], set()
    while pila:
        e = pila.pop()
        if not isinstance(e, BaseException) or id(e) in vistos:
            continue
        vistos.add(id(e))
        if isinstance(e, ConnectionRefusedError):
            return True
        pila.extend((getattr(e, "reason", None), e.__cause__, e.__context__))
        pila.extend(a for a in getattr(e, "args", ()) if isinstance(a, BaseException))
    texto = str(error).lower()
    return "10061" in texto or "connection refused" in texto


def _nueva_sesion() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": _USER_AGENT})
    return s


def en_segundo_plano(fn: Callable[[], Any],
                     al_terminar: Optional[Callable[[Any], None]] = None) -> threading.Thread:
    """
    Ejecuta `fn` en un hilo daemon (p. ej. `descargar_modelo`, `precalentar` o
    `probar` desde un slot de la UI) y pasa su resultado a `al_terminar`, que
    corre en ESE hilo: desde Qt, reenvíalo con una señal.
    """
    def _run():
        try:
            resultado = fn()
        except Exception:
            resultado = None
        if al_terminar:
            try:
                al_terminar(resultado)
            except Exception:
                pass

    hilo = threading.Thread(target=_run, name="lune-ia-aux", daemon=True)
    hilo.start()
    return hilo


# ── URLs de servidores compatibles con OpenAI ─────────────────────────────────

_RED_TAILSCALE = ipaddress.ip_network("100.64.0.0/10")
_DOMINIOS_LOCALES = (".local", ".lan", ".home", ".internal", ".localhost", ".ts.net")


def _host_de(url: str) -> str:
    texto = (url or "").strip()
    if "://" not in texto:
        texto = "http://" + texto
    try:
        return (urlparse(texto).hostname or "").lower()
    except ValueError:
        return ""


def es_host_local(url: str) -> bool:
    """¿La URL apunta a este equipo o a la red local (LAN, Tailscale, *.local)?"""
    host = _host_de(url)
    if not host:
        return False
    if host == "localhost" or host.endswith(_DOMINIOS_LOCALES):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return "." not in host          # nombre de equipo de la red ("pc-potente")
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip in _RED_TAILSCALE


def base_compat(url: str) -> str:
    """
    Normaliza la URL base de un servidor compatible con OpenAI:
    «localhost:1234» → «http://localhost:1234/v1»; «api.openai.com» →
    «https://api.openai.com/v1»; si pegaron el endpoint completo
    («…/v1/chat/completions») se le quita la cola. Una ruta propia
    («https://api.groq.com/openai/v1», «http://pc:3000/api») se respeta.
    """
    b = (url or "").strip().rstrip("/")
    if not b:
        return ""
    if "://" not in b:
        b = ("http://" if es_host_local(b) else "https://") + b
    for sufijo in ("/chat/completions", "/completions", "/models"):
        if b.lower().endswith(sufijo):
            b = b[: -len(sufijo)].rstrip("/")
            break
    try:
        ruta = urlparse(b).path
    except ValueError:
        ruta = ""
    if ruta in ("", "/"):
        b = b.rstrip("/") + "/v1"
    return b


def endpoint_chat_compat(url: str) -> str:
    b = base_compat(url)
    return f"{b}/chat/completions" if b else ""


def endpoint_modelos_compat(url: str) -> str:
    b = base_compat(url)
    return f"{b}/models" if b else ""


def es_razonamiento_openai(modelo: str) -> bool:
    """
    ¿Es un modelo de razonamiento de la API de OpenAI (o1, o3, o4-mini, gpt-5,
    gpt-5-mini…)? Los «-chat» de gpt-5 no razonan y aceptan temperature.
    """
    m = (modelo or "").strip().lower()
    return bool(re.match(r"o\d", m)) or (m.startswith("gpt-5") and "-chat" not in m)


# ── Parámetros de muestreo → campos de cada API ───────────────────────────────

def opciones_ollama(p: Dict[str, Any]) -> Dict[str, Any]:
    """`options` de Ollama desde `datos.parametros_muestreo()` (solo lo definido)."""
    opciones = {"num_ctx": p["num_ctx"], "temperature": p["temperatura"]}
    for clave in ("top_p", "top_k", "min_p", "repeat_penalty", "num_predict", "seed"):
        if p.get(clave) is not None:
            opciones[clave] = p[clave]
    return opciones


def campos_openai(p: Dict[str, Any], *, extendidos: bool,
                  nombre_repeat: str = "repetition_penalty",
                  campo_max: str = "max_tokens") -> Dict[str, Any]:
    """
    Campos de muestreo para /chat/completions. Los estándar de OpenAI siempre;
    top_k, min_p y la penalización de repetición solo con `extendidos`.
    Sin `num_predict` el tope de salida es `bot.max_tokens`, como siempre.
    """
    campos: Dict[str, Any] = {
        "temperature": p["temperatura"],
        campo_max: p["num_predict"] if p.get("num_predict") else datos.max_tokens(),
    }
    if p.get("top_p") is not None:
        campos["top_p"] = p["top_p"]
    if p.get("seed") is not None:
        campos["seed"] = p["seed"]
    if extendidos:
        if p.get("top_k") is not None:
            campos["top_k"] = p["top_k"]
        if p.get("min_p") is not None:
            campos["min_p"] = p["min_p"]
        if p.get("repeat_penalty") is not None:
            campos[nombre_repeat] = p["repeat_penalty"]
    return campos


def _limpiar_detalle(texto: str, limite: int = 240) -> str:
    """Mensaje de error del servidor apto para la UI: una línea, corto y sin marcadores."""
    texto = re.sub(r"\s+", " ", str(texto or "")).strip()
    if len(texto) > limite:
        texto = texto[: limite - 1] + "…"
    # Un servidor no debe poder colar `<|CALL …|>` en lo que Lune muestra.
    return texto.replace("<|", "< |")


def _detalle_de_cuerpo(cuerpo: str) -> str:
    """Extrae el mensaje de error de un cuerpo JSON estilo OpenAI (o el texto tal cual)."""
    try:
        d = json.loads(cuerpo)
    except (TypeError, ValueError):
        return _limpiar_detalle(cuerpo)
    if isinstance(d, dict):
        err = d.get("error", d)
        if isinstance(err, dict):
            return _limpiar_detalle(err.get("message") or err.get("detail") or json.dumps(err))
        if isinstance(err, str):
            return _limpiar_detalle(err)
        if d.get("message") or d.get("detail"):
            return _limpiar_detalle(d.get("message") or d.get("detail"))
    return _limpiar_detalle(cuerpo)


def _leer_cuerpo(respuesta, limite: int = 4096) -> str:
    """Lee como mucho `limite` bytes del cuerpo (una respuesta en streaming no lo trae leído)."""
    try:
        trozos, total = [], 0
        for trozo in respuesta.iter_content(1024):
            if not trozo:
                continue
            trozos.append(trozo)
            total += len(trozo)
            if total >= limite:
                break
        return b"".join(trozos)[:limite].decode("utf-8", errors="replace")
    except Exception:
        return ""


def _es_timeout_lectura(error: Exception) -> bool:
    if isinstance(error, requests.exceptions.ReadTimeout):
        return True
    # A mitad del stream requests lo envuelve en un ConnectionError.
    return (isinstance(error, requests.exceptions.ConnectionError)
            and any(isinstance(a, ReadTimeoutError) for a in error.args))


class AIProvider(ABC):
    ERROR = "Error:"
    # Esperas de reintento (ver docstring del módulo) y si el timeout de
    # lectura cuenta como fallo transitorio en este proveedor.
    ESPERAS = ESPERAS_REINTENTO
    REINTENTA_TIMEOUT_LECTURA = True
    TOPE_REINTENTOS = TOPE_REINTENTOS_S

    def __init__(self):
        self.cancel_flag = False
        self.conversation_history: List[dict] = []
        self.ultimo_uso: Dict = {}
        self._session = _nueva_sesion()
        # ¿La ventana del último envío (no efímero) llevaba algo de terceros?
        self._envio_contaminado = False

    @abstractmethod
    async def chat(self, message: str, system_prompt: str = "",
                   on_token: Callable = None, imagenes: Optional[List[str]] = None, *,
                   origen: Optional[str] = None, efimero: bool = False,
                   prefijo: str = "", anexo: str = "") -> str: ...
    @abstractmethod
    def is_available(self) -> bool: ...

    def clear_history(self) -> None:
        self.conversation_history = []
        self.ultimo_uso = {}
        self._envio_contaminado = False

    def cargar_historial(self, mensajes: List[dict]):
        """Reinyecta una conversación guardada para poder retomarla (con su
        marca de terceros si la trae)."""
        historial = []
        for m in mensajes:
            if not m.get("content"):
                continue
            entrada = {"role": m.get("role", "user"), "content": m.get("content", "")}
            if m.get(MARCA_NO_CONFIABLE):
                entrada[MARCA_NO_CONFIABLE] = True
            historial.append(entrada)
        self.conversation_history = historial
        self._envio_contaminado = False
        self._recortar_historial()

    # ── Historial ─────────────────────────────────────────────────────────────
    def _limite_historial(self) -> int:
        return max(1, datos.max_historial()) * 2

    def _recortar_historial(self):
        """
        Conserva como mucho N turnos (user + assistant). Al pasarse, recorta desde
        el principio (lo más viejo) un BLOQUE de mensajes de golpe: así el
        principio de la conversación no cambia en cada turno y la caché de prefijo
        del modelo sigue valiendo hasta el siguiente recorte. Con ventanas muy
        pequeñas (≤ 3 turnos) el bloque se reduce hasta el recorte de siempre.
        """
        limite = self._limite_historial()
        if len(self.conversation_history) > limite:
            bloque = min(BLOQUE_RECORTE, (limite // 2) // 2 * 2)
            nuevo = self.conversation_history[-(limite - bloque):]
            if bloque:
                # Que no empiece por una respuesta suelta (se recorta al llegar el mensaje).
                while len(nuevo) > 1 and nuevo[0].get("role") == "assistant":
                    nuevo = nuevo[1:]
            self.conversation_history = nuevo

    def _mensajes_para_envio(self, message: str, system_prompt: str, *,
                             origen: Optional[str] = None, efimero: bool = False,
                             prefijo: str = "", anexo: str = "") -> List[dict]:
        """
        Los mensajes que se envían: system + la ventana del historial + el nuevo.
        Un turno no confiable queda marcado en el historial; uno efímero no se
        guarda y solo ve los últimos VENTANA_EFIMERA mensajes. `prefijo` (la hora)
        se guarda con el mensaje; `anexo` (adjuntos, notas) va al final del que se
        envía y no se guarda. Al proveedor solo le llegan role y content.
        """
        entrada = {"role": "user", "content": f"{prefijo or ''}{message}"}
        if es_no_confiable(origen):
            entrada[MARCA_NO_CONFIABLE] = True
        if efimero:
            previo = min(VENTANA_EFIMERA, self._limite_historial() - 1)
            ventana = (list(self.conversation_history[-previo:]) if previo > 0 else []) + [entrada]
        else:
            self.conversation_history.append(entrada)
            self._recortar_historial()
            ventana = list(self.conversation_history)
            self._envio_contaminado = any(m.get(MARCA_NO_CONFIABLE) for m in ventana)
        mensajes = [{"role": m.get("role", "user"), "content": m.get("content", "")}
                    for m in ventana]
        if anexo and str(anexo).strip():
            mensajes[-1]["content"] = f"{mensajes[-1]['content']}\n\n{str(anexo).strip()}"
        if system_prompt:
            mensajes.insert(0, {"role": "system", "content": system_prompt})
        return mensajes

    def _registrar_respuesta(self, texto: str, *, origen: Optional[str] = None,
                             efimero: bool = False):
        if efimero:
            return
        if texto and not texto.startswith(self.ERROR) and not self.cancel_flag:
            contenido = respuesta_para_historial(texto)
            entrada = {"role": "assistant", "content": contenido}
            if es_no_confiable(origen):
                # Lo que respondió a texto de terceros: marcado y sin CALL que el
                # modelo pueda «recordar» como algo que ya hizo.
                entrada = {"role": "assistant", "content": neutralizar_calls(contenido),
                           MARCA_NO_CONFIABLE: True}
            self.conversation_history.append(entrada)
            self._recortar_historial()

    def contexto_contaminado(self) -> bool:
        """¿El último envío o el historial actual llevan texto de terceros?"""
        if self._envio_contaminado:
            return True
        return any(isinstance(m, dict) and m.get(MARCA_NO_CONFIABLE)
                   for m in list(self.conversation_history))

    # ── Claves ────────────────────────────────────────────────────────────────
    def _secretos(self) -> tuple:
        return tuple(s for s in (getattr(self, "api_key", ""),) if s)

    def _redactar(self, texto) -> str:
        return redactar_secretos(texto, self._secretos())

    # ── Reintentos ────────────────────────────────────────────────────────────
    def _es_reintentable(self, error: Exception) -> bool:
        """ConnectionError, Timeout, HTTP 5xx o 429. Nunca otro 4xx, un error de TLS
        ni una conexión rechazada (no hay nadie escuchando: no va a aparecer)."""
        if isinstance(error, requests.exceptions.HTTPError):
            r = error.response
            codigo = r.status_code if r is not None else None
            return codigo == 429 or (codigo is not None and 500 <= codigo <= 599)
        if isinstance(error, requests.exceptions.SSLError):
            return False                    # un certificado malo no se arregla solo
        if _es_timeout_lectura(error):
            return self.REINTENTA_TIMEOUT_LECTURA
        if isinstance(error, requests.exceptions.ConnectionError) and _conexion_rechazada(error):
            return False
        return isinstance(error, (requests.exceptions.ConnectionError,
                                  requests.exceptions.Timeout,
                                  requests.exceptions.ChunkedEncodingError))

    @staticmethod
    def _espera_para(error: Exception, base: float) -> float:
        """La espera fija, o el `Retry-After` del servidor si pide más (con tope)."""
        r = getattr(error, "response", None)
        try:
            pedido = float(r.headers.get("Retry-After")) if r is not None else 0.0
        except (TypeError, ValueError, AttributeError):
            pedido = 0.0
        return max(base, min(pedido, _RETRY_AFTER_MAX))

    def _esperar(self, segundos: float) -> bool:
        """Duerme en tramos cortos; devuelve False si el usuario canceló mientras tanto."""
        fin = time.monotonic() + segundos
        while not self.cancel_flag:
            resta = fin - time.monotonic()
            if resta <= 0:
                return True
            time.sleep(min(0.1, resta))
        return False

    def _post_con_reintentos(self, url: str, *, consumir: Callable, on_token: Callable = None,
                             timeout=60, **kwargs) -> str:
        """
        POST en streaming con reintentos seguros.

        `consumir(respuesta, emitir)` lee el stream y devuelve el texto; cada
        token visible debe pasar por `emitir`, que lo reenvía a `on_token` y
        marca que ya salió algo: desde ese momento ningún error se reintenta.
        Lo que no se reintenta se relanza (un HTTPError lleva `.detalle`, el
        mensaje del servidor ya limpio). Cancelar durante una espera devuelve "".
        """
        hubo_token = False

        def emitir(token: str):
            nonlocal hubo_token
            hubo_token = True
            if on_token:
                on_token(token)

        esperas = tuple(self.ESPERAS)
        inicio = time.monotonic()
        for intento in range(len(esperas) + 1):
            respuesta = None
            try:
                respuesta = self._session.post(url, timeout=timeout, stream=True, **kwargs)
                respuesta.raise_for_status()
                return consumir(respuesta, emitir)
            except Exception as e:
                espera = 0.0
                reintentar = not (hubo_token or self.cancel_flag or intento >= len(esperas)
                                  or not self._es_reintentable(e))
                if reintentar:
                    espera = self._espera_para(e, esperas[intento])
                    # Tope total desde el primer intento: si con esta espera ya se
                    # pasa, no se reintenta (un equipo apagado no multiplica la espera).
                    reintentar = time.monotonic() - inicio + espera <= self.TOPE_REINTENTOS
                if not reintentar:
                    if isinstance(e, requests.exceptions.HTTPError) and respuesta is not None:
                        e.detalle = self._redactar(_detalle_de_cuerpo(_leer_cuerpo(respuesta)))
                    raise
            finally:
                if respuesta is not None:
                    try:
                        respuesta.close()
                    except Exception:
                        pass
            if not self._esperar(espera):
                return ""
        return ""


# ── Ollama (Local / Offline) ──────────────────────────────────────────────────
class OllamaProvider(AIProvider):
    ERROR = "Error Ollama:"
    # Su timeout (datos.ollama_timeout, 300 s) ya cubre el arranque en frío;
    # reintentarlo convertiría 5 minutos en 20.
    REINTENTA_TIMEOUT_LECTURA = False
    # Conectar a un equipo de la LAN tarda milisegundos: 5 s de tope para
    # conectar. Un equipo apagado falla en ~10.5 s (dos intentos, por
    # TOPE_REINTENTOS_S) y un puerto cerrado en lo que tarde el rechazo (sin
    # reintentos), como en 10.2.
    TIMEOUT_CONEXION = 5.0
    # 5xx que sí son pasajeros (proxy o servidor arrancando). Un 500 de Ollama
    # suele ser «sin memoria para el modelo»: repetirlo no lo arregla.
    HTTP_REINTENTABLES = (502, 503, 504)

    def __init__(self, url: str, model: str):
        super().__init__()
        self.url = url
        self.model = model

    def configurar(self, url: str, model: str):
        self.url, self.model = url, model

    def _es_reintentable(self, error: Exception) -> bool:
        if isinstance(error, requests.exceptions.HTTPError):
            r = error.response
            codigo = r.status_code if r is not None else None
            return codigo == 429 or codigo in self.HTTP_REINTENTABLES
        return super()._es_reintentable(error)

    async def chat(self, message: str, system_prompt: str = "",
                   on_token: Callable = None, imagenes: Optional[List[str]] = None, *,
                   origen: Optional[str] = None, efimero: bool = False,
                   prefijo: str = "", anexo: str = "") -> str:
        if not message or not message.strip():
            return "El mensaje está vacío"
        if not self.model:
            return (f"{self.ERROR} no hay ningún modelo local seleccionado. "
                    "Ve a Configuración → Red Neuronal · Local y pulsa «Buscar modelos».")

        messages = self._mensajes_para_envio(message, system_prompt, origen=origen,
                                             efimero=efimero, prefijo=prefijo, anexo=anexo)
        if imagenes:
            # Ollama espera las imágenes en el propio mensaje, en base64 plano.
            messages[-1] = {**messages[-1], "images": imagenes}

        timeout = datos.ollama_timeout()
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            # keep_alive evita que Ollama descargue el modelo de VRAM entre
            # mensajes; sin esto se paga la recarga completa cada pocos minutos.
            "keep_alive": datos.ollama_keep_alive(),
            "options": opciones_ollama(datos.parametros_muestreo()),
        }
        self.ultimo_uso = {}

        def _call():
            try:
                return self._post_con_reintentos(
                    f"{self.url}/api/chat", json=payload,
                    timeout=(min(self.TIMEOUT_CONEXION, timeout), timeout),
                    consumir=self._consumir_ndjson, on_token=on_token,
                )
            except requests.exceptions.HTTPError as e:
                codigo = e.response.status_code if e.response is not None else "?"
                detalle = getattr(e, "detalle", "")
                return f"{self.ERROR} HTTP {codigo}" + (f": {detalle}" if detalle else ".")
            except requests.exceptions.ConnectionError:
                return (f"{self.ERROR} no pude conectar con {self._redactar(self.url)}. "
                        "¿Está corriendo «ollama serve»?")
            except requests.exceptions.Timeout:
                return (f"{self.ERROR} el modelo no respondió en {timeout}s. "
                        "Si es grande y arranca en frío, sube el timeout en Configuración.")
            except Exception as e:
                return f"{self.ERROR} {self._redactar(e)}"

        result = await asyncio.get_event_loop().run_in_executor(None, _call)
        self._registrar_respuesta(result, origen=origen, efimero=efimero)
        return result

    def _consumir_ndjson(self, respuesta, emitir: Callable[[str], None]) -> str:
        """Stream de /api/chat: una línea JSON por trozo, la última con `done`."""
        full_response = ""
        for line in respuesta.iter_lines():
            if self.cancel_flag:
                break
            if not line:
                continue
            try:
                chunk = json.loads(line.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if not isinstance(chunk, dict):
                continue
            if chunk.get("error"):
                return f"{self.ERROR} {self._redactar(_limpiar_detalle(chunk['error']))}"
            token = (chunk.get("message") or {}).get("content", "")
            if token:
                full_response += token
                emitir(token)
            if chunk.get("done"):
                self.ultimo_uso = self._uso_desde(chunk)
                break
        return full_response

    @staticmethod
    def _uso_desde(chunk: dict) -> dict:
        entrada = chunk.get("prompt_eval_count", 0) or 0
        salida = chunk.get("eval_count", 0) or 0
        # eval_duration viene en nanosegundos
        dur = (chunk.get("eval_duration") or 0) / 1e9
        return {
            "entrada": entrada,
            "salida": salida,
            "total": entrada + salida,
            "tokens_por_segundo": round(salida / dur, 1) if dur > 0 else None,
            "costo": 0.0,     # local = gratis
            "local": True,
        }

    def is_available(self) -> bool:
        try:
            return self._session.get(f"{self.url}/api/tags", timeout=3).status_code == 200
        except Exception:
            return False

    # ── Memoria del modelo ────────────────────────────────────────────────────
    def descargar_modelo(self, modelo: Optional[str] = None) -> bool:
        """
        «Liberar VRAM»: pide a Ollama que descargue el modelo ya
        (POST /api/generate con keep_alive 0 y sin prompt). El siguiente
        mensaje lo vuelve a cargar. Bloquea: desde la UI, `en_segundo_plano`.
        """
        return self._generate_sin_prompt(modelo, 0, 15)

    def precalentar(self, modelo: Optional[str] = None) -> bool:
        """
        Carga el modelo en VRAM sin generar nada (keep_alive de datos, 30m por
        defecto), para que el primer mensaje no pague el arranque en frío.
        Puede tardar lo que tarde en cargar: llámalo en segundo plano.
        """
        return self._generate_sin_prompt(modelo, datos.ollama_keep_alive(), datos.ollama_timeout())

    def _generate_sin_prompt(self, modelo: Optional[str], keep_alive, timeout: float) -> bool:
        nombre = modelo or self.model
        if not nombre:
            return False
        try:
            with _nueva_sesion() as s:
                r = s.post(f"{self.url}/api/generate",
                           json={"model": nombre, "keep_alive": keep_alive, "stream": False},
                           timeout=(min(self.TIMEOUT_CONEXION, timeout), timeout))
                return r.status_code == 200
        except requests.RequestException:
            return False


# ── OpenRouter (Nube / Automático) ────────────────────────────────────────────
class OpenRouterProvider(AIProvider):
    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
    ERROR = "Error OpenRouter:"
    TIMEOUT = (10.0, 60.0)          # (conectar, leer)

    def __init__(self, api_key: str, model: str):
        super().__init__()
        self.api_key = api_key
        self.model = model

    def configurar(self, api_key: str, model: str):
        self.api_key, self.model = api_key, model

    async def chat(self, message: str, system_prompt: str = "",
                   on_token: Callable = None, imagenes: Optional[List[str]] = None, *,
                   origen: Optional[str] = None, efimero: bool = False,
                   prefijo: str = "", anexo: str = "") -> str:
        falta = self._falta_configuracion()
        if falta:
            return falta

        messages = self._mensajes_para_envio(message, system_prompt, origen=origen,
                                             efimero=efimero, prefijo=prefijo, anexo=anexo)
        if imagenes:
            # Formato de contenido por partes de OpenAI (OpenRouter y compatibles).
            partes = [{"type": "text", "text": messages[-1]["content"]}]
            for img in imagenes:
                partes.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img}"},
                })
            messages[-1] = {"role": "user", "content": partes}
        self.ultimo_uso = {}

        def _call():
            try:
                error = self._preparar()
                if error:
                    return error
                return self._post_con_reintentos(
                    self._url_chat(), headers=self._cabeceras(), json=self._payload(messages),
                    timeout=self._timeout(), consumir=self._consumir_sse, on_token=on_token,
                )
            except requests.exceptions.HTTPError as e:
                codigo = e.response.status_code if e.response is not None else "?"
                return self._mensaje_http(codigo, getattr(e, "detalle", ""))
            except requests.exceptions.ConnectionError:
                return self._mensaje_sin_conexion()
            except requests.exceptions.Timeout:
                return f"{self.ERROR} el servidor no respondió a tiempo."
            except Exception as e:
                # p. ej. requests.InvalidHeader con «Bearer <clave>» dentro.
                return f"{self.ERROR} {self._redactar(e)}"

        result = await asyncio.get_event_loop().run_in_executor(None, _call)
        self._registrar_respuesta(result, origen=origen, efimero=efimero)
        return result

    # ── Ganchos que CompatProvider redefine ───────────────────────────────────
    def _falta_configuracion(self) -> str:
        """Mensaje si falta algo imprescindible (se comprueba antes de tocar el historial)."""
        return "" if self.api_key else "API key de OpenRouter no configurada."

    def _preparar(self) -> str:
        """Trabajo de red previo al POST (en el hilo del executor). Devuelve un error o ""."""
        return ""

    def _url_chat(self) -> str:
        return self.BASE_URL

    def _timeout(self):
        return self.TIMEOUT

    def _cabeceras(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://lunecd.local",
            "X-Title": "Lune CD",
        }

    def _payload(self, messages: List[dict]) -> dict:
        payload = {"model": self.model, "messages": messages, "stream": True}
        payload.update(campos_openai(datos.parametros_muestreo(), extendidos=True))
        # Pide que el chunk final traiga tokens y costo real.
        payload["usage"] = {"include": True}
        return payload

    def _mensaje_http(self, codigo, detalle: str = "") -> str:
        if codigo == 401:
            return f"{self.ERROR} API key inválida o revocada."
        if codigo == 402:
            return f"{self.ERROR} sin créditos en tu cuenta de OpenRouter."
        if codigo == 429:
            return f"{self.ERROR} demasiadas peticiones, espera un momento."
        return f"{self.ERROR} HTTP {codigo}."

    def _mensaje_sin_conexion(self) -> str:
        return f"{self.ERROR} sin conexión a internet."

    # ── Stream SSE (OpenAI) ───────────────────────────────────────────────────
    def _consumir_sse(self, respuesta, emitir: Callable[[str], None]) -> str:
        full_response = ""
        for line in respuesta.iter_lines():
            if self.cancel_flag:
                break
            if not line:
                continue
            decoded = line.decode("utf-8", errors="replace")
            # «data: {…}» o «data:{…}» (el espacio es opcional en SSE).
            if not decoded.startswith("data:"):
                continue
            data_str = decoded[5:].strip()
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
            except json.JSONDecodeError:
                continue
            if not isinstance(chunk, dict):
                continue
            if chunk.get("error"):
                if full_response:
                    break                   # conserva lo que ya llegó
                return f"{self.ERROR} {self._redactar(self._texto_error(chunk['error']))}"
            if chunk.get("usage"):
                self.ultimo_uso = self._uso_desde(chunk["usage"])
            opciones = chunk.get("choices") or []
            if not opciones or not isinstance(opciones[0], dict):
                continue
            token = (opciones[0].get("delta") or {}).get("content") or ""
            if token:
                full_response += token
                emitir(token)
        return full_response

    @staticmethod
    def _texto_error(error) -> str:
        if isinstance(error, dict):
            return _limpiar_detalle(error.get("message") or json.dumps(error))
        return _limpiar_detalle(error)

    @staticmethod
    def _uso_desde(uso: dict) -> dict:
        entrada = uso.get("prompt_tokens", 0) or 0
        salida = uso.get("completion_tokens", 0) or 0
        return {
            "entrada": entrada,
            "salida": salida,
            "total": uso.get("total_tokens", entrada + salida),
            "tokens_por_segundo": None,
            "costo": float(uso.get("cost", 0) or 0),
            "local": False,
        }

    def is_available(self) -> bool:
        return bool(self.api_key and self.api_key.strip())


# ── Compatible con OpenAI (LM Studio, llama.cpp, Groq, OpenAI, Together…) ────
class CompatProvider(OpenRouterProvider):
    """
    Cualquier servidor con /v1/chat/completions en streaming SSE. La clave es
    opcional (LM Studio no la pide); si no hay modelo configurado se usa el
    primero que devuelva /models (lo normal con LM Studio: el que está cargado).
    """
    ERROR = "Error API compatible:"

    def __init__(self, base_url: str, api_key: str = "", model: str = ""):
        super().__init__(api_key, model)
        self.base_url = base_url
        self._modelo_auto = ""

    def configurar(self, base_url: str, api_key: str = "", model: str = ""):
        if (base_url, api_key) != (self.base_url, self.api_key) or model != self.model:
            self._modelo_auto = ""
        self.base_url, self.api_key, self.model = base_url, api_key, model

    # ── Ganchos ───────────────────────────────────────────────────────────────
    def _falta_configuracion(self) -> str:
        if not endpoint_chat_compat(self.base_url):
            return (f"{self.ERROR} falta la URL del servidor "
                    "(Configuración → IA avanzada → API compatible).")
        return ""

    def _preparar(self) -> str:
        if self.model or self._modelo_auto:
            return ""
        modelos = self.listar_modelos()
        if not modelos:
            return (f"{self.ERROR} no hay modelo configurado y el servidor no devolvió "
                    "ninguno en /models. Escribe el nombre del modelo en Configuración.")
        self._modelo_auto = modelos[0]
        return ""

    def modelo_efectivo(self) -> str:
        return self.model or self._modelo_auto

    def _url_chat(self) -> str:
        return endpoint_chat_compat(self.base_url)

    def _timeout(self):
        return (10.0, float(datos.compat_timeout()))

    def _cabeceras(self) -> dict:
        cab = {"Content-Type": "application/json"}
        if self.api_key:
            cab["Authorization"] = f"Bearer {self.api_key}"
        return cab

    def _payload(self, messages: List[dict]) -> dict:
        modelo = self.modelo_efectivo()
        payload = {"model": modelo, "messages": messages, "stream": True}
        host = _host_de(self.base_url)
        es_openai = host == "api.openai.com"
        # OpenAI ya prefiere max_completion_tokens (sus modelos de razonamiento
        # rechazan max_tokens); el resto del mundo sigue con max_tokens.
        campos = campos_openai(
            datos.parametros_muestreo(), extendidos=es_host_local(self.base_url),
            nombre_repeat="repeat_penalty",
            campo_max="max_completion_tokens" if es_openai else "max_tokens",
        )
        if es_openai and es_razonamiento_openai(modelo):
            # o1/o3/o4 y gpt-5 dan 400 con cualquier temperature distinta de 1 o
            # con top_p; y lo que razonan sale del mismo tope de salida, así que
            # con el esfuerzo por defecto una respuesta corta podía llegar vacía.
            campos.pop("temperature", None)
            campos.pop("top_p", None)
            campos["reasoning_effort"] = "low"
        if host == "mistral.ai" or host.endswith(".mistral.ai"):
            # Mistral valida estricto (422 ante campos extra) y llama así a la semilla.
            if "seed" in campos:
                campos["random_seed"] = campos.pop("seed")
        payload.update(campos)
        return payload

    def _mensaje_http(self, codigo, detalle: str = "") -> str:
        cola = f": {detalle}" if detalle else ""
        if codigo in (401, 403):
            return f"{self.ERROR} el servidor rechazó la clave (HTTP {codigo}){cola}."
        if codigo == 402:
            return f"{self.ERROR} sin créditos en esa cuenta (HTTP 402){cola}."
        if codigo == 404:
            return (f"{self.ERROR} no encontrado (HTTP 404){cola}. Revisa la URL "
                    "(suele terminar en /v1) y el nombre del modelo.")
        if codigo == 429:
            return f"{self.ERROR} demasiadas peticiones, espera un momento{cola}."
        return f"{self.ERROR} HTTP {codigo}{cola}."

    def _mensaje_sin_conexion(self) -> str:
        return (f"{self.ERROR} no pude conectar con {_host_de(self.base_url) or self.base_url}. "
                "¿Está encendido el servidor?")

    def _uso_desde(self, uso: dict) -> dict:
        base = OpenRouterProvider._uso_desde(uso)
        base["local"] = es_host_local(self.base_url)
        return base

    # ── Descubrimiento ────────────────────────────────────────────────────────
    def _get_modelos(self, timeout: float):
        with _nueva_sesion() as s:
            return s.get(endpoint_modelos_compat(self.base_url),
                         headers=self._cabeceras(), timeout=timeout)

    @staticmethod
    def _ids_de(cuerpo) -> List[str]:
        lista = cuerpo.get("data") if isinstance(cuerpo, dict) else cuerpo
        if not isinstance(lista, list):
            return []
        ids = []
        for m in lista:
            ident = m.get("id") if isinstance(m, dict) else m
            if isinstance(ident, str) and ident.strip():
                ids.append(ident.strip())
        return ids

    def listar_modelos(self, timeout: float = 5.0) -> List[str]:
        """Ids de GET /models; [] si no hay URL, no responde o no lo implementa."""
        if not endpoint_modelos_compat(self.base_url):
            return []
        try:
            r = self._get_modelos(timeout)
            if r.status_code != 200:
                return []
            return self._ids_de(r.json())
        except (requests.RequestException, ValueError):
            return []

    def probar(self) -> Dict[str, Any]:
        """
        Diagnóstico para el botón «Probar conexión» de la UI:
        {ok, mensaje, modelos, url, ms}. No gasta tokens (solo GET /models).
        `ms` es la latencia de esa petición (None si no llegó respuesta).
        """
        url = endpoint_chat_compat(self.base_url)
        if not url:
            return {"ok": False, "mensaje": "Falta la URL del servidor.", "modelos": [], "url": "",
                    "ms": None}
        host = _host_de(self.base_url)
        try:
            inicio = time.monotonic()
            r = self._get_modelos(5.0)
            ms = round((time.monotonic() - inicio) * 1000)
        except requests.exceptions.SSLError:
            return self._resultado(False, f"Error de certificado TLS con {host}.", url)
        except requests.exceptions.ConnectionError:
            return self._resultado(False, f"No pude conectar con {host}. ¿Está encendido?", url)
        except requests.exceptions.Timeout:
            return self._resultado(False, f"{host} no respondió a tiempo.", url)
        except requests.RequestException as e:
            return self._resultado(False, _limpiar_detalle(self._redactar(e)), url)
        if r.status_code in (401, 403):
            return self._resultado(False, f"El servidor rechazó la clave (HTTP {r.status_code}).",
                                   url, ms=ms)
        if r.status_code == 404:
            return self._resultado(False, "No encontré /models en esa URL; suele terminar en /v1.",
                                   url, ms=ms)
        if r.status_code != 200:
            return self._resultado(False, f"El servidor respondió HTTP {r.status_code}.", url, ms=ms)
        try:
            modelos = self._ids_de(r.json())
        except ValueError:
            modelos = []
        if self.model and modelos and self.model not in modelos:
            aviso = f" Ojo: «{_limpiar_detalle(self.model, 80)}» no aparece en la lista."
        else:
            aviso = ""
        return self._resultado(True, f"Conectado: {len(modelos)} modelos.{aviso}", url,
                               modelos=modelos[:500], ms=ms)

    @staticmethod
    def _resultado(ok: bool, mensaje: str, url: str, modelos: Optional[List[str]] = None,
                   ms: Optional[int] = None) -> Dict[str, Any]:
        return {"ok": ok, "mensaje": mensaje, "modelos": modelos or [], "url": url, "ms": ms}

    def is_available(self) -> bool:
        """Vivo = responde a /models sin rechazar la clave (un 404 aún puede chatear)."""
        if not endpoint_modelos_compat(self.base_url):
            return False
        try:
            r = self._get_modelos(3.0)
            return r.status_code < 500 and r.status_code not in (401, 403)
        except Exception:
            return False


# ── Manager ───────────────────────────────────────────────────────────────────
class AIManager:
    def __init__(self):
        self.providers: Dict[str, AIProvider] = {
            "ollama": OllamaProvider(datos.ollama_url(), datos.ollama_model()),
            "openrouter": OpenRouterProvider(datos.openrouter_key(), datos.openrouter_model()),
        }
        self._sincronizar_compat()

    def _sincronizar_compat(self):
        """
        'compat' existe solo si hay URL configurada. El dict se sustituye (no se
        muta) para que un hilo que lo esté recorriendo, como el sondeo de
        proveedores, no reviente con «dictionary changed size».
        """
        url = datos.compat_url()
        actual = self.providers.get("compat")
        if url:
            if actual is None:
                nuevo = CompatProvider(url, datos.compat_key(), datos.compat_model())
                self.providers = {**self.providers, "compat": nuevo}
            else:
                actual.configurar(url, datos.compat_key(), datos.compat_model())
        elif actual is not None:
            self.providers = {k: v for k, v in self.providers.items() if k != "compat"}

    def reload_provider(self, provider_id: str = None):
        """
        Reaplica la configuración sin recrear los proveedores, para que un
        cambio de ajustes no borre la conversación en curso.
        """
        self.providers["ollama"].configurar(datos.ollama_url(), datos.ollama_model())
        self.providers["openrouter"].configurar(datos.openrouter_key(), datos.openrouter_model())
        self._sincronizar_compat()

    async def chat(self, message: str, system_prompt: str = "",
                   provider: Optional[str] = "openrouter", on_token: Callable = None,
                   imagenes: Optional[List[str]] = None, *,
                   origen: Optional[str] = None, efimero: bool = False,
                   prefijo: str = "", anexo: str = "") -> str:
        """
        origen   'usuario' | 'no_confiable' (None = usuario). Un turno no confiable
                 queda marcado en el historial (ver «HISTORIAL CON ORIGEN»).
        efimero  True: ni el prompt ni la respuesta entran en el historial.
        prefijo  delante del mensaje, también en el historial (la hora).
        anexo    detrás del mensaje enviado, NO en el historial (adjuntos, notas).
        """
        if provider not in self.providers:
            return f"Proveedor '{provider}' no disponible"
        prov = self.providers[provider]
        extra = {}
        if origen is not None:
            extra["origen"] = origen
        if efimero:
            extra["efimero"] = True
        if prefijo:
            extra["prefijo"] = prefijo
        if anexo:
            extra["anexo"] = anexo
        texto = await prov.chat(message, system_prompt, on_token=on_token, imagenes=imagenes,
                                **extra)
        # Red de seguridad: ninguna clave configurada sale en el texto (y en un
        # error, nada con forma de credencial).
        if not isinstance(texto, str) or not texto:
            return texto
        es_error = texto.startswith(getattr(prov, "ERROR", "Error")) or texto.startswith("Error")
        return redactar_secretos(texto, self.secretos(), formas=es_error)

    def secretos(self) -> tuple:
        """Las claves configuradas (para redactarlas de errores y registros)."""
        claves = []
        for p in list(self.providers.values()):
            claves.extend(getattr(p, "_secretos", lambda: ())())
        try:
            claves.extend([datos.openrouter_key(), datos.compat_key()])
        except Exception:
            pass
        return tuple(c for c in claves if c)

    def redactar(self, texto) -> str:
        """Texto de error sin claves (para mostrarlo, registrarlo o guardarlo)."""
        return redactar_secretos(texto, self.secretos())

    def contexto_contaminado(self, provider: Optional[str] = None) -> bool:
        """
        ¿El contexto que vio el modelo en el último turno (o el historial actual)
        lleva texto de terceros? Con un proveedor desconocido o sin decir, mira
        todos (fail-closed). El Ejecutor lo consulta al ejecutar las acciones.
        """
        provs = self.providers
        if provider and provider in provs:
            candidatos = [provs[provider]]
        else:
            candidatos = list(provs.values())
        for p in candidatos:
            fn = getattr(p, "contexto_contaminado", None)
            try:
                if callable(fn) and fn():
                    return True
            except Exception:
                return True
        return False

    def uso(self, provider: str) -> dict:
        p = self.providers.get(provider)
        return p.ultimo_uso if p else {}

    def clear_history(self, provider: Optional[str] = None):
        """Borra la conversación (y con ella las marcas de texto de terceros)."""
        if provider and provider in self.providers:
            self.providers[provider].clear_history()
        else:
            for p in self.providers.values():
                p.clear_history()

    def cargar_historial(self, mensajes: List[dict]):
        for p in self.providers.values():
            p.cargar_historial(mensajes)

    # ── IA avanzada ───────────────────────────────────────────────────────────
    def descargar_modelo(self) -> bool:
        """«Liberar VRAM» del modelo local. Bloquea: úsalo con `en_segundo_plano`."""
        return self.providers["ollama"].descargar_modelo()

    def precalentar(self) -> bool:
        """Carga el modelo local en VRAM sin generar. Bloquea: `en_segundo_plano`."""
        return self.providers["ollama"].precalentar()

    def probar_compat(self) -> Dict[str, Any]:
        """Prueba la configuración 'compat' guardada, esté registrada o no."""
        prov = self.providers.get("compat")
        if prov is None:
            prov = CompatProvider(datos.compat_url(), datos.compat_key(), datos.compat_model())
        return prov.probar()
