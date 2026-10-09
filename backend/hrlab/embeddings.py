"""Embeddings of every event (case narratives and decision log entries).

Storage is Redis, next to the rest of the lab: one hash per document with the
text, metadata and the vector (float32, base64). Search is exact cosine over a
numpy matrix kept in memory by each API process and reloaded when the index
version changes. For the volumes of a lab (tens of thousands of documents) an
exact scan is fast enough and avoids another moving part; the docs explain the
path to a dedicated vector store.

Embedding model: Ollama `/api/embed` (default `nomic-embed-text`). When Ollama
is unreachable the indexer waits, unless the simulated fallback is enabled in
the settings: then a deterministic hashing embedding is used and every document
indexed that way is marked and re-embedded when Ollama returns.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import unicodedata
import zlib
from typing import Any

import httpx
import numpy as np

from .agent import AgentUnavailable
from .store import P, Store, dumps, now_ms

DOC_KEY = f"{P}:vec:doc:"
IDS_KEY = f"{P}:vec:ids"
SIMULATED_KEY = f"{P}:vec:simulated"
VERSION_KEY = f"{P}:vec:version"
DIRTY_KEY = f"{P}:vec:dirty"
STATUS_KEY = f"{P}:vec:status"
HASH_MODEL = "hash-512 (simulado)"
HASH_DIMS = 512

_WORD = re.compile(r"[a-z0-9][a-z0-9_\-\.]*")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def tokens(text: str) -> list[str]:
    return _WORD.findall(normalize_text(text))


STOPWORDS = set("""a o e de da do das dos em no na nos nas um uma uns umas por para com sem que se ao aos as os ou the
foi ser sao esta este esse essa isso caso evento cargo colaborador""".split())


def hash_embed(text: str) -> list[float]:
    """Deterministic bag-of-words embedding used by the simulated mode.

    Features are words, 5-letter prefixes (a cheap stemmer for Portuguese:
    "desligamento" and "desligado" share "desli") and prefix bigrams, mapped
    by signed hashing into 512 dimensions.
    """
    vec = [0.0] * HASH_DIMS
    toks = [t for t in tokens(text) if len(t) > 2 and t not in STOPWORDS]
    stems = [t[:5] for t in toks]
    feats = toks + [f"~{s}" for s in stems] + [f"{a} {b}" for a, b in zip(stems, stems[1:])]
    for f in feats:
        h = zlib.crc32(f.encode())
        vec[h % HASH_DIMS] += 1.0 if (h >> 16) & 1 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _prefix(model: str, kind: str) -> str:
    # nomic-embed-text was trained with task prefixes
    if "nomic" in model:
        return "search_query: " if kind == "query" else "search_document: "
    return ""


async def ollama_embed(settings: dict, texts: list[str], kind: str = "document") -> list[list[float]]:
    model = settings["embedding_model"]
    url = settings["ollama_base_url"].rstrip("/")
    inputs = [_prefix(model, kind) + t for t in texts]
    try:
        async with httpx.AsyncClient(timeout=settings["ollama_timeout_s"]) as client:
            resp = await client.post(f"{url}/api/embed", json={"model": model, "input": inputs, "keep_alive": settings["ollama_keep_alive"],
                                                               "truncate": True})
            if resp.status_code == 404 and "model" not in resp.text:
                # older Ollama: one prompt per call
                out = []
                for t in inputs:
                    r = await client.post(f"{url}/api/embeddings", json={"model": model, "prompt": t})
                    r.raise_for_status()
                    out.append(r.json()["embedding"])
                return out
            resp.raise_for_status()
            return resp.json()["embeddings"]
    except (httpx.HTTPError, OSError, KeyError) as exc:
        raise AgentUnavailable(f"embeddings indisponíveis: {type(exc).__name__}: {exc}") from exc


async def embed(store: Store, texts: list[str], kind: str = "document") -> tuple[list[list[float]], str]:
    """Embeds with Ollama, or with the simulated hashing model when allowed."""
    settings = await store.settings()
    try:
        return await ollama_embed(settings, texts, kind), settings["embedding_model"]
    except AgentUnavailable:
        if settings.get("heuristic_fallback_enabled"):
            return [hash_embed(t) for t in texts], HASH_MODEL
        raise


def _pack(vec: list[float]) -> str:
    return base64.b64encode(np.asarray(vec, dtype=np.float32).tobytes()).decode()


def _unpack(raw: str) -> np.ndarray:
    return np.frombuffer(base64.b64decode(raw), dtype=np.float32)


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:24]


# ---------------------------------------------------------------- writes
async def existing_hash(store: Store, doc_id: str) -> tuple[str | None, str | None]:
    h, model = await store.r.hmget(DOC_KEY + doc_id, ["hash", "model"])
    return h, model


async def upsert(store: Store, docs: list[dict], vectors: list[list[float]], model: str) -> None:
    pipe = store.r.pipeline()
    for doc, vec in zip(docs, vectors):
        pipe.hset(DOC_KEY + doc["id"], mapping={"text": doc["text"], "meta": dumps(doc["meta"]), "vec": _pack(vec), "model": model,
                                               "hash": doc["hash"], "atualizado_em": now_ms()})
        pipe.sadd(IDS_KEY, doc["id"])
        if model == HASH_MODEL:
            pipe.sadd(SIMULATED_KEY, doc["id"])
        else:
            pipe.srem(SIMULATED_KEY, doc["id"])
    pipe.incr(VERSION_KEY)
    await pipe.execute()


async def mark_dirty(store: Store, refs: dict[str, int]) -> None:
    if refs:
        await store.r.zadd(DIRTY_KEY, refs)


async def clear(store: Store) -> None:
    async for key in store.r.scan_iter(match=DOC_KEY + "*", count=500):
        await store.r.delete(key)
    await store.r.delete(IDS_KEY, SIMULATED_KEY, DIRTY_KEY, STATUS_KEY)
    await store.r.incr(VERSION_KEY)


async def status(store: Store) -> dict:
    st = await store.get_json(STATUS_KEY) or {}
    st.update({"documentos": await store.r.scard(IDS_KEY), "pendentes": await store.r.zcard(DIRTY_KEY),
               "simulados": await store.r.scard(SIMULATED_KEY), "versao": int(await store.r.get(VERSION_KEY) or 0)})
    return st


# ---------------------------------------------------------------- search
class VectorCache:
    """In-process matrix of all vectors, reloaded when the index version changes."""

    def __init__(self) -> None:
        self.version = -1
        self.ids: list[str] = []
        self.models: list[str] = []
        self.metas: list[dict] = []
        self.texts: list[str] = []
        self.matrix: dict[str, np.ndarray] = {}
        self.rows: dict[str, list[int]] = {}
        self.hash_matrix: np.ndarray | None = None

    async def refresh(self, store: Store) -> None:
        version = int(await store.r.get(VERSION_KEY) or 0)
        if version == self.version:
            return
        ids = sorted(await store.r.smembers(IDS_KEY))
        pipe = store.r.pipeline()
        for i in ids:
            pipe.hmget(DOC_KEY + i, ["text", "meta", "vec", "model"])
        raws = await pipe.execute() if ids else []
        self.ids, self.models, self.metas, self.texts = [], [], [], []
        vecs: dict[str, list[np.ndarray]] = {}
        self.rows = {}
        for doc_id, (text, meta, vec, model) in zip(ids, raws):
            if not vec:
                continue
            self.ids.append(doc_id)
            self.models.append(model)
            self.metas.append(json.loads(meta or "{}"))
            self.texts.append(text or "")
            v = _unpack(vec)
            vecs.setdefault(model, []).append(v)
            self.rows.setdefault(model, []).append(len(self.ids) - 1)
        self.matrix = {}
        for model, vs in vecs.items():
            dims = {v.shape[0] for v in vs}
            if len(dims) != 1:
                continue
            m = np.vstack(vs)
            norms = np.linalg.norm(m, axis=1, keepdims=True)
            norms[norms == 0] = 1
            self.matrix[model] = m / norms
        self.hash_matrix = None
        self.version = version

    def simulated_matrix(self) -> np.ndarray:
        """Hashing vectors for every document, whatever model indexed it.

        In simulated mode the query cannot be compared with vectors of a real
        model, so every text is re-embedded with the hashing model (cheap and
        cached until the index changes) and the search still covers everything.
        """
        if self.hash_matrix is None:
            self.hash_matrix = np.asarray([hash_embed(t) for t in self.texts], dtype=np.float32).reshape(len(self.texts), HASH_DIMS)
        return self.hash_matrix


_cache = VectorCache()


def _meta_match(meta: dict, filtros: dict) -> bool:
    for key, want in filtros.items():
        if want in (None, "", []):
            continue
        if key == "fonte":
            if meta.get("fonte") != want:
                return False
        elif key == "desde":
            if (meta.get("dia") or "") < str(want)[:10]:
                return False
        elif key == "colaborador_nome":
            if str(want).lower() not in (meta.get("colaborador_nome") or "").lower():
                return False
        elif key in meta:
            vals = want if isinstance(want, list) else [want]
            if str(meta.get(key) or "").upper() not in [str(v).upper() for v in vals]:
                return False
    return True


async def search(store: Store, query: str, *, k: int = 8, filtros: dict | None = None) -> dict:
    """Semantic search with metadata filters and a small lexical boost."""
    await _cache.refresh(store)
    started = now_ms()
    [qvec], model = await embed(store, [query], kind="query")
    if model == HASH_MODEL:
        m, rows = _cache.simulated_matrix(), list(range(len(_cache.ids)))
    else:
        m, rows = _cache.matrix.get(model), _cache.rows.get(model, [])
    if m is None or not rows:
        return {"modelo": model, "resultados": [], "aviso": f"nenhum documento indexado com o modelo {model}", "duracao_ms": now_ms() - started}
    q = np.asarray(qvec, dtype=np.float32)
    q = q / (np.linalg.norm(q) or 1)
    scores = m @ q
    qtoks = {t[:5] for t in tokens(query) if len(t) > 2 and t not in STOPWORDS}
    filtros = {k2: v for k2, v in (filtros or {}).items() if v not in (None, "", [])}
    scored = []
    for local, row in enumerate(rows):
        meta = _cache.metas[row]
        if filtros and not _meta_match(meta, filtros):
            continue
        lexical = 0.0
        if qtoks:
            ttoks = {t[:5] for t in tokens(_cache.texts[row])}
            lexical = len(qtoks & ttoks) / len(qtoks)
        scored.append((float(scores[local]) + 0.05 * lexical, float(scores[local]), lexical, row))
    scored.sort(key=lambda x: -x[0])
    results = []
    for final, cos, lex, row in scored[:k]:
        results.append({"id": _cache.ids[row], "score": round(final, 4), "similaridade": round(cos, 4), "lexical": round(lex, 3),
                        "meta": _cache.metas[row], "texto": _cache.texts[row]})
    pending_other = 0 if model == HASH_MODEL else sum(len(r) for mdl, r in _cache.rows.items() if mdl != model)
    out: dict[str, Any] = {"modelo": model, "simulado": model == HASH_MODEL, "resultados": results, "candidatos": len(scored),
                           "duracao_ms": now_ms() - started}
    if pending_other:
        out["aviso"] = f"{pending_other} documento(s) indexados com outro modelo ficaram fora desta busca até serem reindexados."
    return out
