# Social platform capability reporting

Report capability per operation and per observed run. Do not turn a payload
parser, a local fixture, an oEmbed metadata response, or a generic browser
operator into a claim that a live platform is fully supported.

Use these labels:

| Label | Meaning |
|---|---|
| `fixture_verified` | Parser or browser workflow passed against packaged deterministic fixtures. |
| `live_verified` | The named operation succeeded against the live public platform in the current dated run and produced activity/capture evidence. |
| `unverified_live` | Code or a recipe exists, but no valid live evidence is attached to the current result. |
| `blocked_auth_required` | The tested public path required authentication; use only a user-authorized lawful session and remain read-only. |
| `blocked` | A lawful bounded attempt failed; record the blocker and fallback result. |

Track these operations independently: discovery, original-item read, nested
replies, pagination/load-more, corrections/edits, transcript/captions, comments,
and authenticated read. One successful operation does not imply the others.

`scripts/social_adapters.py capabilities` reports packaged parser/fixture state.
It deliberately leaves `live_verified` empty. A research run may add live proof
only through its own activity logs and hash-bound capture records.
