"""
respuestas.py — Banco de respuestas predeterminadas para Lune CD
================================================================
Intercepta frases comunes (saludos, agradecimientos, despedidas, hora,
fecha, "quién eres", chistes, etc.) ANTES de llamar a la IA.

Beneficios:
  Respuesta instantánea (0 ms de latencia de red)
  Cero consumo de tokens / API
  Personalidad consistente, alegre y servicial de Lune

Uso desde main.py:
    from respuestas import BancoRespuestas
    banco = BancoRespuestas()
    rta = banco.responder("hola")     # -> str alegre, o None si no aplica
    if rta:
        # mostrar al instante sin llamar a la IA
        ...

El banco es configurable: se puede desactivar por completo o silenciar
categorías concretas pasando un set de categorías deshabilitadas.
"""

import re
import random
from datetime import datetime
from typing import Optional, List, Dict, Callable


# ── Días y meses en español (para hora/fecha sin depender del locale) ──────────
_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _saludo_segun_hora() -> str:
    h = datetime.now().hour
    if 5 <= h < 12:
        return "Buenos días"
    if 12 <= h < 20:
        return "Buenas tardes"
    return "Buenas noches"


class BancoRespuestas:
    """Banco de respuestas predeterminadas con la voz alegre de Lune."""

    def __init__(self, nombre_asistente: str = "Lune",
                 categorias_desactivadas: Optional[set] = None,
                 nombre_usuario: Optional[str] = None):
        self.nombre = nombre_asistente or "Lune"
        self.desactivadas = categorias_desactivadas or set()
        self.nombre_usuario = nombre_usuario
        self._reglas = self._construir_reglas()

    # ── API pública ────────────────────────────────────────────────────────────

    def set_nombre_usuario(self, nombre: Optional[str]):
        self.nombre_usuario = nombre

    def responder(self, texto: str) -> Optional[str]:
        """
        Devuelve una respuesta predeterminada alegre si el mensaje encaja
        en alguna categoría, o None para dejar pasar el mensaje a la IA.
        """
        if not texto or not texto.strip():
            return None

        limpio = texto.lower().strip()
        # Normaliza signos para que "¿hola!" también encaje
        normal = re.sub(r"[¿?¡!.,]", "", limpio).strip()

        for categoria, patrones, generador in self._reglas:
            if categoria in self.desactivadas:
                continue
            for patron in patrones:
                if patron.fullmatch(normal) or patron.fullmatch(limpio):
                    return generador()
        return None

    # ── Helpers de personalidad ────────────────────────────────────────────────

    def _con_nombre(self) -> str:
        return f", {self.nombre_usuario}" if self.nombre_usuario else ""

    def _elegir(self, opciones: List[str]) -> str:
        return random.choice(opciones)

    # ── Generadores de respuesta (alegre y servicial) ──────────────────────────

    def _r_saludo(self) -> str:
        n = self._con_nombre()
        return self._elegir([
            f"{_saludo_segun_hora()}{n} ¿En qué te ayudo hoy?",
            f"¡Hola{n}! Aquí estoy, lista para lo que necesites.",
            f"¡Hey{n}! Qué gusto verte. ¿Por dónde empezamos?",
            f"{_saludo_segun_hora()}{n} Cuéntame, ¿qué hacemos?",
        ])

    def _r_que_tal(self) -> str:
        return self._elegir([
            "¡De maravilla y con pilas! ¿Y tú cómo vas?",
            "¡Genial! Lista para cocinar ideas contigo ¿Tú qué tal?",
            "¡Muy bien, gracias por preguntar! ¿En qué andamos hoy?",
        ])

    def _r_gracias(self) -> str:
        n = self._con_nombre()
        return self._elegir([
            f"¡Con muchísimo gusto{n}! Para eso estoy.",
            "¡Un placer ayudarte! ¿Algo más en lo que te eche la mano?",
            f"¡Cuando quieras{n}! Me encanta ser útil.",
            "¡Nada que agradecer! Aquí seguimos.",
        ])

    def _r_despedida(self) -> str:
        n = self._con_nombre()
        return self._elegir([
            f"¡Hasta pronto{n}! Aquí estaré cuando me necesites.",
            f"¡Nos vemos{n}! Cuídate mucho.",
            "¡Que te vaya increíble! Vuelve cuando quieras.",
            f"¡Adiós{n}! Fue un gusto, como siempre.",
        ])

    def _r_quien_eres(self) -> str:
        return self._elegir([
            f"Soy {self.nombre} tu asistente de escritorio: te ayudo a escribir, "
            "buscar, abrir apps y mantener tus cosas en orden. ¡Y siempre con buena onda!",
            f"¡Soy {self.nombre}! Tu copiloto digital. Puedo investigar, redactar, "
            "lanzar programas, recordar cosas por ti y hasta optimizar tu PC.",
        ])

    def _r_que_haces(self) -> str:
        return (
            "¡Puedo con bastante!\n"
            "• Buscar en Google/YouTube y abrir webs al instante\n"
            "• Lanzar apps de tu PC\n"
            "• Recordar tus datos y preferencias\n"
            "• Optimizar y limpiar tu equipo (estilo Stacer)\n"
            "• Escribir, resumir, traducir e investigar contigo\n"
            "Solo dime qué necesitas."
        )

    def _r_hora(self) -> str:
        ahora = datetime.now()
        return f"Son las {ahora.strftime('%I:%M %p').lstrip('0')}. {self._elegir(['¡Aprovecha el día! ', '¡A darle con todo! ', ''])}".strip()

    def _r_fecha(self) -> str:
        ahora = datetime.now()
        dia_semana = _DIAS[ahora.weekday()]
        mes = _MESES[ahora.month - 1]
        return f"Hoy es {dia_semana}, {ahora.day} de {mes} de {ahora.year}. ¡Que sea un gran día! "

    def _r_chiste(self) -> str:
        return self._elegir([
            "¿Qué le dice un bit al otro? — Nos vemos en el bus ",
            "¿Por qué los programadores confunden Halloween con Navidad? "
            "Porque OCT 31 = DEC 25 ",
            "Iba a contarte un chiste sobre UDP… pero igual no sé si te llega ",
            "¿Cuál es el animal más antiguo? La cebra, porque está en blanco y negro ",
            "Tengo un chiste de la nube… pero mejor te lo guardo en caché ",
        ])

    def _r_animo(self) -> str:
        n = self._con_nombre()
        return self._elegir([
            f"¡Tú puedes con esto{n}! Vamos paso a paso, yo te acompaño.",
            "Respira hondo y vamos por partes. ¡Lo resolvemos juntos! ",
            f"Confío en ti{n} Dime en qué te apoyo y lo sacamos adelante.",
        ])

    def _r_te_quiero(self) -> str:
        return self._elegir([
            "¡Aww! Yo también te aprecio un montón. ¡Hacemos buen equipo!",
            "Qué lindo. Aquí estaré siempre para ayudarte.",
        ])

    def _r_ayuda(self) -> str:
        return (
            "¡Claro que sí! Algunas cosas que puedes pedirme:\n"
            "• «abre youtube» / «busca en google gatos»\n"
            "• «lanza la app paint»\n"
            "• «recuerda que me llamo...»\n"
            "• «estado del pc» o abre el Optimizador\n"
            "…o simplemente charla conmigo "
        )

    # ── Construcción de reglas (categoría, patrones regex, generador) ───────────

    def _p(self, *frases: str) -> List[re.Pattern]:
        """Compila frases a patrones de coincidencia exacta (tolerando espacios)."""
        return [re.compile(f, re.IGNORECASE) for f in frases]

    def _construir_reglas(self):
        # Orden importa: lo más específico primero.
        reglas: List = [
            ("que_tal", self._p(
                r"(c[oó]mo|que) (est[aá]s|andas|te va|te encuentras|vas)",
                r"qu[eé] (tal|onda|hubo|pasa|hay)",
                r"todo bien",
            ), self._r_que_tal),

            ("saludo", self._p(
                r"hola+", r"hola lune", r"buenas", r"buenos d[ií]as",
                r"buenas tardes", r"buenas noches", r"hey", r"holi",
                r"ey", r"qu[eé] hay", r"saludos",
            ), self._r_saludo),

            ("gracias", self._p(
                r"gracias", r"muchas gracias", r"mil gracias",
                r"te lo agradezco", r"gracias lune", r"ty", r"thx",
            ), self._r_gracias),

            ("despedida", self._p(
                r"adi[oó]s", r"chau", r"chao", r"hasta luego",
                r"hasta pronto", r"nos vemos", r"bye", r"me voy",
                r"hasta ma[ñn]ana", r"buenas noches lune",
            ), self._r_despedida),

            ("quien_eres", self._p(
                r"qui[eé]n eres", r"qui[eé]n sos", r"c[oó]mo te llamas",
                r"cu[aá]l es tu nombre", r"qu[eé] eres",
            ), self._r_quien_eres),

            ("que_haces", self._p(
                r"qu[eé] (puedes|sabes) hacer", r"para qu[eé] sirves",
                r"qu[eé] haces", r"cu[aá]les son tus funciones",
            ), self._r_que_haces),

            ("ayuda", self._p(
                r"ayuda", r"help", r"no s[eé] qu[eé] hacer",
                r"c[oó]mo te uso", r"c[oó]mo funcionas",
            ), self._r_ayuda),

            ("hora", self._p(
                r"qu[eé] hora es", r"dime la hora", r"la hora",
                r"qu[eé] hora", r"me dices la hora",
            ), self._r_hora),

            ("fecha", self._p(
                r"qu[eé] d[ií]a es hoy", r"qu[eé] fecha es",
                r"la fecha", r"qu[eé] d[ií]a es", r"dime la fecha",
                r"en qu[eé] d[ií]a estamos",
            ), self._r_fecha),

            ("chiste", self._p(
                r"cu[eé]ntame un chiste", r"dime un chiste", r"un chiste",
                r"hazme re[ií]r", r"cu[eé]ntame algo gracioso",
            ), self._r_chiste),

            ("animo", self._p(
                r"estoy (triste|cansad[oa]|estresad[oa]|agobiad[oa])",
                r"me siento mal", r"no puedo m[aá]s", r"qu[eé] d[ií]a tan malo",
            ), self._r_animo),

            ("afecto", self._p(
                r"te quiero", r"te amo", r"eres genial", r"eres la mejor",
                r"me caes bien", r"eres incre[ií]ble",
            ), self._r_te_quiero),
        ]
        return reglas


# ── Prueba rápida manual ───────────────────────────────────────────────────────
if __name__ == "__main__":
    banco = BancoRespuestas(nombre_usuario="Diego")
    for prueba in ["hola", "¿cómo estás?", "gracias!", "qué hora es",
                   "quién eres", "cuéntame un chiste", "adiós", "¿qué día es hoy?",
                   "ayúdame con un código en python"]:
        print(f"> {prueba}\n {banco.responder(prueba)}\n")
