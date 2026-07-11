const DEFAULT_MAX_RESPONSE_BYTES = 20 * 1024 * 1024;

export class BrowserResourceLimitError extends Error {
  constructor({ url, limit, observed = null, detail = null }) {
    super(detail || `browser response exceeds ${limit} bytes`);
    this.name = 'BrowserResourceLimitError';
    this.code = 'http_max_bytes';
    this.url = url || null;
    this.limit = limit;
    this.observed = observed;
    this.exitCode = 3;
  }

  toJSON() {
    return {
      error: 'resource_limit',
      code: this.code,
      message: this.message,
      url: this.url,
      limit: this.limit,
      observed: this.observed,
      incomplete: true,
      complete: false,
    };
  }
}

export function resolveBrowserResponseLimit(cliValue = null, env = process.env) {
  const raw = cliValue ?? env.D_RESEARCH_HTTP_MAX_BYTES ?? DEFAULT_MAX_RESPONSE_BYTES;
  const parsed = typeof raw === 'number' ? raw : Number(String(raw).trim());
  if (!Number.isSafeInteger(parsed) || parsed < 1) {
    throw new Error('--max-response-bytes/D_RESEARCH_HTTP_MAX_BYTES must be a positive integer');
  }
  return parsed;
}

function parseContentLength(response) {
  const raw = response?.headers()?.['content-length'];
  if (typeof raw !== 'string' || !/^\d+$/.test(raw.trim())) return null;
  const parsed = Number(raw);
  return Number.isSafeInteger(parsed) ? parsed : null;
}

async function withTimeout(promise, timeoutMs) {
  let timer;
  try {
    return await Promise.race([
      promise,
      new Promise((_, reject) => {
        timer = setTimeout(
          () => reject(new Error(`response size inspection timed out after ${timeoutMs}ms`)),
          timeoutMs,
        );
      }),
    ]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

export async function enforceBrowserResponseLimit(response, limit, timeoutMs) {
  if (!response) return 0;
  const url = response.url();
  const declared = parseContentLength(response);
  if (declared !== null && declared > limit) {
    throw new BrowserResourceLimitError({ url, limit, observed: declared });
  }

  let observed = declared;
  try {
    const sizes = await withTimeout(response.request().sizes(), timeoutMs);
    if (Number.isSafeInteger(sizes?.responseBodySize) && sizes.responseBodySize >= 0) {
      observed = Math.max(observed ?? 0, sizes.responseBodySize);
    }
  } catch (error) {
    throw new BrowserResourceLimitError({
      url,
      limit,
      observed,
      detail: String(error?.message || error),
    });
  }
  if (observed !== null && observed > limit) {
    throw new BrowserResourceLimitError({ url, limit, observed });
  }
  return observed ?? 0;
}

export function resourceLimitPayload(error) {
  return error instanceof BrowserResourceLimitError ? error.toJSON() : null;
}

export function selfTestBrowserLimits() {
  if (resolveBrowserResponseLimit(123) !== 123) throw new Error('explicit browser limit failed');
  if (resolveBrowserResponseLimit(null, { D_RESEARCH_HTTP_MAX_BYTES: '456' }) !== 456) {
    throw new Error('browser limit environment override failed');
  }
  for (const invalid of [0, -1, 1.5, 'garbage']) {
    try {
      resolveBrowserResponseLimit(invalid, {});
      throw new Error(`invalid browser limit accepted: ${invalid}`);
    } catch (error) {
      if (String(error?.message || error).startsWith('invalid browser limit accepted')) throw error;
    }
  }
  const payload = new BrowserResourceLimitError({
    url: 'https://example.test/',
    limit: 10,
    observed: 11,
  }).toJSON();
  if (payload.code !== 'http_max_bytes' || payload.complete !== false || payload.incomplete !== true) {
    throw new Error('browser resource-limit payload failed');
  }
}
