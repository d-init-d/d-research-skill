#!/usr/bin/env python3
"""Generate a minimal valid PDF test fixture for pdf_extract.py self-test.

This script creates a PDF with:
- Title metadata: "Test Document"
- Author metadata: "d-research-skill"
- One page with a sample text paragraph
- One simple 2x2 table

The output is written to examples/fixtures/test.pdf and must be <= 10 KB.
"""

import sys
from pathlib import Path


def build_pdf() -> bytes:
    """Build a minimal valid PDF with metadata, text, and a table."""
    # We'll construct the PDF manually using raw PDF operators.
    # PDF structure: header, body (objects), xref table, trailer.

    objects = []  # list of (obj_number, bytes)

    # Object 1: Catalog
    objects.append((1, b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"))

    # Object 2: Pages
    objects.append((2, b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"))

    # Object 3: Page
    objects.append((3, (
        b"3 0 obj\n"
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]\n"
        b"   /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\n"
        b"endobj\n"
    )))

    # Object 4: Page content stream (text paragraph + table)
    content = (
        # Text paragraph
        b"BT\n"
        b"/F1 12 Tf\n"
        b"72 720 Td\n"
        b"(This is a sample text paragraph for testing PDF text extraction.) Tj\n"
        b"0 -18 Td\n"
        b"(The d-research-skill project uses this fixture to validate that) Tj\n"
        b"0 -18 Td\n"
        b"(pdftotext and pdfinfo can correctly process PDF documents.) Tj\n"
        b"ET\n"
        # Table: draw a 2x2 table with lines and text
        # Table position: x=72, y=550, cell width=150, cell height=25
        b"% Table border lines\n"
        b"0.5 w\n"
        # Outer border
        b"72 550 m 372 550 l S\n"
        b"72 525 m 372 525 l S\n"
        b"72 500 m 372 500 l S\n"
        b"72 475 m 372 475 l S\n"
        # Vertical lines
        b"72 550 m 72 475 l S\n"
        b"222 550 m 222 475 l S\n"
        b"372 550 m 372 475 l S\n"
        # Table cell text
        b"BT\n"
        b"/F1 10 Tf\n"
        b"80 532 Td (Header A) Tj\n"
        b"150 0 Td (Header B) Tj\n"
        b"-150 -25 Td (Cell 1) Tj\n"
        b"150 0 Td (Cell 2) Tj\n"
        b"ET\n"
    )

    stream_obj = (
        b"4 0 obj\n"
        b"<< /Length " + str(len(content)).encode() + b" >>\n"
        b"stream\n" + content + b"\nendstream\n"
        b"endobj\n"
    )
    objects.append((4, stream_obj))

    # Object 5: Font (Helvetica - standard PDF font, no embedding needed)
    objects.append((5, (
        b"5 0 obj\n"
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\n"
        b"endobj\n"
    )))

    # Object 6: Info dictionary (metadata)
    objects.append((6, (
        b"6 0 obj\n"
        b"<< /Title (Test Document) /Author (d-research-skill)\n"
        b"   /CreationDate (D:20240101120000+00'00')\n"
        b"   /ModDate (D:20240101120000+00'00')\n"
        b"   /Producer (d-research-skill test fixture generator) >>\n"
        b"endobj\n"
    )))

    # Assemble PDF
    pdf = bytearray()
    pdf.extend(b"%PDF-1.4\n")
    # Binary comment to mark as binary (per PDF spec recommendation)
    pdf.extend(b"%\xe2\xe3\xcf\xd3\n")

    # Write objects and record offsets
    offsets = {}
    for obj_num, obj_data in objects:
        offsets[obj_num] = len(pdf)
        pdf.extend(obj_data)

    # Cross-reference table
    xref_offset = len(pdf)
    pdf.extend(b"xref\n")
    pdf.extend(f"0 {len(objects) + 1}\n".encode())
    pdf.extend(b"0000000000 65535 f \n")
    for obj_num in range(1, len(objects) + 1):
        pdf.extend(f"{offsets[obj_num]:010d} 00000 n \n".encode())

    # Trailer
    pdf.extend(b"trailer\n")
    pdf.extend(f"<< /Size {len(objects) + 1} /Root 1 0 R /Info 6 0 R >>\n".encode())
    pdf.extend(b"startxref\n")
    pdf.extend(f"{xref_offset}\n".encode())
    pdf.extend(b"%%EOF\n")

    return bytes(pdf)


def main():
    repo_root = Path(__file__).resolve().parent.parent
    output_dir = repo_root / "examples" / "fixtures"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "test.pdf"

    pdf_bytes = build_pdf()

    # Verify size constraint
    size_kb = len(pdf_bytes) / 1024
    if size_kb > 10:
        print(f"error: generated PDF is {size_kb:.1f} KB, exceeds 10 KB limit", file=sys.stderr)
        sys.exit(1)

    output_path.write_bytes(pdf_bytes)
    print(f"Created {output_path} ({len(pdf_bytes)} bytes, {size_kb:.2f} KB)")


if __name__ == "__main__":
    main()
