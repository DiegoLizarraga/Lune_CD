"""
Tests de servicios/diagnostico.py (la comprobación de `LunePatata.exe --comprobar`) con
recursos, carpetas e imports FALSOS: nada de importar PyQt6 ni Whisper de verdad.
"""
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from servicios import diagnostico as D  # noqa: E402

CPP = ("ctranslate2", "onnxruntime", "av", "faster_whisper")


def _recursos(raiz: Path) -> Path:
    """Un árbol con todo lo que diagnostico espera que traiga Lune."""
    for rel in ("ui_web/ui_kits/lune-desktop/index.html", "assets/inicio.mp4", "assets/lune_icon.ico",
                "fonts/SpaceGrotesk.ttf", "lune_face/lune_normal.png", "sonidos/default/pack.json",
                "datos.example.json"):
        f = raiz / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x", encoding="utf-8")
    return raiz


def _importador(tmp: Path, faltan=(), orden=None, sin_vad=False):
    assets = tmp / "fw_assets"
    assets.mkdir(exist_ok=True)
    if not sin_vad:
        (assets / "silero_vad_v6.onnx").write_bytes(b"onnx")
    ffmpeg = tmp / "ffmpeg.exe"
    ffmpeg.write_bytes(b"MZ")
    cacert = tmp / "cacert.pem"
    cacert.write_text("-----", encoding="utf-8")
    modulos = {
        "ctranslate2": SimpleNamespace(__version__="4.8.2",
                                       get_supported_compute_types=lambda d: {"int8", "float32"}),
        "onnxruntime": SimpleNamespace(__version__="1.30.0",
                                       get_available_providers=lambda: ["CPUExecutionProvider"]),
        "faster_whisper.utils": SimpleNamespace(get_assets_path=lambda: str(assets)),
        "huggingface_hub": SimpleNamespace(__version__="1.16.1", snapshot_download=lambda *a, **k: None),
        "sounddevice": SimpleNamespace(__version__="0.5.6", get_portaudio_version=lambda: (1, "PortAudio V19")),
        "imageio_ffmpeg": SimpleNamespace(get_ffmpeg_exe=lambda: str(ffmpeg)),
        "certifi": SimpleNamespace(where=lambda: str(cacert)),
        "pygame": SimpleNamespace(__version__="2.6.1", get_sdl_version=lambda: (2, 28, 4)),
    }

    def importar(nombre):
        if orden is not None:
            orden.append(nombre)
        if nombre in faltan:
            raise ImportError(f"No module named '{nombre}'")
        return modulos.get(nombre, SimpleNamespace(__version__="1.0"))
    return importar


def _ctx(tmp: Path, **kw) -> D.Contexto:
    base = dict(recursos=_recursos(tmp / "rec"), datos=tmp / "datos", local=tmp / "local",
                windows=True, precargar=lambda: "precargados de System32: x",
                msvc_cargada=lambda: (r"C:\Windows\System32\msvcp140.dll", (14, 44, 35211, 0)))
    base.update(kw)
    if "importar" not in base:
        base["importar"] = _importador(tmp)
    return D.Contexto(**base)


def _item(res, id_):
    return next(i for i in res["items"] if i["id"] == id_)


def test_todo_bien(tmp_path):
    res = D.comprobar(ctx=_ctx(tmp_path))
    assert res["ok"] is True, D.informe(res)
    assert res["modo"] in ("instalada", "codigo")
    assert res["version"] and res["version"] != "?"
    ids = [i["id"] for i in res["items"]]
    assert len(ids) == len(set(ids))
    for i in res["items"]:
        assert set(i) == {"id", "seccion", "nombre", "ok", "detalle"}
        assert i["seccion"] in D.SECCIONES
        assert i["ok"] in (True, False, None)
    json.dumps(res)                                            # se puede pasar a JSON tal cual
    assert {"recursos", "datos", "modulos"} <= {i["seccion"] for i in res["items"]}
    assert "silero_vad_v6.onnx" in _item(res, "faster_whisper")["detalle"]
    assert "CPU:" in _item(res, "ctranslate2")["detalle"]


def test_comprueba_lo_que_pide_el_paquete(tmp_path):
    res = D.comprobar(ctx=_ctx(tmp_path))
    ids = {i["id"] for i in res["items"]}
    assert {"piel_web", "video_inicio", "fuentes", "caritas", "sonidos", "plantilla_datos", "carpeta_datos",
            "qt_webengine", "qt_multimedia", "numpy", "sounddevice", "pygame", "edge_tts", "gtts", "pypdf",
            "docx", "pil", "psutil", "zeroconf", "win32gui", "comtypes", "ffmpeg", "faster_whisper",
            "ctranslate2", "onnxruntime", "av", "websockets", "requests"} <= ids


def test_un_modulo_que_falta_falla_sin_tumbar_el_resto(tmp_path):
    res = D.comprobar(ctx=_ctx(tmp_path, importar=_importador(tmp_path, faltan={"PyQt6.QtWebEngineWidgets"})))
    assert res["ok"] is False
    web = _item(res, "qt_webengine")
    assert web["ok"] is False and "ImportError" in web["detalle"]
    assert _item(res, "qt_multimedia")["ok"] is True            # sigue con los demás
    assert _item(res, "requests")["ok"] is True


def test_una_dll_que_no_carga_tambien_se_apunta(tmp_path):
    def importar(nombre):
        if nombre == "ctranslate2":
            raise OSError("[WinError 126] No se puede encontrar el módulo especificado")
        return _importador(tmp_path)(nombre)
    res = D.comprobar(ctx=_ctx(tmp_path, importar=importar))
    assert _item(res, "ctranslate2")["ok"] is False
    assert "OSError" in _item(res, "ctranslate2")["detalle"]


def test_orden_precarga_luego_cpp_luego_qt(tmp_path):
    """El crash de MSVCP140: primero la precarga, luego lo de C++ y después PyQt6."""
    orden = []
    ctx = _ctx(tmp_path, importar=_importador(tmp_path, orden=orden),
               precargar=lambda: orden.append("PRECARGA") or "hecho")
    D.comprobar(ctx=ctx)
    assert orden[0] == "PRECARGA"
    primer_qt = min(i for i, n in enumerate(orden) if n.startswith("PyQt6"))
    for m in CPP:
        assert orden.index(m) < primer_qt, orden
    assert all(not n.startswith("PyQt6") for n in orden[:primer_qt])


def test_recurso_que_falta(tmp_path):
    ctx = _ctx(tmp_path)
    (ctx.recursos / "assets" / "inicio.mp4").unlink()
    res = D.comprobar(ctx=ctx)
    assert _item(res, "video_inicio")["ok"] is False
    assert "assets/inicio.mp4" in _item(res, "video_inicio")["detalle"]
    assert res["ok"] is False


def test_carpeta_vacia_de_fuentes_falla(tmp_path):
    ctx = _ctx(tmp_path)
    (ctx.recursos / "fonts" / "SpaceGrotesk.ttf").unlink()
    assert _item(D.comprobar(ctx=ctx), "fuentes")["ok"] is False


def test_carpeta_de_datos_que_no_se_puede_escribir(tmp_path):
    archivo = tmp_path / "soy_un_archivo"
    archivo.write_text("x", encoding="utf-8")
    res = D.comprobar(ctx=_ctx(tmp_path, datos=archivo))
    assert _item(res, "carpeta_datos")["ok"] is False
    assert res["ok"] is False


def test_la_prueba_de_escritura_no_deja_basura(tmp_path):
    ctx = _ctx(tmp_path)
    D.comprobar(ctx=ctx)
    assert list(ctx.datos.iterdir()) == [] and list(ctx.local.iterdir()) == []


def test_local_igual_a_datos_no_aplica(tmp_path):
    res = D.comprobar(ctx=_ctx(tmp_path, local=tmp_path / "datos"))
    assert _item(res, "carpeta_local")["ok"] is None
    assert res["ok"] is True


def test_fuera_de_windows_lo_de_windows_no_aplica(tmp_path):
    res = D.comprobar(ctx=_ctx(tmp_path, windows=False,
                               importar=_importador(tmp_path, faltan={"win32gui", "comtypes"})))
    for id_ in ("win32gui", "comtypes", "precarga_msvc", "msvc_cargada"):
        assert _item(res, id_)["ok"] is None, id_
    assert res["ok"] is True


def test_msvcp140_vieja_falla(tmp_path):
    ctx = _ctx(tmp_path, msvc_cargada=lambda: (r"C:\x\PyQt6\Qt6\bin\MSVCP140.dll", (14, 26, 28720, 3)))
    item = _item(D.comprobar(ctx=ctx), "msvc_cargada")
    assert item["ok"] is False and "14.26" in item["detalle"]


def test_faster_whisper_sin_vad_falla(tmp_path):
    res = D.comprobar(ctx=_ctx(tmp_path, importar=_importador(tmp_path, sin_vad=True)))
    assert _item(res, "faster_whisper")["ok"] is False
    assert "silero_vad" in _item(res, "faster_whisper")["detalle"]


def test_ffmpeg_sin_binario_falla(tmp_path):
    importar = _importador(tmp_path)
    (tmp_path / "ffmpeg.exe").unlink()
    assert _item(D.comprobar(ctx=_ctx(tmp_path, importar=importar)), "ffmpeg")["ok"] is False


def test_red_solo_con_red_true(tmp_path, monkeypatch):
    llamadas = []
    red = D.Comprobacion("ollama", "red", "Ollama", lambda ctx: llamadas.append(1) or (True, "responde"))
    monkeypatch.setattr(D, "COMPROBACIONES_RED", [red])
    sin = D.comprobar(ctx=_ctx(tmp_path))
    assert "ollama" not in {i["id"] for i in sin["items"]} and llamadas == []
    con = D.comprobar(True, ctx=_ctx(tmp_path))
    assert _item(con, "ollama") == {"id": "ollama", "seccion": "red", "nombre": "Ollama", "ok": True,
                                    "detalle": "responde"}
    assert llamadas == [1]


def test_al_avanzar_va_item_a_item(tmp_path):
    vistos = []
    res = D.comprobar(ctx=_ctx(tmp_path), al_avanzar=vistos.append)
    assert vistos == res["items"]


def test_modulos_empaquetados_para_el_spec():
    m = D.modulos_empaquetados()
    for nombre in ("PyQt6.QtWebEngineWidgets", "PyQt6.QtMultimedia", "faster_whisper", "faster_whisper.utils",
                   "ctranslate2", "onnxruntime", "av", "win32gui", "comtypes", "certifi", "imageio_ffmpeg",
                   "sounddevice", "zeroconf", "nucleo.runtime_win"):
        assert nombre in m, nombre
    assert len(m) == len(set(m))


def test_main_json(tmp_path):
    salida = []
    assert D.main(como_json=True, escribir=salida.append, ctx=_ctx(tmp_path)) == 0
    datos = json.loads(salida[0])
    assert datos["ok"] is True and datos["items"]


def test_main_legible_y_codigo_de_salida(tmp_path):
    salida = []
    assert D.main(escribir=salida.append, ctx=_ctx(tmp_path)) == 0
    texto = "\n".join(salida)
    assert "Lo que traigo" in texto and "Tus carpetas" in texto and "Librerías" in texto
    assert "Todo en orden" in texto and "[ok]" in texto
    salida.clear()
    malo = _ctx(tmp_path, importar=_importador(tmp_path, faltan={"pygame", "gtts"}))
    assert D.main(escribir=salida.append, ctx=malo) == 1
    texto = "\n".join(salida)
    assert "[FALLA]" in texto and "Me fallan 2" in texto


def test_el_informe_se_puede_imprimir_en_cp1252(tmp_path):
    """La consola de Windows redirigida (construir.py) no es UTF-8: nada de flechas ni emojis."""
    res = D.comprobar(ctx=_ctx(tmp_path))
    texto = D.informe(res).replace(str(tmp_path), "")
    texto.encode("cp1252")


def test_informe_junta_todo(tmp_path):
    res = D.comprobar(ctx=_ctx(tmp_path))
    texto = D.informe(res)
    assert texto.splitlines()[0].startswith("Lune CD ")
    assert texto.count("[ok]") == sum(1 for i in res["items"] if i["ok"] is True)


def test_los_recursos_del_repo_estan(tmp_path):
    """Lo que la comprobación espera que traiga Lune existe de verdad en el repo."""
    res = D.comprobar(ctx=_ctx(tmp_path, recursos=RAIZ))
    for i in res["items"]:
        if i["seccion"] == "recursos":
            assert i["ok"] is True, i


def test_importar_diagnostico_no_carga_nada_pesado():
    codigo = ("import sys; import servicios.diagnostico; "
              "print(sorted(m for m in ('PyQt6', 'faster_whisper', 'ctranslate2', 'numpy', 'pygame') "
              "if m in sys.modules))")
    r = subprocess.run([sys.executable, "-c", codigo], cwd=str(RAIZ), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "[]"


# ── patata --comprobar ──────────────────────────────────────────────────────────

@pytest.fixture
def patata_mod():
    import patata
    return patata


@pytest.mark.parametrize("argv, como_json", [
    (["--comprobar"], False),
    (["--COMPROBAR", "--json"], True),
    (["--autoinicio", "--comprobar"], False),
])
def test_patata_comprobar_va_antes_que_todo(monkeypatch, patata_mod, argv, como_json):
    def prohibido(*a, **k):
        raise AssertionError("no debía arrancar")
    monkeypatch.setattr(patata_mod, "Patata", prohibido)
    monkeypatch.setattr(patata_mod, "_nueva_instancia", prohibido)
    monkeypatch.setattr(patata_mod, "arranque_con_windows", prohibido)
    llamadas = []
    monkeypatch.setattr(D, "main", lambda **k: llamadas.append(k) or 1)
    assert patata_mod.main(argv) == 1
    assert llamadas == [{"como_json": como_json}]


def test_patata_ayuda_menciona_comprobar(patata_mod):
    assert "--comprobar" in patata_mod.TXT_USO


# ── 11.3: tu equipo, la red y los servicios (con todo FALSO: nada sale a internet) ──

# Clave FALSA. Va en dos trozos para que el guardián de secretos de CI (tests.yml: git grep de
# «sk-or-v1-» + 20 caracteres) no la tome por una de verdad.
CLAVE = "sk-or-v1-" + "claveSecretaDePrueba0123456789"
TOKEN = "123456789:AAH-tokenSecretoDePrueba_0123456"


class _Resp:
    def __init__(self, codigo=200, datos=None):
        self.status_code, self._datos = codigo, datos

    def json(self):
        return self._datos


def _http(rutas):
    pedidas = []

    def get(url, headers=None, timeout=None):
        pedidas.append(url)
        for trozo, r in rutas.items():
            if trozo in url:
                if isinstance(r, BaseException):
                    raise r
                return r
        raise AssertionError(url)
    get.pedidas = pedidas
    return get


def _sd(mics=1, salidas=1):
    disp = [{"name": f"Mic {i}", "max_input_channels": 1, "max_output_channels": 0} for i in range(mics)]
    disp += [{"name": f"Alt {i}", "max_input_channels": 0, "max_output_channels": 2} for i in range(salidas)]
    return SimpleNamespace(query_devices=lambda: disp)


def _ctx_red(tmp_path, ajustes=None, rutas=None, **kw):
    base = dict(
        http=_http(rutas if rutas is not None else {
            "api.github.com": _Resp(200, {}),
            "/api/v1/key": _Resp(200, {"data": {"label": CLAVE[:12]}}),
            "/getMe": _Resp(200, {"ok": True, "result": {"username": "LuneBot"}})}),
        ajustes=lambda: dict(ajustes if ajustes is not None else {
            "openrouter_key": CLAVE, "openrouter_model": "openrouter/auto", "ollama_url": "http://localhost:11434",
            "ollama_model": "qwen2.5:7b", "telegram_token": TOKEN, "telegram_admin_id": "42",
            "modelo_whisper": "base"}),
        node=lambda: {"ok": True, "version": "v20.0.0", "mensaje": ""},
        sonido=_sd(), whisper=lambda m: True,
        disco=lambda ruta: (100, 10, 20 * 1024 ** 3),
        listar_ollama=lambda url: (True, ["qwen2.5:7b"], "ok"),
        carpeta_bot=lambda: True)
    base.update(kw)
    return _ctx(tmp_path, **base)


def test_red_todo_bien_y_sin_secretos(tmp_path):
    res = D.comprobar(True, ctx=_ctx_red(tmp_path))
    assert res["ok"] is True, D.informe(res)
    for id_ in ("internet", "openrouter", "ollama", "telegram", "node", "audio", "whisper_modelo", "espacio_libre"):
        assert _item(res, id_)["ok"] is True, _item(res, id_)
    assert "@LuneBot" in _item(res, "telegram")["detalle"]
    texto = json.dumps(res, ensure_ascii=False) + D.informe(res)
    assert CLAVE not in texto and TOKEN not in texto and CLAVE[:12] not in texto
    secs = [i["seccion"] for i in res["items"]]
    assert secs.index("equipo") < secs.index("red") and secs[-1] == "red"


def test_sin_red_no_se_toca_internet(tmp_path):
    ctx = _ctx_red(tmp_path)
    res = D.comprobar(ctx=ctx)
    assert "red" not in {i["seccion"] for i in res["items"]} and ctx.http.pedidas == []
    assert _item(res, "audio")["ok"] is True                 # tu equipo sí (sin red)


def test_red_sin_configurar_no_aplica(tmp_path):
    vacio = {"openrouter_key": "", "openrouter_model": "openrouter/auto", "ollama_url": "", "ollama_model": "",
             "telegram_token": "", "telegram_admin_id": "", "modelo_whisper": "base"}
    ctx = _ctx_red(tmp_path, ajustes=vacio, node=lambda: {"ok": False, "version": "", "mensaje": ""},
                   rutas={"api.github.com": _Resp(200, {})})
    res = D.comprobar(True, ctx=ctx)
    for id_ in ("openrouter", "ollama", "telegram", "node"):
        assert _item(res, id_)["ok"] is None, _item(res, id_)
    assert res["ok"] is True and ctx.http.pedidas == [D._pruebas().URL_INTERNET]


class ConnectionError(Exception):          # como requests: el texto lleva la URL (con el token)
    pass


def test_red_fallos_con_que_hacer(tmp_path):
    rutas = {"api.github.com": ConnectionError("sin red"),
             "/api/v1/key": _Resp(401, {"error": CLAVE}),
             "/getMe": ConnectionError(f"https://api.telegram.org/bot{TOKEN}/getMe")}
    ctx = _ctx_red(tmp_path, rutas=rutas, listar_ollama=lambda u: (False, [], "No hay nadie escuchando ahí."),
                   node=lambda: {"ok": False, "version": "v14.0.0", "mensaje": ""})
    res = D.comprobar(True, ctx=ctx)
    assert res["ok"] is False
    assert "Wi-Fi" in _item(res, "internet")["detalle"]
    assert "openrouter.ai/keys" in _item(res, "openrouter")["detalle"]
    assert "ollama serve" in _item(res, "ollama")["detalle"]
    assert "internet" in _item(res, "telegram")["detalle"]
    assert "v14.0.0" in _item(res, "node")["detalle"]
    texto = json.dumps(res, ensure_ascii=False) + D.informe(res)
    assert CLAVE not in texto and TOKEN not in texto
    assert "Me fallan 5" in D.resumen(res)


def test_red_telegram_sin_carpeta_o_con_id_malo(tmp_path):
    res = D.comprobar(True, ctx=_ctx_red(tmp_path, carpeta_bot=lambda: False))
    assert _item(res, "telegram")["ok"] is False and "carpeta" in _item(res, "telegram")["detalle"]
    malo = {"telegram_token": TOKEN, "telegram_admin_id": "abc", "ollama_model": ""}
    res = D.comprobar(True, ctx=_ctx_red(tmp_path, ajustes=malo))
    assert _item(res, "telegram")["ok"] is False and "solo números" in _item(res, "telegram")["detalle"]


def test_equipo_sin_microfono_ni_modelo_no_es_fallo(tmp_path):
    res = D.comprobar(ctx=_ctx_red(tmp_path, sonido=_sd(0, 0), whisper=lambda m: False))
    assert _item(res, "audio")["ok"] is None and _item(res, "whisper_modelo")["ok"] is None
    assert "145 MB" in _item(res, "whisper_modelo")["detalle"]
    assert res["ok"] is True


def test_poco_espacio_falla(tmp_path):
    res = D.comprobar(ctx=_ctx_red(tmp_path, disco=lambda r: (1, 1, 50 * 1024 ** 2)))
    assert _item(res, "espacio_libre")["ok"] is False and res["ok"] is False


def test_parar_corta_antes_de_la_siguiente(tmp_path):
    vistos = []
    res = D.comprobar(True, ctx=_ctx_red(tmp_path), al_avanzar=vistos.append, parar=lambda: len(vistos) >= 3)
    assert len(res["items"]) == 3 and res["parado"] is True
    assert "a medias" in D.resumen(res)
    assert D.evento_fin(res)["parado"] is True


def test_eventos_para_la_interfaz(tmp_path):
    ini = D.evento_inicio(True)
    assert ini["tipo"] == "inicio" and ini["total"] == len(D.comprobaciones(True))
    assert [s["id"] for s in ini["secciones"]] == ["recursos", "datos", "modulos", "equipo", "red"]
    assert all(s["nombre"] for s in ini["secciones"])
    res = D.comprobar(True, ctx=_ctx_red(tmp_path))
    it = D.evento_item(res["items"][0])
    assert it["tipo"] == "item" and it["seccion_nombre"] == "Lo que traigo"
    fin = D.evento_fin(res)
    assert fin["tipo"] == "fin" and fin["ok"] is True and fin["fallan"] == 0
    assert fin["cuentan"] + fin["no_aplica"] == len(res["items"])
    json.dumps([ini, it, fin])


def test_ajustes_se_leen_sin_escribir_nada(tmp_path):
    datos_dir = tmp_path / "datos"
    datos_dir.mkdir()
    (datos_dir / "datos.json").write_text(json.dumps({"apis": {"telegram_token": TOKEN},
                                                      "modelos": {"ollama_model": "m"}}), "utf-8")
    ctx = _ctx(tmp_path, datos=datos_dir)
    a = D._ajustes(ctx)
    assert a["telegram_token"] == TOKEN and a["ollama_model"] == "m"
    assert a["openrouter_model"] == "openrouter/auto" and a["modelo_whisper"] == "base"
    assert sorted(p.name for p in datos_dir.iterdir()) == ["datos.json"]       # ni config.json nuevo
    vacio = _ctx(tmp_path / "otra", datos=tmp_path / "otra")
    assert D._ajustes(vacio)["openrouter_key"] == ""


def test_importar_sin_cargar_solo_mira(tmp_path):
    marca = D.importar_sin_cargar("faster_whisper", cargados={}, buscar=lambda n: object())
    assert getattr(marca, D.SIN_CARGAR) is True
    with pytest.raises(ImportError):
        D.importar_sin_cargar("ctranslate2", cargados={}, buscar=lambda n: None)
    ya = SimpleNamespace(__version__="9")
    assert D.importar_sin_cargar("faster_whisper", cargados={"faster_whisper": ya}) is ya
    # Con la marca, el item sale bien sin mirar dentro (ni el VAD ni la CPU).
    normal = _importador(tmp_path)

    def importar(n):
        return SimpleNamespace(**{D.SIN_CARGAR: True}) if n in D.SOLO_MIRAR_EN_APP else normal(n)
    res = D.comprobar(ctx=_ctx(tmp_path, importar=importar))
    assert _item(res, "faster_whisper")["ok"] is True and "lo cargo" in _item(res, "faster_whisper")["detalle"]
    assert _item(res, "qt_webengine")["ok"] is True


def test_contexto_en_app_no_precarga_ni_carga_lo_pesado():
    ctx = D.contexto_en_app()
    assert ctx.importar is D.importar_sin_cargar
    assert "app" in ctx.precargar()


def test_patata_comprobar_con_red(monkeypatch, patata_mod):
    llamadas = []
    monkeypatch.setattr(D, "main", lambda **k: llamadas.append(k) or 0)
    assert patata_mod.main(["--comprobar", "--red"]) == 0
    assert patata_mod.main(["--comprobar", "--json", "--RED"]) == 0
    assert llamadas == [{"como_json": False, "red": True}, {"como_json": True, "red": True}]
    assert "--red" in patata_mod.TXT_USO
