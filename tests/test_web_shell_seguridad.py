"""
ui/web_shell.py — guarda de navegación de la ventana principal (revisión de
seguridad S2) y recarga del VRM de la barra solo si cambia el archivo
(revisión funcional E #1).

S2: la página principal tiene `window.lune` (el puente: configuración,
aprobaciones, chat). Soltar un enlace o un .html en la ventana, o una
redirección, navegaba el marco principal a otra web que recibía el canal.
"""
import json
import shutil
import subprocess
import types

import pytest

pytest.importorskip("PyQt6.QtWebEngineWidgets")

from PyQt6.QtCore import QUrl  # noqa: E402
from PyQt6.QtWebEngineCore import QWebEnginePage  # noqa: E402

import ui.web_shell as ws  # noqa: E402

T = QWebEnginePage.NavigationType
ORIGEN = QUrl("http://127.0.0.1:54321/ui_kits/lune-desktop/index.html")


@pytest.mark.parametrize("url, tipo, principal, esperado", [
    ("http://127.0.0.1:54321/ui_kits/lune-desktop/index.html", T.NavigationTypeTyped, True, ws.PERMITIR),
    ("http://127.0.0.1:54321/otra.html", T.NavigationTypeLinkClicked, True, ws.PERMITIR),
    ("http://127.0.0.1:54321/", T.NavigationTypeReload, True, ws.PERMITIR),
    # Otro puerto u otro host del PC: no es Lune.
    ("http://127.0.0.1:8080/", T.NavigationTypeTyped, True, ws.RECHAZAR),
    ("http://localhost:54321/", T.NavigationTypeTyped, True, ws.RECHAZAR),
    ("https://127.0.0.1:54321/", T.NavigationTypeTyped, True, ws.RECHAZAR),
    # Soltar algo en la ventana, redirecciones y formularios hacia fuera: rechazados.
    ("https://evil.example/x.html", T.NavigationTypeTyped, True, ws.RECHAZAR),
    ("https://evil.example/", T.NavigationTypeRedirect, True, ws.RECHAZAR),
    ("https://evil.example/", T.NavigationTypeFormSubmitted, True, ws.RECHAZAR),
    ("file:///C:/Users/x/pagina.html", T.NavigationTypeTyped, True, ws.RECHAZAR),
    ("file:///C:/Users/x/pagina.html", T.NavigationTypeLinkClicked, True, ws.RECHAZAR),
    ("data:text/html,<b>x</b>", T.NavigationTypeLinkClicked, True, ws.RECHAZAR),
    ("javascript:alert(1)", T.NavigationTypeLinkClicked, True, ws.RECHAZAR),
    # Un enlace http(s) pulsado: al navegador del sistema.
    ("https://www.youtube.com/watch?v=1", T.NavigationTypeLinkClicked, True, ws.EXTERNO),
    ("http://example.com/", T.NavigationTypeLinkClicked, True, ws.EXTERNO),
    # Un iframe no recibe el canal: no se toca.
    ("https://www.youtube.com/embed/1", T.NavigationTypeOther, False, ws.PERMITIR),
])
def test_decidir_navegacion(url, tipo, principal, esperado):
    assert ws.decidir_navegacion(QUrl(url), tipo, principal, ORIGEN) == esperado


def test_la_pagina_abre_fuera_y_no_navega():
    """acceptNavigationRequest de PaginaLune (sin crear WebEngine: self de mentira)."""
    abiertas = []
    yo = types.SimpleNamespace(origen=ORIGEN, _abrir_fuera=lambda u: abiertas.append(u.toString()),
                               rechazadas=[])
    aceptar = ws.PaginaLune.acceptNavigationRequest
    assert aceptar(yo, QUrl("http://127.0.0.1:54321/a.html"), T.NavigationTypeLinkClicked, True) is True
    assert aceptar(yo, QUrl("https://evil.example/"), T.NavigationTypeLinkClicked, True) is False
    assert abiertas == ["https://evil.example/"]
    assert aceptar(yo, QUrl("file:///C:/x.html"), T.NavigationTypeTyped, True) is False
    assert aceptar(yo, QUrl("https://evil.example/soltado"), T.NavigationTypeTyped, True) is False
    assert abiertas == ["https://evil.example/"]                  # lo soltado no se abre en ningún lado
    assert [m for _, m in yo.rechazadas] == [ws.EXTERNO, ws.RECHAZAR, ws.RECHAZAR]


def _ventana_falsa(info_inicial):
    js = []
    yo = types.SimpleNamespace(_vrm_info=info_inicial, web=None, bridge=types.SimpleNamespace(
        config=None, vrm_barra_info={}))
    yo._js = js.append
    return yo, js


def test_cambio_de_render_no_recarga_el_vrm(monkeypatch):
    """E #1: pasar de vrm a animado avisa a la barra, pero no vuelve a descargar el .vrm."""
    info = {"url": "/vrm/actual.vrm", "v": "a1", "archivo": "a.vrm", "params": "", "render": "vrm"}
    yo, js = _ventana_falsa(dict(info))
    config = types.SimpleNamespace(get=lambda *a: "animado")
    yo.bridge.config = config
    monkeypatch.setattr(ws, "publicar_vrm", lambda srv, cfg: {k: v for k, v in info.items() if k != "render"})
    yo._servidor = None
    ws.VentanaWeb._publicar_vrm(yo)
    assert len(js) == 1 and js[0].rstrip().endswith("false);")     # aviso, sin recargar
    assert yo.bridge.vrm_barra_info["render"] == "animado"
    # Otro archivo (otra versión): sí se recarga.
    info["v"] = "b2"
    ws.VentanaWeb._publicar_vrm(yo)
    assert len(js) == 2 and js[1].rstrip().endswith("true);")


@pytest.mark.skipif(shutil.which("node") is None, reason="sin Node")
def test_js_vrm_barra_sin_recargar_en_node(tmp_path):
    codigo = ws.js_vrm_barra({"url": "/vrm/actual.vrm", "v": "v1", "params": '{"luz":2}',
                              "render": "animado"}, recargar=False)
    arnes = tmp_path / "arnes.cjs"
    arnes.write_text("""
const vm = require('vm');
const llamadas = [];
const pag = { eventos: [] };
pag.window = pag;
pag.LuneVRMBarra = { params(p) { llamadas.push(['params', p]); }, recargar(u, v) { llamadas.push(['recargar']); return 1; } };
pag.CustomEvent = class { constructor(t, o) { this.type = t; this.detail = o && o.detail; } };
pag.dispatchEvent = (ev) => { pag.eventos.push(ev); return true; };
pag.Object = Object;
vm.createContext(pag);
vm.runInContext(process.argv[2], pag);
console.log(JSON.stringify({ llamadas, eventos: pag.eventos.map(e => [e.type, e.detail.recargados, e.detail.render]) }));
""", encoding="utf-8")
    r = subprocess.run(["node", str(arnes), codigo], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    salida = json.loads(r.stdout.strip().splitlines()[-1])
    assert salida["llamadas"] == [["params", '{"luz":2}']]            # calibración sí, recarga no
    assert salida["eventos"] == [["lune-vrm-modelo", 0, "animado"]]
