#!/usr/bin/env python3
"""Wikidata entity search, retrieval, disambiguation, and SPARQL queries.

Subcommands:
    search       Search Wikidata for entities matching a term.
    entity       Retrieve detailed information about a Wikidata entity by Q-ID.
    disambiguate Disambiguate a name against Wikidata using context.
    sparql       Execute a SPARQL SELECT query against the Wikidata query service.
    self-test    Run offline self-tests with mocked HTTP responses.

Exit codes:
    0  success
    1  runtime error (HTTP, network, parse, not-found)
    2  invalid arguments
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Optional shared HTTP cache (opt-in via D_RESEARCH_HTTP_CACHE_PATH).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import http_cache as _http_cache
except ImportError:  # pragma: no cover
    _http_cache = None


# ---------------------------------------------------------------------------
# WikidataClient — HTTP wrapper with User-Agent enforcement
# ---------------------------------------------------------------------------

class WikidataClient:
    """HTTP client for Wikidata API with User-Agent enforcement."""

    BASE_URL = "https://www.wikidata.org/w/api.php"
    SPARQL_URL = "https://query.wikidata.org/sparql"
    USER_AGENT = (
        "d-research-skill/0.3.0 "
        "(https://github.com/d-init-d/d-research-skill; contact@example.com)"
    )

    def _request(self, url: str, data: bytes | None = None) -> bytes:
        """Make an HTTP request with User-Agent header. Returns response bytes.

        For GET requests (data is None) and when D_RESEARCH_HTTP_CACHE_PATH is
        set, results are cached. Cache failures are non-fatal.
        """
        is_get = data is None
        request_headers = {"User-Agent": self.USER_AGENT}

        if is_get and _http_cache is not None:
            try:
                cached = _http_cache.get("GET", url, request_headers=request_headers)
                if cached:
                    return cached["body"]
            except Exception:  # noqa: BLE001
                pass

        req = urllib.request.Request(url)
        req.add_header("User-Agent", self.USER_AGENT)
        if data is not None:
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(req, data=data) as resp:
                body = resp.read()
                resp_headers = dict(resp.headers.items()) if resp.headers else {}
                status = resp.status
        except urllib.error.HTTPError as exc:
            print(
                f"Error: Wikidata API returned HTTP {exc.code}: {exc.reason}",
                file=sys.stderr,
            )
            sys.exit(1)
        except urllib.error.URLError as exc:
            print(f"Error: Network error: {exc.reason}", file=sys.stderr)
            sys.exit(1)

        if is_get and _http_cache is not None and 200 <= status < 300:
            try:
                _http_cache.put(
                    "GET", url, status, resp_headers, body,
                    request_headers=request_headers,
                )
            except Exception:  # noqa: BLE001
                pass
        return body

    def search_entities(
        self, term: str, type_filter: str | None = None, limit: int = 5
    ) -> list[dict]:
        """Call wbsearchentities, return [{qid, label, description, aliases}]."""
        params = urllib.parse.urlencode({
            "action": "wbsearchentities",
            "search": term,
            "language": "en",
            "limit": limit,
            "format": "json",
        })
        url = f"{self.BASE_URL}?{params}"
        raw = self._request(url)
        try:
            body = json.loads(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            print(
                f"Error: Failed to parse API response: {exc}", file=sys.stderr
            )
            sys.exit(1)

        results = []
        for item in body.get("search", []):
            results.append({
                "qid": item.get("id", ""),
                "label": item.get("label", ""),
                "description": item.get("description", ""),
                "aliases": item.get("aliases", []),
            })

        if type_filter:
            results = self._filter_by_type(results, type_filter)

        return results

    def _filter_by_type(
        self, results: list[dict], type_filter: str
    ) -> list[dict]:
        """Filter results by entity type keyword in description."""
        type_keywords: dict[str, list[str]] = {
            "person": ["human", "person", "people", "born", "died"],
            "org": [
                "organization", "organisation", "company", "institution",
                "agency", "corporation",
            ],
            "product": ["product", "software", "brand", "model", "device"],
            "place": [
                "city", "country", "village", "town", "municipality",
                "region", "state", "province", "location",
            ],
        }
        keywords = type_keywords.get(type_filter, [])
        if not keywords:
            return results
        filtered = []
        for r in results:
            desc_lower = r.get("description", "").lower()
            if any(kw in desc_lower for kw in keywords):
                filtered.append(r)
        return filtered

    def get_entity(
        self, qid: str, lang: str = "en", fields: list[str] | None = None
    ) -> dict:
        """Call wbgetentities, return filtered entity dict."""
        params = urllib.parse.urlencode({
            "action": "wbgetentities",
            "ids": qid,
            "languages": lang,
            "format": "json",
        })
        url = f"{self.BASE_URL}?{params}"
        raw = self._request(url)
        try:
            body = json.loads(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            print(
                f"Error: Failed to parse API response: {exc}", file=sys.stderr
            )
            sys.exit(1)

        entities = body.get("entities", {})
        if qid not in entities or "missing" in entities.get(qid, {}):
            print(f"Error: Entity {qid} not found", file=sys.stderr)
            sys.exit(1)

        entity_data = entities[qid]
        result: dict = {"qid": qid}

        # Extract labels
        labels_raw = entity_data.get("labels", {})
        result["labels"] = {
            code: val.get("value", "")
            for code, val in labels_raw.items()
        }

        # Extract descriptions
        descs_raw = entity_data.get("descriptions", {})
        result["descriptions"] = {
            code: val.get("value", "")
            for code, val in descs_raw.items()
        }

        # Extract aliases
        aliases_raw = entity_data.get("aliases", {})
        result["aliases"] = {
            code: [a.get("value", "") for a in alias_list]
            for code, alias_list in aliases_raw.items()
        }

        # Extract claims (simplified)
        claims_raw = entity_data.get("claims", {})
        result["claims"] = {}
        for prop, claim_list in claims_raw.items():
            values = []
            for claim in claim_list:
                mainsnak = claim.get("mainsnak", {})
                datavalue = mainsnak.get("datavalue", {})
                value = datavalue.get("value", {})
                if isinstance(value, dict):
                    values.append({
                        "value": value.get("id", str(value)),
                        "label": value.get("id", ""),
                    })
                else:
                    values.append({"value": str(value), "label": str(value)})
            result["claims"][prop] = values

        # Extract sitelinks
        sitelinks_raw = entity_data.get("sitelinks", {})
        result["sitelinks"] = {
            site: link.get("title", "")
            for site, link in sitelinks_raw.items()
        }

        # Filter to requested fields only
        if fields:
            valid_fields = {"claims", "labels", "descriptions", "aliases", "sitelinks"}
            requested = set(fields) & valid_fields
            keys_to_remove = valid_fields - requested
            for key in keys_to_remove:
                result.pop(key, None)

        return result

    def run_sparql(self, query: str) -> list[dict]:
        """POST SPARQL query, return list of result bindings."""
        data = urllib.parse.urlencode({
            "query": query,
            "format": "json",
        }).encode("utf-8")
        req = urllib.request.Request(self.SPARQL_URL, data=data)
        req.add_header("User-Agent", self.USER_AGENT)
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        req.add_header("Accept", "application/sparql-results+json")
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            print(
                f"Error: SPARQL endpoint returned HTTP {exc.code}: {exc.reason}",
                file=sys.stderr,
            )
            sys.exit(1)
        except urllib.error.URLError as exc:
            print(f"Error: Network error: {exc.reason}", file=sys.stderr)
            sys.exit(1)

        try:
            body = json.loads(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            print(
                f"Error: Failed to parse API response: {exc}", file=sys.stderr
            )
            sys.exit(1)

        bindings = body.get("results", {}).get("bindings", [])
        results = []
        for binding in bindings:
            row = {}
            for var, val in binding.items():
                row[var] = val.get("value", "")
            results.append(row)
        return results


# ---------------------------------------------------------------------------
# Disambiguation scorer
# ---------------------------------------------------------------------------

def compute_overlap_score(context: str, candidate_text: str) -> float:
    """Score a candidate by token overlap between context and candidate text.

    Uses stdlib str.split() and set intersection.
    Returns a float in [0.0, 1.0].
    """
    context_tokens = set(context.lower().split())
    candidate_tokens = set(candidate_text.lower().split())
    if not context_tokens:
        return 0.0
    intersection = context_tokens & candidate_tokens
    return len(intersection) / len(context_tokens)


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_search(args: argparse.Namespace) -> None:
    """Handle the 'search' subcommand."""
    client = WikidataClient()
    results = client.search_entities(
        term=args.term,
        type_filter=args.type,
        limit=args.limit,
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))


def cmd_entity(args: argparse.Namespace) -> None:
    """Handle the 'entity' subcommand."""
    client = WikidataClient()
    fields = None
    if args.fields:
        fields = [f.strip() for f in args.fields.split(",")]
    result = client.get_entity(qid=args.id, lang=args.lang, fields=fields)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_disambiguate(args: argparse.Namespace) -> None:
    """Handle the 'disambiguate' subcommand."""
    client = WikidataClient()
    candidates = client.search_entities(term=args.term, limit=10)
    if not candidates:
        print(
            f'Error: No candidates found for "{args.term}"', file=sys.stderr
        )
        sys.exit(1)

    scored = []
    for c in candidates:
        candidate_text = " ".join([
            c.get("label", ""),
            c.get("description", ""),
            " ".join(c.get("aliases", [])),
        ])
        score = compute_overlap_score(args.context, candidate_text)
        scored.append({
            "qid": c["qid"],
            "label": c["label"],
            "description": c["description"],
            "score": round(score, 4),
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    print(json.dumps(scored, ensure_ascii=False, indent=2))


def cmd_sparql(args: argparse.Namespace) -> None:
    """Handle the 'sparql' subcommand."""
    client = WikidataClient()
    results = client.run_sparql(args.query)

    if args.out:
        # Write CSV
        if not results:
            Path(args.out).write_text("", encoding="utf-8")
            return
        fieldnames = list(results[0].keys())
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
    else:
        print(json.dumps(results, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def cmd_self_test(_args: argparse.Namespace) -> None:
    """Run offline self-tests with mocked HTTP responses."""
    failures: list[str] = []

    # Isolate the HTTP cache so a stale local cache cannot mask mock HTTP.
    cache_env = "D_RESEARCH_HTTP_CACHE_PATH"
    saved_cache = os.environ.pop(cache_env, None)

    # --- Mock infrastructure ---
    mock_responses: dict[str, bytes] = {}
    mock_should_fail: dict[str, int] = {}

    class MockResponse:
        """Minimal mock for urllib response."""

        def __init__(self, data: bytes, code: int = 200):
            self._data = io.BytesIO(data)
            self.code = code
            self.status = code
            self.reason = "OK" if code == 200 else "Not Found"
            self.headers = {"content-type": "application/json"}

        def read(self) -> bytes:
            return self._data.read()

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            pass

    original_urlopen = urllib.request.urlopen

    def mock_urlopen(req, **_kwargs):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        # Check for forced failures
        for pattern, code in mock_should_fail.items():
            if pattern in url:
                raise urllib.error.HTTPError(
                    url, code, "Mocked Error", {}, io.BytesIO(b"")
                )
        # Return mock data
        for pattern, data in mock_responses.items():
            if pattern in url:
                return MockResponse(data)
        # Fallback: check POST data for SPARQL
        if hasattr(req, "data") and req.data:
            for pattern, data in mock_responses.items():
                if pattern in url or "sparql" in pattern.lower():
                    return MockResponse(data)
        raise urllib.error.URLError(f"No mock for URL: {url}")

    # Monkey-patch
    urllib.request.urlopen = mock_urlopen

    try:
        # --- Test 1: search subcommand ---
        mock_responses.clear()
        mock_should_fail.clear()
        mock_responses["wbsearchentities"] = json.dumps({
            "search": [
                {
                    "id": "Q42",
                    "label": "Douglas Adams",
                    "description": "English author and humourist, born 1952, died 2001",
                    "aliases": ["Douglas Noël Adams"],
                },
                {
                    "id": "Q21454969",
                    "label": "Douglas Adams",
                    "description": "American football player",
                    "aliases": [],
                },
            ]
        }).encode("utf-8")

        client = WikidataClient()
        results = client.search_entities("Douglas Adams", limit=5)
        assert len(results) == 2, f"search: expected 2 results, got {len(results)}"
        assert results[0]["qid"] == "Q42", "search: first result qid mismatch"
        assert "label" in results[0], "search: missing label key"
        assert "description" in results[0], "search: missing description key"
        assert "aliases" in results[0], "search: missing aliases key"

        # Test type filter
        filtered = client.search_entities("Douglas Adams", type_filter="person", limit=5)
        assert len(filtered) >= 1, "search type filter: expected at least 1 person"
        for r in filtered:
            desc = r["description"].lower()
            assert any(
                kw in desc
                for kw in ["human", "person", "people", "born", "died"]
            ), f"search type filter: '{r['description']}' doesn't match person"

        # --- Test 2: entity subcommand ---
        mock_responses.clear()
        mock_should_fail.clear()
        mock_responses["wbgetentities"] = json.dumps({
            "entities": {
                "Q42": {
                    "labels": {"en": {"value": "Douglas Adams"}},
                    "descriptions": {
                        "en": {"value": "English author and humourist"}
                    },
                    "aliases": {
                        "en": [{"value": "Douglas Noël Adams"}]
                    },
                    "claims": {
                        "P31": [{
                            "mainsnak": {
                                "datavalue": {
                                    "value": {"id": "Q5"}
                                }
                            }
                        }]
                    },
                    "sitelinks": {
                        "enwiki": {"title": "Douglas Adams"}
                    },
                }
            }
        }).encode("utf-8")

        entity = client.get_entity("Q42", lang="en")
        assert entity["qid"] == "Q42", "entity: qid mismatch"
        assert "labels" in entity, "entity: missing labels"
        assert "descriptions" in entity, "entity: missing descriptions"
        assert "aliases" in entity, "entity: missing aliases"
        assert "claims" in entity, "entity: missing claims"
        assert "sitelinks" in entity, "entity: missing sitelinks"

        # Test field filtering
        entity_filtered = client.get_entity("Q42", lang="en", fields=["labels", "claims"])
        assert "labels" in entity_filtered, "entity fields: missing labels"
        assert "claims" in entity_filtered, "entity fields: missing claims"
        assert "descriptions" not in entity_filtered, "entity fields: descriptions should be filtered"
        assert "aliases" not in entity_filtered, "entity fields: aliases should be filtered"
        assert "sitelinks" not in entity_filtered, "entity fields: sitelinks should be filtered"

        # --- Test 3: disambiguate (scoring + sort) ---
        mock_responses.clear()
        mock_should_fail.clear()
        mock_responses["wbsearchentities"] = json.dumps({
            "search": [
                {
                    "id": "Q42",
                    "label": "Douglas Adams",
                    "description": "English author and humourist who wrote Hitchhiker",
                    "aliases": ["writer"],
                },
                {
                    "id": "Q21454969",
                    "label": "Douglas Adams",
                    "description": "American football player in NFL",
                    "aliases": [],
                },
            ]
        }).encode("utf-8")

        # Build args namespace for disambiguate
        ns = argparse.Namespace(term="Douglas Adams", context="English author Hitchhiker")
        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        cmd_disambiguate(ns)
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        ranked = json.loads(output)
        assert len(ranked) == 2, f"disambiguate: expected 2 results, got {len(ranked)}"
        assert ranked[0]["score"] >= ranked[1]["score"], "disambiguate: not sorted descending"
        assert ranked[0]["qid"] == "Q42", "disambiguate: wrong top result"
        for r in ranked:
            assert "qid" in r, "disambiguate: missing qid"
            assert "label" in r, "disambiguate: missing label"
            assert "description" in r, "disambiguate: missing description"
            assert "score" in r, "disambiguate: missing score"

        # --- Test 4: sparql subcommand ---
        mock_responses.clear()
        mock_should_fail.clear()
        mock_responses["query.wikidata.org"] = json.dumps({
            "results": {
                "bindings": [
                    {
                        "item": {"type": "uri", "value": "http://www.wikidata.org/entity/Q42"},
                        "itemLabel": {"type": "literal", "value": "Douglas Adams"},
                    },
                    {
                        "item": {"type": "uri", "value": "http://www.wikidata.org/entity/Q5"},
                        "itemLabel": {"type": "literal", "value": "human"},
                    },
                ]
            }
        }).encode("utf-8")

        # Test JSON output
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        ns = argparse.Namespace(query="SELECT ?item WHERE {}", out=None)
        cmd_sparql(ns)
        sparql_output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        sparql_results = json.loads(sparql_output)
        assert len(sparql_results) == 2, f"sparql: expected 2 results, got {len(sparql_results)}"
        assert sparql_results[0]["item"] == "http://www.wikidata.org/entity/Q42"
        assert sparql_results[0]["itemLabel"] == "Douglas Adams"

        # Test CSV output
        import tempfile
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        )
        tmp.close()
        tmp_path = tmp.name

        # Re-mock for second sparql call
        mock_responses["query.wikidata.org"] = json.dumps({
            "results": {
                "bindings": [
                    {
                        "item": {"type": "uri", "value": "http://www.wikidata.org/entity/Q42"},
                        "itemLabel": {"type": "literal", "value": "Douglas Adams"},
                    },
                ]
            }
        }).encode("utf-8")

        ns = argparse.Namespace(query="SELECT ?item WHERE {}", out=tmp_path)
        cmd_sparql(ns)

        with open(tmp_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 1, f"sparql csv: expected 1 row, got {len(rows)}"
        assert rows[0]["item"] == "http://www.wikidata.org/entity/Q42"
        assert rows[0]["itemLabel"] == "Douglas Adams"

        # Clean up temp file
        Path(tmp_path).unlink(missing_ok=True)

        # --- Test 5: HTTP error handling ---
        mock_responses.clear()
        mock_should_fail.clear()
        mock_should_fail["wbsearchentities"] = 404

        exit_code = None
        old_stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            client.search_entities("test")
        except SystemExit as e:
            exit_code = e.code
        stderr_output = sys.stderr.getvalue()
        sys.stderr = old_stderr

        assert exit_code == 1, f"error handling: expected exit 1, got {exit_code}"
        assert "HTTP" in stderr_output, "error handling: stderr should mention HTTP"

    except AssertionError as exc:
        failures.append(str(exc))
    except Exception as exc:
        failures.append(f"Unexpected error: {type(exc).__name__}: {exc}")
    finally:
        # Restore original urlopen
        urllib.request.urlopen = original_urlopen
        if saved_cache is not None:
            os.environ[cache_env] = saved_cache

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        sys.exit(1)

    print("wikidata self-test ok")


# ---------------------------------------------------------------------------
# CLI setup
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Build the argparse CLI parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="wikidata.py",
        description="Wikidata entity search, retrieval, disambiguation, and SPARQL queries.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # search
    p_search = subparsers.add_parser("search", help="Search Wikidata entities by term")
    p_search.add_argument("--term", required=True, help="Search term")
    p_search.add_argument(
        "--type",
        choices=["person", "org", "product", "place"],
        default=None,
        help="Filter by entity type",
    )
    p_search.add_argument(
        "--limit", type=int, default=5, help="Max results (default: 5)"
    )
    p_search.set_defaults(func=cmd_search)

    # entity
    p_entity = subparsers.add_parser("entity", help="Retrieve entity details by Q-ID")
    p_entity.add_argument("--id", required=True, help="Wikidata Q-ID (e.g. Q42)")
    p_entity.add_argument(
        "--lang", default="en", help="Language code (default: en)"
    )
    p_entity.add_argument(
        "--fields",
        default=None,
        help="Comma-separated fields: claims,labels,descriptions,aliases,sitelinks",
    )
    p_entity.set_defaults(func=cmd_entity)

    # disambiguate
    p_disamb = subparsers.add_parser(
        "disambiguate", help="Disambiguate a name using context"
    )
    p_disamb.add_argument("--term", required=True, help="Name to disambiguate")
    p_disamb.add_argument(
        "--context", required=True, help="Context for scoring candidates"
    )
    p_disamb.set_defaults(func=cmd_disambiguate)

    # sparql
    p_sparql = subparsers.add_parser("sparql", help="Execute a SPARQL query")
    p_sparql.add_argument("--query", required=True, help="SPARQL SELECT query")
    p_sparql.add_argument(
        "--out", default=None, help="Output CSV file path (default: JSON to stdout)"
    )
    p_sparql.set_defaults(func=cmd_sparql)

    # self-test
    p_test = subparsers.add_parser("self-test", help="Run offline self-tests")
    p_test.set_defaults(func=cmd_self_test)

    return parser


def main() -> None:
    """Entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help(sys.stderr)
        sys.exit(2)

    # Validate --type for search
    if args.command == "search" and args.type:
        valid_types = {"person", "org", "product", "place"}
        if args.type not in valid_types:
            print(
                f'Error: Invalid type "{args.type}". Valid: person, org, product, place',
                file=sys.stderr,
            )
            sys.exit(2)

    args.func(args)


if __name__ == "__main__":
    main()
