"""
Tests del actualizador por GitHub Releases (servicios/actualizador.py), sin red.

Lo crítico: nunca descargar ni lanzar nada que no venga de github.com/DiegoLizarraga/Lune_CD
con su SHA-256 comprobado. El HTTP es falso (GetFalso: respuestas por URL, como requests),
el disco es tmp_path y el Popen del instalador es un doble que solo apunta.
"""
import hashlib
import json
import os
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from servicios import actualizador as A  # noqa: E402

REPO = "https://github.com/DiegoLizarraga/Lune_CD"
URL_SETUP = f"{REPO}/releases/download/v11.4/LuneCD-Setup-11.4.exe"
URL_SHA = f"{URL_SETUP}.sha256"
URL_CDN = "https://release-assets.githubusercontent.com/github-production-release-asset/1/abc?sig=x"
CONTENIDO = b"MZ" + b"lune" * 5000          # el «Setup» falso (20 002 bytes)
SHA = hashlib.sha256(CONTENIDO).hexdigest()


class Resp:
    def __init__(self, estado=200, cuerpo=b"", cab=None, json_=None, trozos=None):
        self.status_code = estado
        self._cuerpo = cuerpo if isinstance(cuerpo, bytes) else str(cuerpo).encode()
        self.headers = dict(cab or {})
        self._json = json_
        self._trozos = trozos
        self.cerrada = False

    @property
    def text(self):
        return self._cuerpo.decode("utf-8", "replace")

    def json(self):
        if self._json is None:
            return json.loads(self.text)
        return self._json

    def iter_content(self, n):
        if self._trozos is not None:
            yield from self._trozos
            return
        for i in range(0, len(self._cuerpo), n):
            yield self._cuerpo[i:i + n]

    def close(self):
        self.cerrada = True


class GetFalso:
    """requests.get falso: respuestas por URL (o función url → Resp); apunta cada llamada."""

    def __init__(self, rutas):
        self.rutas = rutas
        self.llamadas = []

    def __call__(self, url, **kw):
        self.llamadas.append((url, kw))
        r = self.rutas.get(url)
        if r is None:
            raise AssertionError(f"petición inesperada a {url}")
        if isinstance(r, Exception):
            raise r
        return r(url, kw) if callable(r) else r

    def urls(self):
        return [u for u, _ in self.llamadas]


def release(version="11.4", assets=None, **extra):
    datos = {
        "tag_name": f"v{version}", "html_url": f"{REPO}/releases/tag/v{version}",
        "published_at": "2026-10-02T10:00:00Z", "draft": False, "prerelease": False,
        "body": f"## Lune CD {version}\n\n**Nuevo**: me actualizo sola.\n- uno\n- [dos](http://x)\n\n"
                "### Cómo instalarme\n\n1. Descarga…",
        "assets": assets if assets is not None else [
            {"name": f"LuneCD-Setup-{version}.exe", "size": len(CONTENIDO),
             "browser_download_url": f"{REPO}/releases/download/v{version}/LuneCD-Setup-{version}.exe",
             "digest": f"sha256:{SHA}"},
            {"name": f"LuneCD-Setup-{version}.exe.sha256", "size": 90,
             "browser_download_url": f"{REPO}/releases/download/v{version}/LuneCD-Setup-{version}.exe.sha256"},
        ],
    }
    datos.update(extra)
    return datos


def api(datos, estado=200, cab=None):
    return GetFalso({A.URL_API_ULTIMA: Resp(estado, json.dumps(datos) if datos is not None else "", cab=cab)})


# ── Versiones ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("texto, tupla", [
    ("v11.2", (11, 2)), ("11.2", (11, 2)), ("V11.2.1", (11, 2, 1)), (" v12 ", (12,)),
    ("11.3-beta", (11, 3)), ("", ()), (None, ()), ("vX", ()),
])
def test_version_tupla(texto, tupla):
    assert A.version_tupla(texto) == tupla


def test_comparar_versiones():
    assert A.es_mas_nueva("11.3", "11.2") and A.es_mas_nueva("v11.10", "11.9")
    assert not A.es_mas_nueva("11.2", "11.2") and not A.es_mas_nueva("11.2.0", "11.2")
    assert not A.es_mas_nueva("11.1", "11.2") and not A.es_mas_nueva("raro", "11.2")
    assert A.misma_version("v11.3", "11.3.0") and not A.misma_version("", "")
    assert A.texto_version("v11.3") == "11.3" and A.texto_version("nada") == ""


def test_modo(tmp_path):
    assert A.modo(instalada=True, raiz=tmp_path) == "instalada"
    assert A.modo(instalada=False, raiz=tmp_path) == "carpeta"
    (tmp_path / ".git").mkdir()
    assert A.modo(instalada=False, raiz=tmp_path) == "git"
    assert A.modo(instalada=True, raiz=tmp_path) == "instalada"     # instalada nunca mira git


# ── Hosts ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("url, ok", [
    (URL_SETUP, True), (URL_CDN, True), ("https://objects.githubusercontent.com/x", True),
    ("http://github.com/x", False), ("https://evil.com/x", False), ("https://github.com.evil.com/x", False),
    ("https://user:pw@github.com/x", False), ("https://github.com:8443/x", False), ("ftp://github.com/x", False),
    ("", False), (None, False),
])
def test_host_permitido(url, ok):
    assert A.host_permitido(url) is ok


def test_solo_assets_de_mi_repo():
    assert A.url_de_release(URL_SETUP)
    assert not A.url_de_release("https://github.com/otro/Lune_CD/releases/download/v1/LuneCD-Setup-1.exe")
    assert not A.url_de_release(URL_CDN)                  # al CDN solo se llega por redirección
    assert not A.url_de_release(f"{REPO}/archive/refs/tags/v11.4.zip")


# ── buscar_release ────────────────────────────────────────────────────────────

def test_buscar_hay_version_nueva_con_digest():
    get = api(release())
    r = A.buscar_release(get, actual="11.3", omitir="")
    assert r["ok"] and r["hay_novedades"] and r["nueva"] and r["instalable"]
    assert r["version"] == "11.4" and r["actual"] == "11.3" and r["sha256"] == SHA
    assert r["asset"] == {"nombre": "LuneCD-Setup-11.4.exe", "url": URL_SETUP, "tamano": len(CONTENIDO)}
    assert r["pagina"] == f"{REPO}/releases/tag/v11.4" and r["fecha"] == "2026-10-02T10:00:00Z"
    assert "11.4" in r["mensaje"]
    # Notas en texto plano: sin Markdown ni enlaces, sin el título ni «Cómo instalarme».
    assert r["notas"].startswith("Nuevo: me actualizo sola.") and "· dos" in r["notas"]
    assert "Cómo instalarme" not in r["notas"] and "**" not in r["notas"] and "http" not in r["notas"]
    # Una sola consulta (el digest basta), con User-Agent, Accept de GitHub y timeout 10, sin token.
    assert get.urls() == [A.URL_API_ULTIMA]
    kw = get.llamadas[0][1]
    assert kw["timeout"] == 10 and kw["headers"]["Accept"] == "application/vnd.github+json"
    assert kw["headers"]["User-Agent"].startswith("LuneCD/") and "Authorization" not in kw["headers"]


def test_sin_digest_usa_el_asset_sha256():
    datos = release()
    del datos["assets"][0]["digest"]
    get = api(datos)
    get.rutas[URL_SHA] = Resp(200, f"{SHA.upper()}  LuneCD-Setup-11.4.exe\n")
    r = A.buscar_release(get, actual="11.3", omitir="")
    assert r["sha256"] == SHA and r["instalable"]
    assert get.llamadas[1][1]["allow_redirects"] is False      # cada salto se valida a mano


def test_sha256_de_otro_archivo_o_raro_no_vale():
    datos = release()
    del datos["assets"][0]["digest"]
    for cuerpo in (f"{SHA}  OtroSetup.exe", "no-es-un-hash", "", "a" * 5000):
        get = api(datos)
        get.rutas[URL_SHA] = Resp(200, cuerpo)
        r = A.buscar_release(get, actual="11.3", omitir="")
        assert r["sha256"] == "" and not r["instalable"] and r["hay_novedades"], cuerpo


def test_sin_sha256_no_es_instalable():
    datos = release(assets=[{"name": "LuneCD-Setup-11.4.exe", "size": 10, "browser_download_url": URL_SETUP}])
    r = A.buscar_release(api(datos), actual="11.3", omitir="")
    assert r["hay_novedades"] and not r["instalable"] and r["asset"] is not None


def test_elige_el_setup_de_esa_version():
    otros = [
        {"name": "LuneCD-Setup-11.3.exe", "size": 5, "browser_download_url": f"{REPO}/releases/download/v11.4/LuneCD-Setup-11.3.exe",
         "digest": "sha256:" + "1" * 64},
        {"name": "notas.txt", "size": 5, "browser_download_url": f"{REPO}/releases/download/v11.4/notas.txt"},
        {"name": "LuneCD-Setup-11.4.exe", "size": 7, "browser_download_url": URL_SETUP, "digest": "sha256:" + "2" * 64},
    ]
    r = A.buscar_release(api(release(assets=otros)), actual="11.3", omitir="")
    assert r["asset"]["nombre"] == "LuneCD-Setup-11.4.exe" and r["sha256"] == "2" * 64
    # El tag v11.4.0 con un LuneCD-Setup-11.4.exe también vale (misma versión).
    r = A.buscar_release(api(release(version="11.4.0", assets=otros)), actual="11.3", omitir="")
    assert r["asset"]["nombre"] == "LuneCD-Setup-11.4.exe"


def test_asset_fuera_de_mi_repo_no_se_ofrece():
    malos = [{"name": "LuneCD-Setup-11.4.exe", "size": 7, "digest": "sha256:" + "2" * 64,
              "browser_download_url": "https://evil.com/LuneCD-Setup-11.4.exe"}]
    r = A.buscar_release(api(release(assets=malos)), actual="11.3", omitir="")
    assert r["hay_novedades"] and r["asset"] is None and not r["instalable"]


def test_al_dia_y_omitida():
    r = A.buscar_release(api(release("11.3")), actual="11.3", omitir="")
    assert r["ok"] and not r["hay_novedades"] and not r["nueva"] and "al día" in r["mensaje"]
    r = A.buscar_release(api(release("11.4")), actual="11.3", omitir="v11.4")
    assert r["ok"] and r["nueva"] and r["omitida"] and not r["hay_novedades"]
    r = A.buscar_release(api(release("11.5")), actual="11.3", omitir="11.4")
    assert r["hay_novedades"] and not r["omitida"]                 # solo se salta ESA versión


def test_omitir_por_defecto_sale_de_la_config(monkeypatch):
    monkeypatch.setattr(A, "_omitir_de_config", lambda: "11.4")
    assert A.buscar_release(api(release("11.4")), actual="11.3")["omitida"]


def test_borradores_y_pruebas_no_cuentan():
    for extra in ({"draft": True}, {"prerelease": True}):
        r = A.buscar_release(api(release("12.0", **extra)), actual="11.3", omitir="")
        assert r["ok"] and not r["hay_novedades"] and r["version"] == ""


def test_errores_de_github_con_calma():
    r = A.buscar_release(api(None, 404), actual="11.3", omitir="")
    assert not r["ok"] and "Todavía no hay" in r["mensaje"]
    r = A.buscar_release(api({"message": "API rate limit exceeded"}, 403, {"X-RateLimit-Remaining": "0"}),
                         actual="11.3", omitir="")
    assert not r["ok"] and "respiro" in r["mensaje"]
    r = A.buscar_release(api(None, 500), actual="11.3", omitir="")
    assert not r["ok"] and "500" in r["mensaje"]
    r = A.buscar_release(GetFalso({A.URL_API_ULTIMA: OSError("sin red")}), actual="11.3", omitir="")
    assert not r["ok"] and "internet" in r["mensaje"]
    r = A.buscar_release(GetFalso({A.URL_API_ULTIMA: Resp(200, "no es json")}), actual="11.3", omitir="")
    assert not r["ok"]
    r = A.buscar_release(api(release(tag_name="latest")), actual="11.3", omitir="")
    assert not r["ok"] and r["pagina"].startswith(REPO)


def test_pagina_ajena_no_se_enseña():
    r = A.buscar_release(api(release(html_url="https://evil.com/phish")), actual="11.3", omitir="")
    assert r["pagina"] == A.URL_RELEASES


# ── descargar ─────────────────────────────────────────────────────────────────

def info(tamano=len(CONTENIDO), sha=SHA, url=URL_SETUP, nombre="LuneCD-Setup-11.4.exe"):
    return {"version": "11.4", "sha256": sha, "asset": {"nombre": nombre, "url": url, "tamano": tamano}}


def redirige_a(destino):
    return Resp(302, cab={"Location": destino})


def test_descarga_con_redireccion_tamano_y_hash(tmp_path):
    (tmp_path / "LuneCD-Setup-11.2.exe").write_bytes(b"viejo")
    (tmp_path / "LuneCD-Setup-11.3.exe.part").write_bytes(b"a medias")
    (tmp_path / "otra_cosa.txt").write_text("se queda")
    get = GetFalso({URL_SETUP: redirige_a(URL_CDN), URL_CDN: Resp(200, CONTENIDO)})
    progreso = []
    r = A.descargar(info(), on_progreso=lambda n, t: progreso.append((n, t)), destino=tmp_path, get=get)
    assert r["ok"] and Path(r["ruta"]) == tmp_path / "LuneCD-Setup-11.4.exe"
    assert Path(r["ruta"]).read_bytes() == CONTENIDO
    assert progreso[-1] == (len(CONTENIDO), len(CONTENIDO)) and len(progreso) >= 1
    assert get.urls() == [URL_SETUP, URL_CDN]
    assert all(kw["allow_redirects"] is False and kw["stream"] is True for _, kw in get.llamadas)
    # Las descargas viejas se van; lo demás de la carpeta se queda.
    assert sorted(p.name for p in tmp_path.iterdir()) == ["LuneCD-Setup-11.4.exe", "otra_cosa.txt"]


def test_redireccion_fuera_de_github_se_corta(tmp_path):
    get = GetFalso({URL_SETUP: redirige_a("https://evil.example/LuneCD-Setup-11.4.exe")})
    r = A.descargar(info(), destino=tmp_path, get=get)
    assert not r["ok"] and "fuera de GitHub" in r["mensaje"] and get.urls() == [URL_SETUP]
    assert list(tmp_path.iterdir()) == []
    get = GetFalso({URL_SETUP: redirige_a("http://objects.githubusercontent.com/x")})     # sin HTTPS
    assert not A.descargar(info(), destino=tmp_path, get=get)["ok"]


def test_demasiadas_redirecciones(tmp_path):
    get = GetFalso({URL_SETUP: redirige_a(URL_SETUP)})
    r = A.descargar(info(), destino=tmp_path, get=get)
    assert not r["ok"] and len(get.llamadas) == A.MAX_REDIRECCIONES + 1


def test_hash_malo_borra_y_no_renombra(tmp_path):
    get = GetFalso({URL_SETUP: Resp(200, CONTENIDO)})
    r = A.descargar(info(sha="0" * 64), destino=tmp_path, get=get)
    assert not r["ok"] and "SHA-256" in r["mensaje"] and list(tmp_path.iterdir()) == []


def test_tamano_malo(tmp_path):
    # Más bytes de los anunciados: se corta en cuanto se pasa.
    r = A.descargar(info(tamano=100), destino=tmp_path, get=GetFalso({URL_SETUP: Resp(200, CONTENIDO)}))
    assert not r["ok"] and "más grande" in r["mensaje"] and list(tmp_path.iterdir()) == []
    # Menos (se cortó la conexión).
    r = A.descargar(info(), destino=tmp_path, get=GetFalso({URL_SETUP: Resp(200, CONTENIDO[:1000])}))
    assert not r["ok"] and "a medias" in r["mensaje"] and list(tmp_path.iterdir()) == []


def test_cancelar_borra_el_part(tmp_path):
    cancelar = threading.Event()
    trozos = [CONTENIDO[:1000], CONTENIDO[1000:2000], CONTENIDO[2000:]]

    def progreso(n, t):
        cancelar.set()                                   # se cancela tras el primer trozo
    get = GetFalso({URL_SETUP: Resp(200, trozos=trozos)})
    r = A.descargar(info(), on_progreso=progreso, cancelar=cancelar, destino=tmp_path, get=get)
    assert not r["ok"] and r["cancelado"] and list(tmp_path.iterdir()) == []


def test_lo_ya_descargado_y_comprobado_no_se_baja_otra_vez(tmp_path):
    (tmp_path / "LuneCD-Setup-11.4.exe").write_bytes(CONTENIDO)
    r = A.descargar(info(), destino=tmp_path, get=GetFalso({}))
    assert r["ok"] and "Ya lo tenía" in r["mensaje"]
    (tmp_path / "LuneCD-Setup-11.4.exe").write_bytes(b"MZ" + b"x" * (len(CONTENIDO) - 2))     # manipulado
    r = A.descargar(info(), destino=tmp_path, get=GetFalso({URL_SETUP: Resp(200, CONTENIDO)}))
    assert r["ok"] and (tmp_path / "LuneCD-Setup-11.4.exe").read_bytes() == CONTENIDO


@pytest.mark.parametrize("cambio, frase", [
    ({"sha": ""}, "SHA-256"), ({"sha": "zz"}, "SHA-256"),
    ({"url": "https://evil.com/LuneCD-Setup-11.4.exe"}, "GitHub"),
    ({"url": URL_CDN}, "GitHub"),
    ({"nombre": "otro.exe"}, "instalador"), ({"nombre": "LuneCD-Setup-11.4.exe.bat"}, "instalador"),
    ({"tamano": 0}, "tamaño"), ({"tamano": A.TAMANO_MAX + 1}, "tamaño"),
])
def test_descargar_se_niega_sin_lo_imprescindible(tmp_path, cambio, frase):
    r = A.descargar(info(**cambio), destino=tmp_path, get=GetFalso({}))
    assert not r["ok"] and frase in r["mensaje"]


def test_github_limita_la_descarga(tmp_path):
    get = GetFalso({URL_SETUP: Resp(429)})
    r = A.descargar(info(), destino=tmp_path, get=get)
    assert not r["ok"] and "respiro" in r["mensaje"]


def test_sin_sitio_en_disco(tmp_path, monkeypatch):
    monkeypatch.setattr(A.shutil, "disk_usage", lambda p: type("U", (), {"free": 10})())
    r = A.descargar(info(), destino=tmp_path, get=GetFalso({}))
    assert not r["ok"] and "No me cabe" in r["mensaje"]


# ── instalar ──────────────────────────────────────────────────────────────────

def test_instalar_lanza_el_setup_en_silencio_y_desacoplado(tmp_path):
    setup = tmp_path / "LuneCD-Setup-11.4.exe"
    setup.write_bytes(CONTENIDO)
    lanzados = []
    assert A.instalar(setup, popen=lambda orden, **kw: lanzados.append((orden, kw)), sha256=SHA) is True
    orden, kw = lanzados[0]
    assert orden == [str(setup), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/RELANZAR=1"]
    assert kw["cwd"] == str(tmp_path) and kw["close_fds"] is True
    if os.name == "nt":
        assert kw["creationflags"] & 0x00000008                  # DETACHED_PROCESS


def test_instalar_se_niega_con_algo_raro(tmp_path):
    lanzados = []
    popen = lambda orden, **kw: lanzados.append(orden)       # noqa: E731
    otro = tmp_path / "virus.exe"
    otro.write_bytes(CONTENIDO)
    assert A.instalar(otro, popen=popen) is False
    assert A.instalar(tmp_path / "LuneCD-Setup-11.4.exe", popen=popen) is False      # no existe
    setup = tmp_path / "LuneCD-Setup-11.4.exe"
    setup.write_bytes(b"cambiado")
    assert A.instalar(setup, popen=popen, sha256=SHA) is False                     # hash distinto
    assert lanzados == []

    def revienta(*a, **k):
        raise OSError("no")
    setup.write_bytes(CONTENIDO)
    assert A.instalar(setup, popen=revienta) is False


# ── Aviso al iniciar: una vez al día ──────────────────────────────────────────

class Cfg:
    def __init__(self, **act):
        self.d = {"actualizaciones": {"comprobar_al_iniciar": True, "ultima_comprobacion": "", **act}}

    def get(self, s, k, d=None):
        return self.d.get(s, {}).get(k, d)

    def set(self, s, k, v):
        self.d.setdefault(s, {})[k] = v


def test_toca_comprobar_una_vez_al_dia():
    ahora = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    cfg = Cfg()
    assert A.toca_comprobar(cfg, ahora)
    assert A.marcar_comprobacion(cfg, ahora) == "2026-10-01T12:00:00Z"
    assert cfg.d["actualizaciones"]["ultima_comprobacion"] == "2026-10-01T12:00:00Z"
    assert not A.toca_comprobar(cfg, ahora + timedelta(hours=23))
    assert A.toca_comprobar(cfg, ahora + timedelta(hours=24))
    assert A.toca_comprobar(Cfg(ultima_comprobacion="basura"), ahora)
    assert A.toca_comprobar(Cfg(ultima_comprobacion="2030-01-01T00:00:00Z"), ahora)   # reloj cambiado
    assert not A.toca_comprobar(Cfg(comprobar_al_iniciar=False), ahora)


def test_buscar_novedades_segun_el_modo():
    git = A.buscar_novedades("git", comprobar_git=lambda rama: {"ok": True, "hay_novedades": True,
                                                                 "pendientes": 2, "commits": ["a", "b"], "rama": rama},
                             rama="master")
    assert git["modo"] == "git" and git["rama"] == "master" and git["pagina"] == A.URL_RELEASES
    assert A.texto_aviso(git) == "Hay 2 cambio(s) nuevo(s) de mí en GitHub. Ajustes → Sistema → Actualizaciones"
    inst = A.buscar_novedades("instalada", get=api(release()), actual="11.3", omitir="")
    assert inst["modo"] == "instalada" and inst["instalable"]
    assert A.texto_aviso(inst) == "Hay una versión nueva de mí (11.4). Ajustes → Sistema → Actualizaciones"
    assert A.texto_aviso(inst, "patata").endswith("/actualizar para verla.")
    carpeta = A.buscar_novedades("carpeta", get=api(release()), actual="11.3", omitir="")
    assert carpeta["hay_novedades"] and not carpeta["instalable"]          # solo avisa
    assert "Descárgala en https://github.com/DiegoLizarraga/Lune_CD/releases" in A.texto_aviso(carpeta)

    def revienta(rama):
        raise RuntimeError("git roto")
    roto = A.buscar_novedades("git", comprobar_git=revienta)
    assert roto["ok"] is False and roto["modo"] == "git"


def test_config_por_defecto():
    from nucleo.config import Config
    act = Config.DEFAULT_CONFIG["actualizaciones"]
    assert act == {"rama": "master", "comprobar_al_iniciar": True, "ultima_comprobacion": "", "omitir_version": ""}


def test_config_viejo_conserva_su_false(tmp_path):
    """Sin migración: un config.json que ya guardó comprobar_al_iniciar=False lo conserva y
    gana las claves nuevas."""
    from nucleo.config import Config
    ruta = tmp_path / "config.json"
    ruta.write_text(json.dumps({"actualizaciones": {"rama": "master", "comprobar_al_iniciar": False}}), encoding="utf-8")
    cfg = Config(str(ruta))
    assert cfg.get("actualizaciones", "comprobar_al_iniciar") is False
    assert cfg.get("actualizaciones", "omitir_version") == "" and cfg.get("actualizaciones", "ultima_comprobacion") == ""
    cfg.set("actualizaciones", "omitir_version", "11.4")
    assert Config(str(ruta)).get("actualizaciones", "omitir_version") == "11.4"
