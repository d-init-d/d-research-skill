import http from 'http';
import { spawn } from 'child_process';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';
import { chromium } from 'playwright';

const DIR_PATH = dirname(fileURLToPath(import.meta.url));
const SERVER_SCRIPT = join(DIR_PATH, 'server.py');
const PORT = 8770;
const BASE_URL = `http://127.0.0.1:${PORT}`;

const FORBIDDEN_STRINGS = [
  'Lumen 2.0.4 Maintenance Release',
  'Lumen 2.1 Release Candidate Dumy',
  'Lumen 2.1 Release Candidate Draft',
  'Lumen 2.1 Final Official Release',
  '2026-08-28',
  'tech_lead_alex',
  'Settings > Data Management > Export CSV',
  'user_danang_01',
  'minh_quan_lead_eng',
  'tester_hcm',
  'EX-21',
  'c_13_reproduce',
  'c_16_contrary',
  'kernel_hacker_vn',
  '01:42',
  'vid_lumen_21_overview',
  'Đính chính chính thức'
];

function fetchUrl(url, method = 'GET', postData = null) {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const options = {
      hostname: parsed.hostname,
      port: parsed.port,
      path: parsed.pathname + parsed.search,
      method: method,
      headers: {}
    };
    if (postData) {
      options.headers['Content-Type'] = 'application/json';
      options.headers['Content-Length'] = Buffer.byteLength(postData);
    }
    const req = http.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => resolve({ statusCode: res.statusCode, headers: res.headers, body: data }));
    });
    req.on('error', reject);
    if (postData) req.write(postData);
    req.end();
  });
}

async function waitForServer(url, timeoutMs = 7000) {
  const start = Date.now
();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetchUrl(`${url}/healthz`);
      if (res.statusCode === 200) return true;
    } catch (e) {
      // retry
    }
    await new Promise(r => setTimeout(r, 100));
  }
  throw new Error(`Server failed to start on ${url} within ${timeoutMs}ms`);
}

async function runChallenge() {
  console.log(`[CHALLENGE] 1. Spawning fixture server on port ${PORT}...`);
  const serverProcess = spawn('python', [SERVER_SCRIPT, String(PORT)], {
    stdio: ['ignore', 'pipe', 'pipe']
  });

  try {
    await waitForServer(BASE_URL);
    console.log(`[PASS] Server is listening and healthy on ${BASE_URL}`);

    // --- PHASE 1: Raw Initial HTML Zero-Precomputation Challenge ---
    console.log('[CHALLENGE] 2. Inspecting initial raw HTML for answer leakage...');
    const rootRes = await fetchUrl(`${BASE_URL}/`);
    if (rootRes.statusCode !== 200) {
      throw new Error(`Root GET returned HTTP ${rootRes.statusCode}, expected 200`);
    }
    const rawHtml = rootRes.body;
    console.log(`Initial HTML length: ${rawHtml.length} bytes`);

    let leakedCount = 0;
    for (const forbidden of FORBIDDEN_STRINGS) {
      if (rawHtml.includes(forbidden)) {
        console.error(`[LEAK DETECTED] Initial HTML contains forbidden string: "${forbidden}"`);
        leakedCount++;
      }
    }
    if (leakedCount > 0) {
      throw new Error(`Integrity Violation: ${leakedCount} forbidden strings leaked in initial HTML!`);
    }
    console.log('[PASS] Initial HTML verified 100% clean: zero precomputed answers found.');

    // --- PHASE 2: Direct API Endpoint Protocol Validation ---
    console.log('[CHALLENGE] 3. Verifying REST API endpoints directly...');
    const searchRes = await fetchUrl(`${BASE_URL}/api/search`, 'POST', JSON.stringify({ query: 'lumen' }));
    const searchData = JSON.parse(searchRes.body);
    if (!searchData.results || searchData.results.length !== 3) {
      throw new Error(`Search API returned unexpected item count: ${searchData.results?.length}`);
    }

    const filterFinalRes = await fetchUrl(`${BASE_URL}/api/filter?type=final`);
    const filterFinalData = JSON.parse(filterFinalRes.body);
    if (filterFinalData.results.length !== 1 || filterFinalData.results[0].status !== 'final') {
      throw new Error(`Filter API returned unexpected results for final: ${JSON.stringify(filterFinalData)}`);
    }

    const filterDraftRes = await fetchUrl(`${BASE_URL}/api/filter?type=draft`);
    const filterDraftData = JSON.parse(filterDraftRes.body);
    if (filterDraftData.results.length !== 2) {
      throw new Error(`Filter API returned unexpected results for draft: ${JSON.stringify(filterDraftData)}`);
    }

    const threadRes = await fetchUrl(`${BASE_URL}/api/thread?id=doc_v21_final`);
    const threadData = JSON.parse(threadRes.body);
    if (!threadData.preview_text || !threadData.full_body) {
      throw new Error('Thread API missing preview or full body');
    }

    const repliesRes = await fetchUrl(`${BASE_URL}/api/replies?thread_id=doc_v21_final`);
    const repliesData = JSON.parse(repliesRes.body);
    if (repliesData.replies.length !== 3) {
      throw new Error(`Replies API returned unexpected count: ${repliesData.replies.length}`);
    }

    const commentsP1 = JSON.parse((await fetchUrl(`${BASE_URL}/api/comments?page=1`)).body);
    const commentsP2 = JSON.parse((await fetchUrl(`${BASE_URL}/api/comments?page=2`)).body);
    if (commentsP1.comments.length !== 1 || commentsP2.comments.length !== 2) {
      throw new Error('Comments pagination API mismatch');
    }

    const transcriptRes = await fetchUrl(`${BASE_URL}/api/transcript?video_id=vid_lumen_21_overview`);
    const transcriptData = JSON.parse(transcriptRes.body);
    if (!transcriptData.cues || transcriptData.cues.length !== 3) {
      throw new Error('Transcript API cues mismatch');
    }
    console.log('[PASS] All 6 dynamic REST endpoints conform to contract.');

    // --- PHASE 3: Playwright Chromium Headless Interactive DOM Challenge ---
    console.log('[CHALLENGE] 4. Launching Playwright Chromium Headless to stress-test 7 actions...');
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();

    page.on('console', msg => console.log('PAGE LOG:', msg.text()));
    page.on('pageerror', err => console.log('PAGE ERROR:', err));
    page.on('response', resp => console.log('HTTP RESP:', resp.status(), resp.url()));

    await page.goto(BASE_URL);

    // Snapshot baseline DOM
    const initialDomCards = await page.locator('.result-card').count();
    const initialDomReplies = await page.locator('.comment-box').count();
    const initialDomTranscript = await page.locator('.transcript-line').count();
    if (initialDomCards !== 0 || initialDomReplies !== 0 || initialDomTranscript !== 0) {
      throw new Error('initial DOM contains unexpected rendered content elements!');
    }
    console.log('[PASS] Initial DOM is purely structural (0 cards, 0 replies, 0 transcript lines).');

    // Edge-test 3A: Search with unknown term
    console.log('[STRESS TEST] Testing unknown search term behavior...');
    await page.fill('#search-input', 'non_existent_query_xyz');
    await page.click('#search-submit');
    await page.waitForSelector('.no-results', { timeout: 3000 });
    const noResultsText = await page.locator('.no-results').textContent();
    console.log(`Observed empty result fallback: "${noResultsText}"`);

    // Action 1: Valid Search Form Submission
    console.log('[ACTION 1] Submitting valid search query "Lumen 2.1"...');
    await page.fill('#search-input', 'Lumen 2.1');
    await page.click('#search-submit');
    await page.waitForSelector('.result-card', { timeout: 3000 });
    const countA1 = await page.locator('.result-card').count();
    console.log(`Action 1 Success: Rendered ${countA1} result cards in DOM.`);
    if (countA1 !== 3) throw new Error(`Expected 3 result cards, got ${countA1}`);

    // Action 2: Filter Selection (Final)
    console.log('[ACTION 2] Selecting filter: "final" and clicking Apply Filter...');
    await page.selectOption('#filter-type', 'final');
    await page.click('#apply-filter');
    await page.waitForSelector('#result-doc_v20', { state: 'detached', timeout: 3000 });
    const countA2 = await page.locator('.result-card').count();
    console.log(`Action 2 Success: Filter reduced cards to ${countA2}.`);
    if (countA2 !== 1) throw new Error(`Expected 1 final result card, got ${countA2}`);

    // Action 3: Open Thread
    console.log('[ACTION 3] Opening thread for doc_v21_final...');
    await page.click('#result-doc_v21_final .open-thread-btn');
    await page.waitForSelector('#thread-section:not(.hidden)', { timeout: 3000 });
    const previewContent = await page.locator('#post-body-container').textContent();
    const isTruncated = previewContent.endsWith('...');
    console.log(`Action 3 Success: Post loaded with truncated preview (ends with ...: ${isTruncated}).`);

    // Action 4: Expand Post Show More
    console.log('[ACTION 4] Expanding truncated post Show More...');
    await page.click('#expand-post-btn');
    const fullBodyContent = await page.locator('#post-body-container').textContent();
    const btnVisible = await page.locator('#expand-post-btn').isVisible();
    console.log(`Action 4 Success: Full body expanded (length: ${fullBodyContent.length}, Show More button visible: ${btnVisible}).`);
    if (btnVisible || !fullBodyContent.includes('Cài đặt')) {
      throw new Error('Action 4 verification failed: post not expanded or button not hidden');
    }

    // Action 5: View Replies
    console.log('[ACTION 5] Clicking View Replies...');
    await page.click('#view-replies-btn');
    await page.waitForSelector('#reply-rep_02_correction', { timeout: 3000 });
    const repliesCount = await page.locator('#replies-container .comment-box').count();
    const correctionText = await page.locator('#reply-rep_02_correction .comment-body').textContent();
    console.log(`Action 5 Success: ${repliesCount} replies rendered. Correction captured: "${correctionText}"`);
    if (repliesCount !== 3 || !correctionText.includes('Settings > Data Management > Export CSV')) {
      throw new Error('Action 5 verification failed: replies count or correction text mismatch');
    }

    // Action 6: Paginate Comments (Load More / Next Page)
    console.log('[ACTION 6] Paginating comments (Load More)...');
    await page.click('#load-more-btn');
    await page.waitForSelector('#comment-c_13_reproduce', { timeout: 3000 });
    const pagedComment = await page.locator('#comment-c_13_reproduce .comment-body').textContent();
    const isBtnDisabled = await page.locator('#load-more-btn').isDisabled();
    console.log(`Action 6 Success: Next page comments rendered. Reproduce details: "${pagedComment}". Button disabled: ${isBtnDisabled}`);
    if (!pagedComment.includes('EX-21') || !isBtnDisabled) {
      throw new Error('Action 6 verification failed: paged comments or button disable state mismatch');
    }

    // Action 7: Toggle Video Transcript
    console.log('[ACTION 7] Toggling video transcript panel...');
    await page.click('#toggle-transcript-btn');
    await page.waitForSelector('#transcript-panel:not(.hidden)', { timeout: 3000 });
    const cueCount = await page.locator('.transcript-line').count();
    const transcriptText = await page.locator('#transcript-panel').textContent();
    console.log(`Action 7 Success: Transcript opened with ${cueCount} cues. 01:42 resolution present: ${transcriptText.includes('01:42')}`);
    if (cueCount !== 3 || !transcriptText.includes('01:42')) {
      throw new Error('Action 7 verification failed: transcript cues or resolution mismatch');
    }

    // Stress test toggle off and on again
    console.log('[STRESS TEST] Testing transcript toggle hide & show...');
    await page.click('#toggle-transcript-btn');
    const isHidden = await page.locator('#transcript-panel').evaluate(el => el.classList.contains('hidden'));
    if (!isHidden) throw new Error('Transcript did not hide on second click');
    await page.click('#toggle-transcript-btn');
    await page.waitForSelector('#transcript-panel:not(.hidden)', { timeout: 3000 });
    console.log('[PASS] Transcript toggle state machine verified.');

    await browser.close();
    console.log('[PASS] Playwright Chromium headless interactions completed successfully.');

  } finally {
    console.log('[CHALLENGE] 5. Cleanly shutting down server process...');
    serverProcess.kill('SIGTERM');
    await new Promise(r => setTimeout(r, 500));
    try {
      await fetchUrl(`${BASE_URL}/healthz`);
      console.warn('Warning: Server still responding after SIGTERM, killing process forcefully...');
      serverProcess.kill('SIGKLLL');
    } catch (e) {
      console.log('[PASS] Server cleanly shut down, port 8770 released.');
    }
  }
}

runChallenge().then(() => {
  console.log('\n=== EMPIRICAL CHALLENGE RESULT: PASS (CONFIRMED) ===\n');
  process.exit(0);
}).catch((err) => {
  console.error('\n=== EMPIRICAL CHALLENGE RESULT: FAIL ===\n', err);
  process.exit(1);
});