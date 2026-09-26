"""
Tests de la biblioteca VRM (nucleo/vrm.py): miniatura que trae el propio modelo,
ficha técnica (meta), ficha para la rejilla y biblioteca entera.

Se construyen GLB sintéticos con un PNG de 1×1 en el chunk BIN, en VRM 1.0
(VRMC_vrm.meta.thumbnailImage → images[i]) y VRM 0.x (VRM.meta.texture →
textures[i].source → images[j]). Sin red ni pantalla.
"""
import base64
import json
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# PNG válido de 1×1 (RGBA) y la cabecera de un JPEG.
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
JPEG_FALSO = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\x00" * 16 + b"\xff\xd9"


def glb(doc: dict, binario: bytes = b"", longitud_falsa=None) -> bytes:
    """GLB 2.0: cabecera + chunk JSON (+ chunk BIN si hay binario), con relleno a 4 bytes."""
    js = json.dumps(doc).encode("utf-8")
    js += b" " * ((4 - len(js) % 4) % 4)
    cuerpo = struct.pack("<II", len(js), 0x4E4F534A) + js
    if binario:
        b = binario + b"\x00" * ((4 - len(binario) % 4) % 4)
        cuerpo += struct.pack("<II", len(b), 0x004E4942) + b
    total = 12 + len(cuerpo)
    return b"glTF" + struct.pack("<II", 2, longitud_falsa or total) + cuerpo


def _imagen_en_bin(imagen: bytes, desplazamiento: int = 8):
    """(binario, bufferViews, images): la imagen tras `desplazamiento` bytes de relleno."""
    binario = b"\xAA" * desplazamiento + imagen
    vistas = [{"buffer": 0, "byteOffset": desplazamiento, "byteLength": len(imagen)}]
    return binario, vistas, [{"bufferView": 0, "mimeType": "image/png"}]


def vrm1_con_miniatura(imagen: bytes = PNG_1X1, **meta_extra) -> bytes:
    binario, vistas, imagenes = _imagen_en_bin(imagen)
    meta = {"name": "Luna", "authors": ["Diego", "Otro"], "thumbnailImage": 0,
            "licenseUrl": "https://vrm.dev/licenses/1.0/", "commercialUsage": "personalNonProfit",
            "allowRedistribution": False}
    meta.update(meta_extra)
    doc = {
        "asset": {"version": "2.0"}, "extensionsUsed": ["VRMC_vrm"],
        "buffers": [{"byteLength": len(binario)}], "bufferViews": vistas, "images": imagenes,
        "accessors": [{"count": 300}, {"count": 90}, {"count": 12}],
        "meshes": [{"primitives": [{"indices": 0, "attributes": {"POSITION": 2}},
                                   {"attributes": {"POSITION": 1}},             # sin índices: count/3
                                   {"indices": 2, "mode": 1}]}],                # líneas: no cuenta
        "extensions": {"VRMC_vrm": {
            "meta": meta,
            "humanoid": {"humanBones": {"head": {"node": 0}, "leftEye": {"node": 1}, "rightEye": {"node": 2}}},
            "lookAt": {"type": "bone"},
            "expressions": {"preset": {"happy": {}, "aa": {}, "blink": {}}, "custom": {"guiño": {}}},
        }},
    }
    return glb(doc, binario)


def vrm0_con_miniatura(imagen: bytes = PNG_1X1, textura=1) -> bytes:
    binario, vistas, imagenes = _imagen_en_bin(imagen, desplazamiento=16)
    # La textura 1 apunta a la imagen 1 (la 0 es otra cosa del modelo, sin bufferView válido)
    imagenes = [{"uri": "otra.png"}] + [dict(imagenes[0])]
    doc = {
        "asset": {"version": "2.0"}, "extensionsUsed": ["VRM"],
        "buffers": [{"byteLength": len(binario)}], "bufferViews": vistas, "images": imagenes,
        "textures": [{"source": 0}, {"source": 1}],
        "extensions": {"VRM": {
            "meta": {"title": "Vieja", "author": "Alguien", "texture": textura,
                     "licenseName": "CC_BY_NC", "commercialUssageName": "Disallow",
                     "otherLicenseUrl": "https://ejemplo.org/licencia"},
            "humanoid": {"humanBones": [{"bone": "head", "node": 0}]},
            "firstPerson": {"lookAtTypeName": "BlendShape"},
            "blendShapeMaster": {"blendShapeGroups": [
                {"name": "Joy", "presetName": "joy"}, {"name": "LookLeft", "presetName": "lookleft"},
                {"name": "Raro", "presetName": "unknown"}]},
        }},
    }
    return glb(doc, binario)


def vrm1_sin_nada() -> bytes:
    return glb({"asset": {"version": "2.0"}, "extensionsUsed": ["VRMC_vrm"],
                "extensions": {"VRMC_vrm": {"meta": {"name": "Pelada", "authors": []}}}})


@pytest.fixture
def carpeta(tmp_path, monkeypatch):
    from nucleo import vrm
    c = tmp_path / "modelo_vrm"; c.mkdir()
    (c / "a_luna.vrm").write_bytes(vrm1_con_miniatura())
    (c / "b_vieja.vrm").write_bytes(vrm0_con_miniatura())
    (c / "c_pelada.vrm").write_bytes(vrm1_sin_nada())
    (c / "roto.vrm").write_bytes(b"esto no es un glb")
    monkeypatch.setattr(vrm, "CARPETA", c)
    vrm._miniatura_url.cache_clear()
    return c


@pytest.fixture
def almacen(monkeypatch):
    """datos.json de mentira para personajes."""
    from nucleo import datos, personajes
    alm = {"bot": {"personaje_default": "Aria"},
           "personajes": [{"nombre": "Lune", "systemPrompt": "x", "vrm": "a_luna.vrm"},
                          {"nombre": "Aria", "systemPrompt": "y", "vrm": "b_vieja.vrm"}]}
    monkeypatch.setattr(personajes, "_load", lambda: alm)
    monkeypatch.setattr(personajes, "_save", lambda d: None)
    monkeypatch.setattr(datos, "invalidar", lambda: None)
    return alm


# ── Miniatura ─────────────────────────────────────────────────────────────────

def test_miniatura_vrm1_png(tmp_path):
    from nucleo import vrm
    p = tmp_path / "m.vrm"; p.write_bytes(vrm1_con_miniatura())
    assert vrm.miniatura(p) == PNG_1X1
    assert vrm.miniatura(str(p)) == PNG_1X1


def test_miniatura_vrm0_por_textura(tmp_path):
    from nucleo import vrm
    p = tmp_path / "m.vrm"; p.write_bytes(vrm0_con_miniatura())
    assert vrm.miniatura(p) == PNG_1X1


def test_miniatura_jpeg(tmp_path):
    from nucleo import vrm
    p = tmp_path / "m.vrm"; p.write_bytes(vrm1_con_miniatura(JPEG_FALSO))
    assert vrm.miniatura(p) == JPEG_FALSO


@pytest.mark.parametrize("contenido", [
    vrm1_sin_nada(),
    vrm0_con_miniatura(textura=-1),                  # UniVRM pone -1 si no hay miniatura
    vrm0_con_miniatura(textura=0),                   # textura → imagen con uri externa: no se sigue
    vrm0_con_miniatura(textura=9),                   # fuera de rango
    vrm0_con_miniatura(textura=True),                # bool no es índice
    vrm1_con_miniatura(thumbnailImage=5),
    vrm1_con_miniatura(thumbnailImage="0"),
    vrm1_con_miniatura(b"no soy una imagen, solo bytes"),
    b"esto no es un glb",
    b"",
])
def test_miniatura_ausente_o_rota_da_none(tmp_path, contenido):
    from nucleo import vrm
    p = tmp_path / "m.vrm"; p.write_bytes(contenido)
    assert vrm.miniatura(p) is None


def test_miniatura_archivo_inexistente():
    from nucleo import vrm
    assert vrm.miniatura("no/existe/nada.vrm") is None


def _doc_y_bin(contenido: bytes):
    js_len = struct.unpack("<I", contenido[12:16])[0]
    doc = json.loads(contenido[20:20 + js_len])
    resto = contenido[20 + js_len:]
    binario = resto[8:] if resto else b""
    return doc, binario


def test_miniatura_no_lee_fuera_del_chunk_bin(tmp_path):
    """Un bufferView que se sale del BIN (o apunta a otro buffer, o a un buffer externo) → None."""
    from nucleo import vrm
    doc, binario = _doc_y_bin(vrm1_con_miniatura())
    casos = []
    d = json.loads(json.dumps(doc)); d["bufferViews"][0]["byteLength"] = len(binario) * 10; casos.append(d)
    d = json.loads(json.dumps(doc)); d["bufferViews"][0]["byteOffset"] = -4; casos.append(d)
    d = json.loads(json.dumps(doc)); d["bufferViews"][0]["buffer"] = 1; casos.append(d)
    d = json.loads(json.dumps(doc)); d["buffers"][0]["uri"] = "fuera.bin"; casos.append(d)
    d = json.loads(json.dumps(doc)); d["bufferViews"][0]["byteLength"] = vrm.MAX_MINIATURA + 1; casos.append(d)
    for i, caso in enumerate(casos):
        p = tmp_path / f"m{i}.vrm"; p.write_bytes(glb(caso, binario))
        assert vrm.miniatura(p) is None, caso["bufferViews"]
    # Sin chunk BIN: tampoco
    p = tmp_path / "sin_bin.vrm"; p.write_bytes(glb(doc))
    assert vrm.miniatura(p) is None


def test_miniatura_en_data_uri(tmp_path):
    from nucleo import vrm
    doc = {"asset": {"version": "2.0"}, "extensionsUsed": ["VRMC_vrm"],
           "images": [{"uri": "data:image/png;base64," + base64.b64encode(PNG_1X1).decode()}],
           "extensions": {"VRMC_vrm": {"meta": {"name": "D", "thumbnailImage": 0}}}}
    p = tmp_path / "d.vrm"; p.write_bytes(glb(doc))
    assert vrm.miniatura(p) == PNG_1X1
    assert vrm.meta(p)["miniatura"] is True
    doc["images"][0]["uri"] = "data:image/png," + "x" * 10          # sin base64
    p.write_bytes(glb(doc))
    assert vrm.miniatura(p) is None


def test_miniatura_data_url_solo_de_la_carpeta(carpeta, tmp_path):
    from nucleo import vrm
    url = vrm.miniatura_data_url("a_luna.vrm")
    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == PNG_1X1
    assert vrm.miniatura_data_url("b_vieja.vrm").startswith("data:image/png;base64,")
    assert vrm.miniatura_data_url("c_pelada.vrm") == ""
    assert vrm.miniatura_data_url("roto.vrm") == ""
    assert vrm.miniatura_data_url("no_existe.vrm") == ""
    # Nada fuera de modelo_vrm/: ni rutas absolutas ni relativas con carpetas
    fuera = tmp_path / "fuera.vrm"; fuera.write_bytes(vrm1_con_miniatura())
    assert vrm.miniatura_data_url(str(fuera)) == ""
    assert vrm.miniatura_data_url("../fuera.vrm") == ""
    assert vrm.miniatura_data_url("") == ""


def test_miniatura_data_url_se_refresca_si_cambia_el_archivo(carpeta):
    from nucleo import vrm
    assert vrm.miniatura_data_url("c_pelada.vrm") == ""
    (carpeta / "c_pelada.vrm").write_bytes(vrm1_con_miniatura(JPEG_FALSO))      # otro tamaño → otra clave
    assert vrm.miniatura_data_url("c_pelada.vrm").startswith("data:image/jpeg;base64,")


# ── Meta ──────────────────────────────────────────────────────────────────────

def test_meta_vrm1(tmp_path):
    from nucleo import vrm
    p = tmp_path / "luna.vrm"; p.write_bytes(vrm1_con_miniatura())
    m = vrm.meta(p)
    assert m["ok"] is True and m["version"] == "1"
    assert m["archivo"] == "luna.vrm"
    assert m["nombre"] == "Luna" and m["autor"] == "Diego"
    assert "VRM Public License 1.0" in m["licencia"] and "sin redistribución" in m["licencia"]
    assert m["licencia_url"] == "https://vrm.dev/licenses/1.0/"
    assert m["triangulos"] == 300 // 3 + 90 // 3          # la primitiva de líneas no cuenta
    assert m["tieneLookAt"] is True and m["lookAt"] == "hueso"
    assert m["miniatura"] is True
    assert m["expresiones"] == ["happy", "aa", "blink", "guiño"]
    assert m["mb"] >= 0


def test_meta_vrm0(tmp_path):
    from nucleo import vrm
    p = tmp_path / "vieja.vrm"; p.write_bytes(vrm0_con_miniatura())
    m = vrm.meta(p)
    assert m["ok"] is True and m["version"] == "0"
    assert m["nombre"] == "Vieja" and m["autor"] == "Alguien"
    assert m["licencia"] == "CC BY-NC · sin uso comercial"
    assert m["licencia_url"] == "https://ejemplo.org/licencia"
    assert m["tieneLookAt"] is True and m["lookAt"] == "expresion"   # BlendShape con lookleft
    assert m["miniatura"] is True
    assert m["expresiones"] == ["joy", "lookleft", "Raro"]
    assert m["triangulos"] == 0


def test_meta_sin_mirada(tmp_path):
    """Sin lookAt (1.0) o sin firstPerson (0.x), three-vrm no mueve los ojos."""
    from nucleo import vrm
    p = tmp_path / "p.vrm"; p.write_bytes(vrm1_sin_nada())
    m = vrm.meta(p)
    assert m["ok"] is True and m["tieneLookAt"] is False and m["lookAt"] == ""
    assert m["miniatura"] is False and m["licencia"] == "" and m["autor"] == ""
    # VRM 1.0 con lookAt de huesos pero sin huesos de ojos
    doc, _ = _doc_y_bin(vrm1_con_miniatura())
    doc["extensions"]["VRMC_vrm"]["humanoid"]["humanBones"] = {"head": {"node": 0}}
    p.write_bytes(glb(doc))
    assert vrm.meta(p)["tieneLookAt"] is False
    # lookAt por expresiones sin lookLeft/Right/Up/Down
    doc["extensions"]["VRMC_vrm"]["lookAt"] = {"type": "expression"}
    p.write_bytes(glb(doc))
    assert vrm.meta(p)["tieneLookAt"] is False
    doc["extensions"]["VRMC_vrm"]["expressions"]["preset"]["lookUp"] = {}
    p.write_bytes(glb(doc))
    assert vrm.meta(p) ["tieneLookAt"] is True and vrm.meta(p)["lookAt"] == "expresion"
    # VRM 0.x con huesos de ojos y firstPerson de huesos
    doc0, bin0 = _doc_y_bin(vrm0_con_miniatura())
    doc0["extensions"]["VRM"]["firstPerson"] = {"lookAtTypeName": "Bone"}
    doc0["extensions"]["VRM"]["humanoid"]["humanBones"].append({"bone": "leftEye", "node": 3})
    p.write_bytes(glb(doc0, bin0))
    assert vrm.meta(p)["tieneLookAt"] is True and vrm.meta(p)["lookAt"] == "hueso"
    del doc0["extensions"]["VRM"]["firstPerson"]
    p.write_bytes(glb(doc0, bin0))
    assert vrm.meta(p)["tieneLookAt"] is False


def test_meta_textos_limpios(tmp_path):
    """Nada de control, bidi ni textos kilométricos desde el modelo a la interfaz."""
    from nucleo import vrm
    doc = {"asset": {"version": "2.0"}, "extensionsUsed": ["VRMC_vrm"],
           "extensions": {"VRMC_vrm": {"meta": {"name": "Lu‮na\x00\n<b>", "authors": ["x" * 500]}}}}
    p = tmp_path / "t.vrm"; p.write_bytes(glb(doc))
    m = vrm.meta(p)
    assert m["nombre"] == "Luna <b>"
    assert len(m["autor"]) <= 120 and m["autor"].endswith("…")


def test_meta_de_archivos_malos(tmp_path):
    from nucleo import vrm
    p = tmp_path / "roto.vrm"; p.write_bytes(b"basura")
    m = vrm.meta(p)
    assert m["ok"] is False and m["motivo"] and m["miniatura"] is False and m["expresiones"] == []
    assert vrm.meta(tmp_path / "no.vrm")["ok"] is False
    raro = {"asset": {"version": "2.0"}, "extensionsUsed": ["VRMC_vrm", 3],
            "meshes": [None, {"primitives": "x"}, {"primitives": [None, {"mode": True}]}],
            "accessors": "no", "images": {"a": 1},
            "extensions": {"VRMC_vrm": {"meta": [], "lookAt": "x", "humanoid": 5, "expressions": None}}}
    p.write_bytes(glb(raro))
    m = vrm.meta(p)
    assert m["ok"] is True and m["triangulos"] == 0 and m["tieneLookAt"] is False


# ── Ficha y biblioteca ────────────────────────────────────────────────────────

class ConfigFalsa:
    def __init__(self, avatar=None):
        self.avatar = dict(avatar or {})

    def get(self, seccion, clave, defecto=None):
        return self.avatar.get(clave, defecto) if seccion == "avatar" else defecto

    def set(self, seccion, clave, valor):
        if seccion == "avatar":
            self.avatar[clave] = valor


def test_ficha(carpeta, almacen):
    from nucleo import vrm
    cfg = ConfigFalsa({"vrm_archivo": "a_luna.vrm", "peso_ojos": 0.5})
    f = vrm.ficha("a_luna.vrm", cfg)
    assert f["ok"] is True and f["archivo"] == "a_luna.vrm" and f["nombre"] == "Luna"
    assert f["personajes"] == ["Lune"] and f["por_defecto"] is True
    assert f["ajustes"] == {} and f["efectivos"]["pesoOjos"] == 0.5
    assert vrm.ficha("b_vieja.vrm", cfg)["personajes"] == ["Aria"]
    assert vrm.ficha("../fuera.vrm")["ok"] is False
    assert vrm.ficha("no_existe.vrm")["ok"] is False
    assert json.loads(vrm.ficha_json("a_luna.vrm", cfg))["nombre"] == "Luna"


def test_biblioteca(carpeta, almacen):
    from nucleo import vrm
    b = vrm.biblioteca(ConfigFalsa({"vrm_archivo": "c_pelada.vrm"}))
    assert [m["archivo"] for m in b["modelos"]] == ["a_luna.vrm", "b_vieja.vrm", "c_pelada.vrm"]   # roto no
    assert b["activo"] == "Aria" and b["activo_vrm"] == "b_vieja.vrm"
    assert b["por_defecto"] == "c_pelada.vrm"
    assert all("efectivos" not in m for m in b["modelos"])
    assert [m["miniatura"] for m in b["modelos"]] == [True, True, False]
    assert b["carpeta"] == str(carpeta)
    j = json.loads(vrm.biblioteca_json(None))
    assert len(j["modelos"]) == 3 and j["por_defecto"] == ""
