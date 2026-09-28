"""
Tests de nucleo/datos.guardar_minecraft: valida la sección `minecraft` de datos.json y
la guarda con la escritura atómica. Siempre sobre un datos.json TEMPORAL.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo import datos  # noqa: E402


@pytest.fixture
def datos_tmp(monkeypatch, tmp_path):
    ruta = tmp_path / "datos.json"
    ruta.write_text(json.dumps({"apis": {"openrouter_key": "sk-no-tocar"},
                                "minecraft": {"_nota": "de la plantilla", "host": "localhost", "port": 25565,
                                              "dueno": "", "visor": False}}), encoding="utf-8")
    monkeypatch.setattr(datos, "_PATH", ruta)
    datos.invalidar()
    yield ruta
    datos.invalidar()


def leer(ruta):
    return json.loads(ruta.read_text(encoding="utf-8"))


def test_guarda_lo_valido_y_conserva_el_resto(datos_tmp):
    mc = datos.guardar_minecraft({"host": " mc.example.com ", "port": "25566", "version": "1.21.1",
                                  "usuario": "LuneBot", "dueno": "Diego_01", "pensar_cada_s": 60,
                                  "defender": "false", "solo_dueno": True, "estilo_frases": "Sobrio"})
    assert mc["host"] == "mc.example.com" and mc["port"] == 25566 and mc["version"] == "1.21.1"
    assert mc["usuario"] == "LuneBot" and mc["dueno"] == "Diego_01" and mc["pensar_cada_s"] == 60
    assert mc["defender"] is False and mc["solo_dueno"] is True and mc["estilo_frases"] == "sobrio"
    d = leer(datos_tmp)
    assert d["apis"] == {"openrouter_key": "sk-no-tocar"}              # lo demás intacto
    assert d["minecraft"]["_nota"] == "de la plantilla"
    assert not datos_tmp.with_name("datos.json.tmp").exists()           # atómico: sin restos


def test_claves_ajenas_y_visor_no_se_escriben(datos_tmp):
    datos.guardar_minecraft({"dueno": "Diego_01", "clave_rara": "<script>", "visor": True, "apis": {"x": 1}})
    d = leer(datos_tmp)
    assert "clave_rara" not in d["minecraft"] and "apis" not in d["minecraft"]
    assert d["minecraft"]["visor"] is False and "x" not in d["apis"]


@pytest.mark.parametrize("cambios,texto", [
    ({"host": "http://evil.com"}, "servidor"), ({"host": "a b"}, "servidor"), ({"host": ""}, "servidor"),
    ({"host": "mc.example.com:25565"}, "puerto"), ({"host": 5}, "servidor"),
    ({"port": 0}, "puerto"), ({"port": 70000}, "puerto"), ({"port": "abc"}, "puerto"), ({"port": True}, "puerto"),
    ({"port": 25565.5}, "puerto"),
    ({"version": "latest"}, "versión"), ({"version": 1.21}, "versión"),
    ({"usuario": "ab"}, "nick"), ({"dueno": "con espacio"}, "nick"), ({"dueno": "x" * 17}, "nick"),
    ({"pensar_cada_s": 10}, "Pensar"), ({"pensar_cada_s": 4000}, "Pensar"),
    ({"defender": "quizá"}, "sí o no"), ({"estilo_frases": "kawaii"}, "estilo"),
    ({"usuario": "Diego_01", "dueno": "diego_01"}, "igual"),
])
def test_rechaza_sin_guardar_nada(datos_tmp, cambios, texto):
    antes = datos_tmp.read_bytes()
    with pytest.raises(ValueError, match=texto):
        datos.guardar_minecraft(cambios)
    assert datos_tmp.read_bytes() == antes


def test_no_puede_llamarse_como_el_dueno_guardado(datos_tmp):
    datos.guardar_minecraft({"dueno": "Diego_01"})
    with pytest.raises(ValueError, match="igual"):
        datos.guardar_minecraft({"usuario": "DIEGO_01"})


def test_vaciar_nicks_y_version_vale(datos_tmp):
    datos.guardar_minecraft({"dueno": "Diego_01", "version": "1.20.4"})
    mc = datos.guardar_minecraft({"dueno": "", "version": "", "usuario": None})
    assert mc["dueno"] == "" and mc["version"] == "" and mc["usuario"] == ""


def test_sin_cambios_no_escribe(datos_tmp):
    antes = datos_tmp.stat().st_mtime_ns
    assert datos.guardar_minecraft({})["host"] == "localhost"
    assert datos_tmp.stat().st_mtime_ns == antes
    with pytest.raises(ValueError):
        datos.guardar_minecraft(["no", "dict"])


def test_dos_guardados_a_la_vez_no_se_pisan(datos_tmp, monkeypatch):
    """Ajustes y `/mc bot on` guardando a la vez: sin cerrojo, el segundo escribía su copia
    vieja y el cambio del primero se perdía."""
    import threading
    import time

    cargar_real = datos.cargar

    def cargar_lento():
        d = cargar_real()
        time.sleep(0.05)                # ensancha la ventana leer → guardar
        return d

    monkeypatch.setattr(datos, "cargar", cargar_lento)
    hilos = [threading.Thread(target=datos.guardar_minecraft, args=({"host": "mc.example.com"},)),
             threading.Thread(target=datos.guardar_minecraft, args=({"pensar_cada_s": 90},))]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(5)
    mc = leer(datos_tmp)["minecraft"]
    assert mc["host"] == "mc.example.com" and mc["pensar_cada_s"] == 90
