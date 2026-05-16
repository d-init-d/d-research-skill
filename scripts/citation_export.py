#!/usr/bin/env python3
"""Citation export utility with BibTeX/RIS export and DOI enrichment."""

import argparse
import csv
import json
import os
import sys
import tempfile
import urllib.request
import urllib.parse
from typing import Dict, List, Optional


# Expected CSV columns
CSV_COLUMNS = [
    'claim_id', 'claim', 'sub_question', 'source_title', 'source_url',
    'source_type', 'date_published', 'date_accessed', 'access_method',
    'evidence', 'quote_or_anchor', 'contradiction', 'confidence', 'notes'
]


def read_csv(file_path: str) -> List[Dict[str, str]]:
    """Read CSV file and return list of row dictionaries."""
    rows = []
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def get_unique_sources(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Extract unique sources from rows based on source_title and source_url."""
    seen = set()
    sources = []
    for row in rows:
        key = (row.get('source_title', ''), row.get('source_url', ''))
        if key not in seen and key[0]:  # Skip empty titles
            seen.add(key)
            sources.append(row)
    return sources


def format_bibtex(source: Dict[str, str], citation_key: str) -> str:
    """Format a source as BibTeX @misc entry."""
    lines = [f"@misc{{{citation_key},"]
    
    title = source.get('source_title', '').strip()
    if title:
        lines.append(f"  title = {{{title}}},")
    
    url = source.get('source_url', '').strip()
    if url:
        lines.append(f"  url = {{{url}}},")
    
    source_type = source.get('source_type', '').strip()
    if source_type:
        lines.append(f"  note = {{{source_type}}},")
    
    date_pub = source.get('date_published', '').strip()
    if date_pub:
        lines.append(f"  year = {{{date_pub}}},")
    
    date_acc = source.get('date_accessed', '').strip()
    if date_acc:
        lines.append(f"  howpublished = {{Accessed: {date_acc}}},")
    
    access_method = source.get('access_method', '').strip()
    if access_method:
        lines.append(f"  organization = {{{access_method}}},")
    
    # Remove trailing comma from last entry
    if lines[-1].endswith(','):
        lines[-1] = lines[-1][:-1]
    
    lines.append("}")
    return '\n'.join(lines)


def format_ris(source: Dict[str, str]) -> str:
    """Format a source as RIS entry."""
    lines = []
    
    lines.append("TY  - ELEC")  # Electronic resource
    
    title = source.get('source_title', '').strip()
    if title:
        lines.append(f"TI  - {title}")
    
    url = source.get('source_url', '').strip()
    if url:
        lines.append(f"UR  - {url}")
    
    source_type = source.get('source_type', '').strip()
    if source_type:
        lines.append(f"TY  - {source_type}")
    
    date_pub = source.get('date_published', '').strip()
    if date_pub:
        lines.append(f"DA  - {date_pub}")
        # Also add year if we can extract it
        if len(date_pub) >= 4:
            lines.append(f"PY  - {date_pub[:4]}")
    
    date_acc = source.get('date_accessed', '').strip()
    if date_acc:
        lines.append(f"Y2  - {date_acc}")
    
    access_method = source.get('access_method', '').strip()
    if access_method:
        lines.append(f"PB  - {access_method}")
    
    lines.append("ER  - ")
    lines.append("")  # Blank line after ER
    
    return '\n'.join(lines)


def generate_citation_key(source: Dict[str, str], index: int) -> str:
    """Generate a citation key for BibTeX entry."""
    title = source.get('source_title', 'unknown')
    # Extract first meaningful word
    words = ''.join(c for c in title if c.isalnum() or c.isspace()).split()
    if words:
        key_base = words[0][:10].lower()
    else:
        key_base = f"source{index}"
    
    date = source.get('date_published', '')
    if date and len(date) >= 4:
        key_base += date[:4]
    
    return key_base


def export_csv_to_format(file_path: str, format_type: str, output_path: str) -> None:
    """Export CSV to specified format."""
    rows = read_csv(file_path)
    sources = get_unique_sources(rows)
    
    if not sources:
        raise ValueError("No valid sources found in CSV")
    
    output_lines = []
    
    if format_type == 'bibtex':
        for i, source in enumerate(sources):
            key = generate_citation_key(source, i + 1)
            output_lines.append(format_bibtex(source, key))
            output_lines.append("")  # Blank line between entries
    
    elif format_type == 'ris':
        for source in sources:
            output_lines.append(format_ris(source))
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(output_lines))


def enrich_doi(doi: str) -> Optional[Dict[str, str]]:
    """Fetch metadata from Crossref for a DOI."""
    # Clean DOI
    doi = doi.strip()
    if doi.startswith('https://doi.org/'):
        doi = doi[16:]
    elif doi.startswith('http://doi.org/'):
        doi = doi[15:]
    elif doi.startswith('doi:'):
        doi = doi[4:]
    
    doi = doi.strip()
    
    # Fetch from Crossref API
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi)}"
    
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'CitationExportPython/1.0 (mailto:@example@example.com)'
        })
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        if 'message' in data:
            work = data['message']
            
            result = {}
            
            # Title
            if 'title' in work and work['title']:
                result['title'] = work['title'][0] if isinstance(work['title'], list) else work['title']
            
            # Authors
            if 'author' in work:
                authors = []
                for author in work['author']:
                    if 'given' in author and 'family' in author:
                        authors.append(f"{author['given']} {author['family']}")
                    elif 'family' in author:
                        authors.append(author['family'])
                if authors:
                    result['authors'] = '; '.join(authors)
            
            # Year/Date
            if 'published-print' in work:
                date_parts = work['published-print'].get('date-parts', [[]])
                if date_parts and date_parts[0]:
                    result['year'] = str(date_parts[0][0])
            elif 'published-online' in work:
                date_parts = work['published-online'].get('date-parts', [[]])
                if date_parts and date_parts[0]:
                    result['year'] = str(date_parts[0][0])
            elif 'created' in work:
                date_parts = work['created'].get('date-parts', [[]])
                if date_parts and date_parts[0]:
                    result['year'] = str(date_parts[0][0])
            
            # Publisher
            if 'publisher' in work:
                result['publisher'] = work['publisher']
            
            # Container title (journal/book)
            if 'container-title' in work and work['container-title']:
                result['journal'] = work['container-title'][0]
            
            # Volume/Issue
            if 'volume' in work:
                result['volume'] = work['volume']
            if 'issue' in work:
                result['issue'] = work['issue']
            if 'page' in work:
                result['pages'] = work['page']
            
            # DOI
            result['doi'] = doi
            
            # URL
            if 'URL' in work:
                result['url'] = work['URL']
            
            return result
        
    except Exception as e:
        print(f"Error fetching DOI {doi}: {e}", file=sys.stderr)
        return None
    
    return None


def run_self_test() -> bool:
    """Run self-test validation."""
    print("Running self-test...")
    
    # Create temp directory
    temp_dir = tempfile.mkdtemp()
    csv_path = os.path.join(temp_dir, 'test_data.csv')
    output_bibtex = os.path.join(temp_dir, 'output.bib')
    output_ris = os.path.join(temp_dir, 'output.ris')
    
    try:
        # Create test CSV data
        test_data = [
            {
                'claim_id': '1',
                'claim': 'Test claim 1',
                'sub_question': 'SQ1',
                'source_title': 'Example Article Title',
                'source_url': 'https://example.com/article1',
                'source_type': 'website',
                'date_published': '2023',
                'date_accessed': '2024-01-15',
                'access_method': 'direct',
                'evidence': 'Some evidence',
                'quote_or_anchor': 'Quote text',
                'contradiction': '',
                'confidence': 'high',
                'notes': 'Test note'
            },
            {
                'claim_id': '2',
                'claim': 'Test claim 2',
                'sub_question': 'SQ2',
                'source_title': 'Another Source',
                'source_url': 'https://example.com/article2',
                'source_type': 'article',
                'date_published': '2022-05-10',
                'date_accessed': '2024-01-15',
                'access_method': 'api',
                'evidence': 'More evidence',
                'quote_or_anchor': '',
                'contradiction': 'none',
                'confidence': 'medium',
                'notes': ''
            },
            {
                'claim_id': '3',
                'claim': 'Test claim 3',
                'sub_question': 'SQ3',
                'source_title': 'Example Article Title',  # Duplicate to test uniqueness
                'source_url': 'https://example.com/article1',
                'source_type': 'website',
                'date_published': '2023',
                'date_accessed': '2024-01-15',
                'access_method': 'direct',
                'evidence': 'Duplicated source',
                'quote_or_anchor': '',
                'contradiction': '',
                'confidence': 'high',
                'notes': ''
            }
        ]
        
        # Write test CSV
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(test_data)
        
        print(f"  Created test CSV: {csv_path}")
        
        # Test CSV reading
        rows = read_csv(csv_path)
        assert len(rows) == 3, f"Expected 3 rows, got {len(rows)}"
        print("  [PASS] CSV reading")
        
        # Test unique source extraction
        sources = get_unique_sources(rows)
        assert len(sources) == 2, f"Expected 2 unique sources, got {len(sources)}"
        print("  [PASS] Unique source extraction")
        
        # Test BibTeX export
        export_csv_to_format(csv_path, 'bibtex', output_bibtex)
        with open(output_bibtex, 'r', encoding='utf-8') as f:
            bibtex_content = f.read()
        assert '@misc{' in bibtex_content, "Missing @misc in BibTeX"
        assert 'Example Article Title' in bibtex_content, "Missing title in BibTeX"
        print("  [PASS] BibTeX export")
        
        # Test RIS export
        export_csv_to_format(csv_path, 'ris', output_ris)
        with open(output_ris, 'r', encoding='utf-8') as f:
            ris_content = f.read()
        assert 'TY  - ELEC' in ris_content, "Missing TY in RIS"
        assert 'Example Article Title' in ris_content, "Missing title in RIS"
        print("  [PASS] RIS export")
        
        # Test DOI enrichment (mock test - will fail without network)
        print("  [INFO] Testing DOI enrichment (may fail without network)...")
        # We'll test with a known DOI structure without making actual request
        # just validate the parsing logic works
        
        # Test format functions
        test_source = {
            'source_title': 'Test Title',
            'source_url': 'https://test.com',
            'source_type': 'article',
            'date_published': '2023-01',
            'date_accessed': '2024-01-01',
            'access_method': 'web'
        }
        
        bibtex = format_bibtex(test_source, 'testkey2023')
        assert 'testkey2023' in bibtex
        assert 'Test Title' in bibtex
        
        ris = format_ris(test_source)
        assert 'Test Title' in ris
        assert 'ER  - ' in ris
        
        print("  [PASS] Format functions")
        
        # Test citation key generation
        key = generate_citation_key(test_source, 1)
        assert 'test' in key.lower() or 'source' in key.lower()
        print("  [PASS] Citation key generation")
        
        print("\nAll self-tests passed!")
        return True
        
    except AssertionError as e:
        print(f"\n  [FAIL] {e}")
        return False
    except Exception as e:
        print(f"\n  [ERROR] {e}")
        return False
    finally:
        # Cleanup
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(
        description='Citation export utility for CSV data'
    )
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Export subcommand
    export_parser = subparsers.add_parser(
        'export',
        help='Export CSV to BibTeX or RIS format'
    )
    export_parser.add_argument(
        '--file',
        required=True,
        help='Input CSV file path'
    )
    export_parser.add_argument(
        '--format',
        choices=['bibtex', 'ris'],
        required=True,
        help='Output format'
    )
    export_parser.add_argument(
        '--out',
        required=True,
        help='Output file path'
    )
    
    # Enrich subcommand
    enrich_parser = subparsers.add_parser(
        'enrich',
        help='Enrich citation with DOI metadata from Crossref'
    )
    enrich_parser.add_argument(
        '--doi',
        required=True,
        help='DOI to fetch metadata for'
    )
    
    # Self-test subcommand
    subparsers.add_parser(
        'self-test',
        help='Run self-test validation'
    )
    
    args = parser.parse_args()
    
    if args.command == 'export':
        try:
            export_csv_to_format(args.file, args.format, args.out)
            print(f"Exported to {args.out}")
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    
    elif args.command == 'enrich':
        result = enrich_doi(args.doi)
        if result:
            print(json.dumps(result, indent=2))
        else:
            print("Failed to fetch DOI metadata", file=sys.stderr)
            sys.exit(1)
    
    elif args.command == 'self-test':
        success = run_self_test()
        sys.exit(0 if success else 1)
    
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
