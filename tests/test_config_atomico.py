"""
Tests de nucleo/config.py con varios escritores (app, patata, tema, bot).

Qué se comprueba:
- dos instancias de Config sobre el mismo archivo cambian claves distintas y
  sobreviven las dos (gana el último por clave, no por archivo), también con
  save() en bloque y entre procesos de verdad;
- un config.json corrupto no se pisa con los valores por defecto: se aparta;
- la escritura es atómica (temporal + os.replace) y no deja restos;
- la ruta por defecto va anclada a la raíz del repo, no al directorio de trabajo;
- DEFAULT_CONFIG trae las claves de la serie 10.3+ y NO las del alcance recortado.
"""
import json
import logging
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import nucleo.config as modulo_config  # noqa: E402
from nucleo.config import Config  # noqa: E402


def leer(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


# ── Varios escritores ──────────────────────────────────────────────────────────

def test_dos_instancias_cambian_claves_distintas_y_sobreviven_las_dos(tmp_path):
    ruta = tmp_path / "config.json"
    app = Config(config_path=str(ruta))
    patata = Config(config_path=str(ruta))        # cargada antes de que la app escriba

    app.set("avatar", "companion_x", 100)
    patata.set("patata", "caritas", "kaomoji")     # no sabe nada del cambio de la app
    app.set("chat", "aburrimiento_min", 3)         # y la app tampoco del de patata

    disco = leer(ruta)
    assert disco["avatar"]["companion_x"] == 100
    assert disco["patata"]["caritas"] == "kaomoji"
    assert disco["chat"]["aburrimiento_min"] == 3
    # cada instancia ve también lo del otro tras su propio guardado
    assert app.get("patata", "caritas") == "kaomoji"
    assert patata.get("avatar", "companion_x") == 100
    # y una tercera que arranca ahora lo ve todo
    assert Config(config_path=str(ruta)).get("avatar", "companion_x") == 100


def test_misma_clave_gana_el_ultimo_aunque_repita_su_propio_valor(tmp_path):
    ruta = tmp_path / "config.json"
    a = Config(config_path=str(ruta))
    b = Config(config_path=str(ruta))
    a.set("avatar", "vrm_tamano", "grande")
    b.set("avatar", "vrm_tamano", "pequeno")
    # `a` ya tenía "grande" en memoria: su set explícito tiene que ganar igual
    a.set("avatar", "vrm_tamano", "grande")
    assert leer(ruta)["avatar"]["vrm_tamano"] == "grande"
    assert b.get("avatar", "vrm_tamano") == "pequeno"      # b no relee hasta escribir
    assert b.recargar() is True
    assert b.get("avatar", "vrm_tamano") == "grande"
    assert b.recargar() is False                           # nada nuevo


def test_set_feature_tambien_fusiona(tmp_path):
    ruta = tmp_path / "config.json"
    a = Config(config_path=str(ruta))
    b = Config(config_path=str(ruta))
    a.set_feature("voz_auto", True)
    b.set_feature("markdown", False)
    disco = leer(ruta)
    assert disco["features"]["voz_auto"] is True and disco["features"]["markdown"] is False


def test_save_en_bloque_no_pisa_lo_de_otros(tmp_path):
    """El panel de ajustes nativo cambia config.config a mano y llama a save()."""
    ruta = tmp_path / "config.json"
    panel = Config(config_path=str(ruta))
    otro = Config(config_path=str(ruta))
    otro.set("tema", "preset", "rosa")
    notas = panel.config.setdefault("notas", {})
    notas["top_k"] = 7
    panel.config["voz"]["idioma"] = "en"
    panel.save()
    disco = leer(ruta)
    assert disco["tema"]["preset"] == "rosa"
    assert disco["notas"]["top_k"] == 7 and disco["voz"]["idioma"] == "en"
    # las referencias a las secciones siguen vivas tras la recarga
    assert notas is panel.config["notas"] and panel.get("tema", "preset") == "rosa"


_FALTA = object()


class SeccionVigilada(dict):
    """Sección de config que apunta, tras cada cambio, lo que vería un lector
    concurrente de `clave` (get() lee sin el lock desde otros hilos)."""

    def __init__(self, datos, clave):
        super().__init__(datos)
        self.clave, self.vistos = clave, []

    def _ver(self):
        self.vistos.append(dict.get(self, self.clave, _FALTA))

    def clear(self):
        super().clear(); self._ver()

    def update(self, *a, **kw):
        super().update(*a, **kw); self._ver()

    def __setitem__(self, k, v):
        super().__setitem__(k, v); self._ver()

    def __delitem__(self, k):
        super().__delitem__(k); self._ver()

    def pop(self, *a):
        r = super().pop(*a); self._ver(); return r


def test_la_recarga_nunca_deja_una_seccion_vacia_a_la_vista(tmp_path):
    """La revisión: _reemplazar_en_sitio hacía clear() + update() y, entre medias,
    un lector de otro hilo (la voz, el worker de la IA) veía la sección vacía y
    se quedaba con el valor por defecto."""
    ruta = tmp_path / "config.json"
    lector = Config(config_path=str(ruta))
    escritor = Config(config_path=str(ruta))
    antes = lector.get("voz", "idioma")
    voz = SeccionVigilada(lector.config["voz"], "idioma")
    lector.config["voz"] = voz
    escritor.set("voz", "idioma", "en")
    escritor.set("voz", "dispositivo_salida", "Altavoces (Realtek)")
    assert lector.recargar() is True
    assert lector.config["voz"] is voz                        # la misma sección, en su sitio
    assert lector.get("voz", "idioma") == "en"
    assert lector.get("voz", "dispositivo_salida") == "Altavoces (Realtek)"
    assert voz.vistos and all(v in (antes, "en") for v in voz.vistos), voz.vistos


def test_la_recarga_quita_las_claves_que_ya_no_estan_sin_vaciar(tmp_path):
    ruta = tmp_path / "config.json"
    lector = Config(config_path=str(ruta))
    escritor = Config(config_path=str(ruta))
    voz = SeccionVigilada(lector.config["voz"], "idioma")
    lector.config["voz"] = voz
    voz_sin_seguimiento = dict(voz)
    dict.__setitem__(voz, "clave_vieja", 1)                   # no está en DEFAULT_CONFIG
    lector._base["voz"]["clave_vieja"] = 1                    # como si viniera del disco
    escritor.set("voz", "idioma", "fr")
    lector.recargar()
    assert "clave_vieja" not in lector.config["voz"] and lector.get("voz", "idioma") == "fr"
    assert all(v is not _FALTA for v in voz.vistos)
    assert set(lector.config["voz"]) == set(voz_sin_seguimiento)


def test_lector_en_otro_hilo_no_ve_valores_por_defecto(tmp_path):
    import threading
    ruta = tmp_path / "config.json"
    lector = Config(config_path=str(ruta))
    escritor = Config(config_path=str(ruta))
    escritor.set("voz", "dispositivo_salida", "A")
    lector.recargar()
    raros, parar = [], threading.Event()

    def leer_sin_parar():
        while not parar.is_set():
            v = lector.get("voz", "dispositivo_salida")
            if v not in ("A", "B"):
                raros.append(v)
    h = threading.Thread(target=leer_sin_parar)
    h.start()
    try:
        for i in range(60):
            escritor.set("voz", "dispositivo_salida", "AB"[i % 2])
            lector.recargar()
    finally:
        parar.set()
        h.join(10)
    assert raros == []


def test_las_copias_de_un_config_corrupto_no_se_suben_a_git():
    """_apartar_corrupto deja config.json.corrupto-* en la raíz del repo (con
    preferencias y rutas personales) y el entorno de Diego publica solo."""
    import shutil
    git = shutil.which("git")
    if not git or not (RAIZ / ".git").exists():
        pytest.skip("sin git o fuera del repo")
    for nombre in ("config.json.corrupto-20260101-000000", "config.json.corrupto-20260101-000000-2",
                   ".config.json.abc123.tmp", "config.json"):
        r = subprocess.run([git, "check-ignore", "-q", nombre], cwd=RAIZ)
        assert r.returncode == 0, f"{nombre} no está en .gitignore"


def test_varios_procesos_a_la_vez_no_pierden_claves(tmp_path):
    """Dos procesos escribiendo claves distintas a la vez: al final están las dos."""
    ruta = tmp_path / "config.json"
    Config(config_path=str(ruta))
    guion = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {str(RAIZ)!r})
        from nucleo.config import Config
        cfg = Config(config_path={str(ruta)!r})
        clave = sys.argv[1]
        for i in range(25):
            cfg.set("chat", clave, i)
    """)
    procesos = [subprocess.Popen([sys.executable, "-c", guion, clave])
                for clave in ("max_sesiones", "aburrimiento_min")]
    for p in procesos:
        assert p.wait(timeout=60) == 0
    disco = leer(ruta)
    assert disco["chat"]["max_sesiones"] == 24
    assert disco["chat"]["aburrimiento_min"] == 24


# ── JSON corrupto ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("contenido", ['{"features": {"voz_auto": tru', "[1, 2, 3]", "\xff\xfe basura"])
def test_json_corrupto_se_aparta_y_no_se_pisa(tmp_path, caplog, contenido):
    ruta = tmp_path / "config.json"
    crudo = contenido.encode("latin-1")
    ruta.write_bytes(crudo)
    with caplog.at_level(logging.WARNING, logger="lune.config"):
        cfg = Config(config_path=str(ruta))
    apartados = list(tmp_path.glob("config.json.corrupto-*"))
    assert len(apartados) == 1
    assert apartados[0].read_bytes() == crudo                  # el original, intacto
    assert leer(ruta)["features"]["voz_auto"] is False          # y uno nuevo válido
    assert cfg.feature("respuestas_predeterminadas") is True
    assert any("corrupto" in r.getMessage() for r in caplog.records)


def test_dos_corruptos_seguidos_no_se_pisan_entre_si(tmp_path):
    ruta = tmp_path / "config.json"
    ruta.write_text("{roto 1", encoding="utf-8")
    Config(config_path=str(ruta))
    ruta.write_text("{roto 2", encoding="utf-8")
    Config(config_path=str(ruta))
    contenidos = sorted(p.read_text(encoding="utf-8") for p in tmp_path.glob("config.json.corrupto-*"))
    assert contenidos == ["{roto 1", "{roto 2"]


def test_corrupto_a_mitad_de_sesion_se_aparta_al_guardar(tmp_path):
    ruta = tmp_path / "config.json"
    cfg = Config(config_path=str(ruta))
    ruta.write_text("{editado a mano y roto", encoding="utf-8")
    cfg.set("avatar", "companion_x", 5)
    assert leer(ruta)["avatar"]["companion_x"] == 5
    assert [p.read_text(encoding="utf-8") for p in tmp_path.glob("config.json.corrupto-*")] == ["{editado a mano y roto"]


def test_bom_de_editor_no_cuenta_como_corrupto(tmp_path):
    ruta = tmp_path / "config.json"
    ruta.write_text(json.dumps({"features": {"voz_auto": True}}), encoding="utf-8-sig")
    cfg = Config(config_path=str(ruta))
    assert cfg.feature("voz_auto") is True
    assert not list(tmp_path.glob("config.json.corrupto-*"))


# ── Escritura atómica ──────────────────────────────────────────────────────────

def test_escritura_atomica_con_temporal_en_la_misma_carpeta(tmp_path, monkeypatch):
    ruta = tmp_path / "config.json"
    cfg = Config(config_path=str(ruta))
    reemplazos = []
    real = os.replace

    def espia(origen, destino):
        reemplazos.append((Path(origen), Path(destino)))
        return real(origen, destino)

    monkeypatch.setattr(modulo_config.os, "replace", espia)
    cfg.set("avatar", "companion_y", 42)
    assert len(reemplazos) == 1
    origen, destino = reemplazos[0]
    assert destino == ruta and origen.parent == ruta.parent and origen != ruta
    assert leer(ruta)["avatar"]["companion_y"] == 42
    assert sorted(p.name for p in tmp_path.iterdir()) == ["config.json"]   # sin restos


def test_si_falla_la_escritura_el_archivo_viejo_queda_intacto(tmp_path, monkeypatch):
    ruta = tmp_path / "config.json"
    cfg = Config(config_path=str(ruta))
    cfg.set("avatar", "companion_x", 1)
    antes = ruta.read_bytes()

    def falla(*_a, **_k):
        raise OSError("disco lleno")

    monkeypatch.setattr(modulo_config.os, "fsync", falla)
    cfg.set("avatar", "companion_x", 2)               # no lanza
    assert ruta.read_bytes() == antes
    assert sorted(p.name for p in tmp_path.iterdir()) == ["config.json"]


def test_reintenta_si_otro_proceso_tiene_el_archivo_abierto(tmp_path, monkeypatch):
    """En Windows os.replace falla con PermissionError si alguien lo está leyendo."""
    ruta = tmp_path / "config.json"
    cfg = Config(config_path=str(ruta))
    real = os.replace
    fallos = {"n": 2}

    def ocupado(origen, destino):
        if fallos["n"]:
            fallos["n"] -= 1
            raise PermissionError(32, "El proceso no tiene acceso al archivo")
        return real(origen, destino)

    monkeypatch.setattr(modulo_config.os, "replace", ocupado)
    monkeypatch.setattr(modulo_config, "_PAUSA_REEMPLAZO_S", 0.001)
    cfg.set("avatar", "companion_x", 9)
    assert leer(ruta)["avatar"]["companion_x"] == 9 and fallos["n"] == 0


# ── Ruta anclada ───────────────────────────────────────────────────────────────

def test_la_ruta_por_defecto_no_depende_del_directorio_de_trabajo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert modulo_config._anclar("config.json") == modulo_config.RAIZ / "config.json"
    assert modulo_config._anclar(None) == modulo_config.RUTA_CONFIG
    assert modulo_config.RUTA_CONFIG == RAIZ / "config.json"
    # una ruta relativa cuelga de la raíz del repo, no del cwd
    raiz_falsa = tmp_path / "repo"
    raiz_falsa.mkdir()
    monkeypatch.setattr(modulo_config, "RAIZ", raiz_falsa)
    cfg = Config()
    assert cfg.config_path == (raiz_falsa / "config.json").resolve()
    assert (raiz_falsa / "config.json").exists() and not (tmp_path / "config.json").exists()
    # y las rutas absolutas (las de los tests) se respetan
    otra = tmp_path / "otra" / "c.json"
    assert Config(config_path=str(otra)).config_path == otra.resolve()


# ── Claves nuevas ──────────────────────────────────────────────────────────────

def test_claves_de_la_serie_10_3_y_nada_del_alcance_recortado():
    d = Config.DEFAULT_CONFIG
    for seccion in ("salvapantallas", "alarmas", "baile", "juego", "sistema", "discord", "minecraft",
                    "comida", "tema", "efectos", "menu_radial", "menu", "atajos", "bandeja", "patata"):
        assert isinstance(d.get(seccion), dict), seccion
    for clave in ("siempre_encima", "fps_max", "seguir_cursor", "peso_cabeza", "peso_torso", "peso_ojos",
                  "sentarse_ventanas", "sentarse_barra", "microexpresiones", "volumen_sfx"):
        assert clave in d["avatar"], clave
    for clave in ("edge_voz", "edge_rate", "edge_pitch", "edge_volumen", "gtts_tld"):
        assert clave in d["voz"], clave
    assert d["features"]["sonido_tecleo"] is False
    assert d["interfaz"]["en_barra_tareas"] is True
    # Alcance recortado: ni hambre, ni asomarse, ni bandeja Win32 en patata, ni API/router.
    assert "hambre" not in d["comida"] and "hambre_por_hora" not in d["comida"]
    assert "asomarse_bordes" not in d["avatar"]
    assert "bandeja" not in d["patata"]
    assert not {"api", "api_http", "router", "router_intencion"} & set(d)
    # Los combos por defecto se pueden registrar tal cual
    from servicios.atajos_globales import comprobar
    for atajo in d["atajos"]["lista"]:
        error, _aviso = comprobar(atajo["combo"])
        assert error is None, (atajo, error)


def test_las_claves_nuevas_no_se_podan_al_releer(tmp_path):
    ruta = tmp_path / "config.json"
    Config(config_path=str(ruta)).set("baile", "favoritos", ["caramelldansen"])
    Config(config_path=str(ruta)).set("atajos", "lista", [{"id": "voz", "combo": "ctrl+alt+shift+j"}])
    cfg = Config(config_path=str(ruta))
    assert cfg.get("baile", "favoritos") == ["caramelldansen"]
    assert cfg.get("atajos", "lista") == [{"id": "voz", "combo": "ctrl+alt+shift+j"}]
