# Source grounding boundary

Strict rendering checks the snapshot bytes and the context of the cited
assertion. The shared `scripts/source_grounding.py` checker normalizes Unicode
and whitespace before locating text, retains attribution around colons/quotes,
and limits negation comparisons to the same proposition. Negation concerning a
different entity does not refute the cited statement.

A literal source assertion can pass automated support checks. A myth, refuted
quote, conditional statement or ambiguous attribution cannot become a verified
fact merely because its words occur in the snapshot. Paraphrases and unresolved
context enter `requires_review`; retain the source and explain the unresolved
support instead of inventing an adjudication receipt. This deterministic checker
does not establish the real-world truth of a source or replace semantic review.

Candidate ledger fields never supply grading oracles. Explicit evaluator oracle
arguments are for trusted evaluation calls only. They are not a route for a
candidate to sign its own report.
