"""
notas_service.py — Puente entre la app y el RAG (lune_core/rag.py).

Mantiene el índice al día e inyecta las notas relevantes en cada mensaje. Todo
perezoso y tolerante a fallos: si Ollama no da embeddings o la carpeta no existe,
la app sigue como si nada (el RAG simplemente no aporta contexto).

El indexado corre en un hilo para no congelar la interfaz.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import List, Optional, Tuple

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from nucleo import datos, rutas

from nucleo.utils import log_info, log_error


class IndexadorWorker(QThread):
    listo = pyqtSignal(object)     # dict {archivo: n_trozos} o {"error": str}

    def __init__(self, almacen, carpeta: Path):
        super().__init__()
        self.almacen = almacen
        self.carpeta = carpeta

    def run(self):
        try:
            resumen = self.almacen.indexar_carpeta(self.carpeta)
            self.listo.emit(resumen)
        except Exception as e:
            log_error(f"[notas] indexado falló: {e}")
            self.listo.emit({"error": str(e)})


class NotasService(QObject):
    indexado = pyqtSignal(object)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.almacen = None
        self._worker = None
        self._lock = threading.Lock()

    # ── Estado ─────────────────────────────────────────────────────────────────
    @property
    def activo(self) -> bool:
        return bool(self.config.get("notas", "activo", False))

    def carpeta(self) -> Path:
        """notas.carpeta; si es relativa (la de serie, «notas»), cuelga de los datos del
        usuario, nunca del directorio de trabajo (instalada, el cwd es otro)."""
        c = Path(str(self.config.get("notas", "carpeta", "notas") or "notas")).expanduser()
        return c if c.is_absolute() else rutas.DATOS / c

    def _ruta_db(self) -> Path:
        return self.carpeta() / ".indice.rag.db"

    # ── Ciclo de vida ──────────────────────────────────────────────────────────
    def _asegurar_almacen(self) -> bool:
        """Crea el almacén perezosamente. False si no se puede (sin RAG)."""
        if self.almacen is not None:
            return True
        with self._lock:
            if self.almacen is not None:
                return True
            try:
                from lune_core.rag import crear_almacen
                carpeta = self.carpeta()
                carpeta.mkdir(parents=True, exist_ok=True)
                # Embeddings por Ollama (donde apunte la app: local o el host).
                url = datos.ollama_url() or None
                modelo = self.config.get("notas", "modelo_embeddings", "nomic-embed-text")
                self.almacen = crear_almacen(self._ruta_db(), url_ollama=url, modelo=modelo)
                return True
            except Exception as e:
                log_error(f"[notas] no pude crear el almacén: {e}")
                return False

    def reindexar(self):
        """Reindexa la carpeta en segundo plano. Emite `indexado` al terminar."""
        if not self.activo or not self._asegurar_almacen():
            self.indexado.emit({"error": "notas desactivadas o sin almacén"})
            return
        if self._worker and self._worker.isRunning():
            return
        self._worker = IndexadorWorker(self.almacen, self.carpeta())
        self._worker.listo.connect(self._on_indexado)
        self._worker.start()

    def _on_indexado(self, resumen):
        if "error" not in resumen:
            total = sum(resumen.values())
            log_info(f"[notas] indexadas {len(resumen)} nota(s), {total} trozo(s)")
        self.indexado.emit(resumen)

    # ── Recuperación (síncrona, con timeout corto vía el embedder) ─────────────
    def contexto_para(self, consulta: str) -> List[Tuple[str, str]]:
        """
        Notas relevantes para el mensaje, como [(fuente, texto), …]. Nunca lanza:
        si el RAG falla (Ollama caído, etc.) devuelve [] y la app sigue igual.
        """
        if not self.activo or not consulta.strip() or not self._asegurar_almacen():
            return []
        try:
            k = int(self.config.get("notas", "top_k", 3))
            return self.almacen.contexto_para(consulta, k=k)
        except Exception as e:
            log_error(f"[notas] recuperación falló: {e}")
            return []

    def contar(self) -> int:
        if not self._asegurar_almacen():
            return 0
        try:
            return self.almacen.contar()
        except Exception:
            return 0

    def cerrar(self):
        if self.almacen is not None:
            try:
                self.almacen.cerrar()
            except Exception:
                pass
