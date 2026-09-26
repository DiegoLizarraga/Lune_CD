"""
Tests de lune_core/frases_mascota.py: qué dice la mascota en cada evento.

Probabilidades con azar sembrado, cooldown global de 20 s con reloj falso, la
bolsa que no repite, las frases del personaje que sobrescriben a las de Lune y
el JSON que se manda a la página. Sin Qt ni red.
"""
import json
import random
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lune_core import frases_mascota as fm  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent


class Reloj:
    """Reloj monótono falso: avanza solo con `avanzar`."""

    def __init__(self, t: float = 1000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def avanzar(self, s: float) -> None:
        self.t += s


def sin_cooldown(personaje=None, semilla=1):
    return fm.FrasesMascota(personaje, reloj=Reloj(), rng=random.Random(semilla), cooldown_s=0)


# ── Frases base ──────────────────────────────────────────────────────────────────

def test_eventos_y_probabilidades():
    assert fm.EVENTOS == ("arrastre", "soltar", "caricia", "dormir", "despertar", "mareo", "aparecer")
    assert fm.PROBABILIDADES == {"arrastre": 0.45, "soltar": 0.30, "caricia": 0.60, "dormir": 0.50,
                                 "despertar": 0.70, "mareo": 1.00, "aparecer": 0.50}
    assert fm.COOLDOWN_S == 20.0
    for ev in fm.EVENTOS:
        assert fm.FRASES_BASE[ev], ev
        assert len(set(fm.FRASES_BASE[ev])) == len(fm.FRASES_BASE[ev]), f"repetidas en {ev}"
        for f in fm.FRASES_BASE[ev]:
            assert f == f.strip() and len(f) <= fm.MAX_LARGO
            assert "amo~" not in f.lower()


# Las 4 listas FRASES que tenía fijas companion_vrm.html hasta el corte 3.
FRASES_VIEJAS_VRM = {
    "arrastre": ["Eh, eh, ¿a dónde me llevas?", "¿Me mudas de sitio otra vez?",
                 "Vale, pero con cuidado.", "Ay… no me sueltes."],
    "caricia": ["…Está bien, un poco más.", "Eso. Justo ahí.", "No te acostumbres."],
    "dormir": ["zzz…"],
    "despertar": ["¿Eh? Ya, ya estoy.", "No estaba dormida. Pensaba."],
}


def test_las_frases_de_la_mascota_salen_de_python():
    """companion_vrm.html ya no elige frases: las elige FrasesMascota en Python (las
    dos mascotas) y las viejas listas de la página siguen en FRASES_BASE."""
    html = (RAIZ / "ui_web" / "companion_vrm.html").read_text(encoding="utf-8")
    assert not re.search(r"\bFRASES\b|\bfrase\(", html), "la página no debe elegir frases"
    for ev, frases in FRASES_VIEJAS_VRM.items():
        for frase in frases:
            assert frase in fm.FRASES_BASE[ev], (ev, frase)
    # Las dos mascotas de escritorio las piden a FrasesMascota con los eventos.
    for archivo in ("ui/companion.py", "ui/avatar_overlay.py"):
        src = (RAIZ / archivo).read_text(encoding="utf-8")
        assert "from lune_core.frases_mascota import frases_para" in src, archivo
        assert "self._frases.elegir(evento)" in src and "self._frases.set_personaje(" in src, archivo
    comp = (RAIZ / "ui" / "companion.py").read_text(encoding="utf-8")
    # evento de la página → frase → burbuja de la página
    assert 'self._frase("arrastre" if datos.get("on") else "soltar")' in comp
    assert "window.comentar && window.comentar({_js_str(t)}, {MS_FRASE})" in comp
    # (el comportamiento, con Qt: tests/test_mascota_corte3.py)


# ── Probabilidades ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("evento", fm.EVENTOS)
def test_probabilidad_de_cada_evento_con_azar_sembrado(evento):
    f = sin_cooldown(semilla=12345)
    n = 4000
    hablo = sum(1 for _ in range(n) if f.elegir(evento) is not None)
    p = fm.PROBABILIDADES[evento]
    if p >= 1.0:
        assert hablo == n
    else:
        assert abs(hablo / n - p) < 0.035, (evento, hablo / n, p)


def test_mismo_azar_mismas_frases():
    f1, f2 = sin_cooldown(semilla=99), sin_cooldown(semilla=99)
    assert [f1.elegir("arrastre") for _ in range(50)] == [f2.elegir("arrastre") for _ in range(50)]


def test_forzar_ignora_dado_y_cooldown():
    reloj = Reloj()
    f = fm.FrasesMascota(None, reloj=reloj, rng=random.Random(1))
    assert f.elegir("soltar", forzar=True) in fm.FRASES_BASE["soltar"]
    assert f.en_cooldown()
    assert f.elegir("soltar", forzar=True) in fm.FRASES_BASE["soltar"]


# ── Cooldown global ──────────────────────────────────────────────────────────────

def test_cooldown_global_de_20_s_entre_eventos():
    reloj = Reloj()
    f = fm.FrasesMascota(None, reloj=reloj, rng=random.Random(3))
    primera = f.elegir("aparecer", forzar=True)
    assert primera and f.ultima == ("aparecer", primera)
    assert f.restante_cooldown() == pytest.approx(20.0)
    # En cooldown calla (cualquier evento) y no gasta el dado
    estado = f._rng.getstate()
    for ev in ("arrastre", "soltar", "caricia", "dormir", "despertar", "aparecer"):
        assert f.elegir(ev) is None
    assert f._rng.getstate() == estado
    reloj.avanzar(19.9)
    assert f.en_cooldown() and f.elegir("despertar") is None
    reloj.avanzar(0.1)
    assert not f.en_cooldown()
    # Pasado el cooldown vuelve a tirar el dado: con p .7 sale en pocos intentos
    dijo = None
    for _ in range(30):
        dijo = f.elegir("despertar")
        if dijo:
            break
    assert dijo in fm.FRASES_BASE["despertar"]
    assert f.restante_cooldown() == pytest.approx(20.0)


def test_mareo_se_salta_el_cooldown_pero_lo_reinicia():
    reloj = Reloj()
    f = fm.FrasesMascota(None, reloj=reloj, rng=random.Random(5))
    f.elegir("aparecer", forzar=True)
    reloj.avanzar(5)
    assert f.elegir("mareo") in fm.FRASES_BASE["mareo"]           # prioritario y p = 1
    assert f.restante_cooldown() == pytest.approx(20.0)            # vuelve a empezar
    reloj.avanzar(15)
    assert f.elegir("caricia") is None


def test_reiniciar_y_marcar_hablado():
    reloj = Reloj()
    f = fm.FrasesMascota(None, reloj=reloj, rng=random.Random(5))
    f.marcar_hablado()
    assert f.en_cooldown()
    f.reiniciar_cooldown()
    assert not f.en_cooldown() and f.restante_cooldown() == 0.0


# ── Bolsa sin repetir ────────────────────────────────────────────────────────────

def test_bolsa_no_repite_hasta_agotar_ni_en_el_cambio_de_tanda():
    elementos = list("abcdef")
    b = fm.Bolsa(elementos, random.Random(11))
    anterior = None
    for _ in range(40):
        tanda = [b.siguiente() for _ in range(len(elementos))]
        assert sorted(tanda) == elementos
        assert tanda[0] != anterior
        anterior = tanda[-1]
    assert fm.Bolsa([], random.Random(1)).siguiente() is None
    uno = fm.Bolsa(["x"], random.Random(1))
    assert [uno.siguiente() for _ in range(3)] == ["x", "x", "x"]


def test_elegir_recorre_todas_las_frases_antes_de_repetir():
    f = sin_cooldown(semilla=21)
    base = fm.FRASES_BASE["arrastre"]
    dichas = [f.elegir("arrastre", forzar=True) for _ in range(len(base))]
    assert sorted(dichas) == sorted(base)
    siguiente = f.elegir("arrastre", forzar=True)
    assert siguiente != dichas[-1]


# ── Frases del personaje ─────────────────────────────────────────────────────────

def test_frases_del_personaje_sobrescriben_por_evento():
    personaje = {
        "nombre": "Aria",
        "frases_mascota": {
            "arrastre": ["¡Eh, que me mareo!", "  ¡Eh, que me mareo!  ", "", 5, "Otra   con\nsaltos"],
            "Caricia": {"frases": ["Jeje"], "p": 0.9},
            "soltar": [],                                   # callada
            "dormir": {"p": 0.1},                           # solo la probabilidad
            "despertar": "Una sola",
            "mareo": [None, 3],                             # todo basura → se queda la base
            "pudor": ["fuera de alcance"],                  # evento desconocido
            "aparecer": {"frases": ["Hola"], "p": 7},       # p recortada a 1
        },
    }
    f = sin_cooldown(personaje)
    assert f.nombre == "Aria"
    assert f.frases("arrastre") == ["¡Eh, que me mareo!", "Otra con saltos"]
    assert f.frases("caricia") == ["Jeje"] and f.probabilidad("caricia") == 0.9
    assert f.frases("soltar") == [] and f.elegir("soltar", forzar=True) is None
    assert f.frases("dormir") == list(fm.FRASES_BASE["dormir"]) and f.probabilidad("dormir") == 0.1
    assert f.frases("despertar") == ["Una sola"]
    assert f.frases("mareo") == list(fm.FRASES_BASE["mareo"])
    assert f.frases("pudor") == [] and f.elegir("pudor", forzar=True) is None
    assert f.probabilidad("aparecer") == 1.0
    assert f.frases("arrastre")[0] in [f.elegir("arrastre", forzar=True) for _ in range(4)]
    # Lo que no trae el personaje sale de la base
    sin = sin_cooldown({"nombre": "Lune"})
    assert sin.frases("caricia") == list(fm.FRASES_BASE["caricia"])


def test_frases_largas_se_recortan_y_hay_tope():
    larga = "x" * 500
    f = sin_cooldown({"frases_mascota": {"caricia": [larga] + [f"f{i}" for i in range(100)]}})
    frases = f.frases("caricia")
    assert len(frases) == fm.MAX_FRASES
    assert len(frases[0]) == fm.MAX_LARGO and frases[0].endswith("…")


def test_personaje_raro_no_revienta():
    for p in (None, {}, {"frases_mascota": None}, {"frases_mascota": ["a"]}, {"frases_mascota": {"caricia": 5}}, "x"):
        f = sin_cooldown(p)
        assert f.frases("caricia") == list(fm.FRASES_BASE["caricia"])


def test_set_personaje_conserva_el_cooldown():
    reloj = Reloj()
    f = fm.FrasesMascota(None, reloj=reloj, rng=random.Random(1))
    f.elegir("aparecer", forzar=True)
    f.set_personaje({"nombre": "Aria", "frases_mascota": {"caricia": ["Jeje"]}})
    assert f.en_cooldown() and f.frases("caricia") == ["Jeje"]


# ── Para la página ───────────────────────────────────────────────────────────────

def test_como_json():
    f = fm.FrasesMascota({"nombre": "Aria", "frases_mascota": {"soltar": [], "caricia": {"frases": ["Jeje"], "p": 0.9}}},
                         reloj=Reloj(), rng=random.Random(1))
    texto = f.como_json()
    assert "\n" not in texto and "¿" in texto and "\\u00bf" not in texto   # ensure_ascii=False
    d = json.loads(texto)
    assert d["v"] == 1 and d["personaje"] == "Aria"
    assert d["cooldown_s"] == 20.0 and d["prioritarios"] == ["mareo"]
    assert list(d["eventos"]) == list(fm.EVENTOS)
    assert d["eventos"]["soltar"] == {"p": 0.3, "frases": []}
    assert d["eventos"]["caricia"] == {"p": 0.9, "frases": ["Jeje"]}
    assert d["eventos"]["arrastre"]["frases"] == list(fm.FRASES_BASE["arrastre"])
    assert d == f.como_dict()


def test_frases_para_usa_el_personaje_activo(monkeypatch):
    from nucleo import personajes
    monkeypatch.setattr(personajes, "get_activo", lambda: {"nombre": "Nyx", "frases_mascota": {"dormir": ["zz"]}})
    f = fm.frases_para(reloj=Reloj(), rng=random.Random(1))
    assert f.nombre == "Nyx" and f.frases("dormir") == ["zz"]
    g = fm.frases_para({"nombre": "Lune"}, reloj=Reloj())
    assert g.nombre == "Lune"

    def rota():
        raise RuntimeError("sin datos.json")
    monkeypatch.setattr(personajes, "get_activo", rota)
    assert fm.frases_para(reloj=Reloj()).frases("dormir") == list(fm.FRASES_BASE["dormir"])
