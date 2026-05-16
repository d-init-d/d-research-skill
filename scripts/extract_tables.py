#!/usr/bin/env python3
"""Extract HTML ``<table>`` elements into CSV files.

stdlib only: uses :mod:`html.parser` and :mod:`csv`. No external
dependencies, no network access. Reads HTML from a file path or stdin
and writes one CSV per table (named ``<stem>_table<N>.csv`` or to a
user-specified directory).

Handles
-------
* ``<thead>``, ``<tbody>``, ``<tfoot>``, plain ``<tr>``
* ``<th>`` treated as ``<td>`` for cell extraction (but the first row
  of ``<thead>`` becomes the CSV header row)
* ``colspan`` / ``rowspan`` (cells are duplicated to fill the spanned
  range, matching what pandas.read_html / Excel does)
* Nested elements inside a cell (only the visible text content is kept;
  scripts and styles are dropped)

Usage
-----
* ``extract_tables.py --in page.html --out-dir out/``
* ``curl -s URL | extract_tables.py --in - --out-dir out/``
* ``extract_tables.py self-test``
"""
from __future__ import annotations

import argparse
import csv
import sys
from html.parser import HTMLParser
from pathlib import Path


class _TableParser(HTMLParser):
    """Parse a stream of HTML and accumulate normalised tables.

    Output structure: ``tables`` is a list of "table dicts" with keys:

    * ``"header"``: ``list[str]`` (rows inside ``<thead>``, joined and
      flattened; empty when the table has no ``<thead>``)
    * ``"rows"``:   ``list[list[str]]`` (one list per body row, with
      ``colspan`` cells duplicated horizontally and ``rowspan`` cells
      duplicated vertically into the right column position)

    Implementation: the parser tracks the current row as a sparse
    ``dict[col, str]`` so that rowspan-occupied columns from a previous
    row claim their column index before any explicit cell does. At row
    flush time the sparse map is rendered into a dense list using
    ``max(col)+1`` as the row width.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[dict] = []
        self._tbl: dict | None = None
        self._in_thead = False
        self._row_idx = 0
        # Sparse current row: col_idx -> text
        self._cur_row: dict[int, str] | None = None
        self._next_col = 0
        # Pending rowspans: {(row_idx, col_idx): text} for future rows.
        self._rowspans: dict[tuple[int, int], str] = {}
        self._cell_text: list[str] | None = None
        self._cell_colspan = 1
        self._cell_rowspan = 1
        self._drop_depth = 0  # ignore content inside <script>/<style>

    # ---- helpers ----------------------------------------------------

    def _advance_past_rowspans(self) -> None:
        """Move ``_next_col`` past any rowspan-occupied columns and write
        their values into the current row dict."""
        if self._cur_row is None:
            return
        while (self._row_idx, self._next_col) in self._rowspans:
            self._cur_row[self._next_col] = self._rowspans.pop(
                (self._row_idx, self._next_col)
            )
            self._next_col += 1

    def _flush_row(self) -> None:
        if self._cur_row is None:
            return
        # Make sure any trailing rowspan cells past the last explicit td
        # are still picked up.
        while (self._row_idx, self._next_col) in self._rowspans:
            self._cur_row[self._next_col] = self._rowspans.pop(
                (self._row_idx, self._next_col)
            )
            self._next_col += 1
        if self._tbl is not None:
            if self._cur_row:
                width = max(self._cur_row) + 1
                row = [self._cur_row.get(i, "") for i in range(width)]
            else:
                row = []
            if self._in_thead and not self._tbl["header"]:
                # First row of <thead> becomes the header. Subsequent
                # <thead> rows (rare) become body rows.
                self._tbl["header"] = row
            else:
                self._tbl["rows"].append(row)
        self._cur_row = None
        self._next_col = 0
        self._row_idx += 1

    def _flush_table(self) -> None:
        if self._tbl is None:
            return
        if self._cur_row is not None:
            self._flush_row()
        self.tables.append(
            {"header": self._tbl["header"], "rows": self._tbl["rows"]}
        )
        self._tbl = None
        self._in_thead = False
        self._row_idx = 0
        self._rowspans = {}

    # ---- HTMLParser overrides ---------------------------------------

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._drop_depth += 1
            return
        attr_dict = {k: (v or "") for k, v in attrs}
        if tag == "table":
            # Tables nesting inside cells: flush parent first (rare; we
            # don't track full nesting for simplicity).
            if self._tbl is not None:
                self._flush_table()
            self._tbl = {"header": [], "rows": []}
            self._row_idx = 0
            self._in_thead = False
            self._rowspans = {}
            return
        if self._tbl is None:
            return
        if tag == "thead":
            self._in_thead = True
        elif tag in {"tbody", "tfoot"}:
            self._in_thead = False
        elif tag == "tr":
            self._cur_row = {}
            self._next_col = 0
            self._advance_past_rowspans()
        elif tag in {"td", "th"}:
            self._cell_text = []
            try:
                self._cell_colspan = max(
                    1, int(attr_dict.get("colspan", "1") or "1")
                )
            except ValueError:
                self._cell_colspan = 1
            try:
                self._cell_rowspan = max(
                    1, int(attr_dict.get("rowspan", "1") or "1")
                )
            except ValueError:
                self._cell_rowspan = 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            if self._drop_depth > 0:
                self._drop_depth -= 1
            return
        if tag == "table":
            self._flush_table()
            return
        if self._tbl is None:
            return
        if tag == "thead":
            self._in_thead = False
        elif tag == "tr":
            self._flush_row()
        elif tag in {"td", "th"}:
            if self._cell_text is None or self._cur_row is None:
                return
            text = " ".join("".join(self._cell_text).split())
            # Place into the current row, expanding for colspan and
            # scheduling rowspan slots for future rows.
            for _ in range(self._cell_colspan):
                self._advance_past_rowspans()
                self._cur_row[self._next_col] = text
                if self._cell_rowspan > 1:
                    for dr in range(1, self._cell_rowspan):
                        self._rowspans[(self._row_idx + dr, self._next_col)] = text
                self._next_col += 1
            self._cell_text = None
            self._cell_colspan = 1
            self._cell_rowspan = 1

    def handle_data(self, data: str) -> None:
        if self._drop_depth > 0:
            return
        if self._cell_text is not None:
            self._cell_text.append(data)


def parse_html(html: str) -> list[dict]:
    p = _TableParser()
    p.feed(html)
    p.close()
    return p.tables


def write_csv(table: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if table["header"]:
            writer.writerow(table["header"])
        for row in table["rows"]:
            writer.writerow(row)


def cmd_extract(in_path: str, out_dir: Path, stem: str | None) -> int:
    if in_path == "-":
        html = sys.stdin.read()
        stem = stem or "stdin"
    else:
        p = Path(in_path)
        if not p.is_file():
            print(f"error: input file not found: {p}", file=sys.stderr)
            return 1
        html = p.read_text(encoding="utf-8", errors="replace")
        stem = stem or p.stem
    tables = parse_html(html)
    if not tables:
        print("warn: no <table> elements found", file=sys.stderr)
        return 0
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, table in enumerate(tables, start=1):
        path = out_dir / f"{stem}_table{i}.csv"
        write_csv(table, path)
        ncols = len(table["header"]) if table["header"] else (
            len(table["rows"][0]) if table["rows"] else 0
        )
        print(
            f"wrote {path} ({len(table['rows'])} rows, {ncols} cols, "
            f"header: {'yes' if table['header'] else 'no'})"
        )
    return 0


SELF_TEST_HTML = """
<html><body>
<table>
  <thead><tr><th>City</th><th>Country</th><th>Population</th></tr></thead>
  <tbody>
    <tr><td>Hanoi</td><td>Vietnam</td><td>8,053,663</td></tr>
    <tr><td>Bangkok</td><td>Thailand</td><td>10,539,000</td></tr>
  </tbody>
</table>

<table>
  <tr><th colspan="2">Quarterly Revenue</th></tr>
  <tr><th>Quarter</th><th>USD millions</th></tr>
  <tr><td>Q1</td><td>120</td></tr>
  <tr><td>Q2</td><td>135</td></tr>
</table>

<table>
  <tr><th>Region</th><th>Product</th><th>Units</th></tr>
  <tr><td rowspan="2">EMEA</td><td>Widget</td><td>10</td></tr>
  <tr><td>Gadget</td><td>20</td></tr>
  <tr><td>APAC</td><td>Widget</td><td>30</td></tr>
</table>

<p>Not a table; should be ignored.</p>
<script>const x = "<table>fake</table>";</script>
</body></html>
"""


def cmd_self_test() -> int:
    print("extract_tables self-test")
    tables = parse_html(SELF_TEST_HTML)
    assert len(tables) == 3, f"expected 3 tables, got {len(tables)}"
    print("  [PASS] detected 3 tables (script content ignored)")

    t1 = tables[0]
    assert t1["header"] == ["City", "Country", "Population"], (
        f"unexpected header: {t1['header']}"
    )
    assert t1["rows"][0] == ["Hanoi", "Vietnam", "8,053,663"], (
        f"unexpected row: {t1['rows'][0]}"
    )
    assert len(t1["rows"]) == 2
    print("  [PASS] table 1: thead/tbody parsed correctly")

    t2 = tables[1]
    # First row uses colspan=2 -> ["Quarterly Revenue", "Quarterly Revenue"]
    assert t2["rows"][0] == ["Quarterly Revenue", "Quarterly Revenue"], (
        f"colspan not expanded: {t2['rows'][0]}"
    )
    assert t2["rows"][1] == ["Quarter", "USD millions"]
    assert t2["rows"][2] == ["Q1", "120"]
    print("  [PASS] table 2: colspan expanded correctly")

    t3 = tables[2]
    # Rowspan: EMEA spans 2 rows. This table has no <thead>, so the first
    # row of `<th>` cells lands in `rows[0]` rather than `header`. The
    # caller can promote it manually if they prefer.
    assert t3["header"] == [], f"unexpected header (no thead): {t3['header']}"
    assert t3["rows"][0] == ["Region", "Product", "Units"]
    assert t3["rows"][1] == ["EMEA", "Widget", "10"]
    assert t3["rows"][2] == ["EMEA", "Gadget", "20"], (
        f"rowspan not duplicated: {t3['rows'][2]}"
    )
    assert t3["rows"][3] == ["APAC", "Widget", "30"]
    print("  [PASS] table 3: rowspan duplicated correctly")

    # CSV round-trip
    import io
    buf = io.StringIO()
    writer = csv.writer(buf)
    if t1["header"]:
        writer.writerow(t1["header"])
    for row in t1["rows"]:
        writer.writerow(row)
    rt = list(csv.reader(io.StringIO(buf.getvalue())))
    assert rt[0] == ["City", "Country", "Population"]
    assert rt[1] == ["Hanoi", "Vietnam", "8,053,663"]
    print("  [PASS] CSV round-trip preserves values")

    print("\nAll self-tests passed!")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        prog="extract_tables.py",
        description="Extract HTML <table> elements into CSV files.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("extract", help="Extract tables from an HTML file or stdin.")
    e.add_argument(
        "--in",
        dest="input",
        default="-",
        help="Input HTML file path, or '-' for stdin (default: -).",
    )
    e.add_argument(
        "--out-dir",
        type=Path,
        required=True,
        help="Directory to write per-table CSV files into.",
    )
    e.add_argument(
        "--stem",
        default=None,
        help="Filename stem (defaults to input file stem, or 'stdin').",
    )

    sub.add_parser("self-test", help="Run offline self-tests.")

    args = p.parse_args()
    if args.cmd == "extract":
        return cmd_extract(args.input, args.out_dir, args.stem)
    if args.cmd == "self-test":
        return cmd_self_test()
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
