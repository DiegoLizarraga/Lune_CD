"""
Tests de la calibración por modelo y de las operaciones de la biblioteca VRM
(nucleo/vrm.py): modelo_vrm/<modelo>.lune.json (claves y rangos validados),
parámetros para window.luneParams, borrar un modelo SIN salir de modelo_vrm/ y la
herramienta `mascota_tamano`.

También comprueba con Node que ui_web/vrm/lune_params.js tiene los MISMOS rangos
y valida igual que AJUSTES (si Node no está, esa parte se salta). Sin red ni pantalla.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Los GLB sintéticos y la config falsa se comparten con test_vrm_miniatura.py
from test_vrm_miniatura import ConfigFalsa, vrm0_con_miniatura, vrm1_con_miniatura  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
PARAMS_JS = RAIZ / "ui_web" / "vrm" / "lune_params.js"


@pytest.fixture
def carpeta(tmp_path, monkeypatch):
    from nucleo import vrm
    c = tmp_path / "modelo_vrm"; c.mkdir()
    (c / "a_luna.vrm").write_bytes(vrm1_con_miniatura())
    (c / "b_vieja.vrm").write_bytes(vrm0_con_miniatura())
    monkeypatch.setattr(vrm, "CARPETA", c)
    vrm._miniatura_url.cache_clear()
    return c


@pytest.fixture
def almacen(monkeypatch):
    from nucleo import datos, personajes
    alm = {"bot": {"personaje_default": "Lune"},
           "personajes": [{"nombre": "Lune", "systemPrompt": "x", "vrm": "a_luna.vrm"},
                          {"nombre": "Aria", "systemPrompt": "y", "vrm": "b_vieja.vrm"},
                          {"nombre": "Nyx", "systemPrompt": "z", "vrm": "C:/otra/carpeta/a_luna.vrm"},
                          {"nombre": "Sol", "systemPrompt": "w"}]}
    guardados = []
    monkeypatch.setattr(personajes, "_load", lambda: alm)
    monkeypatch.setattr(personajes, "_save", lambda d: guardados.append(json.loads(json.dumps(d))))
    monkeypatch.setattr(datos, "invalidar", lambda: None)
    alm["_guardados"] = guardados
    return alm


# ── Ajustes guardados y validados ─────────────────────────────────────────────

def test_ajustes_se_guardan_validados_en_su_archivo(carpeta):
    from nucleo import vrm
    assert vrm.ajustes_modelo("a_luna.vrm") == {}
    r = vrm.guardar_ajustes_modelo("a_luna.vrm", {
        "luz": 9, "altura": -0.25, "pesoOjos": "0,5", "invertirH": True, "invertirV": 3,
        "invertirEjes": "auto", "fov": 90, "__proto__": 1, "pesoCabeza": float("nan"),
    })
    assert r == {"invertirEjes": 0, "invertirH": -1, "invertirV": 1, "luz": 3.0, "altura": -0.25, "pesoOjos": 0.5}
    archivo = carpeta / "a_luna.lune.json"
    assert archivo.is_file()
    assert json.loads(archivo.read_text("utf-8")) == r
    assert list(json.loads(archivo.read_text("utf-8"))) == list(r)          # orden estable
    assert vrm.ajustes_modelo("a_luna.vrm") == r
    assert vrm.ajustes_modelo(str(carpeta / "a_luna.vrm")) == r             # también por ruta
    assert not list(carpeta.glob("*.tmp"))                                   # escritura atómica sin restos


def test_ajustes_se_mezclan_se_borran_con_none_y_se_reemplazan(carpeta):
    from nucleo import vrm
    vrm.guardar_ajustes_modelo("a_luna.vrm", {"luz": 1.5, "altura": 0.1})
    assert vrm.guardar_ajustes_modelo("a_luna.vrm", {"pesoTorso": 0.2}) == {"luz": 1.5, "altura": 0.1, "pesoTorso": 0.2}
    assert vrm.guardar_ajustes_modelo("a_luna.vrm", {"luz": None}) == {"altura": 0.1, "pesoTorso": 0.2}
    assert vrm.guardar_ajustes_modelo("a_luna.vrm", '{"invertirPiernas": -1}', reemplazar=True) == {"invertirPiernas": -1}
    # Si no queda nada, el archivo desaparece
    assert vrm.guardar_ajustes_modelo("a_luna.vrm", {"invertirPiernas": None}) == {}
    assert not (carpeta / "a_luna.lune.json").exists()
    assert vrm.guardar_ajustes_modelo("a_luna.vrm", "") == {}
    assert vrm.guardar_ajustes_modelo("a_luna.vrm", b'{"luz": 2}') == {"luz": 2.0}


def test_ajustes_rechazan_json_malo(carpeta):
    from nucleo import vrm
    with pytest.raises(ValueError):
        vrm.guardar_ajustes_modelo("a_luna.vrm", "{roto")
    with pytest.raises(ValueError):
        vrm.guardar_ajustes_modelo("a_luna.vrm", [1, 2])
    with pytest.raises(ValueError):
        vrm.guardar_ajustes_modelo("a_luna.vrm", "[1, 2]")


def test_ajustes_rotos_o_enormes_se_ignoran(carpeta):
    from nucleo import vrm
    (carpeta / "a_luna.lune.json").write_text("{no es json", "utf-8")
    assert vrm.ajustes_modelo("a_luna.vrm") == {}
    (carpeta / "a_luna.lune.json").write_text(json.dumps({"luz": 2, "x": "y" * 70000}), "utf-8")
    assert vrm.ajustes_modelo("a_luna.vrm") == {}
    (carpeta / "a_luna.lune.json").write_text("[1]", "utf-8")
    assert vrm.ajustes_modelo("a_luna.vrm") == {}
    # Y se pueden volver a guardar encima
    assert vrm.guardar_ajustes_modelo("a_luna.vrm", {"luz": 2}) == {"luz": 2.0}


@pytest.mark.parametrize("nombre", [
    "../fuera.vrm", "..\\fuera.vrm", "sub/a_luna.vrm", "C:a_luna.vrm", "a_luna.txt", ".vrm", "",
    "con.vrm", "NUL.vrm", "a\x00.vrm", "a?.vrm", "x" * 300 + ".vrm", "..",
])
def test_nombres_que_no_valen(carpeta, nombre):
    from nucleo import vrm
    with pytest.raises(ValueError):
        vrm.ruta_ajustes(nombre)
    with pytest.raises(ValueError):
        vrm.guardar_ajustes_modelo(nombre, {"luz": 2})
    assert vrm.ajustes_modelo(nombre) == {}
    with pytest.raises(ValueError):
        vrm.borrar_modelo(nombre)


def test_ruta_ajustes_siempre_en_la_carpeta(carpeta, tmp_path):
    from nucleo import vrm
    assert vrm.ruta_ajustes("a_luna.vrm") == carpeta / "a_luna.lune.json"
    # Una ruta absoluta de otro sitio: solo cuenta su nombre (los ajustes viven en modelo_vrm/)
    assert vrm.ruta_ajustes(str(tmp_path / "otra" / "b.vrm")) == carpeta / "b.lune.json"


def test_validar_valor_por_tipo():
    from nucleo import vrm
    assert vrm.validar_valor("invertirEjes", 0.5) == 1           # Math.round de JS, no al par
    assert vrm.validar_valor("invertirEjes", -0.5) == 0
    assert vrm.validar_valor("invertirEjes", -7) == -1
    assert vrm.validar_valor("invertirEjes", True) is None
    assert vrm.validar_valor("invertirH", 0) == 1
    assert vrm.validar_valor("invertirH", "-2") == -1
    assert vrm.validar_valor("luz", "abc") is None
    assert vrm.validar_valor("luz", float("inf")) is None
    assert vrm.validar_valor("luz", None) is None
    assert vrm.validar_valor("pesoCabeza", 0.123456) == 0.1235
    assert vrm.validar_valor("nada", 1) is None
    assert vrm.validar_ajustes("no dict") == {}


# ── Parámetros para la mascota ────────────────────────────────────────────────

def test_params_modelo(carpeta):
    from nucleo import vrm
    base = vrm.params_modelo()
    assert set(base) == set(vrm.AJUSTES) and base["luz"] == 1.0 and base["invertirEjes"] == 0
    cfg = ConfigFalsa({"peso_cabeza": 0.3, "peso_torso": "basura", "peso_ojos": 7})
    p = vrm.params_modelo("a_luna.vrm", cfg)
    assert p["pesoCabeza"] == 0.3 and p["pesoTorso"] == 1.0 and p["pesoOjos"] == 1.0
    vrm.guardar_ajustes_modelo("a_luna.vrm", {"pesoCabeza": 0.8, "luz": 2})
    p = vrm.params_modelo("a_luna.vrm", cfg)
    assert p["pesoCabeza"] == 0.8 and p["luz"] == 2.0                # el modelo manda sobre config
    cfg.avatar["seguir_cursor"] = False
    p = vrm.params_modelo("a_luna.vrm", cfg)
    assert p["pesoCabeza"] == p["pesoTorso"] == p["pesoOjos"] == 0.0 and p["luz"] == 2.0
    assert json.loads(vrm.params_modelo_json("a_luna.vrm", cfg))["luz"] == 2.0
    assert vrm.params_modelo("../fuera.vrm")["luz"] == 1.0           # nombre malo → defectos


def test_guardar_ajustes_json(carpeta):
    from nucleo import vrm
    r = json.loads(vrm.guardar_ajustes_json("a_luna.vrm", '{"altura": 0.2}', ConfigFalsa()))
    assert r["ok"] is True and r["archivo"] == "a_luna.vrm"
    assert r["ajustes"] == {"altura": 0.2} and r["efectivos"]["altura"] == 0.2 and r["efectivos"]["luz"] == 1.0
    r = json.loads(vrm.guardar_ajustes_json("../x.vrm", "{}"))
    assert r["ok"] is False and r["error"]
    r = json.loads(vrm.guardar_ajustes_json("a_luna.vrm", "{roto"))
    assert r["ok"] is False


# ── Borrar: solo dentro de modelo_vrm/ ────────────────────────────────────────

def test_borrar_modelo_quita_archivo_ajustes_y_asignaciones(carpeta, almacen):
    from nucleo import vrm
    vrm.guardar_ajustes_modelo("a_luna.vrm", {"luz": 2})
    cfg = ConfigFalsa({"vrm_archivo": "a_luna.vrm"})
    r = vrm.borrar_modelo("a_luna.vrm", cfg)
    assert r["ok"] is True and r["archivo"] == "a_luna.vrm"
    assert not (carpeta / "a_luna.vrm").exists()
    assert not (carpeta / "a_luna.lune.json").exists()
    assert (carpeta / "b_vieja.vrm").exists()
    assert r["personajes"] == ["Lune"]                     # Nyx apunta a OTRA carpeta: no se toca
    assert r["por_defecto"] is True and cfg.avatar["vrm_archivo"] == ""
    assert r["modelos"] == ["b_vieja.vrm"]
    pers = {p["nombre"]: p for p in almacen["personajes"]}
    assert "vrm" not in pers["Lune"] and pers["Aria"]["vrm"] == "b_vieja.vrm"
    assert pers["Nyx"]["vrm"] == "C:/otra/carpeta/a_luna.vrm"
    assert len(almacen["_guardados"]) == 1
    with pytest.raises(ValueError):
        vrm.borrar_modelo("a_luna.vrm")                    # ya no está


def test_borrar_no_sale_de_la_carpeta(carpeta, almacen, tmp_path):
    from nucleo import vrm
    fuera = tmp_path / "fuera.vrm"; fuera.write_bytes(vrm1_con_miniatura())
    vecino = tmp_path / "vecino"; vecino.mkdir()
    (vecino / "x.vrm").write_bytes(b"x")
    for nombre in ("../fuera.vrm", "..\\fuera.vrm", str(fuera), "../vecino/x.vrm", "..", "../modelo_vrm/../fuera.vrm"):
        with pytest.raises(ValueError):
            vrm.borrar_modelo(nombre)
    assert fuera.exists() and (vecino / "x.vrm").exists()
    assert json.loads(vrm.borrar_json(str(fuera)))["ok"] is False
    assert fuera.exists()
    assert almacen["_guardados"] == []


def test_borrar_json_y_modelo_sin_asignar(carpeta, almacen):
    from nucleo import vrm
    (carpeta / "suelto.vrm").write_bytes(vrm1_con_miniatura())
    r = json.loads(vrm.borrar_json("suelto.vrm", ConfigFalsa({"vrm_archivo": "b_vieja.vrm"})))
    assert r["ok"] is True and r["personajes"] == [] and r["por_defecto"] is False
    assert almacen["_guardados"] == []                     # nadie lo usaba: datos.json no se reescribe
    assert json.loads(vrm.borrar_json("no_existe.vrm"))["ok"] is False


def test_personajes_con(carpeta, almacen):
    from nucleo import vrm
    assert vrm.personajes_con("a_luna.vrm") == ["Lune"]
    assert vrm.personajes_con("B_VIEJA.vrm") == ["Aria"]
    assert vrm.personajes_con("nadie.vrm") == []


# ── Herramienta mascota_tamano ────────────────────────────────────────────────

class MascotaFalsa:
    def __init__(self, render="vrm"):
        self.render = render
        self.tamanos = []

    def aplicar_tamano(self, t):
        self.tamanos.append(t)


@pytest.mark.parametrize("entrada,esperado", [
    ("pequeno", "pequeno"), ("Pequeña", "pequeno"), ("PEQUEÑO", "pequeno"), ("mini", "pequeno"),
    ("normal", "normal"), ("Mediana", "normal"), ("grande", "grande"), ("ENORME", "grande"),
    ("gigante", None), ("", None), (None, None), (3, None),
])
def test_normalizar_tamano(entrada, esperado):
    from nucleo import vrm
    assert vrm.normalizar_tamano(entrada) == esperado


def test_herramienta_tamano_con_mascota_3d():
    from nucleo import vrm
    cfg, m = ConfigFalsa(), MascotaFalsa()
    ok, msg = vrm.herramienta_tamano({"tamano": "Grande"}, {"config": cfg, "mascota": m})
    assert ok is True and "grande" in msg
    assert cfg.avatar["vrm_tamano"] == "grande" and m.tamanos == ["grande"]
    # En el hilo de Qt si el ctx trae en_ui
    colas = []
    ok, _ = vrm.herramienta_tamano({"tamano": "pequeno"}, {"config": cfg, "mascota": m, "en_ui": colas.append})
    assert ok and m.tamanos == ["grande"] and len(colas) == 1
    colas[0]()
    assert m.tamanos == ["grande", "pequeno"]


def test_herramienta_tamano_sin_mascota_3d_solo_guarda():
    from nucleo import vrm
    cfg = ConfigFalsa()
    animada = MascotaFalsa(render="animado")
    ok, msg = vrm.herramienta_tamano({"tamano": "normal"}, {"config": cfg, "mascota": animada})
    assert ok is True and "Guardado" in msg and cfg.avatar["vrm_tamano"] == "normal" and animada.tamanos == []
    ok, msg = vrm.herramienta_tamano({"tamano": "normal"}, None)
    assert ok is False
    ok, msg = vrm.herramienta_tamano({"tamano": "gigante"}, {"config": cfg})
    assert ok is False and "pequeno" in msg


def test_herramienta_tamano_ctx_objeto_y_envuelto():
    """El Ejecutor envuelve un ctx que no es dict como {'contexto': objeto}."""
    from nucleo import vrm

    class Ctx:
        def __init__(self):
            self.config, self.mascota = ConfigFalsa(), MascotaFalsa()

    c = Ctx()
    assert vrm.herramienta_tamano({"tamano": "grande"}, c)[0] is True and c.mascota.tamanos == ["grande"]
    c2 = Ctx()
    assert vrm.herramienta_tamano({"tamano": "grande"}, {"modo": "vrm", "contexto": c2})[0] is True
    assert c2.mascota.tamanos == ["grande"] and c2.config.avatar["vrm_tamano"] == "grande"


def test_herramienta_tamano_si_la_mascota_falla():
    from nucleo import vrm

    class Rota(MascotaFalsa):
        def aplicar_tamano(self, t):
            raise RuntimeError("se cerró")

    ok, msg = vrm.herramienta_tamano({"tamano": "grande"}, {"config": ConfigFalsa(), "mascota": Rota()})
    assert ok is False and "se cerró" in msg


def test_catalogo_apunta_al_handler():
    """lune_core/catalogo_herramientas declara nucleo.vrm.herramienta_tamano: que exista."""
    from nucleo import vrm
    assert callable(vrm.herramienta_tamano)
    assert set(vrm.TAMANOS) == {"pequeno", "normal", "grande"}


# ── Paridad con ui_web/vrm/lune_params.js ─────────────────────────────────────

MUESTRAS = [1, -1, 0, 0.4, 0.5, -0.5, 0.6, 7, -3, 0.123456, "0,5", " 2 ", "-1", "auto", "abc", True, False,
            None, 2.5, -0.25, 1e9, -1e9, 0.2, 3.0]

ARNES = r"""
import(process.argv[2]).then((m) => {
  const muestras = JSON.parse(process.argv[3]);
  const out = { rangos: {}, claves: [...m.CLAVES_MODELO], valores: {} };
  for (const k of m.CLAVES_MODELO) out.rangos[k] = m.RANGOS[k];
  for (const k of m.CLAVES_MODELO) out.valores[k] = muestras.map((v) => m.validarValor(k, v));
  console.log(JSON.stringify(out));
});
"""


def test_mismos_rangos_y_validacion_que_lune_params_js(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node no está instalado")
    from nucleo import vrm
    arnes = tmp_path / "paridad.mjs"
    arnes.write_text(ARNES, encoding="utf-8")
    r = subprocess.run([node, str(arnes), PARAMS_JS.as_uri(), json.dumps(MUESTRAS)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    assert r.returncode == 0, r.stderr
    js = json.loads(r.stdout.strip().splitlines()[-1])
    assert js["claves"] == list(vrm.AJUSTES), "mismas claves y en el mismo orden"
    for clave, rango in vrm.AJUSTES.items():
        rj = js["rangos"][clave]
        assert rj["tipo"] == rango["tipo"], clave
        assert rj["defecto"] == rango["defecto"], clave
        if rango["tipo"] == "real":
            assert (rj["min"], rj["max"]) == (rango["min"], rango["max"]), clave
        if rango["tipo"] == "opcion":
            assert sorted(rj["valores"]) == sorted(rango["valores"]), clave
        py = [vrm.validar_valor(clave, v) for v in MUESTRAS]
        assert js["valores"][clave] == py, f"{clave}: JS {js['valores'][clave]} ≠ Python {py}"


def test_herramienta_tamano_usa_lo_que_devuelve_en_ui():
    """G5 / contrato en_ui(fn) -> resultado de fn: un aplicar_tamano que dice False no es éxito."""
    from nucleo import vrm

    class Terca(MascotaFalsa):
        def aplicar_tamano(self, t):
            return False

    cfg = ConfigFalsa()
    ok, msg = vrm.herramienta_tamano({"tamano": "grande"},
                                     {"config": cfg, "mascota": Terca(), "en_ui": lambda fn: fn()})
    assert ok is False and "no puedo" in msg.lower()
    ok, _ = vrm.herramienta_tamano({"tamano": "grande"},
                                   {"config": cfg, "mascota": MascotaFalsa(), "en_ui": lambda fn: fn()})
    assert ok is True
