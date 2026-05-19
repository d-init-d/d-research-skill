#!/usr/bin/env python3
"""Citation graph traversal via OpenAlex API.

Subcommands
-----------
* ``cited-by``    - find papers that cite a given DOI
* ``references``  - find papers referenced by a given DOI
* ``expand``      - snowball expansion from seed DOIs (both directions)
* ``to-frontier`` - convert graph nodes to frontier-ledger CSV
* ``coauthors``   - find coauthor network for an ORCID
* ``self-test``   - run offline self-tests with mock server

Uses OpenAlex public API. Rate-limited to ~1 req/sec. No API key required
(but include mailto for polite pool). Caps traversal to prevent runaway.
"""
from __future__ import annotations

import argparse
import csv
import http.server
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

# Optional shared HTTP cache (opt-in via D_RESEARCH_HTTP_CACHE_PATH).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import http_cache as _http_cache
except ImportError:  # pragma: no cover
    _http_cache = None

OPENALEX_API = "https://api.openalex.org"
USER_AGENT = (
    "d-research-skill/0.3.0 "
    "(https://github.com/d-init-d/d-research-skill; contact@example.com)"
)
DEFAULT_DELAY = 1.0
DEFAULT_MAX_EXPAND = 500
DEFAULT_MAX_CITED_BY = 200
GRAPH_SCHEMA_VERSION = "1.0"

FRONTIER_FIELDS = [
    "node_id", "parent_id", "node_type", "value", "gap_id",
    "expansion_method", "priority", "status", "access_status",
    "blocked_reason", "claim_ids", "date_visited", "notes",
]


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _request(url: str, delay: float | None = None) -> dict[str, Any] | None:
    """Polite GET request to OpenAlex.

    When D_RESEARCH_HTTP_CACHE_PATH is set, results are cached. Cache
    failures are non-fatal and never bypass the polite delay on a real fetch.
    """
    request_headers = {"User-Agent": USER_AGENT}

    # Cache lookup happens before the polite delay - a hot cache should be fast.
    if _http_cache is not None:
        try:
            cached = _http_cache.get("GET", url, request_headers=request_headers)
            if cached:
                try:
                    return json.loads(cached["body"])
                except (json.JSONDecodeError, ValueError):
                    pass  # Fall through to live fetch
        except Exception:  # noqa: BLE001
            pass

    actual_delay = DEFAULT_DELAY if delay is None else delay
    if actual_delay > 0:
        time.sleep(actual_delay)
    req = urllib.request.Request(url, headers=request_headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
            resp_headers = dict(resp.headers.items()) if resp.headers else {}
            status = resp.status
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        print(f"warning: request failed for {url}: {e}", file=sys.stderr)
        return None

    if _http_cache is not None and 200 <= status < 300:
        try:
            _http_cache.put(
                "GET", url, status, resp_headers, body,
                request_headers=request_headers,
            )
        except Exception:  # noqa: BLE001
            pass

    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        print(f"warning: invalid JSON for {url}: {e}", file=sys.stderr)
        return None


def _doi_to_openalex_url(doi: str) -> str:
    clean = doi.strip().removeprefix("https://doi.org/")
    return f"{OPENALEX_API}/works/doi:{urllib.parse.quote(clean, safe='')}"


def _extract_work(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "openalex_id": data.get("id", ""),
        "doi": (data.get("doi") or "").removeprefix("https://doi.org/"),
        "title": data.get("title", ""),
        "year": data.get("publication_year"),
        "cited_by_count": data.get("cited_by_count", 0),
        "authors": [
            a.get("author", {}).get("display_name", "")
            for a in (data.get("authorships") or [])[:5]
        ],
    }


def _build_graph(
    seed_works: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    cap_hit: bool,
) -> dict[str, Any]:
    return {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "seed_works": seed_works,
        "nodes": nodes,
        "edges": edges,
        "stats": {"node_count": len(nodes), "edge_count": len(edges), "cap_hit": cap_hit},
    }


# ---------------------------------------------------------------------------
# Traversal helpers
# ---------------------------------------------------------------------------


def _fetch_cited_by(
    openalex_id: str, max_results: int, seen: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fetch papers citing openalex_id. Returns (new_nodes, new_edges)."""
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    url = f"{OPENALEX_API}/works?filter=cites:{openalex_id}&per_page=50"
    cursor = "*"
    while len(nodes) < max_results:
        page_url = f"{url}&cursor={cursor}"
        data = _request(page_url)
        if not data:
            break
        for r in data.get("results", []):
            if len(nodes) >= max_results:
                break
            rid = r.get("id", "")
            if rid and rid not in seen:
                seen.add(rid)
                nodes.append(_extract_work(r))
                edges.append({"src": rid, "dst": openalex_id, "kind": "cites"})
        cursor = (data.get("meta") or {}).get("next_cursor")
        if not cursor or not data.get("results"):
            break
    return nodes, edges


def _fetch_references(
    work_data: dict[str, Any], max_results: int, seen: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fetch referenced works. Returns (new_nodes, new_edges)."""
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    openalex_id = work_data.get("id", "")
    for ref_id in (work_data.get("referenced_works") or [])[:max_results]:
        if len(nodes) >= max_results:
            break
        rid = ref_id.split("/")[-1]
        full_id = f"https://openalex.org/{rid}"
        if full_id in seen:
            edges.append({"src": openalex_id, "dst": full_id, "kind": "cites"})
            continue
        ref_url = f"{OPENALEX_API}/works/{rid}"
        ref_data = _request(ref_url)
        if ref_data:
            actual_id = ref_data.get("id", full_id)
            seen.add(actual_id)
            nodes.append(_extract_work(ref_data))
            edges.append({"src": openalex_id, "dst": actual_id, "kind": "cites"})
    return nodes, edges


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_cited_by(args: argparse.Namespace) -> int:
    """Find papers that cite a given DOI."""
    url = _doi_to_openalex_url(args.doi)
    work_data = _request(url)
    if not work_data:
        print(f"error: could not resolve DOI: {args.doi}", file=sys.stderr)
        return 1

    seed = _extract_work(work_data)
    openalex_id = work_data.get("id", "")
    seen: set[str] = {openalex_id}
    depth = getattr(args, "depth", 1)
    max_per_hop = args.max

    nodes: list[dict[str, Any]] = [seed]
    edges: list[dict[str, Any]] = []
    cap_hit = False

    # Depth 1: direct citers
    new_nodes, new_edges = _fetch_cited_by(openalex_id, max_per_hop, seen)
    nodes.extend(new_nodes)
    edges.extend(new_edges)
    if len(nodes) - 1 >= max_per_hop:
        cap_hit = True

    # Depth 2: citers of citers (global cap)
    if depth >= 2 and not cap_hit:
        hop1_ids = [n["openalex_id"] for n in new_nodes]
        for h1_id in hop1_ids:
            remaining = max_per_hop - (len(nodes) - 1)
            if remaining <= 0:
                cap_hit = True
                break
            h2_nodes, h2_edges = _fetch_cited_by(h1_id, min(remaining, 10), seen)
            nodes.extend(h2_nodes)
            edges.extend(h2_edges)
        if len(nodes) - 1 >= max_per_hop:
            cap_hit = True

    graph = _build_graph([seed], nodes, edges, cap_hit)
    out = json.dumps(graph, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(out, encoding="utf-8")
        print(f"wrote {args.out} ({len(nodes)} nodes, {len(edges)} edges)")
    else:
        print(out)
    return 0


def cmd_references(args: argparse.Namespace) -> int:
    """Find papers referenced by a given DOI."""
    url = _doi_to_openalex_url(args.doi)
    work_data = _request(url)
    if not work_data:
        print(f"error: could not resolve DOI: {args.doi}", file=sys.stderr)
        return 1

    seed = _extract_work(work_data)
    openalex_id = work_data.get("id", "")
    seen: set[str] = {openalex_id}
    depth = getattr(args, "depth", 1)
    max_results = args.max

    nodes: list[dict[str, Any]] = [seed]
    edges: list[dict[str, Any]] = []
    cap_hit = False

    # Depth 1: direct references
    new_nodes, new_edges = _fetch_references(work_data, max_results, seen)
    nodes.extend(new_nodes)
    edges.extend(new_edges)
    if len(nodes) - 1 >= max_results:
        cap_hit = True

    # Depth 2: references of references (global cap)
    if depth >= 2 and not cap_hit:
        hop1_ids = [n["openalex_id"] for n in new_nodes]
        for h1_id in hop1_ids:
            remaining = max_results - (len(nodes) - 1)
            if remaining <= 0:
                cap_hit = True
                break
            h1_url = f"{OPENALEX_API}/works/{h1_id.split('/')[-1]}"
            h1_data = _request(h1_url)
            if h1_data:
                h2_nodes, h2_edges = _fetch_references(h1_data, min(remaining, 10), seen)
                nodes.extend(h2_nodes)
                edges.extend(h2_edges)
        if len(nodes) - 1 >= max_results:
            cap_hit = True

    graph = _build_graph([seed], nodes, edges, cap_hit)
    out = json.dumps(graph, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(out, encoding="utf-8")
        print(f"wrote {args.out} ({len(nodes)} nodes, {len(edges)} edges)")
    else:
        print(out)
    return 0


def cmd_expand(args: argparse.Namespace) -> int:
    """Snowball expansion from seed DOIs (both directions by default)."""
    seed_path = Path(args.seed)
    if not seed_path.is_file():
        print(f"error: seed file not found: {seed_path}", file=sys.stderr)
        return 1

    direction = getattr(args, "direction", "both")

    seeds: list[str] = []
    with seed_path.open(newline="", encoding="utf-8") as f:
        first_line = f.readline().strip()
        f.seek(0)
        if "," in first_line and "doi" in first_line.lower():
            reader = csv.DictReader(f)
            for row in reader:
                doi = (row.get("doi") or row.get("DOI") or "").strip()
                if doi:
                    seeds.append(doi)
        else:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    seeds.append(line)

    if not seeds:
        print("error: no seed DOIs found", file=sys.stderr)
        return 1

    max_nodes = args.max
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    seen: set[str] = set()
    seed_works: list[dict[str, Any]] = []
    cap_hit = False

    for doi in seeds:
        if len(nodes) >= max_nodes:
            cap_hit = True
            break
        url = _doi_to_openalex_url(doi)
        data = _request(url)
        if not data:
            continue
        work = _extract_work(data)
        oid = data.get("id", "")
        if oid not in seen:
            seen.add(oid)
            nodes.append(work)
            seed_works.append(work)

        # Backward: references
        if direction in ("both", "references") and len(nodes) < max_nodes:
            remaining = min(50, max_nodes - len(nodes))
            ref_nodes, ref_edges = _fetch_references(data, remaining, seen)
            nodes.extend(ref_nodes)
            edges.extend(ref_edges)

        # Forward: cited-by
        if direction in ("both", "cited-by") and len(nodes) < max_nodes:
            remaining = min(50, max_nodes - len(nodes))
            cb_nodes, cb_edges = _fetch_cited_by(oid, remaining, seen)
            nodes.extend(cb_nodes)
            edges.extend(cb_edges)

        if len(nodes) >= max_nodes:
            cap_hit = True

    graph = _build_graph(seed_works, nodes, edges, cap_hit)
    out = json.dumps(graph, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(out, encoding="utf-8")
        print(f"wrote {args.out} ({len(nodes)} nodes, {len(edges)} edges)")
    else:
        print(out)
    return 0


def cmd_to_frontier(args: argparse.Namespace) -> int:
    """Convert graph nodes to frontier-ledger CSV (exact schema)."""
    graph_path = Path(args.graph)
    if not graph_path.is_file():
        print(f"error: graph not found: {graph_path}", file=sys.stderr)
        return 1

    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    nodes = graph.get("nodes", [])

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FRONTIER_FIELDS)
        writer.writeheader()
        for i, node in enumerate(nodes):
            doi = node.get("doi", "")
            value = f"https://doi.org/{doi}" if doi else node.get("openalex_id", "")
            writer.writerow({
                "node_id": node.get("openalex_id", f"N{i:04d}"),
                "parent_id": "",
                "node_type": "citation",
                "value": value,
                "gap_id": "",
                "expansion_method": "citation_graph",
                "priority": "",
                "status": "pending",
                "access_status": "unknown",
                "blocked_reason": "",
                "claim_ids": "",
                "date_visited": "",
                "notes": f"year={node.get('year', '')} cited_by={node.get('cited_by_count', '')}",
            })
    print(f"wrote {out_path} ({len(nodes)} candidates)")
    return 0


def cmd_coauthors(args: argparse.Namespace) -> int:
    """Find coauthor network for an ORCID (depth=1 only)."""
    depth = getattr(args, "depth", 1)
    if depth != 1:
        print("error: coauthors only supports --depth 1", file=sys.stderr)
        return 1

    orcid = args.orcid.strip()
    url = f"{OPENALEX_API}/authors/orcid:{orcid}"
    author_data = _request(url)
    if not author_data:
        print(f"error: could not resolve ORCID: {orcid}", file=sys.stderr)
        return 1

    author_name = author_data.get("display_name", "")
    author_id = author_data.get("id", "")

    works_url = f"{OPENALEX_API}/works?filter=author.id:{author_id}&per_page=50"
    works_data = _request(works_url)
    if not works_data:
        return 1

    coauthors: dict[str, dict[str, Any]] = {}
    for work in works_data.get("results", []):
        for authorship in work.get("authorships", []):
            a = authorship.get("author", {})
            aid = a.get("id", "")
            if aid and aid != author_id:
                if aid not in coauthors:
                    coauthors[aid] = {"id": aid, "name": a.get("display_name", ""), "collaborations": 0}
                coauthors[aid]["collaborations"] += 1

    result = {
        "author": {"id": author_id, "name": author_name, "orcid": orcid},
        "coauthors": sorted(coauthors.values(), key=lambda x: x["collaborations"], reverse=True),
    }
    out = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(out, encoding="utf-8")
        print(f"wrote {args.out} ({len(coauthors)} coauthors)")
    else:
        print(out)
    return 0


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


class _MockHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path.startswith("/works/doi:"):
            data = {
                "id": "https://openalex.org/W1234",
                "doi": "https://doi.org/10.1234/test",
                "title": "Test Paper",
                "publication_year": 2023,
                "cited_by_count": 42,
                "authorships": [{"author": {"id": "https://openalex.org/A1", "display_name": "Author One"}}],
                "referenced_works": ["https://openalex.org/W5555", "https://openalex.org/W6666"],
            }
            self._respond(200, json.dumps(data).encode(), "application/json")
        elif path.startswith("/works/W"):
            wid = path.split("/")[-1]
            data = {
                "id": f"https://openalex.org/{wid}",
                "doi": f"https://doi.org/10.9999/{wid.lower()}",
                "title": f"Paper {wid}",
                "publication_year": 2020,
                "cited_by_count": 10,
                "authorships": [{"author": {"id": "https://openalex.org/A3", "display_name": "Ref Author"}}],
                "referenced_works": [],
            }
            self._respond(200, json.dumps(data).encode(), "application/json")
        elif path == "/works" and any("cites" in v for v in query.get("filter", [])):
            data = {
                "meta": {"next_cursor": None},
                "results": [{
                    "id": "https://openalex.org/W9999",
                    "doi": "https://doi.org/10.9999/citing",
                    "title": "Citing Paper",
                    "publication_year": 2024,
                    "cited_by_count": 5,
                    "authorships": [{"author": {"id": "https://openalex.org/A4", "display_name": "Citer"}}],
                    "referenced_works": [],
                }],
            }
            self._respond(200, json.dumps(data).encode(), "application/json")
        elif path.startswith("/authors/orcid:"):
            self._respond(200, json.dumps({"id": "https://openalex.org/A1", "display_name": "Test Author"}).encode(), "application/json")
        elif path == "/works" and any("author.id" in v for v in query.get("filter", [])):
            data = {"results": [{"authorships": [
                {"author": {"id": "https://openalex.org/A1", "display_name": "Test Author"}},
                {"author": {"id": "https://openalex.org/A5", "display_name": "Coauthor One"}},
            ]}]}
            self._respond(200, json.dumps(data).encode(), "application/json")
        else:
            self._respond(404, b"Not Found", "text/plain")

    def _respond(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def cmd_self_test(_args: argparse.Namespace) -> int:
    global OPENALEX_API, DEFAULT_DELAY  # noqa: PLW0603
    import tempfile

    orig_api, orig_delay = OPENALEX_API, DEFAULT_DELAY
    DEFAULT_DELAY = 0

    # Isolate the HTTP cache so a stale local cache cannot mask mock HTTP.
    cache_env = "D_RESEARCH_HTTP_CACHE_PATH"
    saved_cache = os.environ.pop(cache_env, None)

    server = http.server.HTTPServer(("127.0.0.1", 0), _MockHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    OPENALEX_API = f"http://127.0.0.1:{port}"
    errors: list[str] = []

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            # Test 1: cited-by depth 1
            out = Path(tmpdir) / "cb.json"
            rc = cmd_cited_by(argparse.Namespace(doi="10.1234/test", max=10, depth=1, out=str(out)))
            if rc != 0:
                errors.append("cited-by depth=1 failed")
            elif out.is_file():
                g = json.loads(out.read_text(encoding="utf-8"))
                if g["stats"]["node_count"] < 2:
                    errors.append("cited-by should have >=2 nodes")

            # Test 2: cited-by depth 2
            out = Path(tmpdir) / "cb2.json"
            rc = cmd_cited_by(argparse.Namespace(doi="10.1234/test", max=10, depth=2, out=str(out)))
            if rc != 0:
                errors.append("cited-by depth=2 failed")

            # Test 3: references depth 1
            out = Path(tmpdir) / "refs.json"
            rc = cmd_references(argparse.Namespace(doi="10.1234/test", max=10, depth=1, out=str(out)))
            if rc != 0:
                errors.append("references depth=1 failed")
            elif out.is_file():
                g = json.loads(out.read_text(encoding="utf-8"))
                if g["stats"]["node_count"] < 2:
                    errors.append("references should have >=2 nodes")

            # Test 4: references depth 2
            out = Path(tmpdir) / "refs2.json"
            rc = cmd_references(argparse.Namespace(doi="10.1234/test", max=10, depth=2, out=str(out)))
            if rc != 0:
                errors.append("references depth=2 failed")

            # Test 5: expand (both directions)
            seed_file = Path(tmpdir) / "seeds.txt"
            seed_file.write_text("10.1234/test\n", encoding="utf-8")
            out = Path(tmpdir) / "exp.json"
            rc = cmd_expand(argparse.Namespace(seed=str(seed_file), max=10, direction="both", out=str(out)))
            if rc != 0:
                errors.append("expand failed")
            elif out.is_file():
                g = json.loads(out.read_text(encoding="utf-8"))
                if not g.get("edges"):
                    errors.append("expand should produce edges")

            # Test 6: to-frontier schema
            frontier_out = Path(tmpdir) / "frontier.csv"
            rc = cmd_to_frontier(argparse.Namespace(graph=str(out), out=str(frontier_out)))
            if rc != 0:
                errors.append("to-frontier failed")
            elif frontier_out.is_file():
                with frontier_out.open(newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    actual_fields = reader.fieldnames or []
                if list(actual_fields) != FRONTIER_FIELDS:
                    errors.append(f"to-frontier header mismatch: {actual_fields}")
                rows = list(csv.DictReader(frontier_out.open(newline="", encoding="utf-8")))
                if rows and rows[0].get("node_type") != "citation":
                    errors.append("to-frontier node_type should be 'citation'")
                if rows and rows[0].get("expansion_method") != "citation_graph":
                    errors.append("to-frontier expansion_method should be 'citation_graph'")

            # Test 7: coauthors depth=1
            out = Path(tmpdir) / "ca.json"
            rc = cmd_coauthors(argparse.Namespace(orcid="0000-0001-2345-6789", depth=1, out=str(out)))
            if rc != 0:
                errors.append("coauthors depth=1 failed")

            # Test 8: coauthors depth=2 should fail
            import io
            old_stderr = sys.stderr
            sys.stderr = io.StringIO()
            rc = cmd_coauthors(argparse.Namespace(orcid="0000-0001-2345-6789", depth=2, out=None))
            sys.stderr = old_stderr
            if rc == 0:
                errors.append("coauthors depth=2 should fail")

    finally:
        OPENALEX_API, DEFAULT_DELAY = orig_api, orig_delay
        if saved_cache is not None:
            os.environ[cache_env] = saved_cache
        server.shutdown()

    if errors:
        print("citation_graph self-test FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("citation_graph self-test ok")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    p = argparse.ArgumentParser(prog="citation_graph.py", description="Citation graph traversal via OpenAlex.")
    sub = p.add_subparsers(dest="cmd", required=True)

    cb_p = sub.add_parser("cited-by", help="Find papers citing a DOI.")
    cb_p.add_argument("--doi", required=True)
    cb_p.add_argument("--depth", type=int, default=1, choices=[1, 2])
    cb_p.add_argument("--max", type=int, default=DEFAULT_MAX_CITED_BY)
    cb_p.add_argument("--out", default=None)

    ref_p = sub.add_parser("references", help="Find papers referenced by a DOI.")
    ref_p.add_argument("--doi", required=True)
    ref_p.add_argument("--depth", type=int, default=1, choices=[1, 2])
    ref_p.add_argument("--max", type=int, default=DEFAULT_MAX_CITED_BY)
    ref_p.add_argument("--out", default=None)

    exp_p = sub.add_parser("expand", help="Snowball expansion from seed DOIs.")
    exp_p.add_argument("--seed", required=True)
    exp_p.add_argument("--max", type=int, default=DEFAULT_MAX_EXPAND)
    exp_p.add_argument("--direction", default="both", choices=["references", "cited-by", "both"])
    exp_p.add_argument("--out", default=None)

    tf_p = sub.add_parser("to-frontier", help="Convert graph to frontier-ledger CSV.")
    tf_p.add_argument("--graph", required=True)
    tf_p.add_argument("--out", required=True)

    ca_p = sub.add_parser("coauthors", help="Find coauthor network for an ORCID.")
    ca_p.add_argument("--orcid", required=True)
    ca_p.add_argument("--depth", type=int, default=1)
    ca_p.add_argument("--out", default=None)

    sub.add_parser("self-test", help="Run offline self-tests.")

    args = p.parse_args()
    if args.cmd == "cited-by":
        return cmd_cited_by(args)
    if args.cmd == "references":
        return cmd_references(args)
    if args.cmd == "expand":
        return cmd_expand(args)
    if args.cmd == "to-frontier":
        return cmd_to_frontier(args)
    if args.cmd == "coauthors":
        return cmd_coauthors(args)
    if args.cmd == "self-test":
        return cmd_self_test(args)
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
