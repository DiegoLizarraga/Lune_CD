"""
Tests de /discord y /autoinicio en patata (servicios/sistema_terminal.py).

Con una presencia falsa y un módulo de autoinicio falso: nada toca Discord ni el
registro de Windows.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from discord_falso import ID, ConfigFalsa  # noqa: E402
from servicios import discord_presencia as dp  # noqa: E402
from servicios.sistema_terminal import SistemaTerminal  # noqa: E402


class PresenciaFalsa:
    def __init__(self):
        self.habilitaciones = []
        self.actualizaciones = 0
        self.cierres = 0
        self.e = {"activo": False, "conectado": False, "usuario": "", "error": "", "publicando": None,
                  "sin_id": False}

    def habilitar(self, on):
        self.habilitaciones.append(bool(on))

    def actualizar(self):
        self.actualizaciones += 1

    def estado(self):
        return dict(self.e)

    def cerrar(self, timeout=1.0):
        self.cierres += 1


class AutoinicioFalso:
    def __init__(self, registrado=False, aprobado=True):
        self.registrado = registrado
        self.aprobado = aprobado
        self.llamadas = []

    def establecer(self, quiere, modo=None, reg=None):
        self.llamadas.append((quiere, modo))
        self.registrado = bool(quiere)
        if quiere:
            self.aprobado = True
        return self.registrado and self.aprobado

    def activo(self, reg=None):
        return self.registrado and self.aprobado

    def estado(self, modo=None, reg=None):
        return {"activo": self.activo(), "registrado": self.registrado, "aprobado": self.aprobado,
                "ruta_ok": True, "modo_ok": True, "comando": "", "esperado": ""}


@pytest.fixture
def s():
    cfg = ConfigFalsa()
    estado = {"juego": False, "pensando": False}
    st = SistemaTerminal(None, cfg, en_juego=lambda: estado["juego"], pensando=lambda: estado["pensando"],
                         presencia=PresenciaFalsa(), autoinicio=AutoinicioFalso())
    st.estado_prueba = estado
    st.iniciar()
    yield st
    st.detener()


# ── /discord ───────────────────────────────────────────────────────────────────

def test_iniciar_habilita_segun_la_config(s):
    assert s._presencia.habilitaciones == [False]


def test_discord_estado_apagado(s):
    assert "apagado" in s.comando("/discord")
    assert "apagado" in s.comando("/discord estado")


def test_discord_on_sin_id_pide_el_application_id(s):
    r = s.comando("/discord on")
    assert s.config.get("discord", "activo") is True
    assert s._presencia.habilitaciones[-1] is True
    assert "Application ID" in r
    assert "falta el Application ID" in s.comando("/discord estado")


def test_discord_on_con_id(s):
    s.config.set("discord", "client_id", ID)
    r = s.comando("/discord on")
    assert "terminal" in r and "nunca" in r


def test_discord_off(s):
    s.comando("/discord on")
    assert "ya no" in s.comando("/discord off")
    assert s.config.get("discord", "activo") is False
    assert s._presencia.habilitaciones[-1] is False


def test_alternar_discord_para_el_menu(s):
    assert s.discord_activo is False
    s.alternar_discord()
    assert s.discord_activo is True and s._presencia.habilitaciones[-1] is True
    assert "ya no" in s.alternar_discord()
    assert s.discord_activo is False


def test_discord_id(s):
    assert "no parece" in s.comando("/discord id 1234")
    assert s.config.get("discord", "client_id") == ""
    r = s.comando(f"/discord id {ID}")
    assert "guardado" in r and "/discord on" in r
    assert s.config.get("discord", "client_id") == ID
    assert s._presencia.actualizaciones == 1
    assert ID in s.comando("/discord id")
    s.comando("/discord id borrar")
    assert s.config.get("discord", "client_id") == ""


def test_discord_estado_conectada_dice_que_ve_discord(s):
    s.config.set("discord", "activo", True)
    s.config.set("discord", "client_id", ID)
    s._presencia.e.update(activo=True, conectado=True, usuario="Diego",
                          publicando={"details": "Lune CD · Terminal", "state": "En la terminal"})
    r = s.comando("/discord estado")
    assert "como Diego" in r and "Discord ve: «Lune CD · Terminal — En la terminal»" in r


def test_discord_estado_sin_conectar_con_el_motivo(s):
    s.config.set("discord", "activo", True)
    s.config.set("discord", "client_id", ID)
    s._presencia.e.update(activo=True, error=dp.TXT_OTRA_LUNE)
    assert dp.TXT_OTRA_LUNE in s.comando("/discord estado")


def test_la_foto_de_patata_solo_lleva_terminal_pensando_y_juego(s):
    cfg = ConfigFalsa()
    act = dp.actividad_de(s.foto(), config=cfg, inicio_ms=0)
    assert (act["details"], act["state"]) == ("Lune CD · Terminal", "En la terminal")
    assert act["assets"]["small_image"] == "patata"
    s.estado_prueba["pensando"] = True
    assert dp.actividad_de(s.foto(), config=cfg, inicio_ms=0)["state"] == "Pensando…"
    s.estado_prueba["juego"] = True
    assert dp.actividad_de(s.foto(), config=cfg, inicio_ms=0) is None
    assert set(s.foto()) == {"modo", "render", "visible", "juego", "pensando"}


def test_detener_cierra_la_presencia(s):
    s.detener()
    assert s._presencia.cierres == 1


# ── /autoinicio ────────────────────────────────────────────────────────────────

def test_autoinicio_on_registra_la_variante_patata(s):
    r = s.comando("/autoinicio on")
    assert s._autoinicio.llamadas == [(True, "patata")]
    assert s.config.get("sistema", "autoinicio") is True
    assert "minimizada" in r


def test_autoinicio_off(s):
    s.comando("/autoinicio on")
    assert "ya no" in s.comando("/autoinicio off")
    assert s._autoinicio.llamadas[-1] == (False, "patata")
    assert s.config.get("sistema", "autoinicio") is False


def test_autoinicio_estado(s):
    r = s.comando("/autoinicio")
    assert "no" in r.splitlines()[0] and "en la bandeja, tras 20 s" in r
    s._autoinicio.registrado, s._autoinicio.aprobado = True, False
    assert "Administrador de tareas" in s.comando("/autoinicio estado")
    s._autoinicio.aprobado = True
    assert "sí" in s.comando("/autoinicio estado")


def test_autoinicio_como(s):
    r = s.comando("/autoinicio como mascota")
    assert s.config.get("sistema", "autoinicio_como") == "mascota" and "mascota" in r
    assert "Usa /autoinicio como" in s.comando("/autoinicio como escritorio")
    assert s.config.get("sistema", "autoinicio_como") == "mascota"


def test_autoinicio_espera(s):
    s.comando("/autoinicio espera 45")
    assert s.config.get("sistema", "autoinicio_retraso_s") == 45
    assert "0 a 120" in s.comando("/autoinicio espera 500")
    assert "Usa /autoinicio espera" in s.comando("/autoinicio espera mucho")
    assert s.config.get("sistema", "autoinicio_retraso_s") == 45


def test_autoinicio_si_no_puede_activarlo(s):
    s._autoinicio.establecer = lambda quiere, modo=None, reg=None: False
    assert "No pude activarlo" in s.comando("/autoinicio on")


# ── Otros ──────────────────────────────────────────────────────────────────────

def test_sentarse_es_de_la_mascota(s):
    assert "mascota de las ventanas" in s.comando("/sentarse")


@pytest.mark.parametrize("linea", ["hola", "/bailar", "/discordia", "", "   ", "/auto"])
def test_lo_que_no_es_suyo_devuelve_none(s, linea):
    assert s.comando(linea) is None


def test_uso_con_argumentos_raros(s):
    assert s.comando("/discord bailar").startswith("Uso:")
    assert s.comando("/autoinicio talvez").startswith("Uso:")


def test_sin_presencia_inyectada_crea_la_real_sin_hilo():
    """Discord apagado (por defecto): la presencia existe pero no hay hilo."""
    st = SistemaTerminal(None, ConfigFalsa(), autoinicio=AutoinicioFalso())
    st.iniciar()
    try:
        assert isinstance(st._presencia, dp.Presencia)
        assert st._presencia._hilo is None
    finally:
        st.detener()
