#!/usr/bin/env python3
"""Semantic retrieval over text corpora and evidence ledgers.

Subcommands
-----------
* ``index``        - build an embedding index from text files
* ``query``        - find top-k similar documents to a query
* ``query-ledger`` - query an evidence-ledger CSV directly
* ``dedupe``       - find near-duplicate documents by similarity
* ``self-test``    - run offline self-tests with stub embedder

Embedding backends (all optional, all soft-fail):
- stub: deterministic hash-based fake (for testing, always available)
- sentence-transformers: pip install sentence-transformers (local, default if available)
- cohere: remote, requires COHERE_API_KEY + --allow-remote or D_RESEARCH_ALLOW_REMOTE_EMBEDDINGS=1
- llama-cli: local shellout to llama-embedding binary

Cosine similarity is implemented with stdlib math (no numpy required).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import sys
from pathlib import Path
from typing import Any

EMBED_DIM_STUB = 32
INDEX_SCHEMA_VERSION = "1.0"


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


def _sentence_transformers_embed(texts: list[str], model_name: str) -> list[list[float]]:
    """Embed via sentence-transformers (optional pip package)."""
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]
    except ImportError:
        print(
            "error: sentence-transformers is not installed.\n"
            "  Install: pip install sentence-transformers>=2.2",
            file=sys.stderr,
        )
        raise SystemExit(1)
    model = SentenceTransformer(model_name)
    embeddings = model.encode(texts, show_progress_bar=False)
    return [e.tolist() for e in embeddings]


def _cohere_embed(
    texts: list[str],
    model_name: str = "embed-english-v3.0",
    input_type: str = "search_document",
) -> list[list[float]]:
    """Embed via Cohere API (remote, requires key + opt-in)."""
    import urllib.error
    import urllib.request

    key = os.environ.get("COHERE_API_KEY", "")
    if not key:
        print("error: COHERE_API_KEY env var not set", file=sys.stderr)
        raise SystemExit(1)

    data = json.dumps({
        "texts": texts,
        "model": model_name,
        "input_type": input_type,
    }).encode()
    req = urllib.request.Request(
        "https://api.cohere.ai/v1/embed",
        data=data,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
            return result.get("embeddings", [])
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
            vec = json.loads(result.stdout)
            embeddings.append(vec if isinstance(vec, list) else vec.get("embedding", []))
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    return embeddings


def _resolved_model_name(backend: str, model: str = "") -> str:
    """Return the concrete model name stored in index metadata."""
    if backend == "sentence-transformers":
        return model or "all-MiniLM-L6-v2"
    if backend == "cohere":
        return model or "embed-english-v3.0"
    if backend == "llama-cli":
        return model or "llama-embedding"
    return model


def embed_texts(
    texts: list[str], backend: str = "stub", model: str = "",
    input_type: str = "search_document",
) -> list[list[float]]:
    """Embed a list of texts using the specified backend."""
    if backend == "stub":
        return [_stub_embed(t) for t in texts]
    if backend == "sentence-transformers":
        model_name = _resolved_model_name(backend, model)
        return _sentence_transformers_embed(texts, model_name)
    if backend == "cohere":
        model_name = _resolved_model_name(backend, model)
        return _cohere_embed(texts, model_name, input_type)
    if backend == "llama-cli":
        return _llama_cli_embed(texts)
    print(f"error: unknown backend: {backend}", file=sys.stderr)
    raise SystemExit(1)


# ---------------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------------


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors (stdlib math only)."""
    if len(a) != len(b):
        raise ValueError(f"embedding dimension mismatch: {len(a)} != {len(b)}")
    dot = math.fsum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(math.fsum(x * x for x in a))
    mag_b = math.sqrt(math.fsum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


# ---------------------------------------------------------------------------
# Index format (JSONL with metadata header)
# ---------------------------------------------------------------------------


def _write_index(
    entries: list[dict[str, Any]], out_path: Path,
    backend: str, model: str, embedding_dim: int,
) -> None:
    """Write index with metadata header line."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    header = {
        "_meta": True,
        "schema_version": INDEX_SCHEMA_VERSION,
        "backend": backend,
        "model": model,
        "embedding_dim": embedding_dim,
    }
    with out_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(header, ensure_ascii=False) + "\n")
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _read_index(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Read index, returning (metadata, entries)."""
    meta: dict[str, Any] = {}
    entries: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("_meta"):
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

    expected_dim = meta.get("embedding_dim")
    if not isinstance(expected_dim, int) or expected_dim <= 0:
        print(f"error: invalid embedding_dim in index metadata: {expected_dim!r}", file=sys.stderr)
        return 1

    for i, entry in enumerate(entries):
        embedding = entry.get("embedding")
        if not isinstance(embedding, list) or not embedding:
            print(f"error: index entry {i} has missing or invalid embedding", file=sys.stderr)
            return 1
        if len(embedding) != expected_dim:
            print(
                f"error: index entry {i} embedding length {len(embedding)} "
                f"does not match embedding_dim {expected_dim}",
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


def cmd_index(args: argparse.Namespace) -> int:
    """Build embedding index from text files in a directory."""
    in_dir = Path(args.input)
    if not in_dir.is_dir():
        print(f"error: directory not found: {in_dir}", file=sys.stderr)
        return 1

    backend = args.backend
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
    embeddings = embed_texts(texts, backend, model, input_type="search_document")
    embedding_dim = len(embeddings[0]) if embeddings else 0

    entries = []
    for i, (path, vec) in enumerate(zip(paths, embeddings)):
        entries.append({
            "id": i,
            "path": path,
            "text_preview": texts[i][:200],
            "embedding": vec,
        })

    out_path = Path(args.out)
    _write_index(entries, out_path, backend, model, embedding_dim)
    print(f"indexed {len(entries)} files -> {out_path} (backend={backend}, dim={embedding_dim})")
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    """Find top-k similar documents to a query."""
    index_path = Path(args.index)
    if not index_path.is_file():
        print(f"error: index not found: {index_path}", file=sys.stderr)
        return 1

    meta, entries = _read_index(index_path)
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
    query_vecs = embed_texts([args.q], backend, model, input_type="search_query")
    query_vec = query_vecs[0]

    # Dimension check
    if expected_dim and len(query_vec) != expected_dim:
        print(
            f"error: embedding dimension mismatch: query has {len(query_vec)} dims "
            f"but index expects {expected_dim}",
            file=sys.stderr,
        )
        return 1

    # Check first entry dimension matches
    if entries[0]["embedding"] and len(entries[0]["embedding"]) != len(query_vec):
        print(
            f"error: embedding dimension mismatch: index entries have "
            f"{len(entries[0]['embedding'])} dims but query has {len(query_vec)}",
            file=sys.stderr,
        )
        return 1

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

    output = json.dumps(results, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(output + "\n", encoding="utf-8")
        print(f"wrote {args.out} ({len(results)} results)")
    else:
        print(output)
    return 0


def cmd_query_ledger(args: argparse.Namespace) -> int:
    """Query an evidence-ledger CSV directly."""
    ledger_path = Path(args.ledger)
    if not ledger_path.is_file():
        print(f"error: ledger not found: {ledger_path}", file=sys.stderr)
        return 1

    backend = getattr(args, "backend", "stub") or "stub"
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

    embeddings = embed_texts(texts, backend, model, input_type="search_document")
    query_vecs = embed_texts([args.q], backend, model, input_type="search_query")
    query_vec = query_vecs[0]

    # Dimension check
    if embeddings and len(embeddings[0]) != len(query_vec):
        print(
            f"error: embedding dimension mismatch: ledger has {len(embeddings[0])} dims "
            f"but query has {len(query_vec)}",
            file=sys.stderr,
        )
        return 1

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

    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


def cmd_dedupe(args: argparse.Namespace) -> int:
    """Find near-duplicate documents by similarity threshold."""
    index_path = Path(args.index)
    if not index_path.is_file():
        print(f"error: index not found: {index_path}", file=sys.stderr)
        return 1

    _meta, entries = _read_index(index_path)
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
        json.dumps(duplicates, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"found {len(duplicates)} duplicate pair(s) -> {out_path}")
    return 0


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def cmd_self_test(_args: argparse.Namespace) -> int:
    """Offline self-test with stub embedder."""
    import tempfile

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
            import contextlib
            import io
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
            }) + "\n")
            f.write(json.dumps({
                "id": 0,
                "path": "x.txt",
                "text_preview": "x",
                "embedding": [0.1] * (EMBED_DIM_STUB - 1),
            }) + "\n")

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
            }) + "\n")
            f.write(json.dumps({
                "id": 0,
                "path": "x.txt",
                "text_preview": "x",
                "embedding": _stub_embed("x"),
            }) + "\n")
        cohere_query_ns = argparse.Namespace(
            index=str(cohere_query_path), q="test", k=1, out=None, allow_remote=False,
        )
        sys.stderr = io.StringIO()
        rc = cmd_query(cohere_query_ns)
        sys.stderr = old_stderr
        if rc == 0:
            errors.append("cohere query without --allow-remote should fail")

        # Dedupe
        dedup_path = Path(tmpdir) / "dupes.json"
        dedup_ns = argparse.Namespace(
            index=str(index_path), threshold=0.5, out=str(dedup_path),
        )
        rc = cmd_dedupe(dedup_ns)
        if rc != 0:
            errors.append("dedupe command failed")

    # Test 9: remote check enforcement
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
    idx_p.add_argument("--backend", default="stub",
                       choices=["stub", "sentence-transformers", "cohere", "llama-cli"])
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
    ql_p.add_argument("--backend", default="stub",
                      choices=["stub", "sentence-transformers", "cohere", "llama-cli"])
    ql_p.add_argument("--model", default="", help="Model name.")
    ql_p.add_argument("--allow-remote", action="store_true", default=False)

    dd_p = sub.add_parser("dedupe", help="Find near-duplicate documents.")
    dd_p.add_argument("--index", required=True, help="JSONL index file.")
    dd_p.add_argument("--threshold", type=float, default=0.92, help="Similarity threshold.")
    dd_p.add_argument("--out", required=True, help="Output JSON path.")

    sub.add_parser("self-test", help="Run offline self-tests.")

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
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
