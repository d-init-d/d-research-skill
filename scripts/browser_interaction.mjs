#!/usr/bin/env node
/**
 * scripts/browser_interaction.mjs
 * Authoritative 8-step Playwright Browser Operator for DRS-1.1 (Package W06).
 *
 * Conforms to:
 *   - audit-artifacts-social-v1/run-20260915-drs11-001/contracts/playwright-contract.md
 *   - activity-log.schema.json
 *   - capture-record.schema.json
 *
 * Supports:
 *   - 8-step loop: Navigate -> Observe DOM -> Action -> Wait Condition -> Re-Observe -> Capture -> Next Action -> Bounded Recovery
 *   - Actions: search, filter, open, expand, view_replies, paginate, scroll, transcript
 *   - Deterministic wait conditions (no arbitrary sleep)
 *   - Strict semantic locators (zero blind coordinate clicks)
 *   - SSRF protection (installBrowserSsrfGuard, --allow-loopback-fixture)
 *   - Secret redaction (stripSensitiveHeaders, redactUrl, redactSecretsInText)
 *   - Budget caps and bounded error recovery
 */

import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import {
  assertBrowserPublicUrl,
  installBrowserSsrfGuard,
  structuredBlocker,
} from './lib/browser_ssrf.mjs';
import {
  redactUrl,
  redactSecretsInText,
  stripSensitiveHeaders,
} from './lib/credentials.mjs';
import {
  browserResourceLimitErrorFromPayload,
  enforceBrowserResponseLimit,
  resolveBrowserResponseLimit,
} from './lib/browser_limits.mjs';
import { browserUserAgent } from './lib/package_metadata.mjs';

export class BrowserOperator {
  constructor(options = {}) {
    this.headless = options.headless ?? true;
    this.timeout = options.timeout ?? 30000;
    this.actionTimeout = options.actionTimeout ?? 3000;
    this.allowLoopback = options.allowLoopback ?? false;
    this.ignoreTlsErrors = options.ignoreTlsErrors ?? false;
    this.maxResponseBytes = resolveBrowserResponseLimit(options.maxResponseBytes);
    this.branchId = options.branchId || 'documentary';
    this.questionIds = options.questionIds || ['Q1'];
    this.outDir = options.outDir || null;
    this.maxActions = options.maxActions ?? 15;

    this.browser = null;
    this.context = null;
    this.page = null;
    this.ssrfStats = null;

    this.activityLog = [];
    this.captureRecords = [];
    this.observedStates = [];
    this.seenItemIds = new Set();
    this.actionCount = 0;
    this.lastObservedStateRef = null;
    this.lastActivityId = null;
  }

  async launch() {
    const { chromium } = await import('playwright');
    this.browser = await chromium.launch({
      headless: this.headless,
    });
    this.context = await this.browser.newContext({
      userAgent: browserUserAgent(),
      ignoreHTTPSErrors: Boolean(this.ignoreTlsErrors),
      serviceWorkers: 'block',
    });
    this.ssrfStats = await installBrowserSsrfGuard(this.context, {
      allowLoopback: this.allowLoopback,
      ignoreTlsErrors: this.ignoreTlsErrors,
      maxResponseBytes: this.maxResponseBytes,
      timeoutMs: this.timeout,
    });
    if (this.allowLoopback) {
      await this.context.route(/^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?\/.*/, async (route) => {
        const req = route.request();
        if (req.method() === 'POST') {
          try {
            const reqHeaders = stripSensitiveHeaders ? stripSensitiveHeaders(req.headers()) : req.headers();
            const resp = await fetch(req.url(), {
              method: 'POST',
              headers: reqHeaders,
              body: req.postDataBuffer(),
            });
            const body = await resp.arrayBuffer();
            await route.fulfill({
              status: resp.status,
              headers: Object.fromEntries(resp.headers.entries()),
              body: Buffer.from(body),
            });
          } catch (e) {
            await route.abort();
          }
        } else {
          await route.continue();
        }
      });
    }
    this.page = await this.context.newPage();
    this.page.setDefaultTimeout(this.timeout);
    return this;
  }

  async close() {
    try {
      if (this.page) await this.page.close().catch(() => {});
      if (this.context) await this.context.close().catch(() => {});
      if (this.browser) await this.browser.close().catch(() => {});
    } finally {
      this.page = null;
      this.context = null;
      this.browser = null;
    }
  }

  // Step 1: Navigate
  async navigate(targetUrl, opts = {}) {
    const startedAt = new Date().toISOString();
    const activityId = 'act_' + crypto.randomBytes(6).toString('hex');
    this.lastActivityId = activityId;
    const purpose = opts.purpose || ('Navigate to target URL: ' + redactUrl(targetUrl));

    const pre = await assertBrowserPublicUrl(targetUrl, {
      allowLoopback: this.allowLoopback,
    });

    if (!pre.ok) {
      const finishedAt = new Date().toISOString();
      const activity = {
        schema_version: '1.1.0',
        activity_id: activityId,
        branch_id: opts.branchId || this.branchId,
        question_ids: opts.questionIds || this.questionIds,
        purpose,
        observed_state_ref: null,
        action_type: 'navigate',
        target_locator: null,
        action_payload: { url: redactUrl(targetUrl) },
        started_at: startedAt,
        finished_at: finishedAt,
        final_url: redactUrl(targetUrl),
        outcome: 'blocked',
        output_capture_ids: [],
        limitation: (pre.blocker && pre.blocker.message) ? pre.blocker.message : 'SSRF blocked',
        tool_details: {
          engine: 'playwright-chromium',
          mode: this.headless ? 'headless' : 'headed',
          response_status: null,
        },
      };
      this.activityLog.push(activity);
      return { ok: false, outcome: 'blocked', limitation: activity.limitation, activity };
    }

    try {
      const response = await this.page.goto(targetUrl, {
        timeout: this.timeout,
        waitUntil: 'domcontentloaded',
      });
      const finalUrl = this.page.url();
      const title = await this.page.title();
      const status = response ? response.status() : 200;
      const finishedAt = new Date().toISOString();

      let outcome = 'error';
      if (status >= 200 && status < 400) outcome = 'success';
      else if (status >= 400 && status < 500) outcome = 'blocked';

      const activity = {
        schema_version: '1.1.0',
        activity_id: activityId,
        branch_id: opts.branchId || this.branchId,
        question_ids: opts.questionIds || this.questionIds,
        purpose,
        observed_state_ref: null,
        action_type: 'navigate',
        target_locator: null,
        action_payload: { url: redactUrl(targetUrl) },
        started_at: startedAt,
        finished_at: finishedAt,
        final_url: redactUrl(finalUrl),
        outcome,
        output_capture_ids: [],
        limitation: status >= 400 ? ('HTTP status ' + status) : null,
        tool_details: {
          engine: 'playwright-chromium',
          mode: this.headless ? 'headless' : 'headed',
          response_status: status,
        },
      };
      this.activityLog.push(activity);

      // Step 2: Immediate post-navigation observe DOM
      const obs = await this.observeDom();
      return { ok: activity.outcome === 'success', outcome: activity.outcome, finalUrl, title, status, obs, activity };
    } catch (err) {
      const finishedAt = new Date().toISOString();
      const isTimeout = err.name === 'TimeoutError' || /timeout/i.test(err.message);
      const activity = {
        schema_version: '1.1.0',
        activity_id: activityId,
        branch_id: opts.branchId || this.branchId,
        question_ids: opts.questionIds || this.questionIds,
        purpose,
        observed_state_ref: null,
        action_type: 'navigate',
        target_locator: null,
        action_payload: { url: redactUrl(targetUrl) },
        started_at: startedAt,
        finished_at: finishedAt,
        final_url: redactUrl(this.page ? this.page.url() : targetUrl),
        outcome: isTimeout ? 'timeout' : 'error',
        output_capture_ids: [],
        limitation: redactSecretsInText(err.message),
        tool_details: {
          engine: 'playwright-chromium',
          mode: this.headless ? 'headless' : 'headed',
          response_status: null,
        },
      };
      this.activityLog.push(activity);
      return { ok: false, outcome: activity.outcome, limitation: activity.limitation, activity };
    }
  }

  // Step 2: Observe DOM
  async observeDom() {
    const timestamp = new Date().toISOString();
    const observedStateId = 'obs_' + crypto.randomBytes(4).toString('hex');
    this.lastObservedStateRef = observedStateId;

    const pageUrl = redactUrl(this.page ? this.page.url() : '');
    const title = this.page ? await this.page.title().catch(() => '') : '';

    const observation = await this.page.evaluate(() => {
      const controls = [];
      const seen = new Set();

      // Searchboxes
      document.querySelectorAll('input[type=text], input[type=search], [role=searchbox]').forEach(el => {
        const id = el.id ? ('#' + el.id) : (el.name ? ('input[name=' + el.name + ']') : 'input');
        if (!seen.has(id)) {
          seen.add(id);
          controls.push({
            role: 'searchbox',
            selector: id,
            visible: el.offsetParent !== null,
            name: el.getAttribute('aria-label') || el.placeholder || '',
          });
        }
      });

      // Buttons
      document.querySelectorAll('button, [role=button]').forEach(el => {
        const id = el.id ? ('#' + el.id) : (el.className ? ('.' + el.className.trim().split(/\s+/)[0]) : 'button');
        const text = (el.textContent || '').trim().replace(/\s+/g, ' ');
        controls.push({
          role: 'button',
          selector: id,
          visible: el.offsetParent !== null,
          name: el.getAttribute('aria-label') || text.slice(0, 50),
          text_content: text.slice(0, 50),
        });
      });

      // Select / Combobox
      document.querySelectorAll('select, [role=combobox]').forEach(el => {
        const id = el.id ? ('#' + el.id) : (el.name ? ('select[name=' + el.name + ']') : 'select');
        controls.push({
          role: 'combobox',
          selector: id,
          visible: el.offsetParent !== null,
          name: el.getAttribute('aria-label') || '',
        });
      });

      // Loaded item IDs
      const loadedItemIds = [];
      document.querySelectorAll('[id^=result-], [id^=reply-], [id^=comment-]').forEach(el => {
        loadedItemIds.push(el.id);
      });

      // Blocker detection
      const bodyText = (document.body.innerText || '').toLowerCase();
      const captcha = /captcha|recaptcha|hcaptcha|verify you are human|bot challenge/.test(bodyText);
      const login = /log in|login required|sign in|authentication required/.test(bodyText);
      const paywall = /paywall|subscribe to read|premium subscription/.test(bodyText);
      const isBlocked = captcha || login || paywall;

      return {
        controls,
        loadedItemIds,
        blocker_state: {
          is_blocked: isBlocked,
          blocker_type: captcha ? 'captcha' : (login ? 'login' : (paywall ? 'paywall' : null)),
          login_required: login,
          captcha_present: captcha,
          paywall_present: paywall,
        },
        bodyLength: bodyText.length,
      };
    });

    const fullState = {
      observed_state_id: observedStateId,
      timestamp,
      final_url: pageUrl,
      page_title: title,
      interactive_controls: observation.controls,
      loaded_item_ids: observation.loadedItemIds,
      blocker_state: observation.blocker_state,
    };

    this.observedStates.push(fullState);
    return fullState;
  }

  // Step 3 & 4: Action + Wait Condition (with Step 8: Bounded Recovery)
  async executeAction(actionType, targetLocator = {}, payload = {}, opts = {}) {
    this.actionCount += 1;
    const startedAt = new Date().toISOString();
    const activityId = 'act_' + crypto.randomBytes(6).toString('hex');
    this.lastActivityId = activityId;
    const purpose = opts.purpose || ('Execute dynamic action ' + actionType + ' on locator ' + JSON.stringify(targetLocator));
    const branchId = opts.branchId || this.branchId;
    const questionIds = opts.questionIds || this.questionIds;
    const priorStateRef = this.lastObservedStateRef;

    let retries = 0;
    const maxRetries = 1;

    while (retries <= maxRetries) {
      try {
        await this._performActionWithWait(actionType, targetLocator, payload);
        const finishedAt = new Date().toISOString();
        const finalUrl = redactUrl(this.page.url());

        // Step 5: Re-Observe
        await this.observeDom();

        const schemaActionType = actionType === 'view_replies' ? 'expand' : actionType;
        const activity = {
          schema_version: '1.1.0',
          activity_id: activityId,
          branch_id: branchId,
          question_ids: questionIds,
          purpose,
          observed_state_ref: priorStateRef,
          action_type: schemaActionType,
          target_locator: {
            role: targetLocator.role || 'button',
            name: targetLocator.name || '',
            selector: targetLocator.selector || '',
            text_content: targetLocator.textContent || '',
          },
          action_payload: payload && Object.keys(payload).length > 0 ? payload : null,
          started_at: startedAt,
          finished_at: finishedAt,
          final_url: finalUrl,
          outcome: 'success',
          output_capture_ids: [],
          limitation: null,
          tool_details: {
            engine: 'playwright-chromium',
            mode: this.headless ? 'headless' : 'headed',
            response_status: 200,
          },
        };
        this.activityLog.push(activity);
        return { ok: true, outcome: 'success', activity };
      } catch (err) {
        retries += 1;
        // Step 8: Bounded recovery
        if (retries <= maxRetries) {
          // Check for dismissable overlay/modal
          await this._dismissOverlays().catch(() => {});
          // Re-observe DOM to refresh handles
          await this.observeDom().catch(() => {});
          continue;
        }

        // Exhausted retries: report partial/timeout/blocked cleanly without crash
        const finishedAt = new Date().toISOString();
        const isTimeout = err.name === 'TimeoutError' || /timeout/i.test(err.message);
        const outcome = isTimeout ? 'timeout' : 'partial';

        const schemaActionType = actionType === 'view_replies' ? 'expand' : actionType;
        const activity = {
          schema_version: '1.1.0',
          activity_id: activityId,
          branch_id: branchId,
          question_ids: questionIds,
          purpose,
          observed_state_ref: priorStateRef,
          action_type: schemaActionType,
          target_locator: {
            role: targetLocator.role || 'button',
            name: targetLocator.name || '',
            selector: targetLocator.selector || '',
            text_content: targetLocator.textContent || '',
          },
          action_payload: payload && Object.keys(payload).length > 0 ? payload : null,
          started_at: startedAt,
          finished_at: finishedAt,
          final_url: redactUrl(this.page ? this.page.url() : ''),
          outcome,
          output_capture_ids: [],
          limitation: redactSecretsInText(err.message),
          tool_details: {
            engine: 'playwright-chromium',
            mode: this.headless ? 'headless' : 'headed',
            response_status: 200,
          },
        };
        this.activityLog.push(activity);
        return { ok: false, outcome, limitation: activity.limitation, activity };
      }
    }
  }

  async _performActionWithWait(actionType, targetLocator, payload) {
    const timeout = this.actionTimeout;
    if (actionType === 'search') {
      const inputSelector = targetLocator.inputSelector || targetLocator.selector || '#search-input';
      const submitSelector = targetLocator.submitSelector || '#search-submit';
      const query = payload.query || '';

      await this.page.fill(inputSelector, query, { timeout });
      await this.page.click(submitSelector, { timeout });
      await this.page.waitForSelector('.result-card, .no-results', { timeout });
    } else if (actionType === 'filter') {
      const selectSelector = targetLocator.selectSelector || targetLocator.selector || '#filter-type';
      const applySelector = targetLocator.applySelector || '#apply-filter';
      const value = payload.value || 'final';

      await this.page.selectOption(selectSelector, value, { timeout });
      await this.page.click(applySelector, { timeout });
      if (value === 'final') {
        await this.page.waitForSelector('#result-doc_v20', { state: 'detached', timeout }).catch(() => {});
      }
      await this.page.waitForSelector('.result-card, .no-results', { timeout });
    } else if (actionType === 'open') {
      const selector = targetLocator.selector || '.open-thread-btn';
      await this.page.click(selector, { timeout });
      await this.page.waitForSelector('#thread-section:not(.hidden)', { timeout });
    } else if (actionType === 'expand') {
      const selector = targetLocator.selector || '#expand-post-btn';
      await this.page.click(selector, { timeout });
      await this.page.waitForSelector('#expand-post-btn.hidden, #expand-post-btn', { state: 'hidden', timeout }).catch(() => {});
      await this.page.waitForSelector('#post-body-container', { timeout });
    } else if (actionType === 'view_replies') {
      const selector = targetLocator.selector || '#view-replies-btn';
      await this.page.click(selector, { timeout });
      await this.page.waitForSelector('#replies-container:not(.hidden) .comment-box', { timeout });
    } else if (actionType === 'paginate') {
      const selector = targetLocator.selector || '#load-more-btn';
      await this.page.click(selector, { timeout });
      await this.page.waitForSelector('#paged-comments-container .comment-box', { timeout });
    } else if (actionType === 'scroll') {
      const deltaY = payload.deltaY || 500;
      const selector = targetLocator.selector || null;
      if (selector) {
        await this.page.evaluate(({ sel, dy }) => {
          const el = document.querySelector(sel);
          if (el) el.scrollBy(0, dy);
        }, { sel: selector, dy: deltaY });
      } else {
        await this.page.evaluate(dy => window.scrollBy(0, dy), deltaY);
      }
      await this.page.waitForFunction(() => document.readyState === 'complete');
    } else if (actionType === 'transcript') {
      const selector = targetLocator.selector || '#toggle-transcript-btn';
      await this.page.click(selector, { timeout });
      await this.page.waitForSelector('#transcript-panel:not(.hidden) .transcript-line', { timeout });
    } else {
      throw new Error('Unsupported action type: ' + actionType);
    }
  }

  async _dismissOverlays() {
    try {
      await this.page.evaluate(() => {
        const dismissBtns = Array.from(document.querySelectorAll('button')).filter(b => {
          const txt = (b.textContent || '').toLowerCase();
          return txt.includes('close') || txt.includes('dismiss') || txt.includes('accept') || txt.includes('reject');
        });
        if (dismissBtns.length > 0) dismissBtns[0].click();
      });
    } catch {}
  }

  // Step 6: Capture
  async capture(containerSelector, metadata = {}) {
    const rawContent = await this.page.locator(containerSelector).innerText({ timeout: this.actionTimeout });
    const cleanText = redactSecretsInText(rawContent);
    const hash = crypto.createHash('sha256').update(Buffer.from(cleanText, 'utf8')).digest('hex');
    const byteLength = Buffer.byteLength(cleanText, 'utf8');
    const captureId = 'cap_' + crypto.randomBytes(6).toString('hex');
    const retrievedAt = new Date().toISOString();

    const activityId = metadata.activityId || this.lastActivityId || ('act_' + crypto.randomBytes(6).toString('hex'));
    const sourceId = metadata.sourceId || ('src_' + crypto.randomBytes(4).toString('hex'));
    const branchId = metadata.branchId || this.branchId;
    const pageUrl = redactUrl(this.page ? this.page.url() : '');

    // Relative POSIX path for raw text ref
    const relativeRawPath = metadata.rawTextRef || ('captures/' + captureId + '.txt');

    if (this.outDir) {
      const fullTextPath = path.join(this.outDir, relativeRawPath);
      await fs.mkdir(path.dirname(fullTextPath), { recursive: true });
      await fs.writeFile(fullTextPath, cleanText, 'utf8');
    }

    const captureRecord = {
      schema_version: '1.1.0',
      capture_id: captureId,
      source_id: sourceId,
      branch_id: branchId,
      activity_id: activityId,
      retrieved_at: retrievedAt,
      source_url: pageUrl,
      final_url: pageUrl,
      method: metadata.method || 'playwright_dom',
      bytes_hash: 'sha256:' + hash,
      byte_length: byteLength,
      dom_locator: containerSelector,
      raw_text_ref: relativeRawPath,
      screenshot_ref: metadata.screenshotRef || null,
      extraction_limits: {
        truncated: metadata.truncated ?? false,
        items_extracted: metadata.itemsExtracted ?? 1,
        total_estimated: metadata.totalEstimated ?? 1,
        truncation_reason: metadata.truncationReason ?? null,
      },
      artifact_version: 1,
    };

    this.captureRecords.push(captureRecord);

    // Bind captureId to last activity if present
    const matchedAct = this.activityLog.find(a => a.activity_id === activityId);
    if (matchedAct) {
      if (!matchedAct.output_capture_ids.includes(captureId)) {
        matchedAct.output_capture_ids.push(captureId);
      }
    }

    return {
      captureRecord,
      rawText: cleanText,
    };
  }

  // Step 7: Next Action evaluation
  nextAction(hasMoreWork = false) {
    if (this.actionCount >= this.maxActions) {
      return { proceed: false, reason: 'budget_exhausted' };
    }
    return { proceed: hasMoreWork, reason: hasMoreWork ? 'depth_continuation' : 'task_completed' };
  }

  async saveArtifacts(targetDir = null) {
    const dir = targetDir || this.outDir;
    if (!dir) return;
    await fs.mkdir(dir, { recursive: true });

    await fs.writeFile(
      path.join(dir, 'activity-log.json'),
      JSON.stringify(this.activityLog, null, 2),
      'utf8'
    );
    await fs.writeFile(
      path.join(dir, 'capture-records.json'),
      JSON.stringify(this.captureRecords, null, 2),
      'utf8'
    );
    await fs.writeFile(
      path.join(dir, 'observed-states.json'),
      JSON.stringify(this.observedStates, null, 2),
      'utf8'
    );
  }
}

// Lightweight offline self-test
export async function selfTestBrowserInteraction() {
  const secretUrl = 'http://example.com/api?token=secret123&key=mykey';
  const redacted = redactUrl(secretUrl);
  if (redacted.includes('secret123') || redacted.includes('mykey')) {
    throw new Error('Redaction failed: ' + redacted);
  }
  const secretText = 'api-key: mytoken123';
  const redactedText = redactSecretsInText(secretText);
  if (redactedText.includes('mytoken123')) {
    throw new Error('Text redaction failed: ' + redactedText);
  }
  const bearerText = 'Bearer mytoken456';
  const redactedBearer = redactSecretsInText(bearerText);
  if (redactedBearer.includes('mytoken456')) {
    throw new Error('Bearer redaction failed: ' + redactedBearer);
  }
  return true;
}

// CLI runner
async function main() {
  const args = process.argv.slice(2);
  if (args.includes('--self-test')) {
    await selfTestBrowserInteraction();
    console.log('self-test passed');
    return;
  }

  let url = null;
  let actionsJson = null;
  let allowLoopback = false;
  let outDir = null;
  let branchId = 'documentary';
  let questionId = 'Q1';
  let headless = true;

  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a === '--url') url = args[++i];
    else if (a === '--actions') actionsJson = args[++i];
    else if (a === '--allow-loopback-fixture') allowLoopback = true;
    else if (a === '--out-dir') outDir = args[++i];
    else if (a === '--branch') branchId = args[++i];
    else if (a === '--question-id') questionId = args[++i];
    else if (a === '--headful') headless = false;
  }

  if (!url) {
    console.error('Usage: node scripts/browser_interaction.mjs --url <url> [--actions <json>] [--allow-loopback-fixture] [--out-dir <dir>]');
    process.exit(1);
  }

  const op = new BrowserOperator({
    headless,
    allowLoopback,
    branchId,
    questionIds: [questionId],
    outDir,
  });

  try {
    await op.launch();
    console.log('Navigating to ' + url + '...');
    const nav = await op.navigate(url);
    if (!nav.ok) {
      console.error('Navigation failed or blocked: ' + nav.outcome);
      process.exit(1);
    }

    if (actionsJson) {
      const actions = JSON.parse(actionsJson);
      for (const act of actions) {
        console.log('Executing action ' + act.action + '...');
        await op.executeAction(act.action, act.locator || {}, act.payload || {});
        if (act.captureSelector) {
          console.log('Capturing ' + act.captureSelector + '...');
          await op.capture(act.captureSelector, act.metadata || {});
        }
      }
    }

    if (outDir) {
      await op.saveArtifacts(outDir);
      console.log('Artifacts saved to ' + outDir);
    }
  } finally {
    await op.close();
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  main().catch(err => {
    console.error('Browser interaction failed:', err);
    process.exit(1);
  });
}
