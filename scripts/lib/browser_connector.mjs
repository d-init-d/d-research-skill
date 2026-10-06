// Centralized browser lifecycle connector supporting standalone Chromium,
// Chrome DevTools Protocol (CDP) session attachment, and automated fallback.
// Enforces strict resource ownership, idempotent cleanup, and SSRF routing guards.

import { existsSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import {
  assertBrowserPublicUrl,
  installBrowserSsrfGuard,
  isTaskPageOrDescendant,
  structuredBlocker,
} from './browser_ssrf.mjs';
import { browserUserAgent } from './package_metadata.mjs';
import { resolveBrowserResponseLimit } from './browser_limits.mjs';

export function resolveCdpEndpoint(cliEndpoint) {
  if (cliEndpoint && typeof cliEndpoint === 'string' && cliEndpoint.trim()) {
    return cliEndpoint.trim();
  }
  const envEndpoint = process.env.D_RESEARCH_CDP_URL;
  if (envEndpoint && typeof envEndpoint === 'string' && envEndpoint.trim()) {
    return envEndpoint.trim();
  }
  return null;
}

export function validateBrowserMode(mode) {
  const normalized = String(mode || 'standalone').toLowerCase().trim();
  if (!['standalone', 'cdp', 'auto'].includes(normalized)) {
    throw new Error(`Invalid --browser-mode: ${mode}. Must be one of standalone, cdp, auto`);
  }
  return normalized;
}

export function assertCdpEndpointAllowed(endpoint) {
  if (!endpoint) return;
  let parsed;
  try {
    parsed = new URL(endpoint);
  } catch {
    throw new Error(`Invalid CDP endpoint URL: ${endpoint}`);
  }
  const host = (parsed.hostname || '').toLowerCase().replace(/^\[|\]$/g, '');
  const isLoopback = host === 'localhost' || host === '127.0.0.1' || host === '::1' || host.endsWith('.localhost');
  if (!isLoopback && process.env.D_RESEARCH_ALLOW_REMOTE_CDP !== '1') {
    const blocker = structuredBlocker(
      'cdp_remote_endpoint_forbidden',
      `CDP endpoint must be a local loopback address (127.0.0.1 or localhost), got: ${host}`,
      { host }
    );
    const error = new Error(blocker.message);
    error.code = blocker.code;
    error.blocker = blocker;
    throw error;
  }
}

export async function releaseBrowserSession(session) {
  if (!session || session.released) return;
  session.released = true;

  if (typeof session.cleanupListeners === 'function') {
    try { session.cleanupListeners(); } catch {}
  }

  if (session.trackedPages) {
    for (const p of session.trackedPages) {
      if (p && typeof p.isClosed === 'function' && !p.isClosed()) {
        try {
          await p.close();
        } catch {
          // ignore close failure
        }
      }
    }
  }

  if (session.unrouteOnRelease && session.context && typeof session.context.unroute === 'function') {
    try {
      if (typeof session.unrouteHandler === 'function') {
        await session.context.unroute('**/*', session.unrouteHandler);
      } else {
        await session.context.unroute('**/*');
      }
    } catch {}
  }

  const { ownership, page, context, browser } = session;

  if (ownership?.ownsPage && page && typeof page.isClosed === 'function' && !page.isClosed()) {
    try {
      await page.close();
    } catch {
      // ignore idempotent close failure
    }
  }

  if (ownership?.ownsContext && context) {
    try {
      await context.close();
    } catch {
      // ignore idempotent close failure
    }
  }

  if (ownership?.ownsBrowser && browser) {
    try {
      await browser.close();
    } catch {
      // ignore idempotent close failure
    }
  } else if (ownership?.isCdp && browser) {
    // Disconnect client without terminating host/remote browser
    try {
      if (typeof browser.disconnect === 'function') {
        await browser.disconnect();
      } else if (typeof browser.close === 'function') {
        await browser.close();
      }
    } catch {
      // ignore idempotent disconnect failure
    }
  }

  session.page = null;
  session.context = null;
  session.browser = null;
}

/**
 * Acquire a browser session according to requested mode.
 *
 * @param {object} options
 * @param {string} [options.browserMode='standalone'] 'standalone' | 'cdp' | 'auto'
 * @param {string} [options.cdpEndpoint] Explicit CDP endpoint URL
 * @param {boolean} [options.reuseSession=false] In CDP mode, reuse existing user context if available
 * @param {boolean} [options.headless=true] For standalone launches
 * @param {number} [options.timeout=30000] Default operation timeout in ms
 * @param {boolean} [options.ignoreTlsErrors=false]
 * @param {boolean} [options.allowLoopbackFixture=false]
 * @param {number|null} [options.maxResponseBytes=null]
 * @param {string} [options.userAgent]
 * @param {boolean} [options.installSsrf=true]
 * @returns {Promise<object>} Session object with browser, context, page, ownership, release()
 */
export async function acquireBrowserSession(options = {}) {
  const browserMode = validateBrowserMode(options.browserMode || options.mode || 'standalone');
  const cdpEndpoint = resolveCdpEndpoint(options.cdpEndpoint);
  const reuseSession = Boolean(options.reuseSession);
  const headless = options.headless ?? true;
  const timeout = options.timeout ?? 30000;
  const ignoreTlsErrors = Boolean(options.ignoreTlsErrors);
  const allowLoopbackFixture = Boolean(options.allowLoopbackFixture);
  const maxResponseBytes = resolveBrowserResponseLimit(options.maxResponseBytes);
  const userAgent = options.userAgent || browserUserAgent();
  const installSsrf = options.installSsrf !== false;

  if (browserMode === 'cdp' && !cdpEndpoint) {
    const blocker = structuredBlocker(
      'missing_cdp_endpoint',
      'CDP mode requested but no endpoint specified via --cdp-endpoint or D_RESEARCH_CDP_URL',
    );
    const error = new Error(blocker.message);
    error.code = blocker.code;
    error.blocker = blocker;
    throw error;
  }

  if (cdpEndpoint) {
    assertCdpEndpointAllowed(cdpEndpoint);
  }

  let chromiumModule;
  try {
    chromiumModule = await import('playwright');
  } catch (err) {
    const blocker = structuredBlocker(
      'missing_playwright_dependency',
      `Playwright package unavailable: ${err.message}`,
    );
    const error = new Error(blocker.message);
    error.code = blocker.code;
    error.blocker = blocker;
    throw error;
  }

  const attempts = [];
  const limitations = [];
  let browser = null;
  let context = null;
  let page = null;
  let effectiveMode = browserMode;
  let ownsBrowser = false;
  let ownsContext = false;
  let ownsPage = false;
  let taskPages = null;
  let cleanupListeners = null;
  let unrouteOnRelease = false;

  if (browserMode === 'cdp') {
    try {
      browser = await chromiumModule.chromium.connectOverCDP(cdpEndpoint, { timeout });
      effectiveMode = 'cdp';
      ownsBrowser = false;
    } catch (err) {
      const blocker = structuredBlocker(
        'cdp_connection_failed',
        `Failed to connect to CDP endpoint ${cdpEndpoint}: ${err.message}`,
      );
      const error = new Error(blocker.message);
      error.code = blocker.code;
      error.blocker = blocker;
      throw error;
    }
  } else if (browserMode === 'auto') {
    if (cdpEndpoint) {
      try {
        browser = await chromiumModule.chromium.connectOverCDP(cdpEndpoint, { timeout });
        effectiveMode = 'cdp';
        ownsBrowser = false;
      } catch (err) {
        attempts.push({
          mode: 'cdp',
          endpoint: cdpEndpoint,
          status: 'failed',
          error: err.message,
        });
        limitations.push('cdp_auto_fallback_to_standalone');
        effectiveMode = 'standalone';
      }
    } else {
      effectiveMode = 'standalone';
    }
  }

  if (!browser && effectiveMode === 'standalone') {
    try {
      browser = await chromiumModule.chromium.launch({ headless });
      ownsBrowser = true;
    } catch (err) {
      const blocker = structuredBlocker(
        'browser_launch_failure',
        `Chromium launch failed: ${err.message}`,
      );
      const error = new Error(blocker.message);
      error.code = blocker.code;
      error.blocker = blocker;
      throw error;
    }
  }

  let ssrfStats = null;
  try {
    if (effectiveMode === 'cdp' && reuseSession) {
      const contexts = browser.contexts();
      const existingPages = new Set();
      if (contexts.length > 0) {
        context = contexts[0];
        ownsContext = false;
        for (const p of context.pages()) existingPages.add(p);
      } else {
        context = await browser.newContext({
          ignoreHTTPSErrors: ignoreTlsErrors,
          serviceWorkers: 'block',
          userAgent,
        });
        ownsContext = true;
      }
      page = await context.newPage();
      ownsPage = true;
      page.setDefaultTimeout(timeout);

      taskPages = new Set([page]);
      const onPopup = (popup) => {
        taskPages.add(popup);
        try { popup.on('popup', onPopup); } catch {}
      };
      const onPage = async (newPage) => {
        try {
          if (await isTaskPageOrDescendant(newPage, taskPages)) {
            taskPages.add(newPage);
            newPage.on('popup', onPopup);
          }
        } catch {}
      };
      page.on('popup', onPopup);
      context.on('page', onPage);
      cleanupListeners = () => {
        page.off('popup', onPopup);
        context.off('page', onPage);
      };
      unrouteOnRelease = true;

      if (installSsrf) {
        ssrfStats = await installBrowserSsrfGuard(context, {
          allowLoopback: allowLoopbackFixture,
          ignoreTlsErrors,
          maxResponseBytes,
          timeoutMs: timeout,
          taskPages,
        });
      }
    } else {
      // Isolated context
      context = await browser.newContext({
        ignoreHTTPSErrors: ignoreTlsErrors,
        serviceWorkers: 'block',
        userAgent,
      });
      ownsContext = true;
      page = await context.newPage();
      ownsPage = true;
      page.setDefaultTimeout(timeout);

      if (installSsrf) {
        ssrfStats = await installBrowserSsrfGuard(context, {
          allowLoopback: allowLoopbackFixture,
          ignoreTlsErrors,
          maxResponseBytes,
          timeoutMs: timeout,
        });
      }
    }
  } catch (err) {
    const partialSession = {
      browser,
      context,
      page,
      ownership: { isCdp: effectiveMode === 'cdp', ownsBrowser, ownsContext, ownsPage },
      trackedPages: taskPages,
      cleanupListeners,
      unrouteOnRelease,
      unrouteHandler: ssrfStats?.routeHandler || null,
      released: false,
    };
    await releaseBrowserSession(partialSession);
    throw err;
  }

  if (ignoreTlsErrors) {
    limitations.push('ignore_tls_errors_enabled');
  }

  const session = {
    browser,
    context,
    page,
    ownership: {
      isCdp: effectiveMode === 'cdp',
      ownsBrowser,
      ownsContext,
      ownsPage,
    },
    trackedPages: taskPages,
    cleanupListeners,
    unrouteOnRelease,
    unrouteHandler: ssrfStats?.routeHandler || null,
    mode: effectiveMode,
    endpoint: effectiveMode === 'cdp' ? cdpEndpoint : null,
    limitations: [...new Set(limitations)],
    attempts,
    ssrfStats,
    released: false,
    async release() {
      await releaseBrowserSession(session);
    },
  };

  return session;
}

export async function selfTest() {
  const errors = [];

  // 1. Mode validator
  try {
    if (validateBrowserMode('standalone') !== 'standalone') errors.push('mode standalone failed');
    if (validateBrowserMode('CDP') !== 'cdp') errors.push('mode cdp failed');
    if (validateBrowserMode('auto') !== 'auto') errors.push('mode auto failed');
  } catch (e) {
    errors.push(`valid modes rejected: ${e.message}`);
  }
  try {
    validateBrowserMode('invalid_mode');
    errors.push('invalid mode was not rejected');
  } catch {
    // expected
  }

  // 2. Endpoint resolution
  if (resolveCdpEndpoint('http://localhost:9222') !== 'http://localhost:9222') {
    errors.push('cli endpoint resolution failed');
  }
  const oldEnv = process.env.D_RESEARCH_CDP_URL;
  process.env.D_RESEARCH_CDP_URL = 'http://localhost:9333';
  if (resolveCdpEndpoint() !== 'http://localhost:9333') {
    errors.push('env endpoint resolution failed');
  }
  if (resolveCdpEndpoint('http://localhost:9444') !== 'http://localhost:9444') {
    errors.push('cli endpoint should take precedence over env');
  }
  if (oldEnv === undefined) delete process.env.D_RESEARCH_CDP_URL;
  else process.env.D_RESEARCH_CDP_URL = oldEnv;

  // 3. CDP mode without endpoint fails explicitly
  try {
    await acquireBrowserSession({ browserMode: 'cdp', cdpEndpoint: null });
    errors.push('cdp mode without endpoint did not throw');
  } catch (err) {
    if (err?.code !== 'missing_cdp_endpoint' && err?.blocker?.code !== 'missing_cdp_endpoint') {
      errors.push(`expected missing_cdp_endpoint, got: ${err.message}`);
    }
  }

  // The package and browser binary are separate optional capabilities.
  let playwrightAvailable = false;
  try {
    const { chromium } = await import('playwright');
    playwrightAvailable = existsSync(chromium.executablePath());
  } catch {
    playwrightAvailable = false;
  }

  if (!playwrightAvailable) {
    console.log('browser lifecycle DELEGATED: CAPABILITY_BROWSER (Playwright or Chromium binary unavailable)');
  } else {
    // 4. Standalone launch & release lifecycle
    try {
      const session = await acquireBrowserSession({
        browserMode: 'standalone',
        headless: true,
        allowLoopbackFixture: true,
      });
      if (!session.ownership.ownsBrowser) errors.push('standalone should own browser');
      if (!session.ownership.ownsContext) errors.push('standalone should own context');
      if (!session.ownership.ownsPage) errors.push('standalone should own page');
      if (session.ownership.isCdp) errors.push('standalone should not be cdp');
      if (!session.page) errors.push('session page should be defined');

      await session.release();
      if (!session.released) errors.push('session should be marked released');
      // Idempotent second release
      await session.release();
    } catch (err) {
      errors.push(`standalone lifecycle failed: ${err.message}`);
    }

    // 5. CDP connection over local debugging port & ownership test
    try {
      const { chromium } = await import('playwright');
      const hostBrowser = await chromium.launch({
        headless: true,
        args: ['--remote-debugging-port=9455'],
      });
      const hostContext = await hostBrowser.newContext();
      const hostPage = await hostContext.newPage();
      await hostPage.setContent('<html><body>User Tab</body></html>');

      try {
        // Connect with reuseSession: true
        const cdpSession = await acquireBrowserSession({
          browserMode: 'cdp',
          cdpEndpoint: 'http://127.0.0.1:9455',
          reuseSession: true,
          allowLoopbackFixture: true,
        });

        if (cdpSession.ownership.ownsBrowser) errors.push('cdp session must not own browser');
        if (cdpSession.ownership.ownsContext) errors.push('reused cdp session must not own context');
        if (!cdpSession.ownership.ownsPage) errors.push('cdp session must own page');
        if (!cdpSession.ownership.isCdp) errors.push('cdp session should have isCdp=true');

        // Release cdp session
        await cdpSession.release();

        // Verify host browser and user tab are still alive and unaffected
        if (!hostBrowser.isConnected()) errors.push('host browser was killed on cdp release');
        const hostText = await hostPage.textContent('body');
        if (hostText !== 'User Tab') errors.push('user tab was corrupted or closed');
      } finally {
        await hostBrowser.close();
      }
    } catch (err) {
      errors.push(`cdp lifecycle test failed: ${err.message}`);
    }
  }

  if (errors.length) {
    console.error('browser_connector.mjs self-test FAILED:');
    for (const e of errors) console.error(`  - ${e}`);
    process.exitCode = 1;
    return 1;
  }
  console.log('browser_connector.mjs self-test ok');
  return 0;
}

const _isMain = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (_isMain && process.argv.includes('--self-test')) {
  selfTest();
}
