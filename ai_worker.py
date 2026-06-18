"""
ai_worker.py — Hilo que consulta a la IA (OpenRouter/Ollama) sin congelar la UI.
Inyecta el system prompt, el contexto de memoria y las reglas de herramientas.
"""
import asyncio

from PyQt6.QtCore import QThread, pyqtSignal

from theme import PROVIDER_META
from utils import log_error


class AIWorker(QThread):
    token_received = pyqtSignal(str)
    response_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, ai_manager, message: str, provider_id: str, extra_context: str = ""):
        super().__init__()
        self.ai_manager    = ai_manager
        self.message       = message
        self.provider_id   = provider_id
        self.extra_context = extra_context
        self._buffer       = ""

    def run(self):
        try:
            sys_val = PROVIDER_META[self.provider_id]["system"]
            system_prompt = sys_val() if callable(sys_val) else sys_val

            if self.extra_context:
                system_prompt = system_prompt + "\n\nCONTEXTO DE MEMORIA DEL USUARIO:\n" + self.extra_context

            system_prompt += (
                "\n\n=========================================\n"
                "REGLAS DE HERRAMIENTAS DE ESCRITORIO:\n"
                "Puedes ejecutar acciones en el PC del usuario si lo consideras necesario. "
                "Para hacerlo, DEBES incluir uno de los siguientes comandos exactamente al FINAL de tu respuesta:\n\n"
                "1. Para buscar en Google o Youtube:\n   ABRIR_BUSQUEDA:[términos]\n"
                "2. Para abrir una URL:\n   ABRIR_URL:[url completa con https://]\n"
                "3. Para lanzar una app:\n   TOOL:lanzar_app:[nombre_del_programa]\n"
                "4. Para verificar info del PC:\n   TOOL:sistema_info:\n"
            )

            def on_token(token):
                self._buffer += token
                self.token_received.emit(self._buffer)

            loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
            try:
                response = loop.run_until_complete(
                    self.ai_manager.chat(self.message, system_prompt, provider=self.provider_id, on_token=on_token)
                )
            finally: loop.close()

            self.response_ready.emit(response or "Sin respuesta")
        except Exception as e:
            log_error(f"AIWorker error: {e}"); self.error_occurred.emit(str(e))
