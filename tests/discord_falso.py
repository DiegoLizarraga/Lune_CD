"""
Dobles para los tests de Discord (servicios/discord_ipc.py y discord_presencia.py).

`DiscordFalso` hace de extremo servidor de `\\\\.\\pipe\\discord-ipc-N`, en memoria:
entiende las tramas que Lune escribe (cabecera <II + JSON) y contesta como el
cliente de Discord (READY, respuesta a SET_ACTIVITY con el mismo nonce, ERROR,
CLOSE 4000, PING). Nada toca una tubería de verdad.
"""
import threading

from servicios import discord_ipc as di

ID = "123456789012345678"
ID2 = "876543210987654321"


class Reloj:
    """Reloj falso: `dormir` lo adelanta (sin esperas reales)."""

    def __init__(self, t=0.0):
        self.t = float(t)

    def __call__(self):
        return self.t

    def dormir(self, s):
        self.t += s


class DiscordFalso:
    def __init__(self, *, ready=True, cierre_handshake=0, error_actividad="", trozo=0, responde_actividad=True):
        self.ready = ready
        self.cierre_handshake = cierre_handshake
        self.error_actividad = error_actividad
        self.responde_actividad = responde_actividad
        self.trozo = trozo                 # >0: cada ReadFile devuelve como mucho esto
        self.entrada = b""
        self.recibidas = []                # (op, datos) que escribió Lune
        self.salida = bytearray()          # lo que Lune leerá
        self.cerrada = False
        self.rota = False
        self.bytes_escritos = b""
        self._lock = threading.Lock()

    # API de la tubería
    def disponibles(self):
        if self.rota:
            raise OSError(109, "tubería rota")
        with self._lock:
            return len(self.salida)

    def leer(self, n):
        if self.rota:
            raise OSError(109, "tubería rota")
        if self.trozo:
            n = min(n, self.trozo)
        with self._lock:
            b = bytes(self.salida[:n])
            del self.salida[:n]
        return b

    def escribir(self, b):
        if self.rota:
            raise OSError(232, "tubería cerrándose")
        self.bytes_escritos += b
        self.entrada += b
        tramas, self.entrada = di.desempaquetar(self.entrada)
        for op, datos in tramas:
            self.recibidas.append((op, datos))
            self._responder(op, datos)

    def cerrar(self):
        self.cerrada = True

    # Lado Discord
    def mandar(self, op, datos):
        with self._lock:
            self.salida += di.empaquetar(op, datos)

    def _responder(self, op, datos):
        if op == di.OP_HANDSHAKE:
            if self.cierre_handshake:
                self.mandar(di.OP_CLOSE, {"code": self.cierre_handshake, "message": "Invalid Client ID"})
            elif self.ready:
                self.mandar(di.OP_FRAME, {"cmd": "DISPATCH", "evt": "READY", "nonce": None,
                                          "data": {"v": 1, "user": {"id": "42", "username": "diego",
                                                                    "global_name": "Diego"}}})
        elif op == di.OP_FRAME and datos.get("cmd") == "SET_ACTIVITY" and self.responde_actividad:
            if self.error_actividad:
                self.mandar(di.OP_FRAME, {"cmd": "SET_ACTIVITY", "evt": "ERROR", "nonce": datos.get("nonce"),
                                          "data": {"code": 4000, "message": self.error_actividad}})
            else:
                self.mandar(di.OP_FRAME, {"cmd": "SET_ACTIVITY", "evt": None, "nonce": datos.get("nonce"),
                                          "data": (datos.get("args") or {}).get("activity")})

    def ordenes(self, cmd):
        return [d for op, d in self.recibidas if op == di.OP_FRAME and d.get("cmd") == cmd]

    def actividades(self):
        return [(d.get("args") or {}).get("activity") for d in self.ordenes("SET_ACTIVITY")]


class ClienteFalso:
    """Un ClienteIPC de mentira para la máquina de la presencia.

    `modo`: "ok" (conecta), "sin_discord" (no hay tubería) o "4000" (ID rechazado)."""

    def __init__(self, client_id, modo="ok"):
        self.client_id = client_id
        self.modo = modo
        self.conectado = False
        self.codigo_cierre = 0
        self.error = ""
        self.enviadas = []          # (actividad, pid)
        self.cerrado = None         # el `limpiar` con que se cerró
        self.atendidas = 0
        self.timeouts = []

    def conectar(self, timeout_s=5.0, *, cancelar=None):
        self.timeouts.append(timeout_s)
        if self.modo == "ok":
            self.conectado = True
            return {"ok": True, "usuario": "Diego", "error": "", "codigo": 0}
        if self.modo == "4000":
            return {"ok": False, "usuario": "", "error": "El Application ID de Discord no es válido.",
                    "codigo": 4000}
        return {"ok": False, "usuario": "", "error": "Discord no está abierto.", "codigo": 0}

    def set_activity(self, actividad, pid, **kw):
        self.enviadas.append((actividad, pid))
        return {"ok": True, "error": "", "codigo": 0}

    def atender(self):
        self.atendidas += 1

    def cerrar(self, limpiar=True):
        if limpiar and self.conectado:
            self.enviadas.append((None, "cierre"))
        self.cerrado = limpiar
        self.conectado = False

    def caer(self, codigo=0):
        """Discord se cerró (o mandó CLOSE con `codigo`)."""
        self.conectado = False
        self.codigo_cierre = codigo
        self.error = "Discord cerró la conexión."


class FabricaClientes:
    """cliente=… de Presencia: crea ClienteFalso con los modos en orden (el último se repite)."""

    def __init__(self, *modos):
        self.modos = list(modos or ("ok",))
        self.clientes = []

    def __call__(self, client_id):
        modo = self.modos.pop(0) if len(self.modos) > 1 else self.modos[0]
        c = ClienteFalso(client_id, modo)
        self.clientes.append(c)
        return c

    @property
    def ultimo(self):
        return self.clientes[-1] if self.clientes else None

    def enviadas(self):
        return [e for c in self.clientes for e in c.enviadas]


class MutexFalso:
    def __init__(self, libre=True):
        self.libre = libre
        self.nombres = []
        self.adquisiciones = 0
        self.liberado = 0

    def __call__(self, nombre):          # fábrica: mutex=MutexFalso(...)
        self.nombres.append(nombre)
        return self

    def adquirir(self):
        self.adquisiciones += 1
        return self.libre

    def liberar(self):
        self.liberado += 1


class ConfigFalsa:
    """Config con get/set como nucleo.config.Config (en memoria)."""

    def __init__(self, **discord):
        self.d = {
            "discord": {"activo": False, "client_id": "", "mostrar_modelo": False, "boton_url": ""},
            "sistema": {"autoinicio": False, "autoinicio_como": "bandeja", "autoinicio_retraso_s": 20},
            "avatar": {"vrm_archivo": ""},
            "interfaz": {"modo": "web"},
        }
        self.d["discord"].update(discord)
        self.sets = []

    def get(self, seccion, clave, defecto=None):
        return self.d.get(seccion, {}).get(clave, defecto)

    def set(self, seccion, clave, valor):
        self.d.setdefault(seccion, {})[clave] = valor
        self.sets.append((seccion, clave, valor))
