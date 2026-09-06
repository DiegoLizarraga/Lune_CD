"""
Tests de la red de seguridad del Optimizador.

El bug que motivó estos tests: la categoría «caché de navegadores» apuntaba a
%APPDATA%/Mozilla/Firefox/Profiles, que NO es una caché sino la raíz de perfiles
(marcadores, contraseñas, cookies). Al limpiar se hacía rmtree sobre cada perfil.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from servicios.optimizador import (  # noqa: E402
    Optimizador, _ruta_vaciable, formatear_bytes,
)


# ── La guarda que impide borrar datos del usuario ──────────────────────────────

@pytest.mark.parametrize("nombre", [
    "Cache", "cache2", "Code Cache", "GPUCache", "Temp", "tmp",
    "CacheStorage", "Cache_Data",
])
def test_carpetas_de_cache_se_pueden_vaciar(tmp_path, nombre):
    ruta = tmp_path / nombre
    ruta.mkdir()
    assert _ruta_vaciable(ruta) is True


@pytest.mark.parametrize("nombre", [
    "Profiles",         # ← la que causaba el desastre
    "User Data",
    "Default",
    "Documents",
    "Desktop",
    "Downloads",
    "Firefox",
    "Mozilla",
    "AppData",
    "Roaming",
    "Windows",
])
def test_carpetas_de_datos_nunca_se_vacian(tmp_path, nombre):
    ruta = tmp_path / nombre
    ruta.mkdir()
    assert _ruta_vaciable(ruta) is False


def test_limpiar_dir_rechaza_una_carpeta_de_perfil(tmp_path):
    """Aunque alguien la meta a mano en las rutas, no debe tocarse."""
    perfil = tmp_path / "Profiles" / "abc.default-release"
    perfil.mkdir(parents=True)
    (perfil / "logins.json").write_text("contraseñas", encoding="utf-8")
    (perfil / "places.sqlite").write_text("marcadores", encoding="utf-8")

    opt = Optimizador()
    liberado, n, errores, bloqueada = opt._limpiar_dir(tmp_path / "Profiles")

    assert bloqueada is True
    assert (liberado, n) == (0, 0)
    assert (perfil / "logins.json").exists()
    assert (perfil / "places.sqlite").exists()


def test_limpiar_dir_si_vacia_una_cache_de_verdad(tmp_path):
    cache = tmp_path / "cache2"
    (cache / "entries").mkdir(parents=True)
    (cache / "entries" / "blob").write_bytes(b"x" * 100)
    (cache / "index").write_bytes(b"y" * 50)

    opt = Optimizador()
    liberado, n, _errores, bloqueada = opt._limpiar_dir(cache)

    assert bloqueada is False
    assert liberado == 150
    assert n == 2
    assert cache.exists()            # la carpeta se conserva
    assert not any(cache.iterdir())  # pero queda vacía


# ── Borrado por patrón: solo toca lo que casa ──────────────────────────────────

def test_patrones_solo_borran_los_archivos_indicados(tmp_path):
    carpeta = tmp_path / "Explorer"
    carpeta.mkdir()
    (carpeta / "thumbcache_256.db").write_bytes(b"a" * 10)
    (carpeta / "iconcache_32.db").write_bytes(b"b" * 10)
    (carpeta / "importante.txt").write_text("no me borres", encoding="utf-8")
    subcarpeta = carpeta / "subcarpeta"
    subcarpeta.mkdir()
    (subcarpeta / "dato.txt").write_text("tampoco", encoding="utf-8")

    opt = Optimizador()
    liberado, n, _errores, bloqueada = opt._limpiar_dir(
        carpeta, patrones=["thumbcache_*.db", "iconcache_*.db"]
    )

    assert bloqueada is False
    assert n == 2 and liberado == 20
    assert not (carpeta / "thumbcache_256.db").exists()
    assert not (carpeta / "iconcache_32.db").exists()
    assert (carpeta / "importante.txt").exists()
    assert (subcarpeta / "dato.txt").exists()


# ── Configuración real de categorías ───────────────────────────────────────────

def test_ninguna_ruta_configurada_apunta_a_datos_del_usuario():
    """
    Recorre las categorías reales de esta máquina y comprueba que todo lo que
    se vaciaría por completo pasa la guarda de seguridad.
    """
    opt = Optimizador()
    for cat in opt.categorias:
        if cat.es_papelera or cat.patrones:
            continue
        for ruta in cat.rutas:
            assert _ruta_vaciable(ruta), (
                f"La categoría «{cat.clave}» intentaría vaciar {ruta}, "
                "que no es una carpeta de caché."
            )


def test_cache_de_navegadores_nunca_incluye_la_raiz_de_un_perfil():
    opt = Optimizador()
    cat = next((c for c in opt.categorias if c.clave == "cache_navegadores"), None)
    if cat is None:
        pytest.skip("Categoría solo disponible en Windows")
    for ruta in cat.rutas:
        partes = [p.lower() for p in ruta.parts]
        assert ruta.name.lower() != "profiles"
        assert ruta.name.lower() != "user data"
        # Si es una ruta de Firefox, tiene que terminar en la caché
        if "firefox" in partes:
            assert ruta.name.lower() == "cache2"


# ── Formato ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("entrada,esperado", [
    (0, "0.0 B"),
    (1023, "1023.0 B"),
    (1024, "1.0 KB"),
    (1024 ** 3, "1.0 GB"),
])
def test_formatear_bytes(entrada, esperado):
    assert formatear_bytes(entrada) == esperado
