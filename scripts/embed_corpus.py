#!/usr/bin/env python3
"""Semantic retrieval over text corpora and evidence ledgers.

Subcommands
-----------
* ``index``        - build an embedding index from text files
* ``query``        - find top-k similar documents to a query
* ``query-ledger`` - query an evidence-ledger CSV directly
* ``dedupe``       - find near-duplicate documents by similarity
* ``self-test``    - run dependency-free offline self-tests
* ``production-self-test`` - exercise the real optional local backend offline

Embedding backends:
- auto: sentence-transformers when importable, otherwise built-in local hashing
- local-hashing: deterministic word/character feature hashing (offline fallback)
- stub: deterministic hash-based fake (explicit testing only, always available)
- sentence-transformers: optional local production backend
- cohere: remote, requires COHERE_API_KEY + --allow-remote or D_RESEARCH_ALLOW_REMOTE_EMBEDDINGS=1
- llama-cli: local shellout to llama-embedding binary

Cosine similarity is implemented with stdlib math (no numpy required).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import sys
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from _ssrf_helpers import public_urlopen_with_redirects
from resource_limits import (
    ResourceLimitError,
    emit_blocker_and_exit,
    load_limits,
    read_http_response_bounded,
)

EMBED_DIM_STUB = 32
EMBED_DIM_LOCAL_HASHING = 512
INDEX_SCHEMA_VERSION = "1.0"
AUTO_BACKEND = "auto"
LOCAL_HASHING_BACKEND = "local-hashing"
LOCAL_HASHING_MODEL = "word-char-hashing-v1"
SENTENCE_TRANSFORMERS_BACKEND = "sentence-transformers"
CONCRETE_BACKENDS = (
    "stub",
    LOCAL_HASHING_BACKEND,
    SENTENCE_TRANSFORMERS_BACKEND,
    "cohere",
    "llama-cli",
)
BACKEND_CHOICES = (AUTO_BACKEND, *CONCRETE_BACKENDS)


class EmbeddingBackendUnavailable(RuntimeError):
    """Raised when a requested optional embedding backend is unavailable."""


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Build a JSON object while rejecting ambiguous duplicate keys."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_nonfinite_json(token: str) -> None:
    """Reject JSON extensions such as NaN and Infinity."""
    raise ValueError(f"non-finite JSON number: {token}")


def _strict_json_loads(payload: str | bytes, *, context: str) -> Any:
    """Decode standards-compliant JSON with unambiguous object keys."""
    try:
        return json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_nonfinite_json,
        )
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"{context}: invalid JSON ({exc})") from exc


def _validate_embedding_batch(
    vectors: Any,
    *,
    expected_count: int,
    expected_dim: int | None = None,
    context: str,
) -> int:
    """Validate backend/index vectors and return their common dimension."""
    if not isinstance(vectors, list):
        raise ValueError(f"{context}: embeddings must be a list")
    if len(vectors) != expected_count:
        raise ValueError(
            f"{context}: backend returned {len(vectors)} embedding(s) "
            f"for {expected_count} input(s)"
        )

    common_dim = expected_dim
    for row_index, vector in enumerate(vectors):
        if not isinstance(vector, list) or not vector:
            raise ValueError(
                f"{context}: embedding {row_index} must be a non-empty list"
            )
        if common_dim is None:
            common_dim = len(vector)
        if len(vector) != common_dim:
            raise ValueError(
                f"{context}: embedding {row_index} has dimension {len(vector)}; "
                f"expected {common_dim}"
            )
        for value_index, value in enumerate(vector):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(
                    f"{context}: embedding {row_index} value {value_index} "
                    "must be a number, not a boolean"
                )
            try:
                finite = math.isfinite(value)
            except (OverflowError, TypeError):
                finite = False
            if not finite:
                raise ValueError(
                    f"{context}: embedding {row_index} value {value_index} "
                    "must be finite"
                )

    if common_dim is None or common_dim <= 0:
        raise ValueError(f"{context}: embeddings must have a positive dimension")
    return common_dim


# ---------------------------------------------------------------------------
# Embedding backends
# ---------------------------------------------------------------------------


def _stub_embed(text: str) -> list[float]:
    """Deterministic hash-based stub embedder (always available)."""
    h = hashlib.sha256(text.encode("utf-8")).digest()
    vec = [(b / 127.5) - 1.0 for b in h[:EMBED_DIM_STUB]]
    mag = math.sqrt(sum(x * x for x in vec))
    if mag > 0:
        vec = [x / mag for x in vec]
    return vec


def _local_hashing_embed(text: str) -> list[float]:
    """Embed text with deterministic word and character feature hashing.

    This built-in backend is intentionally lexical rather than a substitute
    for a trained semantic model. It preserves useful overlap and spelling
    similarity for offline retrieval without dependencies, model downloads,
    network access, or the random-looking behavior of the test stub.
    """
    normalized = " ".join(unicodedata.normalize("NFKC", text).casefold().split())
    if not normalized:
        return [0.0] * EMBED_DIM_LOCAL_HASHING
    words = re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)
    features: list[tuple[str, float]] = []
    features.extend((f"word:{word}", 2.0) for word in words)
    features.extend(
        (f"bigram:{left}\u0000{right}", 1.25)
        for left, right in zip(words, words[1:])
    )
    padded = f"  {normalized}  "
    for width, weight in ((3, 0.35), (4, 0.25)):
        features.extend(
            (f"char{width}:{padded[offset:offset + width]}", weight)
            for offset in range(max(0, len(padded) - width + 1))
        )

    vector = [0.0] * EMBED_DIM_LOCAL_HASHING
    for feature, weight in features:
        digest = hashlib.sha256(feature.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % EMBED_DIM_LOCAL_HASHING
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[bucket] += sign * weight

    magnitude = math.sqrt(math.fsum(value * value for value in vector))
    if magnitude:
        return [value / magnitude for value in vector]
    return vector


def _sentence_transformers_available() -> bool:
    """Return whether the optional local production backend is importable."""
    try:
        return importlib.util.find_spec("sentence_transformers") is not None
    except (ImportError, ValueError):
        return False


def _resolve_backend(backend: str) -> str:
    """Resolve a selection policy to a concrete backend without remote fallback."""
    if backend != AUTO_BACKEND:
        return backend
    if _sentence_transformers_available():
        return SENTENCE_TRANSFORMERS_BACKEND
    return LOCAL_HASHING_BACKEND


def _sentence_transformers_embed(texts: list[str], model_name: str) -> list[list[float]]:
    """Embed via sentence-transformers (optional pip package)."""
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]
    except ImportError as exc:
        raise EmbeddingBackendUnavailable(
            "sentence-transformers is not installed.\n"
            "  Install: python -m pip install -e \".[embeddings]\""
        ) from exc
    try:
        model = SentenceTransformer(model_name)
        embeddings = model.encode(texts, show_progress_bar=False)
        return [e.tolist() for e in embeddings]
    except Exception as exc:
        # Optional model loading may fail because the model is unavailable,
        # the local cache is corrupt, or the backend runtime cannot encode.
        # Normalize those library-specific failures for CLI and API callers
        # without catching BaseException control flow such as Ctrl+C.
        raise EmbeddingBackendUnavailable(
            "sentence-transformers could not load or run the requested model "
            f"({type(exc).__name__}).\n"
            "  Ensure the model is available locally and the embeddings extra is healthy.\n"
            "  Install/repair: python -m pip install -e \".[embeddings]\""
        ) from exc


def _cohere_embed(
    texts: list[str],
    model_name: str = "embed-english-v3.0",
    input_type: str = "search_document",
) -> list[list[float]]:
    """Embed via Cohere API (remote, requires key + opt-in)."""
    key = os.environ.get("COHERE_API_KEY", "")
    if not key:
        print("error: COHERE_API_KEY env var not set", file=sys.stderr)
        raise SystemExit(1)

    data = json.dumps({
        "texts": texts,
        "model": model_name,
        "input_type": input_type,
    }, allow_nan=False).encode()
    req = urllib.request.Request(
        "https://api.cohere.ai/v1/embed",
        data=data,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        limits = load_limits()
        with public_urlopen_with_redirects(
            req,
            timeout=limits.http_timeout_sec,
        ) as resp:
            result = _strict_json_loads(
                read_http_response_bounded(resp, limits),
                context="Cohere response",
            )
            if not isinstance(result, dict):
                raise ValueError("Cohere response: expected a JSON object")
            return result.get("embeddings", [])
    except ResourceLimitError as exc:
        emit_blocker_and_exit(exc)
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        print(f"error: Cohere API request failed: {e}", file=sys.stderr)
        raise SystemExit(1)


def _llama_cli_embed(texts: list[str]) -> list[list[float]]:
    """Embed via llama-embedding CLI (local shellout)."""
    import subprocess
    import tempfile

    binary = shutil.which("llama-embedding") or shutil.which("llama-embed")
    if not binary:
        print(
            "error: llama-embedding binary not found on PATH.\n"
            "  Install llama.cpp and ensure llama-embedding is available.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    embeddings: list[list[float]] = []
    for text in texts:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write(text)
            tmp_path = f.name
        try:
            result = subprocess.run(
                [binary, "--file", tmp_path],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                print(f"error: llama-embedding failed: {result.stderr}", file=sys.stderr)
                raise SystemExit(1)
            parsed = _strict_json_loads(
                result.stdout,
                context="llama-embedding response",
            )
            if isinstance(parsed, list):
                vec = parsed
            elif isinstance(parsed, dict):
                vec = parsed.get("embedding", [])
            else:
                raise ValueError(
                    "llama-embedding response: expected a vector or object"
                )
            embeddings.append(vec)
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    return embeddings


def _resolved_model_name(backend: str, model: str = "") -> str:
    """Return the concrete model name stored in index metadata."""
    if backend == SENTENCE_TRANSFORMERS_BACKEND:
        return model or "all-MiniLM-L6-v2"
    if backend == LOCAL_HASHING_BACKEND:
        return LOCAL_HASHING_MODEL
    if backend == "cohere":
        return model or "embed-english-v3.0"
    if backend == "llama-cli":
        return model or "llama-embedding"
    return model


def embed_texts(
    texts: list[str], backend: str = AUTO_BACKEND, model: str = "",
    input_type: str = "search_document",
) -> list[list[float]]:
    """Embed a list of texts using the specified backend."""
    backend = _resolve_backend(backend)
    if backend == "stub":
        return [_stub_embed(t) for t in texts]
    if backend == LOCAL_HASHING_BACKEND:
        return [_local_hashing_embed(t) for t in texts]
    if backend == SENTENCE_TRANSFORMERS_BACKEND:
        model_name = _resolved_model_name(backend, model)
        return _sentence_transformers_embed(texts, model_name)
    if backend == "cohere":
        model_name = _resolved_model_name(backend, model)
        return _cohere_embed(texts, model_name, input_type)
    if backend == "llama-cli":
        return _llama_cli_embed(texts)
    raise ValueError(f"unknown backend: {backend}")


# ---------------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------------


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors (stdlib math only)."""
    if len(a) != len(b):
        raise ValueError(f"embedding dimension mismatch: {len(a)} != {len(b)}")
    scale_a = max((abs(value) for value in a), default=0.0)
    scale_b = max((abs(value) for value in b), default=0.0)
    if scale_a == 0 or scale_b == 0:
        return 0.0
    scaled_a = [value / scale_a for value in a]
    scaled_b = [value / scale_b for value in b]
    dot = math.fsum(x * y for x, y in zip(scaled_a, scaled_b))
    mag_a = math.sqrt(math.fsum(x * x for x in scaled_a))
    mag_b = math.sqrt(math.fsum(x * x for x in scaled_b))
    similarity = dot / (mag_a * mag_b)
    if not math.isfinite(similarity):
        raise ValueError("cosine similarity is not finite")
    return max(-1.0, min(1.0, similarity))


# ---------------------------------------------------------------------------
# Index format (JSONL with metadata header)
# ---------------------------------------------------------------------------


def _write_index(
    entries: list[dict[str, Any]], out_path: Path,
    backend: str, model: str, embedding_dim: int,
) -> None:
    """Write index with metadata header line."""
    if backend not in CONCRETE_BACKENDS:
        raise ValueError(f"index metadata requires a concrete backend, got {backend!r}")
    if (
        isinstance(embedding_dim, bool)
        or not isinstance(embedding_dim, int)
        or embedding_dim <= 0
    ):
        raise ValueError(f"invalid output embedding dimension: {embedding_dim!r}")
    if not entries or not all(isinstance(entry, dict) for entry in entries):
        raise ValueError("index output entries must be a non-empty list of objects")
    _validate_embedding_batch(
        [entry.get("embedding") for entry in entries],
        expected_count=len(entries),
        expected_dim=embedding_dim,
        context="index output",
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    header = {
        "_meta": True,
        "schema_version": INDEX_SCHEMA_VERSION,
        "backend": backend,
        "model": model,
        "embedding_dim": embedding_dim,
    }
    with out_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(header, ensure_ascii=False, allow_nan=False) + "\n")
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False, allow_nan=False) + "\n")


def _read_index(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Read index, returning (metadata, entries)."""
    meta: dict[str, Any] = {}
    entries: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line_number, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue
            obj = _strict_json_loads(
                line,
                context=f"index line {line_number}",
            )
            if not isinstance(obj, dict):
                raise ValueError(
                    f"index line {line_number}: expected a JSON object"
                )
            if obj.get("_meta"):
                if meta:
                    raise ValueError(
                        f"index line {line_number}: duplicate metadata header"
                    )
                meta = obj
            else:
                entries.append(obj)
    # Fallback metadata for legacy indexes without header
    if not meta:
        meta = {"backend": "stub", "model": "", "embedding_dim": EMBED_DIM_STUB}
    return meta, entries


def _validate_index(meta: dict[str, Any], entries: list[dict[str, Any]]) -> int:
    """Validate embedding dimensions and metadata consistency."""
    if not entries:
        print("error: index is empty", file=sys.stderr)
        return 1

    backend = meta.get("backend")
    if backend not in CONCRETE_BACKENDS:
        print(
            f"error: invalid concrete backend in index metadata: {backend!r}",
            file=sys.stderr,
        )
        return 1

    if "_meta" in meta:
        if meta.get("_meta") is not True:
            print("error: index metadata _meta must be true", file=sys.stderr)
            return 1
        if meta.get("schema_version") != INDEX_SCHEMA_VERSION:
            print(
                f"error: unsupported index schema_version: {meta.get('schema_version')!r}",
                file=sys.stderr,
            )
            return 1
    if not isinstance(meta.get("model", ""), str):
        print("error: index metadata model must be a string", file=sys.stderr)
        return 1

    expected_dim = meta.get("embedding_dim")
    if (
        isinstance(expected_dim, bool)
        or not isinstance(expected_dim, int)
        or expected_dim <= 0
    ):
        print(f"error: invalid embedding_dim in index metadata: {expected_dim!r}", file=sys.stderr)
        return 1

    try:
        _validate_embedding_batch(
            [entry.get("embedding") for entry in entries],
            expected_count=len(entries),
            expected_dim=expected_dim,
            context="index",
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for entry_index, entry in enumerate(entries):
        entry_id = entry.get("id")
        if isinstance(entry_id, bool) or not isinstance(entry_id, (int, str)):
            print(f"error: index entry {entry_index} has an invalid id", file=sys.stderr)
            return 1
        if not isinstance(entry.get("path"), str) or not entry["path"].strip():
            print(f"error: index entry {entry_index} has an invalid path", file=sys.stderr)
            return 1
        if "text_preview" in entry and not isinstance(entry["text_preview"], str):
            print(
                f"error: index entry {entry_index} text_preview must be a string",
                file=sys.stderr,
            )
            return 1
    return 0


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def _is_remote_allowed() -> bool:
    return os.environ.get("D_RESEARCH_ALLOW_REMOTE_EMBEDDINGS", "").strip() in ("1", "true", "yes")


def _check_remote(backend: str, allow_remote: bool) -> int:
    """Check remote opt-in. Returns 0 if ok, 1 if blocked."""
    if backend == "cohere" and not allow_remote and not _is_remote_allowed():
        print(
            "error: cohere backend is remote. Requires --allow-remote or "
            "D_RESEARCH_ALLOW_REMOTE_EMBEDDINGS=1",
            file=sys.stderr,
        )
        return 1
    return 0


def _resolve_cli_backend(requested_backend: str) -> str | None:
    """Resolve a CLI backend and convert optional-backend errors to diagnostics."""
    try:
        return _resolve_backend(requested_backend)
    except EmbeddingBackendUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None


def _read_index_for_cli(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    """Read an index while converting malformed data into a CLI diagnostic."""
    try:
        return _read_index(path)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"error: could not read index: {exc}", file=sys.stderr)
        return None


def _query_is_blank(query: Any) -> bool:
    """Return whether a query is absent or contains only whitespace."""
    return not isinstance(query, str) or not query.strip()


def cmd_index(args: argparse.Namespace) -> int:
    """Build embedding index from text files in a directory."""
    in_dir = Path(args.input)
    if not in_dir.is_dir():
        print(f"error: directory not found: {in_dir}", file=sys.stderr)
        return 1

    requested_backend = getattr(args, "backend", AUTO_BACKEND) or AUTO_BACKEND
    backend = _resolve_cli_backend(requested_backend)
    if backend is None:
        return 1
    model = getattr(args, "model", "") or ""
    allow_remote = getattr(args, "allow_remote", False)

    if _check_remote(backend, allow_remote) != 0:
        return 1

    # Collect text files
    files = sorted(
        f for f in in_dir.rglob("*")
        if f.is_file() and f.suffix in (".txt", ".md", ".csv", ".json")
    )
    if not files:
        print(f"error: no text files found in {in_dir}", file=sys.stderr)
        return 1

    texts: list[str] = []
    paths: list[str] = []
    for f in files:
        content = f.read_text(encoding="utf-8", errors="replace")[:10000]
        texts.append(content)
        paths.append(str(f.relative_to(in_dir)))

    model = _resolved_model_name(backend, model)
    try:
        embeddings = embed_texts(texts, backend, model, input_type="search_document")
        embedding_dim = _validate_embedding_batch(
            embeddings,
            expected_count=len(texts),
            context=f"{backend} backend",
        )
    except (EmbeddingBackendUnavailable, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    entries = []
    for i, (path, vec) in enumerate(zip(paths, embeddings)):
        entries.append({
            "id": i,
            "path": path,
            "text_preview": texts[i][:200],
            "embedding": vec,
        })

    out_path = Path(args.out)
    try:
        _write_index(entries, out_path, backend, model, embedding_dim)
    except (OSError, TypeError, ValueError) as exc:
        print(f"error: could not write index: {exc}", file=sys.stderr)
        return 1
    print(f"indexed {len(entries)} files -> {out_path} (backend={backend}, dim={embedding_dim})")
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    """Find top-k similar documents to a query."""
    if _query_is_blank(getattr(args, "q", None)):
        print("error: query must not be blank", file=sys.stderr)
        return 1

    index_path = Path(args.index)
    if not index_path.is_file():
        print(f"error: index not found: {index_path}", file=sys.stderr)
        return 1

    loaded = _read_index_for_cli(index_path)
    if loaded is None:
        return 1
    meta, entries = loaded
    if not entries:
        print("error: index is empty", file=sys.stderr)
        return 1
    if _validate_index(meta, entries) != 0:
        return 1

    # Use same backend/model as index
    backend = meta.get("backend", "stub")
    model = meta.get("model", "")
    expected_dim = meta.get("embedding_dim", 0)
    allow_remote = getattr(args, "allow_remote", False)

    if _check_remote(backend, allow_remote) != 0:
        return 1

    # Embed query with same backend
    try:
        query_vecs = embed_texts([args.q], backend, model, input_type="search_query")
        _validate_embedding_batch(
            query_vecs,
            expected_count=1,
            expected_dim=expected_dim,
            context=f"{backend} query backend",
        )
    except (EmbeddingBackendUnavailable, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    query_vec = query_vecs[0]

    # Score all entries
    scored: list[tuple[float, dict[str, Any]]] = []
    for entry in entries:
        try:
            sim = cosine_similarity(query_vec, entry["embedding"])
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        scored.append((sim, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    k = args.k
    top_k = scored[:k]

    results = []
    for sim, entry in top_k:
        results.append({
            "id": entry["id"],
            "path": entry["path"],
            "similarity": round(sim, 4),
            "text_preview": entry.get("text_preview", ""),
        })

    output = json.dumps(results, indent=2, ensure_ascii=False, allow_nan=False)
    if args.out:
        Path(args.out).write_text(output + "\n", encoding="utf-8")
        print(f"wrote {args.out} ({len(results)} results)")
    else:
        print(output)
    return 0


def cmd_query_ledger(args: argparse.Namespace) -> int:
    """Query an evidence-ledger CSV directly."""
    if _query_is_blank(getattr(args, "q", None)):
        print("error: query must not be blank", file=sys.stderr)
        return 1

    ledger_path = Path(args.ledger)
    if not ledger_path.is_file():
        print(f"error: ledger not found: {ledger_path}", file=sys.stderr)
        return 1

    requested_backend = getattr(args, "backend", AUTO_BACKEND) or AUTO_BACKEND
    backend = _resolve_cli_backend(requested_backend)
    if backend is None:
        return 1
    model = getattr(args, "model", "") or ""
    allow_remote = getattr(args, "allow_remote", False)

    if _check_remote(backend, allow_remote) != 0:
        return 1

    with ledger_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("error: ledger is empty", file=sys.stderr)
        return 1

    # Build inline embeddings from claim + evidence fields
    texts = []
    for row in rows:
        text = f"{row.get('claim', '')} {row.get('evidence', '')} {row.get('source_title', '')}"
        texts.append(text.strip())

    try:
        embeddings = embed_texts(texts, backend, model, input_type="search_document")
        embedding_dim = _validate_embedding_batch(
            embeddings,
            expected_count=len(texts),
            context=f"{backend} ledger backend",
        )
        query_vecs = embed_texts([args.q], backend, model, input_type="search_query")
        _validate_embedding_batch(
            query_vecs,
            expected_count=1,
            expected_dim=embedding_dim,
            context=f"{backend} query backend",
        )
    except (EmbeddingBackendUnavailable, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    query_vec = query_vecs[0]

    scored: list[tuple[float, int]] = []
    for i, vec in enumerate(embeddings):
        try:
            sim = cosine_similarity(query_vec, vec)
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        scored.append((sim, i))

    scored.sort(key=lambda x: x[0], reverse=True)
    k = args.k
    top_k = scored[:k]

    results = []
    for sim, idx in top_k:
        row = rows[idx]
        results.append({
            "claim_id": row.get("claim_id", ""),
            "claim": row.get("claim", ""),
            "similarity": round(sim, 4),
            "source_url": row.get("source_url", ""),
        })

    print(json.dumps(results, indent=2, ensure_ascii=False, allow_nan=False))
    return 0


def cmd_dedupe(args: argparse.Namespace) -> int:
    """Find near-duplicate documents by similarity threshold."""
    index_path = Path(args.index)
    if not index_path.is_file():
        print(f"error: index not found: {index_path}", file=sys.stderr)
        return 1

    loaded = _read_index_for_cli(index_path)
    if loaded is None:
        return 1
    _meta, entries = loaded
    if _validate_index(_meta, entries) != 0:
        return 1
    threshold = args.threshold
    duplicates: list[dict[str, Any]] = []

    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            try:
                sim = cosine_similarity(entries[i]["embedding"], entries[j]["embedding"])
            except ValueError as e:
                print(f"error: {e}", file=sys.stderr)
                return 1
            if sim >= threshold:
                duplicates.append({
                    "a": entries[i]["path"],
                    "b": entries[j]["path"],
                    "similarity": round(sim, 4),
                })

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            duplicates,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        ) + "\n",
        encoding="utf-8",
    )
    print(f"found {len(duplicates)} duplicate pair(s) -> {out_path}")
    return 0


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def cmd_self_test(_args: argparse.Namespace) -> int:
    """Dependency-free offline self-test."""
    import contextlib
    import io
    import tempfile
    from unittest import mock

    errors: list[str] = []

    # Test 1: stub embedder produces unit vectors of correct dimension
    vec = _stub_embed("hello world")
    if len(vec) != EMBED_DIM_STUB:
        errors.append(f"stub embed dim: expected {EMBED_DIM_STUB}, got {len(vec)}")
    mag = math.sqrt(sum(x * x for x in vec))
    if abs(mag - 1.0) > 0.001:
        errors.append(f"stub embed not unit vector: magnitude={mag}")

    # Test 2: deterministic
    vec2 = _stub_embed("hello world")
    if vec != vec2:
        errors.append("stub embed not deterministic")

    # Test 3: different text produces different embedding
    vec3 = _stub_embed("goodbye world")
    if vec == vec3:
        errors.append("stub embed same for different text")

    # Test 4: cosine similarity
    sim_self = cosine_similarity(vec, vec)
    if abs(sim_self - 1.0) > 0.001:
        errors.append(f"cosine self-similarity should be 1.0, got {sim_self}")
    huge_similarity = cosine_similarity([1e308, 1e308], [1e308, 1e308])
    if not math.isfinite(huge_similarity) or abs(huge_similarity - 1.0) > 1e-12:
        errors.append("cosine similarity must remain finite for large finite vectors")

    # Test 5: cosine with dimension mismatch fails loudly
    try:
        cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0])
        errors.append("cosine dimension mismatch should raise ValueError")
    except ValueError:
        pass

    # Test 6: index + query round-trip
    with tempfile.TemporaryDirectory() as tmpdir:
        corpus_dir = Path(tmpdir) / "corpus"
        corpus_dir.mkdir()
        (corpus_dir / "doc1.txt").write_text("Machine learning is a subset of artificial intelligence", encoding="utf-8")
        (corpus_dir / "doc2.txt").write_text("The weather today is sunny and warm", encoding="utf-8")
        (corpus_dir / "doc3.txt").write_text("Deep learning uses neural networks with many layers", encoding="utf-8")

        index_path = Path(tmpdir) / "index.jsonl"

        # Index
        index_ns = argparse.Namespace(
            input=str(corpus_dir), out=str(index_path),
            backend="stub", model="", allow_remote=False,
        )
        rc = cmd_index(index_ns)
        if rc != 0:
            errors.append("index command failed")
        elif not index_path.is_file():
            errors.append("index file not created")
        else:
            meta, entries = _read_index(index_path)
            if len(entries) != 3:
                errors.append(f"index should have 3 entries, got {len(entries)}")
            if meta.get("backend") != "stub":
                errors.append(f"index metadata backend should be 'stub', got {meta.get('backend')}")
            if meta.get("embedding_dim") != EMBED_DIM_STUB:
                errors.append(f"index metadata dim should be {EMBED_DIM_STUB}, got {meta.get('embedding_dim')}")

            # Query
            captured = io.StringIO()
            query_ns = argparse.Namespace(
                index=str(index_path), q="neural networks AI", k=2, out=None, allow_remote=False,
            )
            with contextlib.redirect_stdout(captured):
                rc = cmd_query(query_ns)
            if rc != 0:
                errors.append("query command failed")
            else:
                results = json.loads(captured.getvalue())
                if len(results) != 2:
                    errors.append(f"query should return 2 results, got {len(results)}")
                if not all("similarity" in r for r in results):
                    errors.append("query results missing similarity field")

        # Test 7: index vector-length mismatch detection
        bad_index_path = Path(tmpdir) / "bad_index.jsonl"
        with bad_index_path.open("w", encoding="utf-8") as f:
            f.write(json.dumps({
                "_meta": True,
                "schema_version": "1.0",
                "backend": "stub",
                "model": "",
                "embedding_dim": EMBED_DIM_STUB,
            }, allow_nan=False) + "\n")
            f.write(json.dumps({
                "id": 0,
                "path": "x.txt",
                "text_preview": "x",
                "embedding": [0.1] * (EMBED_DIM_STUB - 1),
            }, allow_nan=False) + "\n")

        captured_err = io.StringIO()
        query_bad_ns = argparse.Namespace(
            index=str(bad_index_path), q="test", k=1, out=None, allow_remote=False,
        )
        old_stderr = sys.stderr
        sys.stderr = captured_err
        rc = cmd_query(query_bad_ns)
        sys.stderr = old_stderr
        if rc == 0:
            errors.append("query should fail on dimension mismatch")

        # Test 8: Cohere remote without opt-in should fail before network
        os.environ.pop("D_RESEARCH_ALLOW_REMOTE_EMBEDDINGS", None)
        cohere_index_ns = argparse.Namespace(
            input=str(corpus_dir), out=str(Path(tmpdir) / "cohere.jsonl"),
            backend="cohere", model="", allow_remote=False,
        )
        old_stderr = sys.stderr
        sys.stderr = io.StringIO()
        rc = cmd_index(cohere_index_ns)
        sys.stderr = old_stderr
        if rc == 0:
            errors.append("cohere index without --allow-remote should fail")

        cohere_query_path = Path(tmpdir) / "cohere_index.jsonl"
        with cohere_query_path.open("w", encoding="utf-8") as f:
            f.write(json.dumps({
                "_meta": True,
                "schema_version": "1.0",
                "backend": "cohere",
                "model": "embed-english-v3.0",
                "embedding_dim": EMBED_DIM_STUB,
            }, allow_nan=False) + "\n")
            f.write(json.dumps({
                "id": 0,
                "path": "x.txt",
                "text_preview": "x",
                "embedding": _stub_embed("x"),
            }, allow_nan=False) + "\n")
        cohere_query_ns = argparse.Namespace(
            index=str(cohere_query_path), q="test", k=1, out=None, allow_remote=False,
        )
        sys.stderr = io.StringIO()
        rc = cmd_query(cohere_query_ns)
        sys.stderr = old_stderr
        if rc == 0:
            errors.append("cohere query without --allow-remote should fail")

        # Test 9: auto resolves to a concrete local production backend
        module = sys.modules[__name__]
        with mock.patch.object(module, "_sentence_transformers_available", return_value=True):
            if _resolve_backend(AUTO_BACKEND) != SENTENCE_TRANSFORMERS_BACKEND:
                errors.append("auto backend should select sentence-transformers when available")
            if _resolve_backend("stub") != "stub":
                errors.append("explicit stub backend should remain available for tests")

            auto_index_path = Path(tmpdir) / "auto_index.jsonl"
            with mock.patch.object(
                module,
                "_sentence_transformers_embed",
                side_effect=lambda values, _model: [_stub_embed(value) for value in values],
            ):
                auto_index_ns = argparse.Namespace(
                    input=str(corpus_dir), out=str(auto_index_path),
                    backend=AUTO_BACKEND, model="", allow_remote=False,
                )
                rc = cmd_index(auto_index_ns)
            if rc != 0:
                errors.append("auto index command failed with available local backend")
            else:
                auto_meta, _auto_entries = _read_index(auto_index_path)
                if auto_meta.get("backend") != SENTENCE_TRANSFORMERS_BACKEND:
                    errors.append("auto index metadata must store the concrete backend")
                if auto_meta.get("model") != "all-MiniLM-L6-v2":
                    errors.append("auto index metadata must store the resolved model")

        # Test 10: auto falls back to deterministic local hashing, never the stub
        fallback_index_path = Path(tmpdir) / "fallback_auto.jsonl"
        with mock.patch.object(module, "_sentence_transformers_available", return_value=False):
            if _resolve_backend(AUTO_BACKEND) != LOCAL_HASHING_BACKEND:
                errors.append("auto backend should select local hashing when ST is unavailable")
            fallback_vectors = embed_texts(
                ["neural network research", "neural networks for research"],
                backend=AUTO_BACKEND,
            )
            if any(len(vector) != EMBED_DIM_LOCAL_HASHING for vector in fallback_vectors):
                errors.append("auto local-hashing fallback returned an invalid dimension")
            if fallback_vectors[0] != _local_hashing_embed("neural network research"):
                errors.append("auto local-hashing fallback is not deterministic")

            fallback_ns = argparse.Namespace(
                input=str(corpus_dir), out=str(fallback_index_path),
                backend=AUTO_BACKEND, model="", allow_remote=False,
            )
            rc = cmd_index(fallback_ns)
            if rc != 0 or not fallback_index_path.exists():
                errors.append("auto local-hashing fallback should produce an index")
            else:
                fallback_meta, _fallback_entries = _read_index(fallback_index_path)
                if fallback_meta.get("backend") != LOCAL_HASHING_BACKEND:
                    errors.append("fallback index must persist the concrete local backend")
                if fallback_meta.get("model") != LOCAL_HASHING_MODEL:
                    errors.append("fallback index must persist the local hashing model")

        related = _local_hashing_embed("secure evidence ledger validation")
        related_variant = _local_hashing_embed("validating secure evidence ledgers")
        unrelated = _local_hashing_embed("tropical weather and ocean tides")
        if cosine_similarity(related, related_variant) <= cosine_similarity(related, unrelated):
            errors.append("local hashing should rank lexical variants above unrelated text")
        if _local_hashing_embed(" \t\r\n ") != [0.0] * EMBED_DIM_LOCAL_HASHING:
            errors.append("local hashing should return a zero vector for blank text")

        # Test 11: model load/encode failures become controlled backend errors
        import types

        class _LoadFailure:
            def __init__(self, _model: str) -> None:
                raise OSError("simulated model load failure")

        class _EncodeFailure:
            def __init__(self, _model: str) -> None:
                pass

            def encode(self, _texts: list[str], *, show_progress_bar: bool) -> list:
                _ = show_progress_bar
                raise RuntimeError("simulated model encode failure")

        for label, fake_class in (
            ("load", _LoadFailure),
            ("encode", _EncodeFailure),
        ):
            fake_module = types.ModuleType("sentence_transformers")
            fake_module.SentenceTransformer = fake_class
            with mock.patch.dict(sys.modules, {"sentence_transformers": fake_module}):
                try:
                    _sentence_transformers_embed(["test"], "test-model")
                except EmbeddingBackendUnavailable as exc:
                    if type(exc.__cause__).__name__ not in {"OSError", "RuntimeError"}:
                        errors.append(
                            f"sentence-transformers {label} failure lost its exception cause"
                        )
                except Exception as exc:
                    errors.append(
                        f"sentence-transformers {label} failure escaped as {type(exc).__name__}"
                    )
                else:
                    errors.append(
                        f"sentence-transformers {label} failure was not reported"
                    )

        failed_model_path = Path(tmpdir) / "failed_model.jsonl"
        fake_module = types.ModuleType("sentence_transformers")
        fake_module.SentenceTransformer = _LoadFailure
        failed_model_ns = argparse.Namespace(
            input=str(corpus_dir), out=str(failed_model_path),
            backend=SENTENCE_TRANSFORMERS_BACKEND, model="test-model", allow_remote=False,
        )
        with mock.patch.dict(sys.modules, {"sentence_transformers": fake_module}):
            with contextlib.redirect_stderr(io.StringIO()):
                rc = cmd_index(failed_model_ns)
        if rc == 0 or failed_model_path.exists():
            errors.append("model load failure must return nonzero without writing an index")

        # Test 12: an index must never persist the auto selection token
        invalid_auto_path = Path(tmpdir) / "invalid_auto_index.jsonl"
        with invalid_auto_path.open("w", encoding="utf-8") as f:
            f.write(json.dumps({
                "_meta": True,
                "schema_version": INDEX_SCHEMA_VERSION,
                "backend": AUTO_BACKEND,
                "model": "all-MiniLM-L6-v2",
                "embedding_dim": EMBED_DIM_STUB,
            }, allow_nan=False) + "\n")
            f.write(json.dumps({
                "id": 0,
                "path": "x.txt",
                "text_preview": "x",
                "embedding": _stub_embed("x"),
            }, allow_nan=False) + "\n")
        invalid_auto_ns = argparse.Namespace(
            index=str(invalid_auto_path), q="test", k=1, out=None, allow_remote=False,
        )
        with contextlib.redirect_stderr(io.StringIO()):
            rc = cmd_query(invalid_auto_ns)
        if rc == 0:
            errors.append("query should reject an auto token persisted as index backend")

        # Test 13: backend batches must have exact, finite, rectangular vectors
        invalid_batches = (
            ("wrong count", [_stub_embed("one")], 2),
            ("empty vector", [[]], 1),
            ("ragged vectors", [[0.1, 0.2], [0.3]], 2),
            ("boolean value", [[True]], 1),
            ("string value", [["0.1"]], 1),
            ("non-finite value", [[float("nan")]], 1),
        )
        for label, batch, expected_count in invalid_batches:
            try:
                _validate_embedding_batch(
                    batch,
                    expected_count=expected_count,
                    context="test backend",
                )
            except ValueError:
                pass
            else:
                errors.append(f"embedding validation accepted {label}")

        invalid_backend_path = Path(tmpdir) / "invalid_backend.jsonl"
        invalid_backend_ns = argparse.Namespace(
            input=str(corpus_dir),
            out=str(invalid_backend_path),
            backend="stub",
            model="",
            allow_remote=False,
        )
        with mock.patch.object(module, "embed_texts", return_value=[_stub_embed("one")]):
            with contextlib.redirect_stderr(io.StringIO()):
                rc = cmd_index(invalid_backend_ns)
        if rc == 0 or invalid_backend_path.exists():
            errors.append("invalid backend vector count must not write an index")

        # Test 14: JSONL input rejects duplicate keys and non-finite numbers
        strict_header = (
            '{"_meta":true,"schema_version":"1.0","backend":"stub",'
            f'"model":"","embedding_dim":{EMBED_DIM_STUB}}}'
        )
        strict_entry = json.dumps({
            "id": 0,
            "path": "x.txt",
            "text_preview": "x",
            "embedding": _stub_embed("x"),
        }, allow_nan=False)
        invalid_json_indexes = (
            (
                "duplicate JSON key",
                strict_header.replace(
                    '"backend":"stub"',
                    '"backend":"stub","backend":"cohere"',
                ) + "\n" + strict_entry + "\n",
                "duplicate JSON key",
            ),
            (
                "non-finite JSON number",
                strict_header + "\n" + strict_entry.replace(
                    '"embedding": [',
                    '"embedding": [NaN, ',
                ) + "\n",
                "non-finite JSON number",
            ),
            (
                "missing metadata schema",
                strict_header.replace('"schema_version":"1.0",', "")
                + "\n"
                + strict_entry
                + "\n",
                "unsupported index schema_version",
            ),
        )
        for filename, payload, expected_message in invalid_json_indexes:
            strict_path = Path(tmpdir) / f"{filename.replace(' ', '_')}.jsonl"
            strict_path.write_text(payload, encoding="utf-8")
            strict_ns = argparse.Namespace(
                index=str(strict_path),
                q="test",
                k=1,
                out=None,
                allow_remote=False,
            )
            captured_err = io.StringIO()
            with contextlib.redirect_stderr(captured_err):
                rc = cmd_query(strict_ns)
            diagnostic = captured_err.getvalue()
            if rc == 0 or expected_message not in diagnostic:
                errors.append(f"query did not reject {filename} cleanly")
            if "Traceback" in diagnostic:
                errors.append(f"query leaked a traceback for {filename}")

        # Test 15: stored vectors reject booleans and blank queries fail early
        bool_index_path = Path(tmpdir) / "bool_index.jsonl"
        bool_entry = {
            "id": 0,
            "path": "x.txt",
            "text_preview": "x",
            "embedding": [True] + [0.0] * (EMBED_DIM_STUB - 1),
        }
        bool_index_path.write_text(
            strict_header + "\n" + json.dumps(bool_entry, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        bool_ns = argparse.Namespace(
            index=str(bool_index_path),
            q="test",
            k=1,
            out=None,
            allow_remote=False,
        )
        with contextlib.redirect_stderr(io.StringIO()):
            rc = cmd_query(bool_ns)
        if rc == 0:
            errors.append("query accepted a boolean embedding value")

        blank_query_ns = argparse.Namespace(
            index=str(index_path),
            q=" \t\n ",
            k=1,
            out=None,
            allow_remote=False,
        )
        captured_err = io.StringIO()
        with contextlib.redirect_stderr(captured_err):
            rc = cmd_query(blank_query_ns)
        if rc == 0 or "query must not be blank" not in captured_err.getvalue():
            errors.append("query command accepted a blank query")

        blank_ledger_ns = argparse.Namespace(
            ledger=str(Path(tmpdir) / "missing.csv"),
            q="   ",
            k=1,
            backend="stub",
            model="",
            allow_remote=False,
        )
        captured_err = io.StringIO()
        with contextlib.redirect_stderr(captured_err):
            rc = cmd_query_ledger(blank_ledger_ns)
        if rc == 0 or "query must not be blank" not in captured_err.getvalue():
            errors.append("query-ledger command accepted a blank query")

        # Dedupe
        dedup_path = Path(tmpdir) / "dupes.json"
        dedup_ns = argparse.Namespace(
            index=str(index_path), threshold=0.5, out=str(dedup_path),
        )
        rc = cmd_dedupe(dedup_ns)
        if rc != 0:
            errors.append("dedupe command failed")

    # Test 13: remote check enforcement
    os.environ.pop("D_RESEARCH_ALLOW_REMOTE_EMBEDDINGS", None)
    if _is_remote_allowed():
        errors.append("_is_remote_allowed should be False when env not set")

    os.environ["D_RESEARCH_ALLOW_REMOTE_EMBEDDINGS"] = "1"
    if not _is_remote_allowed():
        errors.append("_is_remote_allowed should be True when env=1")
    del os.environ["D_RESEARCH_ALLOW_REMOTE_EMBEDDINGS"]

    if errors:
        print("embed_corpus self-test FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print("embed_corpus self-test ok")
    return 0


def cmd_production_self_test(_args: argparse.Namespace) -> int:
    """Exercise sentence-transformers with a generated local model only."""
    import tempfile

    try:
        from sentence_transformers import (  # type: ignore[import-not-found]
            SentenceTransformer,
            models,
        )
    except ImportError:
        print(
            "embed_corpus production-self-test FAILED: install .[embeddings]",
            file=sys.stderr,
        )
        return 1

    if _resolve_backend(AUTO_BACKEND) != SENTENCE_TRANSFORMERS_BACKEND:
        print(
            "embed_corpus production-self-test FAILED: auto did not select "
            "sentence-transformers",
            file=sys.stderr,
        )
        return 1

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = Path(tmpdir) / "local-bow-model"
            vocabulary = [
                "evidence",
                "ledger",
                "research",
                "semantic",
                "source",
                "validation",
            ]
            local_model = SentenceTransformer(modules=[models.BoW(vocab=vocabulary)])
            local_model.save(str(model_path))
            vectors = _sentence_transformers_embed(
                ["evidence ledger validation", "semantic research source"],
                str(model_path),
            )
    except Exception as exc:
        print(
            "embed_corpus production-self-test FAILED: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1

    if len(vectors) != 2 or not vectors[0] or len(vectors[0]) != len(vectors[1]):
        print(
            "embed_corpus production-self-test FAILED: invalid embedding shape",
            file=sys.stderr,
        )
        return 1
    if vectors[0] == vectors[1] or not all(math.isfinite(value) for row in vectors for value in row):
        print(
            "embed_corpus production-self-test FAILED: invalid embedding values",
            file=sys.stderr,
        )
        return 1

    print("embed_corpus production-self-test ok")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    p = argparse.ArgumentParser(
        prog="embed_corpus.py",
        description="Semantic retrieval over text corpora and evidence ledgers.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    idx_p = sub.add_parser("index", help="Build embedding index from text files.")
    idx_p.add_argument("--in", dest="input", required=True, help="Directory of text files.")
    idx_p.add_argument("--out", required=True, help="Output JSONL index path.")
    idx_p.add_argument(
        "--backend", default=AUTO_BACKEND, choices=BACKEND_CHOICES,
        help=(
            "Embedding backend (default: auto; prefers sentence-transformers, "
            "falls back to local-hashing)."
        ),
    )
    idx_p.add_argument("--model", default="", help="Model name (for sentence-transformers).")
    idx_p.add_argument("--allow-remote", action="store_true", default=False)

    q_p = sub.add_parser("query", help="Find top-k similar documents.")
    q_p.add_argument("--index", required=True, help="JSONL index file.")
    q_p.add_argument("--q", required=True, help="Query text.")
    q_p.add_argument("--k", type=int, default=10, help="Number of results.")
    q_p.add_argument("--out", default=None, help="Output JSON path.")
    q_p.add_argument("--allow-remote", action="store_true", default=False)

    ql_p = sub.add_parser("query-ledger", help="Query evidence-ledger directly.")
    ql_p.add_argument("--ledger", required=True, help="Evidence-ledger CSV.")
    ql_p.add_argument("--q", required=True, help="Query text.")
    ql_p.add_argument("--k", type=int, default=10, help="Number of results.")
    ql_p.add_argument(
        "--backend", default=AUTO_BACKEND, choices=BACKEND_CHOICES,
        help=(
            "Embedding backend (default: auto; prefers sentence-transformers, "
            "falls back to local-hashing)."
        ),
    )
    ql_p.add_argument("--model", default="", help="Model name.")
    ql_p.add_argument("--allow-remote", action="store_true", default=False)

    dd_p = sub.add_parser("dedupe", help="Find near-duplicate documents.")
    dd_p.add_argument("--index", required=True, help="JSONL index file.")
    dd_p.add_argument("--threshold", type=float, default=0.92, help="Similarity threshold.")
    dd_p.add_argument("--out", required=True, help="Output JSON path.")

    sub.add_parser("self-test", help="Run offline self-tests.")
    sub.add_parser(
        "production-self-test",
        help="Exercise the installed sentence-transformers backend without network access.",
    )

    args = p.parse_args()
    if args.cmd == "index":
        return cmd_index(args)
    if args.cmd == "query":
        return cmd_query(args)
    if args.cmd == "query-ledger":
        return cmd_query_ledger(args)
    if args.cmd == "dedupe":
        return cmd_dedupe(args)
    if args.cmd == "self-test":
        return cmd_self_test(args)
    if args.cmd == "production-self-test":
        return cmd_production_self_test(args)
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
