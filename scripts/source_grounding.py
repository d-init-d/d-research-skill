"""Conservative literal grounding with sentence-local source context.

This is a text checker, not an entailment model. Ambiguous attribution and
paraphrases require independent semantic review; a matching quote alone is not
proof that the source asserts it. Decisions never use candidate grading fields.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import tempfile
import unicodedata
from pathlib import Path
from typing import Any, NamedTuple


class Grounding(NamedTuple):
    status: str
    reason: str
    excerpt: str


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    text = text.translate(str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"}))
    return re.sub(r"\s+", " ", text).strip()


def _sentences(text: str) -> list[str]:
    # Retain colons and closing quotes. Carry quotation context over sentence
    # boundaries so the middle of a quoted passage cannot become an assertion.
    parts = re.split(r'(?<=[.!?])\s+|(?<=[.!?]["\'])\s+|[\r\n]+', text)
    sentences = []
    quoted = False
    for part in parts:
        sentence = part.strip()
        if not sentence:
            continue
        sentences.append(('"' if quoted else '') + sentence)
        if sentence.count('"') % 2:
            quoted = not quoted
    return sentences


def _polarity(text: str) -> tuple[str, bool] | None:
    """Compare literal propositions differing only by an explicit negator."""
    contractions = {"isn't": "is not", "aren't": "are not", "wasn't": "was not",
                    "weren't": "were not", "cannot": "can not", "can't": "can not",
                    "won't": "will not", "hasn't": "has not", "haven't": "have not"}
    for short, full in contractions.items():
        text = re.sub(r"\b" + re.escape(short) + r"\b", full, text)
    if re.search(r"\bnot only\b|\bkhông chỉ\b|\bkhông những\b", text):
        return None
    negators = list(re.finditer(r"\b(?:not|never|không phải|không|chưa|chẳng)\b", text))
    if len(negators) > 1:
        return None
    if not negators:
        return text, False
    match = negators[0]
    return normalize(text[:match.start()] + " " + text[match.end():]), True


def assess_source_context(source: str, statement: str) -> Grounding:
    """Return literal support, contradiction, or an explicit review route.

    No arbitrary character window: an unrelated entity in an adjacent sentence
    cannot negate a claim. Normalization precedes both locating and interpreting
    spans, preventing whitespace and Unicode from bypassing context checks.
    """
    claim = normalize(re.sub(r"\[C\d+\]", "", statement)).strip(' .!?"\'')
    if not claim:
        return Grounding("requires_review", "empty_claim", "")
    if normalize(statement).rstrip('"\'').endswith("?"):
        return Grounding("requires_review", "claim_is_a_question", "")
    pattern = re.compile(r"(?<!\w)" + re.escape(claim) + r"(?!\w)")
    decisions: list[Grounding] = []
    sentences = _sentences(normalize(source))
    for index, sentence in enumerate(sentences):
        for match in pattern.finditer(sentence):
            prefix = sentence[:match.start()].strip(' \"\'')
            suffix = sentence[match.end():].strip(' .!?\"\'')
            context = prefix + " " + suffix
            previous = sentences[index-1] if index else ""
            following = sentences[index+1] if index+1 < len(sentences) else ""
            if sentence.rstrip('"\'').endswith("?"):
                decisions.append(Grounding("requires_review", "source_asks_rather_than_asserts", sentence))
                continue
            if re.search(r"\b(?:following|next) (?:statement|claim|assertion)\b", previous):
                context += " " + previous
            if re.match(r"(?:this|that|the preceding|the previous) (?:statement|claim|assertion)\b", following):
                context += " " + following
            if re.match(r"(?:this|that|it) (?:is|was|has been)\b|(?:điều (?:này|đó)|đây) (?:là|không)\b", following):
                context += " " + following
            if re.search(r"\b(?:false|myth|untrue|incorrect|debunked|refuted|disproved|misleading)\b|không đúng|\bsai\b|bác bỏ", context):
                # Negated metalinguistic claims need a reader, not a second regex inference.
                if re.search(r"\b(?:not|isn't|wasn't)\s+(?:false|incorrect|a myth)\b", context):
                    decisions.append(Grounding("requires_review", "ambiguous_source_context", sentence))
                else:
                    decisions.append(Grounding("contradicts", "source_context_refutes_claim", sentence))
            elif prefix and not suffix and re.fullmatch(r"[\w .-]+\b(?:confirmed|verified|documented|validated)(?: that)?", prefix) and not re.search(r"\b(?:not|never|no|if|whether|allegedly)\b", prefix):
                decisions.append(Grounding("supports", "literal_source_assertion", sentence))
            elif prefix or suffix:
                decisions.append(Grounding("requires_review", "attributed_or_qualified_source_span", sentence))
            elif sentence.strip().startswith(('"', "'")):
                decisions.append(Grounding("requires_review", "unattributed_source_quote", sentence))
            else:
                decisions.append(Grounding("supports", "literal_source_assertion", sentence))
    # Only an asserted same-proposition negation is a conflict. Quoted negatives
    # and questions do not become factual counter-evidence through punctuation stripping.
    polarity = _polarity(claim)
    if polarity is not None:
        for sentence in sentences:
            proposition = re.sub(r"^(?:however|in fact|actually|tuy nhiên|thực tế)[,:]?\s+", "", sentence)
            if proposition.startswith(('"', "'")) or proposition.rstrip('"\'').endswith("?"):
                continue
            other = _polarity(proposition.strip(' .!'))
            if other is not None and other[0] == polarity[0] and other[1] != polarity[1]:
                decisions.append(Grounding("contradicts", "same_entity_opposite_assertion", sentence))
    statuses = {d.status for d in decisions}
    if "contradicts" in statuses:
        return next(d for d in decisions if d.status == "contradicts")
    if "requires_review" in statuses:
        return next(d for d in decisions if d.status == "requires_review")
    if decisions:
        return decisions[0]
    return Grounding("requires_review", "semantic_paraphrase_requires_review", "")


def detect_context_refutation(source: str, quote: str, statement: str) -> tuple[bool, str]:
    result = assess_source_context(source, statement or quote)
    return result.status == "contradicts", result.reason if result.status == "contradicts" else ""


_GROUNDING_STOPWORDS = frozenset({
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
    "have", "has", "had", "not", "but", "into", "about", "more", "than", "when",
    "của", "và", "các", "những", "trong", "cho", "với", "được", "không", "một",
    "này", "khi", "như", "từ", "về", "để", "tại", "theo", "trên", "là", "có",
})


def _content_tokens(text: str) -> set[str]:
    norm = normalize(text)
    return {
        tok
        for tok in re.findall(r"[^\W_]{2,}", norm, flags=re.UNICODE)
        if tok not in _GROUNDING_STOPWORDS and not tok.isdigit()
    }


def _numeric_tokens(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:[.,:/-]\d+)*%?", normalize(text)))


def _has_negator(text: str) -> bool:
    return bool(re.search(r"\b(?:not|never|no|false|incorrect|không|chưa|chẳng|sai|bác bỏ)\b", normalize(text)))


def assess_paraphrase_grounding(source: str, statement: str) -> dict[str, Any]:
    """Evaluate literal or paraphrase grounding with exact numeric and polarity consistency."""
    base = assess_source_context(source, statement)
    if base.status == "supports":
        return {
            "status": "literal_supported",
            "reason": base.reason,
            "excerpt": base.excerpt,
            "token_overlap": 1.0,
            "numeric_match": True,
        }
    if base.status == "contradicts":
        return {
            "status": "contradicted",
            "reason": base.reason,
            "excerpt": base.excerpt,
            "token_overlap": 0.0,
            "numeric_match": False,
        }
    if base.reason != "semantic_paraphrase_requires_review":
        return {
            "status": "ungrounded_requires_review",
            "reason": base.reason,
            "excerpt": base.excerpt,
            "token_overlap": 0.0,
            "numeric_match": True,
        }

    claim_clean = re.sub(r"\[C\d+\]", "", statement)
    claim_tokens = _content_tokens(claim_clean)
    claim_nums = _numeric_tokens(claim_clean)
    claim_neg = _has_negator(claim_clean)
    if not claim_tokens and not claim_nums:
        return {
            "status": "ungrounded_requires_review",
            "reason": "empty_content_tokens",
            "excerpt": "",
            "token_overlap": 0.0,
            "numeric_match": False,
        }

    best_overlap = 0.0
    best_sentence = ""
    best_nums: set[str] = set()
    for sentence in _sentences(source):
        if sentence.strip().startswith(('"', "'")) or sentence.strip().endswith("?"):
            continue
        sent_tokens = _content_tokens(sentence)
        overlap = len(claim_tokens & sent_tokens) / max(1, len(claim_tokens))
        if overlap > best_overlap:
            best_overlap = overlap
            best_sentence = sentence
            best_nums = _numeric_tokens(sentence)

    if best_overlap >= 0.5:
        sent_neg = _has_negator(best_sentence)
        numeric_ok = claim_nums <= best_nums
        if sent_neg != claim_neg:
            return {
                "status": "contradicted",
                "reason": "paraphrase_polarity_mismatch",
                "excerpt": best_sentence,
                "token_overlap": round(best_overlap, 4),
                "numeric_match": numeric_ok,
            }
        if claim_nums and not numeric_ok and best_nums:
            return {
                "status": "contradicted",
                "reason": "numeric_mismatch_in_matching_context",
                "excerpt": best_sentence,
                "token_overlap": round(best_overlap, 4),
                "numeric_match": False,
            }
        if best_overlap >= 0.6 and numeric_ok:
            return {
                "status": "paraphrase_supported",
                "reason": "token_and_numeric_paraphrase_overlap",
                "excerpt": best_sentence,
                "token_overlap": round(best_overlap, 4),
                "numeric_match": True,
            }

    return {
        "status": "ungrounded_requires_review",
        "reason": "insufficient_paraphrase_support",
        "excerpt": best_sentence,
        "token_overlap": round(best_overlap, 4),
        "numeric_match": claim_nums <= best_nums if best_sentence else False,
    }


def audit_ledger_grounding(ledger_path: Path, workspace_dir: Path | None = None) -> dict[str, Any]:
    """Audit claim rows in an evidence-ledger CSV against captured text or row evidence."""
    capture_texts: dict[str, str] = {}
    if workspace_dir:
        for cap_name in ("capture-records.json", "research-output/capture-records.json"):
            cap_file = workspace_dir / cap_name
            if cap_file.is_file():
                raw = json.loads(cap_file.read_text(encoding="utf-8"))
                items = raw if isinstance(raw, list) else (raw.get("records") or raw.get("captures") or [])
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    url = str(item.get("final_url") or item.get("source_url") or "").strip()
                    ref = str(item.get("raw_text_ref") or "").strip()
                    if url and ref:
                        text_path = (workspace_dir / ref) if not Path(ref).is_absolute() else Path(ref)
                        if text_path.is_file():
                            capture_texts[url] = text_path.read_text(encoding="utf-8", errors="replace")

    with ledger_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    findings: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for row in rows:
        if (row.get("record_type") or "").strip().lower() not in {"", "claim"}:
            continue
        claim_id = (row.get("claim_id") or "").strip()
        claim_text = (row.get("claim") or "").strip()
        if not claim_id or not claim_text:
            continue
        src_url = (row.get("source_url") or "").strip()
        source_body = capture_texts.get(src_url) or " ".join(
            part for part in ((row.get("quote_or_anchor") or "").strip(), (row.get("evidence") or "").strip()) if part
        )
        assessment = assess_paraphrase_grounding(source_body, claim_text)
        status = assessment["status"]
        counts[status] = counts.get(status, 0) + 1
        findings.append({"claim_id": claim_id, **assessment})

    return {
        "total_claims": len(findings),
        "counts": counts,
        "findings": findings,
    }


def _cmd_self_test() -> int:
    assert assess_source_context("The server is secure.", "The server is secure.").status == "supports"
    assert assess_source_context("The server is secure. The server is not secure.", "The server is secure.").status == "contradicts"

    para_ok = assess_paraphrase_grounding(
        "In September 2026, the Federal Reserve raised the policy rate by 25 bps to curb inflation.",
        "Federal Reserve raised policy rate 25 bps in 2026",
    )
    assert para_ok["status"] == "paraphrase_supported", para_ok

    para_num_bad = assess_paraphrase_grounding(
        "In September 2026, the Federal Reserve raised the policy rate by 25 bps to curb inflation.",
        "Federal Reserve raised policy rate 50 bps in 2026",
    )
    assert para_num_bad["status"] == "contradicted", para_num_bad

    with tempfile.TemporaryDirectory() as tmp:
        ledger = Path(tmp) / "ledger.csv"
        ledger.write_text(
            "claim_id,claim,evidence,quote_or_anchor,record_type,source_url\n"
            "C1,OpenAlex returns up to 200 works per page,OpenAlex API returns up to 200 works per page each request,,claim,https://docs.openalex.org\n",
            encoding="utf-8",
        )
        audit = audit_ledger_grounding(ledger)
        assert audit["total_claims"] == 1 and audit["counts"].get("paraphrase_supported") == 1, audit

    print("source_grounding self-test ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DRS-1.1 Literal and Paraphrase Source Grounding Verifier")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_chk = sub.add_parser("check", help="Check a claim against a source text file")
    p_chk.add_argument("--source-file", required=True, help="Path to source text file")
    p_chk.add_argument("--claim", required=True, help="Claim text to verify")

    p_aud = sub.add_parser("audit-ledger", help="Audit claims in an evidence-ledger CSV")
    p_aud.add_argument("--ledger", required=True, help="Path to evidence-ledger.csv")
    p_aud.add_argument("--workspace", default="", help="Optional workspace directory with capture-records.json")
    p_aud.add_argument("--out", default="", help="Optional JSON output path")

    sub.add_parser("self-test", help="Run offline source_grounding self-tests")

    args = parser.parse_args(argv)
    if args.cmd == "self-test":
        return _cmd_self_test()
    if args.cmd == "check":
        src = Path(args.source_file).read_text(encoding="utf-8", errors="replace")
        print(json.dumps(assess_paraphrase_grounding(src, args.claim), indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "audit-ledger":
        ws = Path(args.workspace) if args.workspace else None
        payload = audit_ledger_grounding(Path(args.ledger), workspace_dir=ws)
        rendered = json.dumps(payload, indent=2, ensure_ascii=False)
        if args.out:
            Path(args.out).write_text(rendered + "\n", encoding="utf-8")
            print(f"wrote {args.out}")
        else:
            print(rendered)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
