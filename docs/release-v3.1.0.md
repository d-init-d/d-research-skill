# Release Consistency and Documentation Polish

v3.1.0 Release Notes

D Research v3.1.0 is a product-polish release for the public documentation and
release surface around the register/jargon upgrade. It does not change the
runtime workflow shipped in v3.0.5 and v3.0.6; it makes the release artifacts,
eval documentation, and reference cross-links consistent enough to ship as a
commercial-quality skill package.

## What's New

- Release notes now follow a consistent product format: a concise title followed
  by a `vX.Y.Z Release Notes` subtitle. The v3.0.5 and v3.0.6 release-note
  artifacts were updated to match the public release style used by earlier
  releases.
- `docs/eval.md` now correctly documents frontier bench 2.2 as **52 tasks across
  26 classes**, including the `register-jargon-recall` class added in v3.0.6.
- `references/frontier-search.md` no longer repeats the same
  `references/register-and-jargon-expansion.md` See also entry twice.
- `README.md` and `README.vi.md` now summarize the v3.0.5, v3.0.6, and v3.1.0
  release sequence so users can see how the register/jargon work moved from
  method, to tool and bench, to release polish.

## Why It Matters

The register/jargon upgrade is already functional and tested, but product-grade
skill packages also need clean release surfaces. Users should see the same naming
pattern across GitHub releases, release-note artifacts, README summaries, and eval
documentation. v3.1.0 removes the last small inconsistencies so the repository is
ready to ship, review, and install without caveats.

## Compatibility

- No runtime behavior changes.
- No new dependencies.
- No evidence-ledger schema changes.
- No script CLI changes.
- Existing v3.0.x workspaces, ledgers, reports, eval fixtures, and release tags
  remain valid.

## Upgrade Notes

Pull the new release for a cleaner public documentation surface. If you already
installed v3.0.6, no workflow migration is required; v3.1.0 preserves the same
register/jargon recall behavior and only polishes documentation, metadata, and
release consistency.
