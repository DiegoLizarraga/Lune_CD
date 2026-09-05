"""
lune_core/rag.py — Memoria larga por recuperación (RAG) sobre notas markdown.

No sustituye a memoria.json (los hechos siguen ahí): añade una memoria de textos
largos. Metes notas en una carpeta, se trocean por encabezados, se convierten en
vectores (embeddings vía Ollama) y se guardan en SQLite. Al preguntar, se
recuperan los trozos más parecidos + recientes y se inyectan como [Contexto].

Diseño:
  · Troceado por encabezados markdown (#, ##, …) con solape de contexto; cada
    trozo lleva su archivo y su encabezado para poder citarlo.
  · Embeddings con caché por hash del contenido: no se recalcula lo que no cambió.
  · Ranking portado del único RAG real de AIRI: score = 1.2·similitud +
    0.2·recencia, umbral 0.5, top-k. Pero la recencia decae EXPONENCIALMENTE con
    una vida media configurable (la lineal de AIRI se volvía negativa a 30 días).
  · El embebedor es intercambiable (`Embedder`): en producción pega a Ollama; en
    tests, uno determinista sin red.

Sin numpy obligatorio: el coseno se calcula en Python puro (los vectores de
nomic-embed-text son 768 floats; para miles de trozos va de sobra). Si numpy
está, se usa y va más rápido.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

try:
    import numpy as _np
except Exception:  # numpy es opcional
    _np = None


# ── Troceado ────────────────────────────────────────────────────────────────────

@dataclass
class Trozo:
    doc: str          # nombre del archivo/fuente
    titulo: str       # encabezado bajo el que cae
    texto: str
    orden: int        # posición dentro del documento

    @property
    def id(self) -> str:
        h = hashlib.sha1(f"{self.doc}|{self.orden}|{self.texto}".encode("utf-8")).hexdigest()
        return h[:16]

    @property
    def hash_texto(self) -> str:
        return hashlib.sha1(self.texto.encode("utf-8")).hexdigest()[:16]


_ENCABEZADO = re.compile(r"^(#{1,6})\s+(.*)$")


def trocear_markdown(texto: str, doc: str, *, max_chars: int = 1200,
                     solape: int = 150) -> List[Trozo]:
    """
    Divide por encabezados; si una sección es larga, la parte en trozos de
    `max_chars` con `solape` caracteres de contexto entre ellos.
    """
    secciones: List[Tuple[str, List[str]]] = []
    titulo_actual = ""
    buffer: List[str] = []
    for linea in texto.splitlines():
        m = _ENCABEZADO.match(linea)
        if m:
            if buffer:
                secciones.append((titulo_actual, buffer))
            titulo_actual = m.group(2).strip()
            buffer = []
        else:
            buffer.append(linea)
    if buffer:
        secciones.append((titulo_actual, buffer))

    trozos: List[Trozo] = []
    orden = 0
    for titulo, lineas in secciones:
        cuerpo = "\n".join(lineas).strip()
        if not cuerpo:
            continue
        for pieza in _partir_largo(cuerpo, max_chars, solape):
            trozos.append(Trozo(doc=doc, titulo=titulo, texto=pieza, orden=orden))
            orden += 1
    return trozos


def _partir_largo(texto: str, max_chars: int, solape: int) -> List[str]:
    if len(texto) <= max_chars:
        return [texto]
    piezas, i = [], 0
    while i < len(texto):
        fin = min(i + max_chars, len(texto))
        # corta en un límite de frase/línea si hay uno cerca
        if fin < len(texto):
            corte = max(texto.rfind("\n", i, fin), texto.rfind(". ", i, fin))
            if corte > i + max_chars // 2:
                fin = corte + 1
        piezas.append(texto[i:fin].strip())
        if fin >= len(texto):
            break
        i = max(fin - solape, i + 1)
    return [p for p in piezas if p]


# ── Similitud ───────────────────────────────────────────────────────────────────

def coseno(a: Sequence[float], b: Sequence[float]) -> float:
    if _np is not None:
        va, vb = _np.asarray(a, dtype=float), _np.asarray(b, dtype=float)
        na, nb = _np.linalg.norm(va), _np.linalg.norm(vb)
        return float(va.dot(vb) / (na * nb)) if na and nb else 0.0
    s = sa = sb = 0.0
    for x, y in zip(a, b):
        s += x * y; sa += x * x; sb += y * y
    return s / math.sqrt(sa * sb) if sa and sb else 0.0


# ── Embebedores ─────────────────────────────────────────────────────────────────

class Embedder:
    """Interfaz: convierte una lista de textos en una lista de vectores."""
    dim: int = 0
    def embed(self, textos: List[str]) -> List[List[float]]:
        raise NotImplementedError


class EmbedderOllama(Embedder):
    """Embeddings reales vía Ollama (o cualquier endpoint /api/embeddings)."""
    def __init__(self, url: str, modelo: str = "nomic-embed-text", timeout: int = 60):
        self.url = url.rstrip("/")
        self.modelo = modelo
        self.timeout = timeout

    def embed(self, textos: List[str]) -> List[List[float]]:
        import requests
        vectores = []
        for t in textos:
            r = requests.post(f"{self.url}/api/embeddings",
                              json={"model": self.modelo, "prompt": t}, timeout=self.timeout)
            r.raise_for_status()
            vectores.append(r.json()["embedding"])
        if vectores and not self.dim:
            self.dim = len(vectores[0])
        return vectores


class EmbedderHash(Embedder):
    """
    Embebedor determinista SIN red, para tests y modo degradado. Proyecta el
    texto a un vector por bolsa de palabras con hashing. No es semántico de
    verdad, pero es estable y suficiente para probar el pipeline.
    """
    def __init__(self, dim: int = 64):
        self.dim = dim

    def embed(self, textos: List[str]) -> List[List[float]]:
        salida = []
        for t in textos:
            v = [0.0] * self.dim
            for palabra in re.findall(r"\w+", t.lower()):
                h = int(hashlib.md5(palabra.encode()).hexdigest(), 16)
                v[h % self.dim] += 1.0
            salida.append(v)
        return salida


# ── Almacén ─────────────────────────────────────────────────────────────────────

class AlmacenRAG:
    """SQLite con un trozo por fila y su vector. Caché de embeddings por hash."""

    def __init__(self, ruta_db: Path, embedder: Embedder):
        self.ruta = Path(ruta_db)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder
        self.db = sqlite3.connect(str(self.ruta))
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS trozos (
                id TEXT PRIMARY KEY, doc TEXT, titulo TEXT, texto TEXT,
                orden INTEGER, hash_texto TEXT, vector TEXT, actualizado REAL
            )""")
        self.db.execute("CREATE INDEX IF NOT EXISTS ix_doc ON trozos(doc)")
        self.db.commit()

    # ── Indexado ───────────────────────────────────────────────────────────────

    def indexar_texto(self, texto: str, doc: str, *, ahora: Optional[float] = None) -> int:
        """(Re)indexa un documento. Devuelve cuántos trozos quedaron."""
        ahora = ahora if ahora is not None else time.time()
        trozos = trocear_markdown(texto, doc)
        # Reutiliza vectores de trozos cuyo texto no cambió (caché por hash).
        cache = {h: v for h, v in self.db.execute(
            "SELECT hash_texto, vector FROM trozos WHERE doc=?", (doc,))}
        self.db.execute("DELETE FROM trozos WHERE doc=?", (doc,))

        por_calcular = [t for t in trozos if t.hash_texto not in cache]
        nuevos = {}
        if por_calcular:
            vs = self.embedder.embed([t.texto for t in por_calcular])
            nuevos = {t.hash_texto: json.dumps(v) for t, v in zip(por_calcular, vs)}

        filas = []
        for t in trozos:
            vec = cache.get(t.hash_texto) or nuevos.get(t.hash_texto)
            filas.append((t.id, t.doc, t.titulo, t.texto, t.orden, t.hash_texto, vec, ahora))
        self.db.executemany(
            "INSERT OR REPLACE INTO trozos VALUES (?,?,?,?,?,?,?,?)", filas)
        self.db.commit()
        return len(trozos)

    def indexar_carpeta(self, carpeta: Path, *, patrones=("*.md", "*.markdown", "*.txt")) -> dict:
        carpeta = Path(carpeta)
        resumen = {}
        vistos = set()
        for patron in patrones:
            for f in carpeta.rglob(patron):
                if f in vistos or not f.is_file():
                    continue
                vistos.add(f)
                try:
                    n = self.indexar_texto(f.read_text("utf-8"), doc=f.name)
                    resumen[f.name] = n
                except OSError:
                    continue
        return resumen

    def olvidar_doc(self, doc: str):
        self.db.execute("DELETE FROM trozos WHERE doc=?", (doc,))
        self.db.commit()

    def contar(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM trozos").fetchone()[0]

    # ── Recuperación ───────────────────────────────────────────────────────────

    def buscar(self, consulta: str, *, k: int = 3, umbral: float = 0.5,
               vida_media_dias: float = 30.0, ahora: Optional[float] = None) -> List[dict]:
        """
        Devuelve hasta `k` trozos relevantes:
            score = 1.2·similitud + 0.2·recencia,   recencia = 0.5^(edad/vida_media)
        Filtra por similitud > umbral. Ordena por score desc.
        """
        ahora = ahora if ahora is not None else time.time()
        filas = self.db.execute(
            "SELECT id, doc, titulo, texto, vector, actualizado FROM trozos "
            "WHERE vector IS NOT NULL").fetchall()
        if not filas:
            return []
        qv = self.embedder.embed([consulta])[0]
        resultados = []
        for id_, doc, titulo, texto, vector, actualizado in filas:
            sim = coseno(qv, json.loads(vector))
            if sim <= umbral:
                continue
            edad_dias = max(0.0, (ahora - (actualizado or ahora)) / 86400.0)
            recencia = 0.5 ** (edad_dias / vida_media_dias) if vida_media_dias > 0 else 0.0
            score = 1.2 * sim + 0.2 * recencia
            resultados.append({"id": id_, "doc": doc, "titulo": titulo, "texto": texto,
                               "similitud": round(sim, 4), "score": round(score, 4)})
        resultados.sort(key=lambda r: r["score"], reverse=True)
        return resultados[:k]

    def contexto_para(self, consulta: str, **kw) -> List[Tuple[str, str]]:
        """
        Recupera y devuelve [(fuente, texto), …] listo para prompt.bloque_contexto.
        La fuente es 'notas:archivo › encabezado' para que el modelo pueda citar.
        """
        hits = self.buscar(consulta, **kw)
        salida = []
        for h in hits:
            fuente = f"notas:{h['doc']}" + (f" › {h['titulo']}" if h["titulo"] else "")
            salida.append((fuente, h["texto"]))
        return salida

    def cerrar(self):
        self.db.close()


def crear_almacen(ruta_db: Path, *, url_ollama: Optional[str] = None,
                  modelo: str = "nomic-embed-text") -> AlmacenRAG:
    """Fábrica: usa Ollama si se da una URL; si no, el embebedor hash (degradado)."""
    emb = EmbedderOllama(url_ollama, modelo) if url_ollama else EmbedderHash()
    return AlmacenRAG(ruta_db, emb)
