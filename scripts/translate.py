#!/usr/bin/env python3
"""Translation adapter: text translation and language detection.

Subcommands
-----------
* ``text``      - translate text (requires a backend + --allow-remote for remote engines)
* ``detect``    - detect language via stdlib trigram heuristic
* ``instances`` - list known LibreTranslate public instances
* ``self-test`` - run offline self-tests (no network)

Translation backends (all opt-in, all soft-fail):
- LibreTranslate (default remote, requires --allow-remote or D_RESEARCH_ALLOW_REMOTE_TRANSLATION=1)
- DeepL (requires DEEPL_API_KEY + --allow-remote)
- Google Translate (requires GOOGLE_TRANSLATE_API_KEY + --allow-remote)
- Argos Translate (local, pip install argostranslate, no remote opt-in needed)

Privacy: remote translation sends text to third-party servers. Requires
explicit opt-in via --allow-remote flag or D_RESEARCH_ALLOW_REMOTE_TRANSLATION=1.
See references/safety-and-access-policy.md.
"""
from __future__ import annotations

import argparse
import collections
import http.server
import json
import math
import os
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

USER_AGENT = (
    "d-research-skill/0.3.0 "
    "(https://github.com/d-init-d/d-research-skill; contact@example.com)"
)

# Known LibreTranslate public instances (best-effort, may go offline)
LIBRETRANSLATE_INSTANCES = [
    "https://libretranslate.com",
    "https://translate.argosopentech.com",
    "https://translate.terraprint.co",
]

LIBRETRANSLATE_API = LIBRETRANSLATE_INSTANCES[0]


# ---------------------------------------------------------------------------
# Language detection (stdlib trigram heuristic)
# ---------------------------------------------------------------------------

# Trigram frequency profiles for common languages (top 30 trigrams each)
# These are precomputed from representative text samples.
_LANG_PROFILES: dict[str, list[str]] = {
    "en": [" th", "the", "he ", "nd ", " an", "and", "ion", "tio", " of",
           "of ", "ati", "to ", " to", "in ", " in", "on ", "ed ", " co",
           "is ", " is", "re ", "er ", " re", "es ", "ng ", "ing", " fo",
           "for", "ent", "al "],
    "vi": [" nh", "ng ", " tr", " th", "nh ", " ch", " kh", "ông", " ng",
           "các", "ác ", " cá", "ung", " và", "và ", "ong", " đư", "ược",
           "được", "ới ", " gi", "ình", " bị", "ện ", " hi", "iện", "ên ",
           "ất ", " ph"],
    "fr": [" de", "es ", " le", "de ", "le ", "ent", " la", "la ", "ion",
           "on ", " co", "tion", "les", " et", "et ", " qu", "re ", "ons",
           "que", " pa", "ait", " un", "nt ", "ne ", " en", "er ", "it ",
           " pr", "te ", "is "],
    "de": [" de", "en ", "er ", "der", "die", "ie ", " di", "ein", "in ",
           "und", "nd ", " un", "ich", "ch ", " ei", "sch", " da", "den",
           "gen", " ge", "ung", "ine", "eit", "nen", "ter", " in", "ber",
           "ver", " ve", "ren"],
    "es": [" de", "de ", " la", "la ", "os ", " el", "el ", "en ", "ión",
           " en", "es ", "ón ", " co", "aci", "ció", " qu", "que", " lo",
           "las", " se", "los", " un", "nte", "con", "ent", "ado", " pa",
           "ión", "al ", "cia"],
    "ja": ["の ", " の", "した", "って", "ている", "する", "ます", "です",
           "ない", "から", "こと", "ました", "ある", "いる", "れた", "った",
           "ので", "ても", "ては", "として", "まし", "られ", "ない", "なっ",
           "その", "これ", "それ", "ている", "ました", "ません"],
    "zh": ["的 ", " 的", "了 ", " 了", "是 ", " 是", "在 ", " 在", "不 ",
           " 不", "有 ", " 有", "人 ", " 人", "这 ", " 这", "中 ", " 中",
           "大 ", " 大", "为 ", " 为", "上 ", " 上", "个 ", " 个", "国 ",
           " 国", "我 ", " 我"],
    "ru": [" не", " на", "ого", " по", " пр", "ние", " ко", "ть ", " в ",
           "ени", "ост", "ать", " об", "ста", "ова", "ани", "ий ", "ных",
           "ной", "ого", " от", "ель", "ных", "ого", "ать", "ить", "ест",
           "ком", "ные", "ого"],
}


def _trigrams(text: str) -> collections.Counter:
    """Extract trigram frequency counter from text."""
    text = text.lower().strip()
    counter: collections.Counter = collections.Counter()
    for i in range(len(text) - 2):
        counter[text[i:i+3]] += 1
    return counter


def _cosine_sim(a: collections.Counter, b: collections.Counter) -> float:
    """Cosine similarity between two counters."""
    keys = set(a) | set(b)
    if not keys:
        return 0.0
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
    mag_a = math.sqrt(sum(v * v for v in a.values()))
    mag_b = math.sqrt(sum(v * v for v in b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def detect_language(text: str, top_n: int = 3) -> list[dict[str, Any]]:
    """Detect language using trigram cosine similarity.

    Returns top-N candidates with confidence scores.
    """
    if len(text.strip()) < 10:
        return [{"lang": "unknown", "confidence": 0.0}]

    input_trigrams = _trigrams(text)
    scores: list[tuple[str, float]] = []

    for lang, profile_list in _LANG_PROFILES.items():
        profile_counter: collections.Counter = collections.Counter()
        for tri in profile_list:
            profile_counter[tri] = 1  # Binary presence
        sim = _cosine_sim(input_trigrams, profile_counter)
        scores.append((lang, sim))

    scores.sort(key=lambda x: x[1], reverse=True)
    results = []
    for lang, score in scores[:top_n]:
        results.append({"lang": lang, "confidence": round(score, 4)})
    return results


# ---------------------------------------------------------------------------
# Translation backends
# ---------------------------------------------------------------------------


def _translate_libretranslate(
    text: str, source: str, target: str, api_url: str = LIBRETRANSLATE_API
) -> str:
    """Translate via LibreTranslate API."""
    data = json.dumps({
        "q": text,
        "source": source if source != "auto" else "auto",
        "target": target,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{api_url}/translate",
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            return result.get("translatedText", "")
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as e:
        print(f"error: LibreTranslate request failed: {e}", file=sys.stderr)
        return ""


def _is_remote_allowed() -> bool:
    """Check if remote translation is explicitly allowed."""
    return os.environ.get("D_RESEARCH_ALLOW_REMOTE_TRANSLATION", "").strip() in ("1", "true", "yes")


def _translate_deepl(text: str, source: str, target: str) -> str:
    """Translate via DeepL API. Requires DEEPL_API_KEY."""
    key = os.environ.get("DEEPL_API_KEY", "")
    if not key:
        print("error: DEEPL_API_KEY env var not set", file=sys.stderr)
        return ""
    data = json.dumps({"text": [text], "source_lang": source.upper(), "target_lang": target.upper()}).encode()
    req = urllib.request.Request(
        "https://api-free.deepl.com/v2/translate",
        data=data,
        headers={"Authorization": f"DeepL-Auth-Key {key}", "Content-Type": "application/json", "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            translations = result.get("translations", [])
            return translations[0]["text"] if translations else ""
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, IndexError, KeyError) as e:
        print(f"error: DeepL request failed: {e}", file=sys.stderr)
        return ""


def _translate_google(text: str, source: str, target: str) -> str:
    """Translate via Google Translate API. Requires GOOGLE_TRANSLATE_API_KEY."""
    key = os.environ.get("GOOGLE_TRANSLATE_API_KEY", "")
    if not key:
        print("error: GOOGLE_TRANSLATE_API_KEY env var not set", file=sys.stderr)
        return ""
    params = urllib.parse.urlencode({"q": text, "source": source, "target": target, "key": key})
    url = f"https://translation.googleapis.com/language/translate/v2?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            translations = result.get("data", {}).get("translations", [])
            return translations[0]["translatedText"] if translations else ""
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, IndexError, KeyError) as e:
        print(f"error: Google Translate request failed: {e}", file=sys.stderr)
        return ""


def _translate_argos(text: str, source: str, target: str) -> str:
    """Translate via Argos Translate (local). Requires pip install argostranslate."""
    try:
        import argostranslate.translate  # type: ignore[import-not-found]
    except ImportError:
        print(
            "error: argostranslate is not installed.\n"
            "  Install: pip install argostranslate\n"
            "  Then download language packs: argos-translate --from en --to vi",
            file=sys.stderr,
        )
        return ""
    try:
        translated = argostranslate.translate.translate(text, source, target)
        return translated or ""
    except Exception as e:
        print(f"error: Argos Translate failed: {e}", file=sys.stderr)
        return ""


def translate_text(
    text: str, source: str = "auto", target: str = "en",
    engine: str = "libretranslate"
) -> str:
    """Translate text using the specified engine."""
    if engine == "libretranslate":
        return _translate_libretranslate(text, source, target)
    if engine == "deepl":
        return _translate_deepl(text, source, target)
    if engine == "google":
        return _translate_google(text, source, target)
    if engine == "argos":
        return _translate_argos(text, source, target)
    print(f"error: unsupported engine: {engine}", file=sys.stderr)
    return ""


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_text(args: argparse.Namespace) -> int:
    """Translate text from stdin or file."""
    if args.input:
        text = Path(args.input).read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()

    if not text.strip():
        print("error: no input text", file=sys.stderr)
        return 1

    source = getattr(args, "from_lang", "auto") or "auto"
    target = args.to
    engine = getattr(args, "engine", "libretranslate")
    allow_remote = getattr(args, "allow_remote", False)

    # Remote engines require explicit opt-in
    remote_engines = {"libretranslate", "deepl", "google"}
    if engine in remote_engines and not allow_remote and not _is_remote_allowed():
        print(
            f"error: engine '{engine}' sends text to a remote server.\n"
            "  This requires explicit opt-in for privacy reasons.\n"
            "  Add --allow-remote flag, or set D_RESEARCH_ALLOW_REMOTE_TRANSLATION=1\n"
            "  See references/safety-and-access-policy.md for details.",
            file=sys.stderr,
        )
        return 1

    result = translate_text(text, source, target, engine)
    if not result:
        return 1

    if args.out:
        Path(args.out).write_text(result, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(result)
    return 0


def cmd_detect(args: argparse.Namespace) -> int:
    """Detect language of input text."""
    if args.input:
        text = Path(args.input).read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()

    if not text.strip():
        print("error: no input text", file=sys.stderr)
        return 1

    results = detect_language(text, top_n=3)
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


def cmd_instances(_args: argparse.Namespace) -> int:
    """List known LibreTranslate public instances."""
    print("Known LibreTranslate public instances (best-effort, may be offline):")
    for inst in LIBRETRANSLATE_INSTANCES:
        print(f"  {inst}")
    print("\nDefault: " + LIBRETRANSLATE_API)
    print("\nNote: Public instances may have rate limits or be temporarily unavailable.")
    return 0


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


class _MockTranslateHandler(http.server.BaseHTTPRequestHandler):
    """Mock LibreTranslate server for self-test."""

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass

    def do_POST(self) -> None:  # noqa: N802
        content_length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(content_length) if content_length > 0 else b""
        try:
            data = json.loads(body) if body else {}
            q = data.get("q", "")
            target = data.get("target", "en")
            translated = f"[{target}] {q}"
            response = json.dumps({"translatedText": translated}).encode("utf-8")
            self._respond(200, response, "application/json")
        except (json.JSONDecodeError, KeyError, ValueError):
            self._respond(400, b'{"error": "bad request"}', "application/json")

    def _respond(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def cmd_self_test(_args: argparse.Namespace) -> int:
    """Offline self-test with mock translation server."""
    global LIBRETRANSLATE_API  # noqa: PLW0603
    orig_api = LIBRETRANSLATE_API

    errors: list[str] = []

    # Test 1: Language detection — English
    en_text = "The quick brown fox jumps over the lazy dog and the cat sleeps on the mat"
    results = detect_language(en_text)
    if not results or results[0]["lang"] != "en":
        errors.append(f"detect English failed: got {results}")

    # Test 2: Language detection — Vietnamese
    vi_text = "Việt Nam là một quốc gia nằm ở phía đông bán đảo Đông Dương thuộc khu vực Đông Nam Á"
    results = detect_language(vi_text)
    if not results or results[0]["lang"] != "vi":
        errors.append(f"detect Vietnamese failed: got {results}")

    # Test 3: Language detection — short text returns unknown
    results = detect_language("hi")
    if not results or results[0]["lang"] != "unknown":
        errors.append(f"detect short text should return unknown: got {results}")

    # Test 4: detect returns top-3
    results = detect_language(en_text, top_n=3)
    if len(results) != 3:
        errors.append(f"detect should return 3 candidates: got {len(results)}")

    # Test 5: Mock translation via local server (with --allow-remote)
    server = http.server.HTTPServer(("127.0.0.1", 0), _MockTranslateHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        LIBRETRANSLATE_API = f"http://127.0.0.1:{port}"
        # With allow-remote, translation should succeed
        os.environ["D_RESEARCH_ALLOW_REMOTE_TRANSLATION"] = "1"
        result = _translate_libretranslate("Hello world", "en", "vi", LIBRETRANSLATE_API)
        if "[vi] Hello world" not in result:
            errors.append(f"mock translation failed: got {result!r}")
        del os.environ["D_RESEARCH_ALLOW_REMOTE_TRANSLATION"]
    finally:
        LIBRETRANSLATE_API = orig_api
        server.shutdown()

    # Test 6: Remote without opt-in should be blocked by cmd_text
    import io as _io
    import tempfile as _tf
    with _tf.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write("Test text for translation")
        tmp_input = f.name
    try:
        # Ensure env var is NOT set
        os.environ.pop("D_RESEARCH_ALLOW_REMOTE_TRANSLATION", None)
        text_ns = argparse.Namespace(
            input=tmp_input, from_lang="en", to="vi",
            engine="libretranslate", allow_remote=False, out=None,
        )
        old_stderr = sys.stderr
        sys.stderr = _io.StringIO()
        rc = cmd_text(text_ns)
        sys.stderr = old_stderr
        if rc == 0:
            errors.append("cmd_text should fail without --allow-remote for remote engine")
    finally:
        Path(tmp_input).unlink(missing_ok=True)

    # Test 7: instances list
    if not LIBRETRANSLATE_INSTANCES:
        errors.append("LIBRETRANSLATE_INSTANCES is empty")

    if errors:
        print("translate self-test FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print("translate self-test ok")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    p = argparse.ArgumentParser(
        prog="translate.py",
        description="Translation adapter with language detection.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    text_p = sub.add_parser("text", help="Translate text.")
    text_p.add_argument("--in", dest="input", default=None, help="Input text file (or stdin).")
    text_p.add_argument("--from", dest="from_lang", default="auto", help="Source language.")
    text_p.add_argument("--to", required=True, help="Target language.")
    text_p.add_argument("--engine", default="libretranslate",
                        choices=["libretranslate", "deepl", "google", "argos"])
    text_p.add_argument("--allow-remote", action="store_true", default=False,
                        help="Explicitly allow sending text to remote translation services.")
    text_p.add_argument("--out", default=None, help="Output file.")

    detect_p = sub.add_parser("detect", help="Detect language.")
    detect_p.add_argument("--in", dest="input", default=None, help="Input text file (or stdin).")

    sub.add_parser("instances", help="List LibreTranslate instances.")
    sub.add_parser("self-test", help="Run offline self-tests.")

    args = p.parse_args()
    if args.cmd == "text":
        return cmd_text(args)
    if args.cmd == "detect":
        return cmd_detect(args)
    if args.cmd == "instances":
        return cmd_instances(args)
    if args.cmd == "self-test":
        return cmd_self_test(args)
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
