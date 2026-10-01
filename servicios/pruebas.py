"""
servicios/pruebas.py — «¿Esto funciona de verdad?»: la prueba de cada apartado, sin Qt.

La usan los botones «Probar» de Ajustes (web: ui/web_bridge.py; nativa: ui/settings_panel.py
con los hilos de ui/pruebas_qt.py), `/probar` de patata y las comprobaciones de
servicios/diagnostico.py («Comprobar que todo funciona» y `/diagnostico`).

Cada prueba devuelve un dict con, al menos, {ok, mensaje}:
    ok True  = funciona · False = no funciona (y el mensaje dice qué hacer) ·
    ok None  = sin configurar o no aplica aquí (no cuenta como fallo).
Los mensajes van en la voz de Lune, cortos y con el siguiente paso.

SECRETOS: la clave de OpenRouter y el token de Telegram nunca salen en un mensaje ni en un
registro. Los errores de requests llevan la URL (y la de Telegram lleva el token dentro):
por eso los fallos de red se cuentan con frases fijas (`_motivo_red`) y todo lo que sale
pasa además por `tapar()`. Tampoco se enseña la «label» que devuelve OpenRouter (lleva un
trozo de la clave).

`http` es como requests.get(url, headers=…, timeout=…) → respuesta con status_code y json();
los tests pasan uno falso. Sin él, requests de verdad (importado aquí dentro: importar este
módulo no carga nada pesado).
"""
from __future__ import annotations

import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

TIMEOUT_S = 8.0
USER_AGENT = "LuneCD/pruebas"
URL_INTERNET = "https://api.github.com/"
URL_OPENROUTER_CLAVE = "https://openrouter.ai/api/v1/key"
URL_OPENROUTER_MODELOS = "https://openrouter.ai/api/v1/models"
URL_TELEGRAM = "https://api.telegram.org/bot{token}/getMe"
MODELO_AUTO = "openrouter/auto"
# Sufijos de OpenRouter que eligen cómo se enruta, no otro modelo (no salen en /models).
SUFIJOS_RUTA = ("nitro", "floor", "online", "thinking", "extended")
# Por debajo de esto, guardar chats, memoria y configuración empieza a fallar.
MB_MINIMOS = 300
# Lo que pesa cada modelo de Whisper la primera vez (aprox., para avisar antes de bajarlo).
WHISPER_MB = {"tiny": 75, "base": 145, "small": 465, "medium": 1500, "large-v3": 3000}
CARPETA_BOT_TG = "telegram-bot-or"
TAPA = "•••"

# Un token de @BotFather: «123456789:AA…». Solo eso va a la URL de Telegram.
_TOKEN_TG = re.compile(r"^\d{5,15}:[A-Za-z0-9_-]{20,80}$")
_ID_TG = re.compile(r"^\d{1,20}$")


# ── Utilidades ────────────────────────────────────────────────────────────────

def tapar(texto: Any, *secretos: Any) -> str:
    """`texto` sin ninguno de los `secretos` (cada aparición cambia por •••)."""
    t = "" if texto is None else str(texto)
    for s in secretos:
        s = str(s or "").strip()
        if len(s) >= 4:
            t = t.replace(s, TAPA)
    return t


def _corto(texto: Any, maximo: int = 300) -> str:
    t = " ".join(str(texto or "").split())
    return t if len(t) <= maximo else t[: maximo - 1] + "…"


def _http_real() -> Callable[..., Any]:
    import requests
    return requests.get


def _motivo_red(e: BaseException) -> str:
    """Un fallo de red en una frase fija (nunca el texto de la excepción: lleva la URL)."""
    nombres = {c.__name__ for c in type(e).__mro__}
    if nombres & {"SSLError", "SSLCertVerificationError"}:
        return "falló el certificado de seguridad (¿un antivirus o un proxy en medio?)"
    if nombres & {"ConnectTimeout", "ReadTimeout", "Timeout", "TimeoutError", "timeout"}:
        return "no respondió a tiempo"
    if nombres & {"ProxyError"}:
        return "el proxy no me dejó pasar"
    if nombres & {"ConnectionError", "ConnectionRefusedError", "ConnectionResetError", "gaierror",
                  "NewConnectionError", "MaxRetryError"}:
        return "no hay conexión"
    if nombres & {"InvalidHeader", "InvalidURL"}:
        return "la clave o la dirección tienen caracteres que no valen"
    return "algo falló por el camino"


def _pedir(http: Optional[Callable[..., Any]], url: str, *, headers: Optional[Dict[str, str]] = None,
           timeout: float = TIMEOUT_S) -> Tuple[Any, str, Optional[int]]:
    """GET → (respuesta, "", ms) o (None, motivo, None). Nunca lanza."""
    cab = {"User-Agent": USER_AGENT}
    cab.update(headers or {})
    try:
        get = http or _http_real()
        inicio = time.monotonic()
        r = get(url, headers=cab, timeout=timeout)
        return r, "", round((time.monotonic() - inicio) * 1000)
    except Exception as e:          # noqa: BLE001 (requests, ssl, socket…: todo es «no llegué»)
        return None, _motivo_red(e), None


def _codigo(r: Any) -> int:
    try:
        return int(getattr(r, "status_code", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _json(r: Any) -> Dict[str, Any]:
    try:
        d = r.json()
    except Exception:               # noqa: BLE001
        return {}
    return d if isinstance(d, dict) else {}


def _tamano(n_bytes: float) -> str:
    gb = n_bytes / (1024 ** 3)
    if gb >= 1:
        return f"{gb:.1f} GB".replace(".0 GB", " GB")
    return f"{int(n_bytes // (1024 ** 2))} MB"


# ── Internet ──────────────────────────────────────────────────────────────────

def probar_internet(http: Optional[Callable[..., Any]] = None, timeout: float = 6.0) -> Dict[str, Any]:
    """¿Llego a internet? (GitHub, que es de donde salen además las actualizaciones)."""
    r, motivo, ms = _pedir(http, URL_INTERNET, headers={"Accept": "application/vnd.github+json"},
                           timeout=timeout)
    if r is None:
        return {"ok": False, "ms": None,
                "mensaje": f"No llego a internet ({motivo}). Revisa la Wi-Fi o el cable; si usas un proxy "
                           "o un cortafuegos, déjame pasar."}
    # Cualquier respuesta (también un 403 por pedir demasiado) quiere decir que hay red.
    return {"ok": True, "ms": ms, "mensaje": f"Hay internet: GitHub me contestó en {ms} ms."}


# ── Nube (OpenRouter) ─────────────────────────────────────────────────────────

def _modelo_en_lista(modelo: str, ids: Iterable[str]) -> bool:
    ids = set(ids)
    if modelo in ids:
        return True
    base, _, sufijo = modelo.partition(":")
    return bool(sufijo) and sufijo.lower() in SUFIJOS_RUTA and base in ids


def probar_openrouter(clave: Any, modelo: Any = "", *, http: Optional[Callable[..., Any]] = None,
                      timeout: float = TIMEOUT_S, comprobar_modelo: bool = True) -> Dict[str, Any]:
    """La clave con GET /api/v1/key (no gasta tokens) y, si hay modelo, que exista en
    /api/v1/models. → {ok, mensaje, modelo_ok (True|False|None), gratis, ms}."""
    clave = str(clave or "").strip()
    modelo = str(modelo or "").strip()
    base = {"modelo_ok": None, "gratis": None, "ms": None}

    def fin(ok, mensaje, **extra):
        return {**base, **extra, "ok": ok, "mensaje": _corto(tapar(mensaje, clave))}

    if not clave:
        return fin(None, "Sin clave de OpenRouter: si quieres que piense en la nube, pega la tuya "
                         "(openrouter.ai/keys).")
    if any(c.isspace() or ord(c) < 32 for c in clave) or "•" in clave:
        return fin(False, "Esa clave lleva espacios o saltos de línea: cópiala otra vez, sin nada más.")
    r, motivo, ms = _pedir(http, URL_OPENROUTER_CLAVE, headers={"Authorization": f"Bearer {clave}"},
                           timeout=timeout)
    if r is None:
        return fin(False, f"No pude hablar con OpenRouter ({motivo}). ¿Hay internet?")
    codigo = _codigo(r)
    if codigo in (401, 403):
        return fin(False, "OpenRouter no reconoce esa clave: cópiala otra vez desde openrouter.ai/keys.", ms=ms)
    if codigo == 429:
        return fin(False, "OpenRouter me pide que espere un poco (muchas pruebas seguidas). Vuelve a probar "
                          "en un minuto.", ms=ms)
    if codigo != 200:
        return fin(False, f"OpenRouter respondió HTTP {codigo}: prueba otra vez en un rato.", ms=ms)
    info = _json(r).get("data")
    info = info if isinstance(info, dict) else {}
    gratis = info.get("is_free_tier") if isinstance(info.get("is_free_tier"), bool) else None
    queda = info.get("limit_remaining")
    queda = queda if isinstance(queda, (int, float)) and not isinstance(queda, bool) else None
    if queda is not None and queda <= 0:
        return fin(False, "Tu clave funciona, pero ya no le queda saldo: recarga en openrouter.ai/credits "
                          "o usa un modelo gratis (los que acaban en :free).", gratis=gratis, ms=ms)
    extra = " (cuenta gratuita)" if gratis else ""
    if queda is not None:
        extra += f" · te quedan ${queda:.2f}"

    modelo_ok = None
    nota_modelo = ""
    if comprobar_modelo and modelo and modelo != MODELO_AUTO:
        r2, _motivo2, _ = _pedir(http, URL_OPENROUTER_MODELOS, timeout=timeout)
        lista = _json(r2).get("data") if r2 is not None and _codigo(r2) == 200 else None
        if isinstance(lista, list):
            ids = [str(m.get("id")) for m in lista if isinstance(m, dict) and m.get("id")]
            modelo_ok = _modelo_en_lista(modelo, ids)
            if not modelo_ok:
                return fin(False, f"Tu clave funciona, pero no encuentro el modelo «{_corto(modelo, 80)}» en "
                                  f"OpenRouter: revisa el nombre (o pon {MODELO_AUTO}, que elige solo).",
                           modelo_ok=False, gratis=gratis, ms=ms)
            nota_modelo = f" y «{_corto(modelo, 80)}» existe"
        else:
            nota_modelo = " (el modelo no lo pude comprobar ahora)"
    elif modelo == MODELO_AUTO or not modelo:
        modelo_ok = True
        nota_modelo = f" y con {MODELO_AUTO} elijo yo el modelo" if modelo else ""
    return fin(True, f"Tu clave de OpenRouter funciona{extra}{nota_modelo}.", modelo_ok=modelo_ok,
               gratis=gratis, ms=ms)


# ── Local (Ollama) ────────────────────────────────────────────────────────────

def probar_ollama(url: Any, modelo: Any = "", *,
                  listar: Optional[Callable[[str], Tuple[bool, List[str], str]]] = None) -> Dict[str, Any]:
    """¿Responde Ollama en `url` y tiene `modelo`? (servicios/ollama_client.listar_modelos)
    → {ok, mensaje, modelos, url}."""
    from servicios import ollama_client
    url = str(url or "").strip()
    modelo = str(modelo or "").strip()
    url_n = ollama_client.normalizar_url(url)
    try:
        ok, modelos, mensaje = (listar or ollama_client.listar_modelos)(url)
    except Exception as e:          # noqa: BLE001 (listar_modelos no lanza; uno falso, quizá)
        ok, modelos, mensaje = False, [], _motivo_red(e)
    modelos = [str(m) for m in (modelos or []) if m]
    if not ok:
        return {"ok": False, "modelos": [], "url": url_n,
                "mensaje": _corto(f"No encuentro Ollama en {url_n}: {mensaje} Ábrelo (o «ollama serve») "
                                  "o revisa la dirección.")}
    if not modelos:
        return {"ok": False, "modelos": [], "url": url_n,
                "mensaje": f"Ollama responde en {url_n}, pero no tiene modelos: baja uno con "
                           "«ollama pull qwen2.5:7b»."}
    n = len(modelos)
    lista = f"{n} modelo{'s' if n != 1 else ''}"
    if modelo:
        if modelo in modelos or f"{modelo}:latest" in modelos:
            return {"ok": True, "modelos": modelos, "url": url_n,
                    "mensaje": f"Ollama responde en {url_n} ({lista}) y «{_corto(modelo, 80)}» está listo."}
        return {"ok": False, "modelos": modelos, "url": url_n,
                "mensaje": _corto(f"Ollama responde ({lista}), pero no tiene «{modelo}»: elige uno de la lista "
                                  f"o bájalo con «ollama pull {modelo}».")}
    return {"ok": True, "modelos": modelos, "url": url_n,
            "mensaje": f"Ollama responde en {url_n} con {lista}: elige uno."}


# ── Telegram ──────────────────────────────────────────────────────────────────

def probar_token_telegram(token: Any, *, http: Optional[Callable[..., Any]] = None,
                          timeout: float = TIMEOUT_S) -> Dict[str, Any]:
    """getMe con el token (sin gastar nada ni mandar mensajes). → {ok, mensaje, bot}."""
    token = str(token or "").strip()

    def fin(ok, mensaje, bot=""):
        return {"ok": ok, "bot": bot, "mensaje": _corto(tapar(mensaje, token))}

    if not token or "TU_TOKEN" in token:
        return fin(None, "Sin token: pídeselo a @BotFather en Telegram (/newbot) y pégalo aquí.")
    if not _TOKEN_TG.match(token):
        return fin(False, "Ese token no tiene la forma de los de @BotFather (números, dos puntos y letras): "
                          "cópialo otra vez entero.")
    r, motivo, _ms = _pedir(http, URL_TELEGRAM.format(token=token), timeout=timeout)
    if r is None:
        return fin(False, f"No pude hablar con Telegram ({motivo}). ¿Hay internet?")
    codigo = _codigo(r)
    if codigo in (401, 404):
        return fin(False, "Telegram no reconoce ese token: pídeselo otra vez a @BotFather (/token).")
    if codigo == 429:
        return fin(False, "Telegram me pide que espere un poco. Vuelve a probar en un minuto.")
    d = _json(r)
    if codigo != 200 or d.get("ok") is not True:
        return fin(False, f"Telegram respondió HTTP {codigo}: prueba otra vez en un rato.")
    yo = d.get("result") if isinstance(d.get("result"), dict) else {}
    usuario = re.sub(r"[^A-Za-z0-9_]", "", str(yo.get("username") or ""))[:40]
    if usuario:
        return fin(True, f"Tu bot @{usuario} responde.", usuario)
    return fin(True, "Tu bot responde.")


def probar_id_telegram(admin_id: Any) -> Dict[str, Any]:
    """Tu ID de Telegram (solo números; con él, solo tú usas el bot)."""
    aid = str(admin_id or "").strip()
    if not aid:
        return {"ok": None, "mensaje": "Sin tu ID cualquiera podría hablarle a tu bot: escríbele /id y pega "
                                       "aquí el número."}
    if not _ID_TG.match(aid):
        return {"ok": False, "mensaje": "Tu ID de Telegram son solo números: escríbele /id a tu bot y copia el "
                                        "número que te da."}
    return {"ok": True, "mensaje": "Tu ID está bien puesto: el bot solo te hace caso a ti."}


def probar_node(estado: Optional[Callable[[], Dict[str, Any]]] = None, *, necesario: bool = True) -> Dict[str, Any]:
    """Node.js 18+ (lo necesitan los bots de Telegram y de Minecraft). Si no hace falta
    (`necesario=False`: ningún bot configurado) y falta, no cuenta como fallo."""
    try:
        if estado is None:
            from servicios import actualizador
            estado = actualizador.estado_node
        e = estado() or {}
    except Exception as e:          # noqa: BLE001
        e = {"ok": False, "version": "", "mensaje": f"No pude mirar Node.js ({type(e).__name__})."}
    if e.get("ok"):
        return {"ok": True, "version": str(e.get("version") or ""),
                "mensaje": f"Node.js {e.get('version') or ''} está listo para los bots.".replace("  ", " ")}
    version = str(e.get("version") or "")
    if version:
        texto = f"Tu Node.js ({version}) es viejo: instala el 18 o más nuevo desde nodejs.org."
    else:
        texto = "Falta Node.js 18 o más nuevo: instálalo desde nodejs.org y reinicia Lune."
    if not necesario:
        return {"ok": None, "version": version,
                "mensaje": texto + " Solo lo necesitan los bots de Telegram y Minecraft."}
    return {"ok": False, "version": version, "mensaje": texto}


def _carpeta_bot_real() -> bool:
    """La carpeta del bot lista: TelegramBotWorker.preparar_carpeta() en la app (con Qt);
    sin Qt cargado (patata, la comprobación), lo mismo a mano: copia el código del bot a su
    carpeta de datos (servicios/copia_bots) y mira que esté."""
    if "PyQt6.QtCore" in sys.modules:
        try:
            from servicios.telegram_worker import TelegramBotWorker
            return bool(TelegramBotWorker.preparar_carpeta())
        except ImportError:
            pass
    from nucleo import rutas
    from servicios import copia_bots
    origen, destino = rutas.recurso(CARPETA_BOT_TG), rutas.dato(CARPETA_BOT_TG)
    if Path(origen).is_dir():
        copia_bots.sincronizar(origen, destino)
    return Path(destino).is_dir()


def probar_telegram(token: Any, admin_id: Any = "", *, http: Optional[Callable[..., Any]] = None,
                    node: Optional[Callable[[], Dict[str, Any]]] = None,
                    carpeta: Optional[Callable[[], bool]] = None,
                    timeout: float = TIMEOUT_S) -> Dict[str, Any]:
    """Todo lo que necesita el bot: el token (getMe), tu ID, Node 18+ y su carpeta.
    → {ok, mensaje, bot, items: [{id, nombre, ok, detalle}]}."""
    token = str(token or "").strip()
    t = probar_token_telegram(token, http=http, timeout=timeout)
    items = [{"id": "token", "nombre": "Token del bot", "ok": t["ok"], "detalle": t["mensaje"]}]
    a = probar_id_telegram(admin_id)
    items.append({"id": "id", "nombre": "Tu ID de Telegram", "ok": a["ok"], "detalle": a["mensaje"]})
    n = probar_node(node, necesario=True)
    items.append({"id": "node", "nombre": "Node.js 18+", "ok": n["ok"], "detalle": n["mensaje"]})
    try:
        hay = bool((carpeta or _carpeta_bot_real)())
    except Exception:               # noqa: BLE001
        hay = False
    items.append({"id": "carpeta", "nombre": "Carpeta del bot", "ok": hay,
                  "detalle": "La carpeta del bot está en su sitio." if hay
                  else f"No encuentro la carpeta del bot ({CARPETA_BOT_TG}): reinstala Lune."})
    for i in items:
        i["detalle"] = _corto(tapar(i["detalle"], token))
    fallos = [i for i in items if i["ok"] is False]
    if fallos:
        ok, mensaje = False, fallos[0]["detalle"]
    elif t["ok"] is None:
        ok, mensaje = None, t["mensaje"]
    else:
        ok = True
        quien = f"tu bot @{t['bot']}" if t.get("bot") else "tu bot"
        mensaje = f"Todo listo: {quien} responde, Node.js está al día y la carpeta del bot, en su sitio."
        if a["ok"] is None:
            mensaje += " Falta tu ID (escríbele /id) para que solo te haga caso a ti."
    return {"ok": ok, "mensaje": _corto(tapar(mensaje, token)), "bot": t.get("bot", ""), "items": items}


# ── Tu equipo: sonido, dictado y disco ────────────────────────────────────────

def probar_audio(sd: Any = None) -> Dict[str, Any]:
    """¿Veo micrófono y altavoces? (sounddevice) → {ok, mensaje, entradas, salidas}.
    Sin alguno de los dos no es un fallo de Lune (ok None): solo no podré dictar u oírme."""
    if sd is None:
        try:
            import sounddevice as sd
        except Exception:           # noqa: BLE001 (ImportError u OSError de PortAudio)
            return {"ok": False, "entradas": 0, "salidas": 0,
                    "mensaje": "No puedo usar el sonido: falta PortAudio (sounddevice)."}
    try:
        dispositivos = list(sd.query_devices())
    except Exception as e:          # noqa: BLE001
        return {"ok": None, "entradas": 0, "salidas": 0,
                "mensaje": _corto(f"No pude ver tus dispositivos de sonido ({type(e).__name__}).")}
    # Windows repite cada aparato una vez por API (MME, DirectSound, WASAPI…): se cuentan los de
    # MME, como la lista de Ajustes (servicios/voz_entrada.listar_entradas).
    try:
        mme = next((i for i, a in enumerate(sd.query_hostapis()) if "MME" in str(a.get("name", ""))), None)
    except Exception:               # noqa: BLE001
        mme = None
    if mme is not None:
        dispositivos = [d for d in dispositivos if isinstance(d, dict) and d.get("hostapi") == mme]
    entradas = {str(d.get("name", "")).strip() for d in dispositivos
                if isinstance(d, dict) and (d.get("max_input_channels") or 0) > 0}
    salidas = {str(d.get("name", "")).strip() for d in dispositivos
               if isinstance(d, dict) and (d.get("max_output_channels") or 0) > 0}
    ne, ns = len(entradas - {""}), len(salidas - {""})
    cuenta = (f"{ne} micrófono{'s' if ne != 1 else ''} y {ns} salida{'s' if ns != 1 else ''}")
    if not ne and not ns:
        return {"ok": None, "entradas": 0, "salidas": 0,
                "mensaje": "No veo ni micrófono ni altavoces: conecta unos si quieres oírme o dictarme."}
    if not ns:
        return {"ok": None, "entradas": ne, "salidas": 0,
                "mensaje": f"Veo {cuenta}: sin altavoces no me vas a oír."}
    if not ne:
        return {"ok": None, "entradas": 0, "salidas": ns,
                "mensaje": f"Veo {cuenta}: para dictarme o llamarme, conecta un micrófono."}
    return {"ok": True, "entradas": ne, "salidas": ns, "mensaje": f"Veo {cuenta}."}


def probar_whisper(modelo: Any = "base", *, descargado: Optional[Callable[[str], bool]] = None,
                   faltan: Optional[List[str]] = None) -> Dict[str, Any]:
    """¿Está bajado el modelo de Whisper del dictado? Si no, no es un fallo: se baja la
    primera vez que dictas (y aquí se dice cuánto pesa)."""
    modelo = str(modelo or "base").strip() or "base"
    mb = WHISPER_MB.get(modelo)
    peso = f" (~{mb} MB)" if mb else ""
    try:
        if faltan is None or descargado is None:
            from servicios import voz_entrada
            faltan = voz_entrada.dependencias_faltantes() if faltan is None else faltan
            descargado = descargado or voz_entrada.modelo_descargado
        if "faster-whisper" in (faltan or []):
            return {"ok": None, "descargado": False, "mb": mb,
                    "mensaje": "El dictado no está disponible aquí (falta faster-whisper)."}
        listo = bool(descargado(modelo))
    except Exception as e:          # noqa: BLE001
        return {"ok": None, "descargado": False, "mb": mb,
                "mensaje": _corto(f"No pude mirar el modelo de dictado ({type(e).__name__}).")}
    if listo:
        return {"ok": True, "descargado": True, "mb": mb,
                "mensaje": f"El modelo «{modelo}» del dictado ya está descargado."}
    return {"ok": None, "descargado": False, "mb": mb,
            "mensaje": f"El modelo «{modelo}» del dictado se descarga la primera vez que me dictes{peso}; "
                       "necesita internet y tarda un poco."}


def espacio_libre(ruta: Any, *, uso: Optional[Callable[[str], Any]] = None,
                  minimo_mb: int = MB_MINIMOS) -> Dict[str, Any]:
    """Espacio libre donde guardo tus cosas. → {ok, mensaje, libre_mb}."""
    p = Path(ruta)
    while not p.exists() and p.parent != p:
        p = p.parent
    try:
        u = (uso or shutil.disk_usage)(str(p))          # (total, usado, libre)
        libre = float(u.free if hasattr(u, "free") else u[2])
    except Exception as e:          # noqa: BLE001
        return {"ok": None, "libre_mb": None,
                "mensaje": _corto(f"No pude mirar el espacio libre ({type(e).__name__}).")}
    libre_mb = int(libre // (1024 ** 2))
    texto = _tamano(libre)
    if libre_mb < minimo_mb:
        return {"ok": False, "libre_mb": libre_mb,
                "mensaje": f"Solo quedan {texto} libres donde guardo tus cosas: libera espacio o me costará "
                           "guardar los chats y la memoria."}
    return {"ok": True, "libre_mb": libre_mb, "mensaje": f"{texto} libres donde guardo tus cosas."}


def probar_salida(voice: Any, nombre: Any = None) -> Dict[str, Any]:
    """Un tono por la salida `nombre` (None = la actual) con el VoiceEngine de la app o de
    patata. → {ok, mensaje}."""
    if voice is None or not getattr(voice, "available", False):
        return {"ok": False, "mensaje": "No tengo motor de voz para sonar (falta pygame o no hay tarjeta de sonido)."}
    aviso = ""
    if nombre is not None:
        nombre = str(nombre or "").strip()
        if nombre != getattr(voice, "salida_actual", "") and not voice.aplicar_salida(nombre):
            aviso = f" No encontré «{_corto(nombre, 60)}»: suena por la del sistema."
    try:
        ok = bool(voice.probar_salida())
    except Exception:               # noqa: BLE001
        ok = False
    if not ok:
        return {"ok": False, "mensaje": "No pude sonar por esa salida." + aviso}
    donde = getattr(voice, "salida_actual", "") or "la salida del sistema"
    return {"ok": True, "mensaje": f"Sonando un tono por «{_corto(donde, 60)}»… ¿me oyes?{aviso}"}


__all__ = ("tapar", "probar_internet", "probar_openrouter", "probar_ollama", "probar_token_telegram",
           "probar_id_telegram", "probar_node", "probar_telegram", "probar_audio", "probar_whisper",
           "espacio_libre", "probar_salida", "WHISPER_MB", "MB_MINIMOS", "MODELO_AUTO")
