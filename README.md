# D Research Skill

D Research is a browser-first deep research and lawful public data extraction skill for AI agents.

Default browser tool: **Playwright**.

## English

### What it is

D Research helps AI agents run structured investigations across public web sources, dynamic pages, files, datasets, APIs, citations, and conflicting evidence. It is designed to support deep research while staying read-only and respecting access controls.

### Use cases

- Deep web research and source discovery
- Public data collection and scraping
- Academic projects and literature reviews
- Technical, market, product, and competitor research
- Evidence ledgers and contradiction checks
- Blocker reports for inaccessible sources

### Key capabilities

- Topic decomposition and source mapping
- Query fanout across broad, exact, official, primary, filetype, dataset/API, recent, and contradiction searches
- Browser-first probing with Playwright for dynamic websites
- Sitemap, robots, public file, and public API discovery
- Crawl expansion through links, pagination, files, references, and citations
- Evidence ledger with claim-level source tracking
- PRISMA-style academic review workflow
- Blocker reports with manual retrieval instructions

### Safety model

D Research is read-only by default. It does not instruct agents to bypass login walls, paywalls, captchas, rate limits, robots restrictions, or access controls. If a source is blocked, the agent must produce a blocker report that explains where the data likely is, why it matters, what was attempted, and how the user can retrieve it manually with proper access.

### Quick start

```bash
npm install
npx playwright install chromium
npm run self-test
```

### Script examples

```bash
node scripts/playwright_probe.mjs --url https://example.com --out research-output/probe.json --screenshot research-output/probe.png
node scripts/playwright_extract.mjs --url https://example.com --format json --out research-output/extract.json
node scripts/playwright_crawl.mjs --seed https://example.com --outDir research-output/crawl --maxDepth 2 --maxPages 30
npm run ledger:init -- --out research-output/evidence.csv
```

### Repository layout

```text
SKILL.md
AGENTS.md
research.config.example.json
references/
adapters/
scripts/
templates/
examples/
```

### Recommended install

For coding agents that read repository instructions, copy `AGENTS.md` to your repository root. For agents that support skills, install this folder as a skill package and keep `SKILL.md` as the primary entrypoint.

---

## Tiếng Việt

### Giới thiệu

D Research là skill nghiên cứu sâu và trích xuất dữ liệu công khai theo hướng browser-first cho AI agents. Skill này giúp agent điều tra có cấu trúc trên web công khai, trang web động, file, dataset, API, citation và các nguồn bằng chứng mâu thuẫn, đồng thời mặc định chỉ đọc và tôn trọng các rào cản truy cập.

### Trường hợp sử dụng

- Nghiên cứu web sâu và tìm nguồn
- Thu thập và cào dữ liệu công khai
- Đồ án học thuật và literature review
- Nghiên cứu kỹ thuật, thị trường, sản phẩm và đối thủ
- Bảng evidence ledger và contradiction check
- Blocker report cho nguồn không truy cập được

### Năng lực chính

- Phân rã chủ đề và lập bản đồ nguồn
- Mở rộng truy vấn theo broad, exact, official, primary, filetype, dataset/API, recent và contradiction query
- Kiểm tra nguồn bằng Playwright trước tiên cho web động
- Phát hiện sitemap, robots, file công khai và API công khai
- Mở rộng crawl qua link, phân trang, file, reference và citation
- Evidence ledger theo từng claim và nguồn
- Quy trình academic review theo phong cách PRISMA
- Blocker report kèm hướng dẫn lấy dữ liệu thủ công

### Mô hình an toàn

D Research mặc định chỉ đọc. Skill không hướng dẫn agent vượt login wall, paywall, captcha, rate limit, robots restriction hoặc access control. Khi nguồn bị chặn, agent phải tạo blocker report nêu URL, lý do nguồn quan trọng, đã thử những gì, bị chặn bởi đâu và người dùng cần tự export, copy, screenshot hoặc download trường dữ liệu nào với quyền truy cập hợp lệ.

### Bắt đầu nhanh

```bash
npm install
npx playwright install chromium
npm run self-test
```

### Ví dụ script

```bash
node scripts/playwright_probe.mjs --url https://example.com --out research-output/probe.json --screenshot research-output/probe.png
node scripts/playwright_extract.mjs --url https://example.com --format json --out research-output/extract.json
node scripts/playwright_crawl.mjs --seed https://example.com --outDir research-output/crawl --maxDepth 2 --maxPages 30
npm run ledger:init -- --out research-output/evidence.csv
```

### Cấu trúc repository

```text
SKILL.md
AGENTS.md
research.config.example.json
references/
adapters/
scripts/
templates/
examples/
```

### Cài đặt khuyến nghị

Với coding agents đọc instruction từ repository, hãy copy `AGENTS.md` vào root repo. Với agent hỗ trợ skill, hãy cài đặt cả thư mục này như một skill package và giữ `SKILL.md` làm entrypoint chính.
