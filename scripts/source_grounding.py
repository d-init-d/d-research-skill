"""Conservative literal grounding with sentence-local source context.

This is a text checker, not an entailment model. Ambiguous attribution and
paraphrases require independent semantic review; a matching quote alone is not
proof that the source asserts it. Decisions never use candidate grading fields.
"""
from __future__ import annotations

import re
import unicodedata
from typing import NamedTuple


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
