"""
Integridad del código de terceros de ui_web/vendor/three (corte 9: reproductor MMD/VRMA).

La asistente VRM no usa CDN en tiempo de ejecución: three.js r160, GLTFLoader,
BufferGeometryUtils, @pixiv/three-vrm y @pixiv/three-vrm-animation van copiados en
ui_web/vendor/three. El manifiesto VENDOR.json dice de dónde sale cada archivo (tarball
del registro npm, con su integridad sha512 comprobada al empaquetar), su versión, su
sha256 y su licencia. Aquí se comprueba que:

- cada archivo del manifiesto existe y su sha256 y tamaño coinciden (nadie lo tocó);
- no hay .js vendorizado fuera del manifiesto;
- las licencias MIT están al lado;
- three-vrm-animation es EXACTAMENTE la misma versión que three-vrm (3.1.6) y solo
  importa «three» (ni fetch, ni eval, ni import() dinámico, ni otros paquetes) y exporta
  lo que usa ui_web/vrm/lune_mmd.js.
"""
import hashlib
import json
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
VENDOR = RAIZ / "ui_web" / "vendor" / "three"
MANIFIESTO = VENDOR / "VENDOR.json"
CLAVES = ("archivo", "paquete", "version", "origen", "sha256", "licencia")


def _manifiesto() -> list:
    return json.loads(MANIFIESTO.read_text(encoding="utf-8"))


def _sha256(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def test_manifiesto_bien_formado():
    entradas = _manifiesto()
    assert isinstance(entradas, list) and len(entradas) >= 5
    vistos = set()
    for e in entradas:
        for k in CLAVES:
            assert isinstance(e.get(k), str) and e[k], (e, k)
        assert e["archivo"] not in vistos, e["archivo"]
        vistos.add(e["archivo"])
        assert re.fullmatch(r"[0-9a-f]{64}", e["sha256"]), e
        assert re.fullmatch(r"\d+\.\d+\.\d+", e["version"]), e
        assert e["origen"].startswith("https://registry.npmjs.org/"), e
        assert e["origen"].endswith(f"-{e['version']}.tgz"), e
        assert e["integridad_npm"].startswith("sha512-"), e
        assert e["licencia"] == "MIT", e
        # rutas relativas dentro de la carpeta, sin salir de ella
        assert not Path(e["archivo"]).is_absolute() and ".." not in Path(e["archivo"]).parts, e


def test_sha256_y_tamano_coinciden_con_el_manifiesto():
    for e in _manifiesto():
        ruta = VENDOR / e["archivo"]
        assert ruta.is_file(), e["archivo"]
        assert _sha256(ruta) == e["sha256"], f"{e['archivo']} cambió respecto al paquete {e['paquete']}@{e['version']}"
        assert ruta.stat().st_size == e["bytes"], e["archivo"]


def test_no_hay_js_vendorizado_fuera_del_manifiesto():
    en_disco = {p.relative_to(VENDOR).as_posix() for p in VENDOR.rglob("*.js")}
    assert en_disco == {e["archivo"] for e in _manifiesto()}


def test_licencias_mit_al_lado():
    for e in _manifiesto():
        lic = VENDOR / e["archivo_licencia"]
        assert lic.is_file(), e["archivo_licencia"]
        texto = lic.read_text(encoding="utf-8")
        assert "MIT License" in texto, lic.name
        assert "Permission is hereby granted, free of charge" in texto, lic.name
    texto = (VENDOR / "LICENSE.three-vrm-animation").read_text(encoding="utf-8")
    assert "pixiv Inc." in texto


def test_three_vrm_animation_misma_version_que_three_vrm():
    por_paquete = {e["paquete"]: e for e in _manifiesto()}
    anim = por_paquete["@pixiv/three-vrm-animation"]
    vrm = por_paquete["@pixiv/three-vrm"]
    assert anim["version"] == vrm["version"] == "3.1.6"
    assert anim["archivo"] == "three-vrm-animation.module.min.js"
    assert por_paquete["three"]["version"] == "0.160.0"
    # el bundle de three-vrm lleva su versión dentro (los de sus paquetes internos)
    assert "3.1.6" in (VENDOR / vrm["archivo"]).read_text(encoding="utf-8")


def test_three_vrm_animation_solo_importa_three_y_no_trae_red():
    src = (VENDOR / "three-vrm-animation.module.min.js").read_text(encoding="utf-8")
    estaticos = re.findall(r"""\b(?:from|import)\s*["']([^"']+)["']""", src)
    assert estaticos and set(estaticos) == {"three"}, set(estaticos)
    # import() dinámico de verdad (no métodos como this._import(e))
    assert not re.search(r"(?<![\w.$])import\s*\(", src)
    for prohibido in ("fetch(", "XMLHttpRequest", "eval(", "new Function", "WebSocket", "document.", "localStorage"):
        assert prohibido not in src, prohibido
    exportado = re.search(r"export\s*\{([^}]*)\}", src)
    assert exportado
    nombres = {p.split(" as ")[-1].strip() for p in exportado.group(1).split(",")}
    for n in ("VRMAnimation", "VRMAnimationLoaderPlugin", "VRMLookAtQuaternionProxy", "createVRMAnimationClip"):
        assert n in nombres, n
