"""
Dobles de la integración de los cortes 9 y 10 (tests/test_contratos_c910.py y
tests/test_anfitriones_c910_int.py). No es un archivo de tests: lo importan.

- `ProcesoFalso`: el ProcesoBot de Minecraft sin node (arrancar/parar/pausas/orden;
  `vivo` dice si «node» sigue en marcha). Con `conectar=True` avisa «conectado» al
  arrancar, como el bot de verdad al entrar en el servidor.
- `CancionFalsa`: la canción por el Mezclador (sprites y patata), sin audio.
- `Registro`: lo que crean las fábricas (controladores, procesos) para contar vivos.
- `fabricas_escenario(reg, carpeta)`: las fábricas de ui/montaje_escenario con los
  controladores DE VERDAD (ControlMMD con la Biblioteca de verdad en `carpeta`, ffmpeg
  falso; ControlMinecraft con ProcesoFalso) para montar_escritorio / FABRICAS_C4.
- `biblioteca(carpeta, config)`: una biblioteca con dos bailes (Alfa con canción, Beta .vrma).
"""
from __future__ import annotations

import random
import sys
from pathlib import Path
from typing import Any, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bailes_falsos as bf  # noqa: E402

DUENO = "Diego_01"


class ProcesoFalso:
    """lune_core.minecraft_proceso.ProcesoBot sin node ni red."""

    def __init__(self, reg: "Registro" = None, *, instalado: bool = True, node_ok: bool = True,
                 conectar: bool = False):
        self.reg = reg
        self.vivo = False
        self._instalado = instalado
        self.node_ok = node_ok
        self.conectar = conectar
        self.arranques: List[dict] = []
        self.ordenes, self.dichos, self.pausas, self.paradas = [], [], [], []
        self.instalaciones = 0
        self.on_evento = self.on_log = self.on_fin = None
        if reg is not None:
            reg.procesos.append(self)

    def requisitos(self, refrescar: bool = False) -> dict:
        return {"node": "v24.19.0" if self.node_ok else None, "node_ok": self.node_ok, "npm": True,
                "instalado": self._instalado}

    def instalado(self) -> bool:
        return self._instalado

    def instalar(self, cancelar=None):
        self.instalaciones += 1
        self._instalado = True
        return True, "Bot de Minecraft instalado."

    def arrancar(self, cfg, probar=False):
        self.arranques.append(dict(cfg))
        self.vivo = True
        if self.conectar and callable(self.on_evento):
            self.on_evento({"tipo": "conectado", "nick": cfg.get("nick", "Lune")})
        return True, "Arrancando el bot…"

    def orden(self, id_, texto):
        self.ordenes.append((id_, texto))
        return True

    def decir(self, texto):
        self.dichos.append(texto)
        return True

    def pausa_llm(self, on):
        self.pausas.append(("llm", bool(on)))
        return True

    def pausa_autonomo(self, on):
        self.pausas.append(("autonomo", bool(on)))
        return True

    def parar(self, espera_s=4.0):
        self.paradas.append(espera_s)
        self.vivo = False


class CancionFalsa:
    """servicios/cancion_python.ReproductorCancion sin audio."""

    def __init__(self):
        self.cargadas, self.reproducciones, self.pausas = [], [], []
        self.pos, self.duracion, self.terminado, self.liberada = 0.0, 0.0, False, 0

    def cargar(self, ruta, al_listo):
        self.cargadas.append(Path(ruta))
        self.duracion = 42.0
        al_listo(True, "")

    def reproducir(self, vol):
        self.reproducciones.append(round(float(vol), 3))
        self.terminado, self.pos = False, 0.0
        return True

    def pausar(self, on):
        self.pausas.append(bool(on))

    def volumen(self, v):
        pass

    def posicion(self):
        return None if self.terminado else self.pos

    def parar(self):
        self.terminado = True

    def liberar(self):
        self.liberada += 1


class Registro:
    def __init__(self):
        self.mmds: List[Any] = []
        self.mcs: List[Any] = []
        self.procesos: List[ProcesoFalso] = []
        self.conectar = False              # los procesos nuevos avisan «conectado» al arrancar

    @staticmethod
    def _vivo(ctl) -> bool:
        try:
            return bool(getattr(ctl, "_iniciado", False))
        except RuntimeError:               # el QObject ya se borró
            return False

    def mmds_vivos(self):
        return [m for m in self.mmds if self._vivo(m)]

    def mcs_vivos(self):
        return [m for m in self.mcs if self._vivo(m)]

    def nodes_vivos(self):
        return [p for p in self.procesos if p.vivo]


def biblioteca(carpeta: Path, config: Any):
    """Biblioteca de verdad en `carpeta` (bailes/ y cache/) con Alfa (VMD + canción) y Beta (.vrma)."""
    from nucleo import bailes as nbl
    raiz = Path(carpeta)
    dir_bailes = raiz / "bailes"
    if not (dir_bailes / "Alfa").exists():
        bf.hacer_baile(dir_bailes, "Alfa", cara=bf.vmd([], [("あ", 5)]))
        bf.hacer_baile(dir_bailes, "Beta", vrma_datos=bf.vrma(3.0), audio=("tema.ogg", bf.OGG))
    ej = bf.EjecutarFalso(pcm=bf.clics(120, primero=0.1))
    return nbl.Biblioteca(dir_bailes, raiz / "cache", config=config, ffmpeg="ffm", ejecutar=ej)


def fabricas_escenario(reg: Registro, carpeta: Path) -> dict:
    """Las fábricas de montar_escenario con los controladores de verdad y los dobles de `reg`."""
    from ui.minecraft_qt import ControlMinecraft
    from ui.mmd_qt import ControlMMD

    def mmd(escritorio, config, *, anfitrion=None, en_ui=None, parent=None):
        m = ControlMMD(escritorio, config, biblioteca=biblioteca(carpeta, config), cancion=CancionFalsa,
                       anfitrion=anfitrion, en_ui=en_ui, parent=parent, hilo=False,
                       dialogo=lambda parent=None: [], abrir=lambda ruta: None, rng=random.Random(2))
        reg.mmds.append(m)
        return m

    def minecraft(escritorio, config, *, anfitrion=None, voice=None, en_ui=None, parent=None):
        p = ProcesoFalso(reg, conectar=reg.conectar)
        mc = ControlMinecraft(escritorio, config, anfitrion=anfitrion, voice=voice, proceso=p, en_ui=en_ui,
                              parent=parent, rng=random.Random(3), rutas=lambda: [],
                              datos_mc=lambda: {"host": "localhost", "port": 25565, "dueno": DUENO,
                                                "usuario": "", "solo_dueno": True},
                              personaje=lambda: {"nombre": "Lune"}, llm=lambda: None,
                              hilo=lambda fn: fn())
        reg.mcs.append(mc)
        return mc

    return {"mmd": mmd, "minecraft": minecraft}
