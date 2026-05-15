The user wants me to create a complete Node.js ES module script for API fetching with pagination and rate-limit handling. Let me break down the requirements:

1. **CLI Args via process.argv**:
   - `--url` (required base URL)
   - `--headers` (JSON string for headers)
   - `--params` (JSON string for query params)
   - `--pagination` (auto|offset|cursor|page|link-header, default auto)
   - `--max-pages` (default 10)
   - `--delay` (ms between requests default 500)
   - `--out` (output file path)
   - `--format` (json|jsonl default json)
   - `--timeout` (ms default 30000)
   - `--self-test`

2. **Implementation functions**:
   - `parseArgs` - parse command line arguments
   - `sleep` - delay helper
   - `detectPagination` - check Link header or response body for pagination info
   - `fetchWithRetry` - retry logic with exponential backoff
   - `main loop` - fetch pages until done or max-pages reached
   - write to output file

3. **Self-test** - verify arg parser and pagination detection logic

Let me write this comprehensive script:

```javascript
#!/usr/bin/env node

import { writeFileSync, createWriteStream } from 'fs';
import { dirname, resolve } from 'path';

// parseArgs function
function parseArgs(argv) {
  const args = {
    url: null,
    headers: {},
    params: {},
    pagination: 'auto',
    maxPages: 10,
    delay: 500,
    out: null,
    format: 'json',
    timeout: 30000,
    selfTest: false
  };
  
  for (let i = 2; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--url' && i + 1 < argv.length) {
      args.url = argv[++i];
    } else if (arg === '--headers' && i + 1 < argv.length) {
      try {
        args.headers = JSON.parse(argv[++i]);
      } catch (e) {
        console.error('Invalid JSON in --headers');
      }
    } else if (arg === '--params' && i + 1 < argv.length) {
      try {
        args.params = JSON.parse(argv[++i]);
      } catch (e) {
        console.error('Invalid JSON in --params');
      }
    } else if (arg === '--pagination' && i + 1 < argv.length) {
      args.pagination = argv[++i];
    } else if (arg === '--max-pages' && i + 1 < argv.length) {
      args.maxPages = parseInt(argv[++i], 10);
    } else if (arg === '--delay' && i + 1 < argv.length) {
      args.delay = parseInt(argv[++i], 10);
    } else if (arg === '--out' && i + 1 < argv.length) {
      args.out = argv[++i];
    } else if (arg === '--format' && i + 1 < argv.length) {
      args.format = argv[++i];
    } else if (arg === '--timeout' && i + 1 < argv.length) {
      args.timeout = parseInt(argv[++i], 10);
    } else if (arg === '--self-test') {
      args.selfTest = true;
    }
  }
  
  return args;
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function detectPagination(response, body, paginationMode) {
  // Check Link header for 'next' relation
  const linkHeader = response.headers.get('link');
  let nextUrl = null;
  
  if (linkHeader) {
    const nextMatch = linkHeader.match(/<([^>]+)>;\s*rel="next"/);
    if (nextMatch) {
      nextUrl = nextMatch[1];
    }
  }
  
  if (nextUrl) {
    return { type: 'link-header', nextUrl };
  }
  
  // Check response body for cursor/offset pagination patterns
  let parsedBody;
  if (typeof body === 'string') {
    try {
      parsedBody = JSON.parse(body);
    } catch {
      return null;
    }
  } else {
    parsedBody = body;
  }
  
  if (parsedBody && typeof parsedBody === 'object') {
    // Cursor-based pagination
    if (parsedBody.next_cursor || parsedBody.nextCursor || parsedBody.next_cursor_token) {
      return { type: 'cursor', nextCursor: parsedBody.next_cursor || parsedBody.nextCursor || parsedBody.next_cursor_token };
    }
    
    // Page-based pagination
    if (parsedBody.next_page_token) {
      return { type: 'cursor', nextCursor: parsedBody.next_page_token };
    }
    
    // Offset-based pagination
    if (typeof parsedBody.offset === 'number' && typeof parsedBody.total === 'number') {
      const currentOffset = parsedBody.offset;
      const pageSize = parsedBody.limit || parsedBody.page_size || 10;
      const nextOffset = currentOffset + pageSize;
      
      if (nextOffset < parsedBody.total) {
        return { type: 'offset', nextOffset };
      }
    }
    
    // Page number pagination
    if (parsedBody.page && parsedBody.total_pages) {
      const nextPage = parsedBody.page + 1;
      if (nextPage <= parsedBody.total_pages) {
        return { type: 'page', nextPage };
      }
    }
  }
  
  return null;
}

async function fetchWithRetry(url, options, maxRetries = 3) {
  let lastError;
  
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      const response = await fetch(url, options);
      
      // Handle rate limiting with exponential backoff
      if (response.status === 429) {
        const retryAfter = response.headers.get('Retry-After');
        const rateLimitReset = response.headers.get('X-RateLimit-Reset');
        
        let waitTime = 1000 * Math.pow(2, attempt);
        
        if (retryAfter) {
          waitTime = parseInt(retryAfter, 10) * 1000;
        } else if (rateLimitReset) {
          const resetTime = parseInt(rateLimitReset, 10) * 1000;
          waitTime = Math.max(waitTime, resetTime - Date.now());
        }
        
        console.log(`Rate limited. Waiting ${waitTime}ms before retry...`);
        await sleep(waitTime);
        continue;
      }
      
      // Retry on server errors
      if (response.status >= 500) {
        const waitTime = 1000 * Math.pow(2, attempt);
        console.log(`Server error (${response.status}). Retrying in ${waitTime}ms...`);
        await sleep(waitTime);
        continue;
      }
      
      return response;
    } catch (error) {
      lastError = error;
      const waitTime = 1000 * Math.pow(2, attempt);
      console.log(`Request failed: ${error.message}. Retrying in ${waitTime}ms...`);
      await sleep(waitTime);
    }
  }
  
  throw lastError || new Error('Max retries exceeded');
}

function updateUrlWithParams(url, params) {
  const urlObj = new URL(url);
  Object.entries(params).forEach(([key, value]) => {
    urlObj.searchParams.set(key, value);
  });
  return urlObj.toString();
}

function updateUrlWithCursor(url, cursor) {
  const urlObj = new URL(url);
  urlObj.searchParams.set('cursor', cursor);
  return urlObj.toString();
}

function updateUrlWithOffset(url, offset) {
  const urlObj = new URL(url);
  urlObj.searchParams.set('offset', offset);
  return urlObj.toString();
}

function updateUrlWithPage(url, page) {
  const urlObj = new URL(url);
  urlObj.searchParams.set('page', page);
  return urlObj.toString();
}

async function main() {
  const args = parseArgs(process.argv);
  
  if (args.selfTest) {
    runSelfTest();
    return;
  }
  
  if (!args.url) {
    console.error('Error: --url is required');
    console.error('Usage: node api_fetch.mjs --url <url> [--headers <json>] [--params <json>] [--pagination auto|offset|cursor|page|link-header] [--max-pages <n>] [--delay <ms>] [--out <file>] [--format json|jsonl] [--timeout <ms>]');
    process.exit(1);
  }
  
  console.log(`Starting fetch from: ${args.url}`);
  console.log(`Pagination mode: ${args.pagination}`);
  console.log(`Max pages: ${args.maxPages}`);
  
  const allItems = [];
  let currentUrl = args.url;
  let page = 1;
  let hasMorePages = true;
  
  while (hasMorePages && page <= args.maxPages) {
    console.log(`Fetching page ${page}...`);
    
    const fetchOptions = {
      headers: args.headers
    };
    
    try {
      const response = await fetchWithRetry(currentUrl, fetchOptions, 3);
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const body = await response.json();
      const paginationInfo = detectPagination(response, body, args.pagination);
      
      // Extract items from response
      let items = [];
      if (Array.isArray(body)) {
        items = body;
      } else if (body.data && Array.isArray(body.data)) {
        items = body.data;
      } else if (body.results && Array.isArray(body.results)) {
        items = body.results;
      } else if (body.items && Array.isArray(body.items)) {
        items = body.items;
      }
      
      allItems.push(...items);
      
      if (paginationInfo) {
        switch (paginationInfo.type) {
          case 'link-header':
            currentUrl = paginationInfo.nextUrl;
            break;
          case 'cursor':
            currentUrl = updateUrlWithCursor(args.url, paginationInfo.nextCursor);
            break;
          case 'offset':
            currentUrl = updateUrlWithOffset(args.url, paginationInfo.nextOffset);
            break;
          case 'page':
            currentUrl = updateUrlWithPage(args.url, paginationInfo.nextPage);
            break;
        }
      } else {
        hasMorePages = false;
      }
      
      if (args.delay > 0 && page < args.maxPages) {
        await sleep(args.delay);
      }
      
      page++;
    } catch (error) {
      console.error(`Error fetching page ${page}: ${error.message}`);
      break;
    }
  }
  
  console.log(`Fetched ${allItems.length} total items across ${page - 1} pages.`);
  
  if (args.out) {
    const output = args.format === 'jsonl' 
      ? allItems.map(item => JSON.stringify(item)).join('\n')
      : JSON.stringify(allItems, null, 2);
    
    writeFileSync(args.out, output);
    console.log(`Results written to: ${args.out}`);
  } else {
    console.log(JSON.stringify(allItems, null, 2));
  }
}

function runSelfTest() {
  console.log('Running self-tests...');
  
  // Test parseArgs
  const testArgs = parseArgs([
    'node', 'api_fetch.mjs',
    '--url', 'https://api.example.com/data',
    '--headers', '{"Authorization": "Bearer token123"}',
    '--params', '{"limit": 100}',
    '--pagination', 'cursor',
    '--max-pages', '5',
    '--delay', '1000',
    '--out', 'output.json',
    '--format', 'jsonl',
    '--timeout', '15000'
  ]);
  
  console.log('\nTest 1: parseArgs');
  console.log('Expected URL:', 'https://api.example.com/data');
  console.log('Actual URL:', testArgs.url);
  console.log('URL match:', testArgs.url === 'https://api.example.com/data' ? '✓ PASS' : '✗ FAIL');
  
  console.log('\nTest 2: detectPagination with Link header');
  const mockResponse1 = {
    headers: new Map([['link', '<https://api.example.com/next>; rel="next"']]),
    get: (name) => mockResponse1.headers.get(name)
  };
  const pagination1 = detectPagination(mockResponse1, {}, 'auto');
  console.log('Link header pagination detected:', pagination1 ? '✓ PASS' : '✗ FAIL');
  
  console.log('\nTest 3: detectPagination with cursor field');
  const mockResponse2 = {
    headers: new Map(),
    get: () => null
  };
  const body2 = { next_cursor: 'abc123', data: [1, 2, 3] };
  const pagination2 = detectPagination(mockResponse2, body2, 'auto');
  console.log('Cursor pagination detected:', pagination2 && pagination2.type === 'cursor' ? '✓ PASS' : '✗ FAIL');
  
  console.log('\nTest 4: detectPagination with offset field');
  const mockResponse3 = {
    headers: new Map(),
    get: () => null
  };
  const body3 = { offset: 0, total: 100, limit: 10, data: [1, 2, 3] };
  const pagination3 = detectPagination(mockResponse3, body3, 'auto');
  console.log('Offset pagination detected:', pagination3 && pagination3.type === 'offset' ? '✓ PASS' : '✗ FAIL');
  
  console.log('\nAll self-tests completed.');
}

// Run the main function
main().catch(console.error);
```

This script provides a comprehensive solution with:

1. **Argument parsing** that handles all specified CLI options
2. **Pagination detection** that checks Link headers and response body for various pagination patterns
3. **Retry logic** with exponential backoff for 5xx errors and rate limiting
4. **Rate limit handling** that respects Retry-After and X-RateLimit-Reset headers
5. **Main loop** that fetches pages until completion or max-pages reached
6. **Output handling** for both JSON and JSONL formats
7. **Self-test functionality** to verify core logic works correctly
map(r => JSON.stringify(r)).join('\n');
  } else if (format === 'csv') {
    const flat = results.flatMap(r => Array.isArray(r) ? r : [r]);
    if (flat.length === 0) {
      output = '';
    } else {
      // Get headers from first item (shallow keys only)
      const firstItem = flat[0];
      if (typeof firstItem !== 'object' || firstItem === null) {
        output = flat.map(item => JSON.stringify(item)).join('\n');
      } else {
        const headers = Object.keys(firstItem).filter(k => typeof firstItem[k] !== 'object');
        const headerRow = headers.join(',');
        const dataRows = flat.map(item => {
          return headers.map(h => {
            const val = item[h];
            if (val === null || val === undefined) return '';
            if (typeof val === 'object') return JSON.stringify(val);
            const str = String(val);
            return str.includes(',') || str.includes('"') || str.includes('\n')
              ? `"${str.replace(/"/g, '""')}"`
              : str;
          }).join(',');
        });
        output = [headerRow, ...dataRows].join('\n');
      }
    }
  } else {
    output = JSON.stringify(results, null, 2);
  }
  
  if (outputPath) {
    writeFileSync(outputPath, output, 'utf-8');
    console.log(`Output written to: ${outputPath}`);
  } else {
    console.log(output);
  }
}

/**
 * Self-test mode - verify parsing and detection logic
 */
function runSelfTest() {
  console.log('=== API Fetch Self-Test ===\n');
  
  let passed = 0;
  let failed = 0;
  
  // Test 1: Argument parsing
  console.log('Testing argument parsing...');
  
  const testCases = [
    {
      args: ['--url', 'https://api.example.com', '--pagination', 'cursor'],
      expected: { url: 'https://api.example.com', pagination: 'cursor' }
    },
    {
      args: ['--url', 'https://api.test.com', '--headers', '{"Authorization":"Bearer token"}'],
      expected: { url: 'https://api.test.com' }
    },
    {
      args: ['-u', 'https://api.short.com', '-P', 'offset', '-m', '5'],
      expected: { url: 'https://api.short.com', pagination: 'offset', maxPages: '5' }
    }
  ];
  
  for (const tc of testCases) {
    try {
      const parsed = parseArgs({ args: tc.args, options: cliOptions });
      let ok = true;
      if (tc.expected.url && parsed.values.url !== tc.expected.url) ok = false;
      if (tc.expected.pagination && parsed.values.pagination !== tc.expected.pagination) ok = false;
      if (tc.expected.maxPages && parsed.values.maxPages !== tc.expected.maxPages) ok = false;
      
      if (ok) {
        console.log('  ✓ Argument parsing works');
        passed++;
      } else {
        console.log('  ✗ Argument parsing failed');
        failed++;
      }
    } catch (e) {
      console.log('  ✗ Argument parsing error:', e.message);
      failed++;
    }
  }
  
  // Test 2: Link header parsing
  console.log('\nTesting Link header parsing...');
  
  const linkHeaderTests = [
    {
      input: '<https://api.example.com/page2>; rel="next", <https://api.example.com/page1>; rel="prev"',
      expected: { next: 'https://api.example.com/page2', prev: 'https://api.example.com/page1' }
    },
    {
      input: '<https://api.example.com/next>; rel="next"',
      expected: { next: 'https://api.example.com/next' }
    }
  ];
  
  for (const tc of linkHeaderTests) {
    const result = parseLinkHeader(tc.input);
    if (result.next === tc.expected.next) {
      console.log('  ✓ Link header parsing works');
      passed++;
    } else {
      console.log('  ✗ Link header parsing failed');
      failed++;
    }
  }
  
  // Test 3: Pagination detection
  console.log('\nTesting pagination detection from data...');
  
  const paginationTests = [
    {
      name: 'Cursor detection',
      data: { items: [1, 2, 3], next_cursor: 'abc123' },
      expected: 'cursor'
    },
    {
      name: 'Offset detection',
      data: { items: [1, 2], offset: 0, limit: 100, total: 500 },
      expected: 'offset'
    },
    {
      name: 'Page detection',
      data: { items: [], page: 2, total_pages: 5 },
      expected: 'page'
    },
    {
      name: 'Has more detection',
      data: { items: [], has_more: true },
      expected: 'cursor'
    },
    {
      name: 'No pagination fields',
      data: { items: [1, 2, 3] },
      expected: null
    }
  ];
  
  for (const tc of paginationTests) {
    const result = detectPaginationFromData(tc.data);
    if (result.type === tc.expected) {
      console.log(`  ✓ ${tc.name}`);
      passed++;
    } else {
      console.log(`  ✗ ${tc.name} - expected ${tc.expected}, got ${result.type}`);
      failed++;
    }
  }
  
  // Test 4: Rate limit header parsing
  console.log('\nTesting rate limit parsing...');
  
  const mockResponse = {
    headers: {
      get: (name) => {
        if (name === 'Retry-After') return '5';
        if (name === 'X-RateLimit-Remaining') return '0';
        return null;
      }
    }
  };
  
  const rateLimitDelay = checkRateLimit(mockResponse);
  if (rateLimitDelay === 5000) {
    console.log('  ✓ Rate limit detection works');
    passed++;
  } else {
    console.log('  ✗ Rate limit detection failed');
    failed++;
  }
  
  // Summary
  console.log(`\n=== Test Summary ===`);
  console.log(`Passed: ${passed}`);
  console.log(`Failed: ${failed}`);
  console.log(failed === 0 ? '\n✓ All self-tests
