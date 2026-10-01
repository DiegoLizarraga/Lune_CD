"""
Tests de los logs de Lune (nucleo/utils.py) y de la rotación de logs/audit.jsonl
(lune_core/herramientas.py).

- Un archivo por día que cambia solo al escribir un registro de otro día, sin
  renombrar nada (la app y patata escriben en el mismo a la vez).
- Al arrancar: fuera los lune_*.log de más de 14 días y, si la carpeta pasa del tope,
  los más viejos. El de hoy nunca.
- Sin stderr (Lune.exe, pythonw) no hay StreamHandler; instalada, el archivo desde INFO.
- audit.jsonl rota a audit.1.jsonl al pasar de 1 MB y se guardan 3.
"""
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo import rutas, utils  # noqa: E402
from lune_core import herramientas as H  # noqa: E402


def _registro(texto: str, cuando: datetime) -> logging.LogRecord:
    r = logging.LogRecord("lune.prueba", logging.INFO, __file__, 1, texto, None, None)
    r.created = cuando.timestamp()
    return r


# ── Archivo diario ────────────────────────────────────────────────────────────

def test_cambia_de_archivo_al_cambiar_el_dia(tmp_path):
    h = utils.ArchivoDiarioHandler(tmp_path / "logs")
    h.setFormatter(logging.Formatter("%(message)s"))
    try:
        h.handle(_registro("antes de medianoche", datetime(2026, 9, 29, 23, 59, 59)))
        assert h.ruta_actual == tmp_path / "logs" / "lune_20260929.log"
        h.handle(_registro("después de medianoche", datetime(2026, 9, 30, 0, 0, 1)))
        assert h.ruta_actual == tmp_path / "logs" / "lune_20260930.log"
        h.handle(_registro("sigue el día", datetime(2026, 9, 30, 12, 0, 0)))
    finally:
        h.close()
    ayer = (tmp_path / "logs" / "lune_20260929.log").read_text("utf-8")
    hoy = (tmp_path / "logs" / "lune_20260930.log").read_text("utf-8")
    assert ayer == "antes de medianoche\n"
    assert hoy == "después de medianoche\nsigue el día\n"
    assert sorted(p.name for p in (tmp_path / "logs").iterdir()) == ["lune_20260929.log", "lune_20260930.log"]


def test_dos_procesos_en_el_mismo_archivo_y_cambio_de_dia_con_el_otro_abierto(tmp_path):
    """La app y patata: el cambio de día de uno no toca el archivo que el otro tiene
    abierto (TimedRotatingFileHandler lo renombraba y en Windows fallaba)."""
    a = utils.ArchivoDiarioHandler(tmp_path)
    b = utils.ArchivoDiarioHandler(tmp_path)
    for h in (a, b):
        h.setFormatter(logging.Formatter("%(message)s"))
    errores = []
    a.handleError = b.handleError = lambda record: errores.append(record)
    try:
        dia1, dia2 = datetime(2026, 9, 29, 23, 0), datetime(2026, 9, 30, 1, 0)
        a.handle(_registro("app 1", dia1))
        b.handle(_registro("patata 1", dia1))
        a.handle(_registro("app 2", dia2))            # b sigue con el de ayer abierto
        b.handle(_registro("patata 1b", dia1))
        b.handle(_registro("patata 2", dia2))
    finally:
        a.close()
        b.close()
    assert not errores
    assert (tmp_path / "lune_20260929.log").read_text("utf-8").split() == \
        ["app", "1", "patata", "1", "patata", "1b"]
    assert (tmp_path / "lune_20260930.log").read_text("utf-8").split() == ["app", "2", "patata", "2"]


def test_crea_la_carpeta_si_no_existe(tmp_path):
    h = utils.ArchivoDiarioHandler(tmp_path / "no" / "existe")
    try:
        h.handle(_registro("hola", datetime.now()))
    finally:
        h.close()
    assert h.ruta_actual.read_text("utf-8").strip().endswith("hola")


# ── Limpieza al arrancar ──────────────────────────────────────────────────────

def _log(carpeta: Path, nombre: str, *, dias: float, tam: int = 10, ahora: float) -> Path:
    ruta = carpeta / nombre
    ruta.write_bytes(b"x" * tam)
    t = ahora - dias * 86400
    os.utime(ruta, (t, t))
    return ruta


def test_borra_los_de_mas_de_14_dias_y_nada_mas(tmp_path):
    ahora = datetime(2026, 9, 30, 12, 0).timestamp()
    viejo = _log(tmp_path, "lune_20260901.log", dias=29, ahora=ahora)
    justo = _log(tmp_path, "lune_20260915.log", dias=15, ahora=ahora)
    reciente = _log(tmp_path, "lune_20260927.log", dias=3, ahora=ahora)
    hoy = _log(tmp_path, "lune_20260930.log", dias=0, ahora=ahora)
    otros = [_log(tmp_path, n, dias=60, ahora=ahora) for n in ("audit.jsonl", "notas.txt", "otro.log")]
    borrados = utils.limpiar_logs(tmp_path, ahora=ahora)
    assert sorted(borrados) == sorted([viejo, justo])
    assert reciente.exists() and hoy.exists()
    assert all(p.exists() for p in otros), "solo lune_*.log"


def test_si_pasan_del_tope_se_van_los_mas_viejos_pero_nunca_el_de_hoy(tmp_path):
    ahora = datetime(2026, 9, 30, 12, 0).timestamp()
    a = _log(tmp_path, "lune_20260926.log", dias=4, tam=400, ahora=ahora)
    b = _log(tmp_path, "lune_20260927.log", dias=3, tam=400, ahora=ahora)
    c = _log(tmp_path, "lune_20260929.log", dias=1, tam=400, ahora=ahora)
    hoy = _log(tmp_path, "lune_20260930.log", dias=0, tam=400, ahora=ahora)
    # 1600 bytes con tope 900: fuera a y b (los más viejos); c y hoy quedan (800)
    assert sorted(utils.limpiar_logs(tmp_path, max_bytes=900, ahora=ahora)) == sorted([a, b])
    assert c.exists() and hoy.exists()
    # aunque el de hoy solo ya pase del tope, no se toca
    assert utils.limpiar_logs(tmp_path, max_bytes=10, ahora=ahora) == [c]
    assert hoy.exists()


def test_limpiar_sin_carpeta_no_falla(tmp_path):
    assert utils.limpiar_logs(tmp_path / "no_existe") == []


def test_constantes_de_retencion():
    assert utils.DIAS_LOGS == 14
    assert 15 * 1024 * 1024 <= utils.MAX_BYTES_LOGS <= 25 * 1024 * 1024


# ── Logger ────────────────────────────────────────────────────────────────────

@pytest.fixture
def logger_nuevo(monkeypatch, tmp_path):
    """Un Logger recién construido en tmp_path/logs, dejando el de la sesión como estaba."""
    lg = logging.getLogger("lune")
    handlers = lg.handlers[:]
    monkeypatch.setattr(utils.Logger, "_instance", None)
    monkeypatch.setattr(rutas, "LOCAL", tmp_path)
    creados = []

    def crear():
        utils.Logger._instance = None
        nuevo = utils.Logger()
        creados.append(nuevo)
        return nuevo

    yield crear
    for h in lg.handlers:
        if h not in handlers:
            h.close()
    lg.handlers = handlers


def test_logger_escribe_en_local_logs_y_limpia_al_arrancar(logger_nuevo, tmp_path):
    (tmp_path / "logs").mkdir()
    viejo = _log(tmp_path / "logs", "lune_20200101.log", dias=400, ahora=time.time())
    lg = logger_nuevo()
    assert not viejo.exists()
    archivo = [h for h in lg.logger.handlers if isinstance(h, utils.ArchivoDiarioHandler)]
    assert len(archivo) == 1 and archivo[0].carpeta == tmp_path / "logs"
    assert archivo[0].level == logging.DEBUG                      # desde el código, como siempre
    lg.info("hola desde los tests")
    hoy = tmp_path / "logs" / f"lune_{datetime.now():%Y%m%d}.log"
    assert "hola desde los tests" in hoy.read_text("utf-8")


def test_logger_sin_stderr_no_pone_consola(logger_nuevo, monkeypatch):
    monkeypatch.setattr(sys, "stderr", None)
    lg = logger_nuevo()
    assert not [h for h in lg.logger.handlers if type(h) is logging.StreamHandler]
    lg.error("sin consola no pasa nada")


def test_logger_con_stderr_si_pone_consola(logger_nuevo):
    lg = logger_nuevo()
    assert [h for h in lg.logger.handlers if type(h) is logging.StreamHandler]


def test_logger_instalada_guarda_desde_info(logger_nuevo, monkeypatch, tmp_path):
    monkeypatch.setattr(rutas, "INSTALADA", True)
    lg = logger_nuevo()
    archivo = [h for h in lg.logger.handlers if isinstance(h, utils.ArchivoDiarioHandler)][0]
    assert archivo.level == logging.INFO
    lg.debug("esto no")
    lg.info("esto sí")
    texto = archivo.ruta_actual.read_text("utf-8")
    assert "esto sí" in texto and "esto no" not in texto


# ── audit.jsonl ───────────────────────────────────────────────────────────────

def test_rotar_audit_guarda_tres_copias(tmp_path):
    audit = tmp_path / "audit.jsonl"
    for n in range(1, 6):
        audit.write_text(f"ronda {n}\n" + "x" * 50, encoding="utf-8")
        assert H.rotar_audit(audit, maximo=20) is True
        assert not audit.exists()
    nombres = sorted(p.name for p in tmp_path.iterdir())
    assert nombres == ["audit.1.jsonl", "audit.2.jsonl", "audit.3.jsonl"]
    assert (tmp_path / "audit.1.jsonl").read_text("utf-8").startswith("ronda 5")
    assert (tmp_path / "audit.3.jsonl").read_text("utf-8").startswith("ronda 3")


def test_rotar_audit_no_toca_uno_pequeno_ni_uno_que_no_existe(tmp_path):
    audit = tmp_path / "audit.jsonl"
    assert H.rotar_audit(audit) is False
    audit.write_text("{}\n", encoding="utf-8")
    assert H.rotar_audit(audit) is False and audit.exists()
    assert H.AUDIT_MAX_BYTES == 1024 * 1024 and H.AUDIT_COPIAS == 3


def test_la_sesion_rota_su_audit_al_pasar_del_tope(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "AUDIT_MAX_BYTES", 300)
    audit = tmp_path / "logs" / "audit.jsonl"
    sesion = H.Sesion(H.registro_basico(), audit_path=audit)
    for i in range(40):
        sesion._auditar("prueba", n=i, relleno="y" * 40)
    archivos = sorted(p.name for p in audit.parent.iterdir())
    assert archivos == ["audit.1.jsonl", "audit.2.jsonl", "audit.3.jsonl", "audit.jsonl"]
    assert audit.stat().st_size <= 300 + 200
    ultima = audit.read_text("utf-8").strip().splitlines()[-1]
    assert '"n": 39' in ultima
