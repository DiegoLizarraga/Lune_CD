"""
Tests de ui/servidor_web.py: carpetas publicadas (publicar_carpeta), protección
contra path traversal, tipos MIME nuevos (bailes y audio), que ya no se manda CORS
abierto y que no se atiende a peticiones con un Host ajeno (DNS rebinding).

Sin red real: un servidor en 127.0.0.1 sobre carpetas temporales. Se usa
http.client para mandar rutas crudas ('/bailes/../x'), porque urllib las normaliza.
"""
import http.client
import os
from pathlib import Path
from urllib.parse import quote

import pytest

from ui.servidor_web import (RECHAZADA, HandlerSilencioso, ServidorEstatico,
                             normalizar_prefijo, resolver_en_carpetas)

SECRETO = "CLAVE-SECRETA-NO-SERVIR"


@pytest.fixture
def entorno(tmp_path):
    web = tmp_path / "web"; web.mkdir()
    (web / "index.html").write_text("<p>hola</p>", "utf-8")
    (web / "sub").mkdir()
    bailes = tmp_path / "bailes"; bailes.mkdir()
    (bailes / "baile.vmd").write_bytes(b"Vocaloid Motion Data 0002" + bytes(40))
    (bailes / "mi baile.vmd").write_bytes(b"con espacio")
    pack = bailes / "pack"; pack.mkdir()
    (pack / "tema.mp3").write_bytes(b"ID3" + bytes(100))
    # Lo que NO se debe poder leer: un archivo junto a la carpeta y una carpeta
    # hermana cuyo nombre empieza igual que el prefijo.
    (tmp_path / "secreto.txt").write_text(SECRETO, "utf-8")
    privados = tmp_path / "bailes_privados"; privados.mkdir()
    (privados / "x.txt").write_text(SECRETO, "utf-8")
    srv = ServidorEstatico(web)
    assert srv.iniciar()
    assert srv.publicar_carpeta("/bailes/", bailes) == "/bailes/"
    try:
        yield srv, tmp_path
    finally:
        srv.detener()


def _pedir(srv, ruta, metodo="GET", cabeceras=None):
    c = http.client.HTTPConnection("127.0.0.1", srv.puerto, timeout=5)
    try:
        c.request(metodo, ruta, headers=cabeceras or {})
        r = c.getresponse()
        return r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()
    finally:
        c.close()


# ── La carpeta publicada se sirve ───────────────────────────────────────────────

def test_carpeta_publicada_sirve_sus_archivos(entorno):
    srv, tmp = entorno
    st, cab, cuerpo = _pedir(srv, "/bailes/baile.vmd?v=3")
    assert st == 200 and cuerpo == (tmp / "bailes" / "baile.vmd").read_bytes()
    assert cab["content-type"] == "application/octet-stream"
    st, _, cuerpo = _pedir(srv, "/bailes/mi%20baile.vmd")
    assert st == 200 and cuerpo == b"con espacio"
    st, cab, cuerpo = _pedir(srv, "/bailes/pack/tema.mp3")
    assert st == 200 and cab["content-type"] == "audio/mpeg" and cuerpo.startswith(b"ID3")
    # ui_web sigue sirviéndose como siempre
    st, _, cuerpo = _pedir(srv, "/index.html")
    assert st == 200 and b"hola" in cuerpo
    # y lo que no existe da 404
    assert _pedir(srv, "/bailes/nada.vmd")[0] == 404


def test_range_206_tambien_en_carpetas(entorno):
    srv, _ = entorno
    st, cab, cuerpo = _pedir(srv, "/bailes/pack/tema.mp3", cabeceras={"Range": "bytes=0-2"})
    assert st == 206 and cuerpo == b"ID3"
    assert cab["content-range"] == "bytes 0-2/103" and cab["content-type"] == "audio/mpeg"
    st, cab, _ = _pedir(srv, "/bailes/pack/tema.mp3", cabeceras={"Range": "bytes=500-"})
    assert st == 416 and cab["content-range"] == "bytes */103"


def test_head_en_carpeta(entorno):
    srv, _ = entorno
    st, cab, cuerpo = _pedir(srv, "/bailes/baile.vmd", metodo="HEAD")
    assert st == 200 and cuerpo == b"" and int(cab["content-length"]) == 65


def test_publicar_y_quitar_en_caliente(entorno, tmp_path):
    srv, _ = entorno
    sonidos = tmp_path / "sonidos"; sonidos.mkdir()
    (sonidos / "hola.wav").write_bytes(b"RIFF....WAVE")
    assert _pedir(srv, "/packs/defecto/hola.wav")[0] == 404
    assert srv.publicar_carpeta("packs/defecto", sonidos) == "/packs/defecto/"
    st, cab, cuerpo = _pedir(srv, "/packs/defecto/hola.wav")
    assert st == 200 and cuerpo == b"RIFF....WAVE" and cab["content-type"] == "audio/wav"
    assert srv.quitar_carpeta("/packs/defecto/") is True
    assert srv.quitar_carpeta("/packs/defecto/") is False
    assert _pedir(srv, "/packs/defecto/hola.wav")[0] == 404


def test_carpeta_relativa_se_ancla_a_la_raiz_del_repo(entorno):
    from ui.servidor_web import RAIZ
    srv, _ = entorno
    srv.publicar_carpeta("/sfx/", "ui_web/assets/sfx")
    assert srv.carpetas["/sfx/"] == (RAIZ / "ui_web" / "assets" / "sfx").resolve()
    st, cab, cuerpo = _pedir(srv, "/sfx/LEEME.txt")
    assert st == 200 and b"generar_sfx.py" in cuerpo


def test_gana_el_prefijo_mas_largo_y_las_rutas_extra_primero(entorno, tmp_path):
    srv, tmp = entorno
    otra = tmp_path / "otra"; otra.mkdir()
    (otra / "tema.mp3").write_bytes(b"ID3otra")
    srv.publicar_carpeta("/bailes/pack/", otra)
    assert _pedir(srv, "/bailes/pack/tema.mp3")[2] == b"ID3otra"
    suelto = tmp_path / "suelto.vmd"; suelto.write_bytes(b"suelto")
    srv.publicar("/bailes/especial.vmd", suelto)
    assert _pedir(srv, "/bailes/especial.vmd")[2] == b"suelto"


# ── Path traversal ──────────────────────────────────────────────────────────────

RUTAS_MALAS = [
    "/bailes/../secreto.txt",
    "/bailes/%2e%2e/secreto.txt",
    "/bailes/%2E%2E/secreto.txt",
    "/bailes/.%2e/secreto.txt",
    "/bailes/..%2fsecreto.txt",
    "/bailes%2f..%2fsecreto.txt",
    "/bailes/..%5csecreto.txt",
    "/bailes/..\\secreto.txt",
    "/bailes/%252e%252e/secreto.txt",
    "/bailes/%252e%252e%252fsecreto.txt",
    "/bailes/pack/../../secreto.txt",
    "/bailes/pack/%2e%2e/%2e%2e/secreto.txt",
    "/bailes/..%00/secreto.txt",
    "/bailes/.../secreto.txt",
    "/bailes//secreto.txt",
    "/bailes/C:/Windows/win.ini",
    "/bailes/C:%5CWindows%5Cwin.ini",
    "/bailes/nul",
    "/bailes/baile.vmd::$DATA",
]


@pytest.mark.parametrize("ruta", RUTAS_MALAS)
def test_traversal_rechazado(entorno, ruta):
    srv, _ = entorno
    st, cab, cuerpo = _pedir(srv, ruta)
    assert st == 404, (ruta, st)
    assert SECRETO.encode() not in cuerpo
    # con Range pasa por otro camino del handler: también se rechaza
    st, _, cuerpo = _pedir(srv, ruta, cabeceras={"Range": "bytes=0-"})
    assert st == 404 and SECRETO.encode() not in cuerpo
    st, _, _ = _pedir(srv, ruta, metodo="HEAD")
    assert st == 404


def test_ruta_absoluta_rechazada(entorno):
    srv, tmp = entorno
    absoluta = str(tmp / "secreto.txt")
    for ruta in ("/bailes/" + quote(absoluta), "/bailes/" + quote(absoluta.replace("\\", "/"), safe="/"),
                 "/bailes/" + quote("/" + absoluta.replace("\\", "/"), safe="/")):
        st, _, cuerpo = _pedir(srv, ruta)
        assert st == 404 and SECRETO.encode() not in cuerpo, ruta


def test_carpeta_hermana_con_el_mismo_comienzo_no_se_sirve(entorno):
    srv, _ = entorno
    st, _, cuerpo = _pedir(srv, "/bailes_privados/x.txt")
    assert st == 404 and SECRETO.encode() not in cuerpo


def test_no_lista_directorios_publicados(entorno):
    srv, _ = entorno
    for ruta in ("/bailes/", "/bailes", "/bailes/pack/", "/bailes/pack", "/bailes/./baile.vmd"):
        st, _, cuerpo = _pedir(srv, ruta)
        assert st == 404, ruta
        assert b"baile.vmd" not in cuerpo and b"tema.mp3" not in cuerpo


def test_enlace_simbolico_hacia_fuera_rechazado(entorno):
    srv, tmp = entorno
    enlace = tmp / "bailes" / "atajo.txt"
    try:
        os.symlink(tmp / "secreto.txt", enlace)
    except (OSError, NotImplementedError):
        pytest.skip("este Windows no deja crear enlaces simbólicos sin permisos")
    st, _, cuerpo = _pedir(srv, "/bailes/atajo.txt")
    assert st == 404 and SECRETO.encode() not in cuerpo


def test_junction_hacia_fuera_rechazada(entorno):
    """Como el enlace simbólico, pero con una junction de Windows (no pide permisos)."""
    srv, tmp = entorno
    try:
        import _winapi
        _winapi.CreateJunction(str(tmp), str(tmp / "bailes" / "puerta"))
    except (ImportError, AttributeError, OSError):
        pytest.skip("sin junctions (no es Windows o no se pudo crear)")
    st, _, cuerpo = _pedir(srv, "/bailes/puerta/secreto.txt")
    assert st == 404 and SECRETO.encode() not in cuerpo


def test_resolver_en_carpetas_puro(tmp_path):
    base = tmp_path / "c"; base.mkdir(); (base / "a.wav").write_bytes(b"x")
    carpetas = {"/c/": base.resolve()}
    assert resolver_en_carpetas("/otra/a.wav", carpetas) is None
    assert resolver_en_carpetas("/c/a.wav?x=1#y", carpetas) == (base / "a.wav").resolve()
    assert resolver_en_carpetas("/c/no_existe.wav", carpetas) == (base / "no_existe.wav").resolve()
    for mala in ("/c/../x", "/c/%2e%2e/x", "/c/", "/c", "/c/a/../../x", "/c/%252e%252e/x"):
        assert resolver_en_carpetas(mala, carpetas) is RECHAZADA, mala
    assert not RECHAZADA   # el centinela es falso: no se confunde con un Path


# ── Prefijos ────────────────────────────────────────────────────────────────────

def test_normalizar_prefijo():
    assert normalizar_prefijo("bailes") == "/bailes/"
    assert normalizar_prefijo("/bailes") == "/bailes/"
    assert normalizar_prefijo("/vrm/biblioteca/") == "/vrm/biblioteca/"
    for malo in ("", "/", "//", "/../x/", "/a/../b", "/a/./b", "/c:/x", "/a\\b/", "/%2e%2e/"):
        with pytest.raises(ValueError):
            normalizar_prefijo(malo)


def test_prefijo_que_taparia_ui_web(entorno, tmp_path):
    srv, _ = entorno
    with pytest.raises(ValueError):
        srv.publicar_carpeta("/sub/", tmp_path)          # existe web/sub
    with pytest.raises(ValueError):
        srv.publicar_carpeta("/index.html/", tmp_path)   # existe web/index.html
    with pytest.raises(ValueError):
        srv.publicar_carpeta("/", tmp_path)


# ── MIME ────────────────────────────────────────────────────────────────────────

MIMES = {
    ".vmd": "application/octet-stream", ".vrma": "model/gltf-binary", ".vrm": "model/gltf-binary",
    ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".opus": "audio/ogg", ".wav": "audio/wav",
    ".flac": "audio/flac", ".json": "application/json", ".webm": "video/webm",
    ".js": "text/javascript",
}


def test_tabla_mime():
    for ext, tipo in MIMES.items():
        assert HandlerSilencioso.extensions_map[ext] == tipo, ext


def test_mime_servido(entorno, tmp_path):
    srv, _ = entorno
    medios = tmp_path / "medios"; medios.mkdir()
    for ext in MIMES:
        (medios / f"a{ext}").write_bytes(b"0123456789")
    (medios / "MAYUS.WAV").write_bytes(b"0123456789")
    srv.publicar_carpeta("/medios/", medios)
    for ext, tipo in MIMES.items():
        st, cab, _ = _pedir(srv, f"/medios/a{ext}")
        assert st == 200 and cab["content-type"] == tipo, ext
        # la respuesta parcial (206) lleva el mismo tipo
        st, cab, _ = _pedir(srv, f"/medios/a{ext}", cabeceras={"Range": "bytes=0-1"})
        assert st == 206 and cab["content-type"] == tipo, ext
    assert _pedir(srv, "/medios/MAYUS.WAV")[1]["content-type"] == "audio/wav"


# ── Sin CORS y solo para 127.0.0.1 ──────────────────────────────────────────────

def test_no_manda_cors(entorno, tmp_path):
    srv, _ = entorno
    modelo = tmp_path / "m.vrm"; modelo.write_bytes(b"glTF....")
    srv.publicar("/vrm/actual.vrm", modelo)
    origen = {"Origin": "https://malicioso.example"}
    for ruta, extra in (("/index.html", {}), ("/bailes/baile.vmd", {}), ("/vrm/actual.vrm", {}),
                        ("/bailes/baile.vmd", {"Range": "bytes=0-3"}), ("/no_existe", {}),
                        ("/bailes/../secreto.txt", {})):
        st, cab, _ = _pedir(srv, ruta, cabeceras={**origen, **extra})
        assert not any(k.startswith("access-control-") for k in cab), (ruta, cab)
    # un preflight tampoco abre nada
    st, cab, _ = _pedir(srv, "/bailes/baile.vmd", metodo="OPTIONS", cabeceras=origen)
    assert st >= 400 and "access-control-allow-origin" not in cab


def test_host_ajeno_rechazado(entorno):
    srv, _ = entorno
    for host in ("malicioso.example", f"malicioso.example:{srv.puerto}", "10.0.0.7",
                 f"127.0.0.1.malicioso.example:{srv.puerto}"):
        st, _, cuerpo = _pedir(srv, "/bailes/baile.vmd", cabeceras={"Host": host})
        assert st == 403, host
        assert b"Vocaloid" not in cuerpo
        st, _, cuerpo = _pedir(srv, "/bailes/baile.vmd", cabeceras={"Host": host, "Range": "bytes=0-3"})
        assert st == 403 and b"Voca" not in cuerpo, host
        assert _pedir(srv, "/index.html", metodo="HEAD", cabeceras={"Host": host})[0] == 403
    for host in (f"127.0.0.1:{srv.puerto}", f"localhost:{srv.puerto}", f"[::1]:{srv.puerto}", "LOCALHOST"):
        assert _pedir(srv, "/bailes/baile.vmd", cabeceras={"Host": host})[0] == 200, host
