/**
 * Verification script for DRS-1.1 dynamic site fixture (W03.03, W03.04).
 * 1. Checks that initial HTML has ZERO answer strings.
 * 2. Uses Playwright Chromium (headless) to execute the 7-step interaction loop:
 *    - Search form submit
 *    - Filter select
 *    - Open thread
 *    - Expand post (Show More)
 *    - View replies (finds correction)
 *    - Paginate / scroll (loads C13/C16 comments)
 *    - Toggle video transcript (finds timecoded 01:42 resolution)
 */

import http from 'http';
import { spawn } from 'child_process';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';
import { chromium } from 'playwright';

const DIR_PATH = dirname(fileURLToPath(import.meta.url));
const SERVER_SCRIPT = join(DIR_PATH, 'server.py');
const PORT = 8769;
const BASE_URL = `http://127.0.0.1:${PORT}`;

// Answer strings that MUST NOT be in initial HTML
const FORBIDDEN_INITIAL_STRINGS = [
  '2026-08-28',
  'Settings > Data Management > Export CSV',
  'CSV không bị loại bỏ',
  'EX-21',
  '01:42',
  'Đính chính chính thức: Tính năng xuất CSV vẫn còn'
];

function fetchRawHtml(url) {
  return new Promise((resolve, reject) => {
    http.get(url, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => resolve(data));
    }).on('error', reject);
  });
}

function waitForServer(url, timeoutMs = 5000) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const check = () => {
      http.get(`${url}/healthz`, (res) => {
        if (res.statusCode === 200) resolve();
        else setTimeout(check, 100);
      }).on('error', () => {
        if (Date.now() - start > timeoutMs) reject(new Error('Server start timeout'));
        else setTimeout(check, 100);
      });
    };
    check();
  });
}

async function run() {
  console.log('Starting Python dynamic fixture server...');
  const serverProcess = spawn('python', [SERVER_SCRIPT, String(PORT)], {
    stdio: 'inherit'
  });

  try {
    await waitForServer(BASE_URL);
    console.log(`Server healthy at ${BASE_URL}`);

    // Verification Step W03.04: Initial HTML contains ZERO answer strings
    console.log('Testing W03.04: Verifying initial HTML has zero precomputed answers...');
    const initialHtml = await fetchRawHtml(`${BASE_URL}/`);
    for (const str of FORBIDDEN_INITIAL_STRINGS) {
      if (initialHtml.includes(str)) {
        throw new Error(`Integrity violation: Initial HTML contains forbidden answer string: "${str}"`);
      }
    }
    console.log('PASS: Initial HTML verified completely free of precomputed answer strings.');

    // Launch Playwright
    console.log('Launching Playwright Chromium (headless)...');
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext();
    const page = await context.newPage();

    console.log(`Navigating to ${BASE_URL}...`);
    await page.goto(BASE_URL);

    // Step 1: Search form submission
    console.log('Executing Step 1: Search form submit...');
    await page.fill('#search-input', 'Lumen 2.1');
    await page.click('#search-submit');
    await page.waitForSelector('.result-card', { timeout: 3000 });
    const cardsCount = await page.locator('.result-card').count();
    console.log(`Step 1 Success: Found ${cardsCount} search result cards.`);
    if (cardsCount < 3) throw new Error('Expected at least 3 initial search cards.');

    // Step 2: Filter selection (Final)
    console.log('Executing Step 2: Apply filter to Final release...');
    await page.selectOption('#filter-type', 'final');
    await Promise.all([
      page.waitForResponse(resp => resp.url().includes('/api/filter') && resp.status() === 200),
      page.click('#apply-filter')
    ]);
    await page.waitForSelector('#result-doc_v20', { state: 'detached', timeout: 3000 });
    const filteredCount = await page.locator('.result-card').count();
    console.log(`Step 2 Success: Filtered down to ${filteredCount} final card(s).`);
    if (filteredCount !== 1) throw new Error('Expected exactly 1 final release card after filter.');

    // Step 3: Open thread
    console.log('Executing Step 3: Open thread details...');
    await page.click('#result-doc_v21_final .open-thread-btn');
    await page.waitForSelector('#thread-section:not(.hidden)', { timeout: 3000 });
    const isPostTruncated = await page.locator('#expand-post-btn').isVisible();
    if (!isPostTruncated) throw new Error('Expected post to initially show Show More expand button.');
    console.log('Step 3 Success: Thread opened with truncated preview.');

    // Step 4: Expand post
    console.log('Executing Step 4: Expand truncated post...');
    await page.click('#expand-post-btn');
    const fullText = await page.locator('#post-body-container').textContent();
    if (!fullText.includes('Đội ngũ kỹ thuật đã rà soát toàn bộ thay đổi')) {
      throw new Error('Expanded post missing expected full body text.');
    }
    console.log('Step 4 Success: Post successfully expanded to full body.');

    // Step 5: View replies and capture correction
    console.log('Executing Step 5: View replies and inspect correction...');
    await page.click('#view-replies-btn');
    await page.waitForSelector('#reply-rep_02_correction', { timeout: 3000 });
    const correctionText = await page.locator('#reply-rep_02_correction .comment-body').textContent();
    console.log(`Step 5 Observed Correction: "${correctionText}"`);
    if (!correctionText.includes('Settings > Data Management > Export CSV')) {
      throw new Error('Authoritative correction missing expected settings path.');
    }
    console.log('Step 5 Success: Correction captured in nested replies.');

    // Step 6: Paginate / virtual scroll comments
    console.log('Executing Step 6: Paginate / load more comments...');
    await page.click('#load-more-btn');
    await page.waitForSelector('#comment-c_13_reproduce', { timeout: 3000 });
    const reproduceComment = await page.locator('#comment-c_13_reproduce .comment-body').textContent();
    console.log(`Step 6 Observed Paged Comment: "${reproduceComment}"`);
    if (!reproduceComment.includes('EX-21')) {
      throw new Error('Paged comments missing expected reproduction comment.');
    }
    console.log('Step 6 Success: Next page comments loaded with reproduction details.');

    // Step 7: Toggle video transcript panel
    console.log('Executing Step 7: Toggle video transcript panel...');
    await page.click('#toggle-transcript-btn');
    await page.waitForSelector('#transcript-panel:not(.hidden)', { timeout: 3000 });
    const transcriptText = await page.locator('#transcript-panel').textContent();
    if (!transcriptText.includes('01:42') || !transcriptText.includes('Tính năng xuất CSV vẫn còn nguyên vẹn trên desktop')) {
      throw new Error('Transcript panel missing expected timecoded resolution at 01:42.');
    }
    console.log('Step 7 Success: Timecoded transcript panel rendered with 01:42 resolution.');

    await browser.close();
    console.log('\nALL 7 INTERACTIVE STEPS AND W03.04 INTEGRITY CHECKS PASSED PERFECTLY!');
  } finally {
    serverProcess.kill('SIGTERM');
  }
}

run().catch((err) => {
  console.error('\nVerification failed:', err);
  process.exit(1);
});
