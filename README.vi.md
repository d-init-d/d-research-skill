# D Research (Tiếng Việt)

[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)
[![Release](https://img.shields.io/github/v/release/d-init-d/d-research-skill?sort=semver)](https://github.com/d-init-d/d-research-skill/releases)
[![Self-test](https://github.com/d-init-d/d-research-skill/actions/workflows/lint-and-self-test.yml/badge.svg)](https://github.com/d-init-d/d-research-skill/actions/workflows/lint-and-self-test.yml)

**Skill nghiên cứu production-grade cho AI agent: web search, browser automation, API, archive, trích xuất dữ liệu, evidence ledger và benchmark tái lập.**

Tài liệu tiếng Anh đầy đủ nhất nằm ở [README.md](README.md). Bản tiếng Việt này là bản giới thiệu thực dụng cho người dùng Việt: đủ để hiểu sản phẩm, cài đặt, kiểm tra và quyết định có nên dùng trong workflow của mình không.

D Research biến research bằng agent từ kiểu "tìm nhanh rồi trả lời" thành một quy trình có kiểm chứng: phân loại dạng research trước khi tìm nguồn, lập kế hoạch câu hỏi, thu thập dữ liệu công khai hợp pháp, trích xuất nội dung, ghi evidence ledger, chạy quality gate trước khi kết luận, xử lý mâu thuẫn, dựng báo cáo có citation và giữ lại metadata để audit.

## Tổng quan nhanh

| Mục | D Research cung cấp |
|---|---|
| Người dùng chính | AI agent, người vận hành agent, researcher, developer hoặc team cần kết quả research có nguồn và có thể kiểm tra lại. |
| Cách truy cập | Read-only mặc định. Skill có thể dùng web search, browser automation, public API, Wayback/archive, database read-only do user cấp, và file local. |
| Đầu ra | Evidence ledger, citation file, bảng trích xuất, frontier ledger, coverage map, research plan, report, metadata tái lập. |
| Kiểm chứng | Self-test offline, internal-reference check, dogfood bench 12 task, frontier bench 52 task / 26 class. |
| Ranh giới an toàn | Không bypass login, paywall, captcha, rate limit, robots restriction hoặc access control. Nguồn bị chặn thì ghi blocker report. |

## Khi nào nên dùng

Dùng D Research khi bạn muốn agent:

- trả lời bằng nguồn rõ ràng, có quote/value và confidence;
- thu thập dữ liệu công khai hợp pháp nhưng vẫn giữ audit trail;
- xử lý PDF, bảng HTML, JSON-LD, API, archive, Wikidata, DOI/PMID/arXiv/ISBN;
- làm systematic review, fact verification, research kỹ thuật, market/public-data scan hoặc task dài nhiều bước;
- kiểm tra sau mỗi lần upgrade rằng skill không yếu đi.

Không dùng skill này để bypass access control, thu thập dữ liệu riêng tư, deanonymize người dùng, né restriction của nền tảng, hoặc biến nó thành live monitoring service nếu chưa có một hệ thống vận hành riêng.

## Phạm vi sản phẩm

Đây là **skill package**, không phải app, API server, crawler SaaS hay package Python. Agent đọc `SKILL.md` và làm theo workflow. Các file trong `references/`, `adapters/`, `templates/`, `examples/` và `scripts/` là tài liệu và helper để agent làm research nhất quán hơn.

Các script trong `scripts/` là helper tùy chọn, nhỏ và dễ audit. Chúng hỗ trợ workflow nhưng không thay thế agent.

## Vòng đời research (v3.x)

Skill được tổ chức theo tám trụ vòng đời. Mỗi trụ là một bước nhỏ, kết quả của trụ này là đầu vào cho trụ kế tiếp.

| # | Trụ | Việc gì xảy ra | File chính |
|---|---|---|---|
| 0 | **intake** | Phân loại dạng research, độ sâu, safety posture, output artifact, authority/source basin và route trước khi mở nguồn. | `references/research-intake.md` |
| 1 | **discover** | Hiểu mục tiêu, chia câu hỏi, tạo source map, sinh fanout query. | `references/topic-decomposition.md`, `references/source-discovery.md`, `references/query-patterns.md` |
| 2 | **fetch** | Probe browser-first + lawful fallback; HTTP cache opt-in dùng chung; resolve canonical ID (DOI/PMID/arXiv/ISBN) trước khi search rộng. | `adapters/playwright.md`, `references/anti-bot-fallback.md`, `references/http-cache.md`, `scripts/citation_resolver.py` |
| 3 | **extract** | Lấy text, table, structured data (JSON-LD, microdata, RDFa), PDF / DOCX / EPUB / XLSX / mbox, OCR ảnh. | `references/data-extraction-toolbox.md`, `references/multi-format-extraction.md`, `scripts/multi_extract.py`, `scripts/pdf_extract.py`, `scripts/ocr.py` |
| 4 | **analyze** | Clean, dedup, score nguồn, đi citation graph, semantic retrieval, dò contradiction. | `scripts/data_clean.py`, `scripts/dedup_near.py`, `scripts/score_source.py`, `scripts/citation_graph.py`, `scripts/embed_corpus.py` |
| 5 | **synthesize** | Tổng hợp claim atomic; apply synthesis pattern; render citation theo style yêu cầu. | `references/synthesis-patterns.md`, `references/citation-management.md`, `scripts/citation_render.py` |
| 6 | **report** | Render báo cáo (Markdown / PDF / DOCX / HTML); lint claim coverage. | `references/report-generation.md`, `scripts/report_render.py` |
| 7 | **audit** | Ký ledger (HMAC-SHA256), export PROV-O JSON-LD, kiểm tra reproducibility, ghi run metadata. | `references/evidence-ledger.md`, `scripts/evidence_ledger.py`, `scripts/run_metadata.py` |

v3.2.1 là bản stable nâng ba nhánh optional lên backend production: semantic
retrieval, citation export giàu metadata và language detection. Semantic
retrieval ưu
tiên sentence-transformers cục bộ và dùng fallback lexical deterministic tích
hợp sẵn khi chưa cài backend model; citation export hỗ
trợ metadata đã validate cho article, book và conference; language detection có
thể dùng `langdetect` cục bộ với kết quả deterministic. Cây stable promote đúng
candidate v3.2.1-rc.2 mà không thay đổi executable, dependency, workflow, route
hay package path. Xem
[`docs/release-v3.2.1.md`](docs/release-v3.2.1.md).

v3.2.0 là bản production-ready của workflow schema 2.0. Bản này có fingerprint
bất biến cho approval, khóa output portable, checklist có ID chuẩn, report
signature fail-closed, eval manifest nghiêm ngặt và budget read-only/tài nguyên
trên toàn browser. Hồ sơ release ghi minh bạch các waiver bảo đảm bên ngoài do
maintainer phê duyệt; các gate annotated tag, 23/23 kiểm thử cục bộ, CI đa nền
tảng đúng SHA, RC ancestry, archive replay, SHA-256 và provenance đều đã pass.
Xem [`docs/release-v3.2.0.md`](docs/release-v3.2.0.md).
Workspace v3.1.1 nên nâng cấp theo hướng dẫn đã có fixture kiểm thử tại
[`docs/upgrade-v3.1.1-to-v3.2.0.md`](docs/upgrade-v3.1.1-to-v3.2.0.md).

v3.1.1 làm chắc hơn bề mặt metadata của skill bằng cách biểu diễn
`description` trong `SKILL.md` theo cú pháp YAML block scalar. Nội dung trigger
không đổi, nhưng các parser nghiêm ngặt với plain scalar có dấu hai chấm sẽ đọc
frontmatter ổn định hơn.

v3.1.0 làm sạch bề mặt release công khai: release notes dùng thống nhất pattern
tiêu đề sản phẩm + subtitle `vX.Y.Z Release Notes`, tài liệu eval khớp bench
52 task / 26 class, và loại bỏ nhiễu duplicate reference nhỏ.

v3.0.6 biến register/jargon recall thành capability có công cụ và có bench:
`scripts/harvest_terms.py` thực thi rule lặp qua ≥2 nguồn độc lập, và frontier
bench có class `register-jargon-recall` gồm 2 task để chống regression.

v3.0.5 thêm register- and jargon-aware recall companion: quy trình
zero-maintenance để harvest vocabulary sống từ kết quả tươi, đi register ladder
hai chiều, và coi term đã học là lead chứ không phải evidence.

v3.0.3 nâng Step 0 thành controller phân loại mạnh hơn: due diligence /
investigation, policy / standards analysis, và creative / cultural research trở
thành các research shape hạng nhất. Agent cũng có chế độ completeness-first cho
các task audit-grade, nhiều rủi ro, red-flag hoặc khi user nói tốc độ không quan
trọng bằng độ chắc.

v3.0.2 bổ sung Step 0 research intake: agent phân loại request theo nhiều nhãn
trước khi mở nguồn, ví dụ fact / URL / người / academic / systematic review /
dataset / API / kỹ thuật / high-stakes / multilingual / long-horizon. Mục tiêu
là tránh chọn sai workflow ngay từ đầu.

v3.0.1 bổ sung lớp execution gate portable trước bước tổng hợp cuối: kiểm
source map, độ phủ nguồn, low-recall, single-basin, ngày/tháng/danh tính,
evidence verification và synthesis readiness. Subagent vẫn là tùy chọn; nếu
runtime không có subagent thì main agent tự chạy checklist.

Lịch sử release đầy đủ xem [CHANGELOG.md](CHANGELOG.md).

## Tính năng chính

- Workflow nghiên cứu cốt lõi: hiểu mục tiêu, chia câu hỏi, tìm nguồn, trích xuất, ledger chứng cứ, kiểm tra mâu thuẫn, tổng hợp.
- Research intake Step 0: phân loại dạng nghiên cứu, research depth (fast / standard / completeness-first), safety posture, authority/source basin, output artifact, freshness/language scope và route trước khi mở nguồn. Bao gồm due diligence / investigation, policy / standards analysis và creative / cultural research. Xem `references/research-intake.md`.
- Execution gates portable: trước khi trả lời các task không tầm thường, agent kiểm source map, coverage/recall, no-single-basin, identity/date/inference, evidence verification và synthesis readiness. Xem `references/execution-gates.md`.
- Research đa kênh: web search, browser automation, fetch-only, public API, Wayback/archive, Wikidata, GraphQL và database read-only khi user cấp quyền.
- Evidence ledger dạng CSV, có thể ký/verify bằng HMAC-SHA256.
- Source scoring v2 tách năm trục tự động (type, authority, freshness, traceability, independence) khỏi ba gate review bắt buộc do người đánh giá quyết định (relevance, method transparency, access quality); xem `scripts/score_source.py` và `references/source-quality-rubric.md`.
- Citation export/render: BibTeX `@article`/`@book`/`@inproceedings` qua metadata sidecar tùy chọn, RIS, APA, MLA, IEEE, Chicago, Vancouver, Harvard, Nature, Science, ACM, AMA.
- Citation resolver cho academic identifiers: DOI, PMID, arXiv ID, ISBN. `scripts/citation_resolver.py` resolve qua các API công khai miễn phí (CrossRef, Datacite, NCBI, arXiv, Open Library, Unpaywall), emit BibTeX hoặc evidence-ledger row. Là Step 0 fast path khi user paste sẵn DOI/PMID/arXiv ID/ISBN — bỏ qua workflow research đầy đủ vì đã có canonical metadata trong 1 request. Xem `adapters/citation-resolver.md`.
- Report generator: `scripts/report_render.py` tạo báo cáo Markdown có cấu trúc từ workspace nghiên cứu (plan + evidence ledger + screening log). Hỗ trợ init skeleton, render final report, lint kiểm tra claim coverage, và export PDF/DOCX/HTML qua pandoc. Xem `references/report-generation.md`.
- Semantic retrieval: `scripts/embed_corpus.py` tìm kiếm trên corpus text hoặc evidence ledger bằng cosine similarity. Mặc định `auto` ưu tiên `sentence-transformers` cục bộ khi đã cài, rồi fallback sang `local-hashing` deterministic tích hợp sẵn; stub chỉ dùng khi chỉ định rõ cho test. Cài extra embeddings để có độ tương đồng ngữ nghĩa từ model; fallback phù hợp nhất với lexical overlap và biến thể chính tả. Xem `references/semantic-retrieval.md`.
- PRISMA 2020 systematic review và template flow diagram.
- Data extraction toolbox: HTML tables, JSON-LD, embedded JSON, sitemaps, RSS, OAI-PMH, REST/GraphQL, PDFs.
- Long-horizon research protocol: tạo workspace riêng, `research-plan.json`, `PLAN.md`, approval gate, notes, sections, report, checklist.
- Frontier search cho follow-up theo evidence gap: khi pass đầu để lại sub-question chưa đủ chứng cứ hoặc thông tin obscure/long-tail, agent dựng một priority queue nhỏ trên các node ứng viên (query, URL, file, API, citation, repo, alias, archive), chấm điểm theo gap còn lại, đào nhánh ưu tiên cao trước, và dừng khi evidence saturation. Không phải pathfinding theo nghĩa CS (không A*/Dijkstra); chỉ là best-first search có ràng buộc. Có `frontier-ledger.csv` và `coverage-map.json` đi kèm `evidence-ledger.csv`. Vẫn không bypass access control. Xem `references/frontier-search.md`.
- Fact-verification fast path cho câu hỏi atomic (1 entity, 1 attribute, có primary source xác định, đáp án 1 câu/1 quote): SHA commit, version package, giới hạn pagination của API, 1 điều khoản license. Bỏ qua decompose/source map/query fanout/crawl; gọi primary source 1 lần, quote nguyên văn, ghi 1 dòng ledger với 1 lần re-check độc lập, rồi report. Nếu primary source trả non-2xx, hai mirror mâu thuẫn, hoặc user hỏi tiếp "tại sao/như thế nào" thì bail về workflow broad. Không nhảy sang `references/frontier-search.md` từ branch này. Xem `references/fact-verification.md`.
- Person aggregation cho yêu cầu tìm thông tin public-role về 1 người cụ thể (maintainer, tác giả, speaker, nhà báo, public figure): anchor vào 1 nguồn canonical (GitHub profile, ORCID, package author, faculty page, byline đã xác minh), cross-aggregate các claim public-role có ít nhất 1 nguồn, disambiguate homonym bằng tín hiệu positive. **Privacy boundary là hard stop, không phải hướng dẫn trừu tượng**: địa chỉ nhà, người thân/gia đình, tài khoản social riêng tư, số điện thoại / email cá nhân, ảnh cá nhân, thông tin y tế / tài chính / pháp lý / xu hướng / hành trình, re-identify pseudonym sang real name, và mọi item người đó đã đánh dấu private đều OUT-OF-SCOPE bất kể có tìm được trên web hay không. Refuse với minors, private individuals, và mọi framing harassment / stalking / doxxing. Saturate ở 25 dòng ledger hoặc khi 3 nguồn liên tiếp không add claim mới đã verified. Xem `references/person-aggregation.md`.
- Eval harness offline hai tầng để bắt regression và đo upgrade: `examples/evals/dogfood-bench.json` là Tier 1 regression guard (12 task), `examples/evals/frontier-bench.json` là Tier 2 frontier probe bench 3.0 (52 task, 26 class), harness stdlib-only là `scripts/run_dogfood.py` với `self-test`, `validate`, `list`, `render`, `score`, `score-all`, `compare`, `baseline`. CI chỉ chạy schema/self-test offline. Mỗi task canonical có `run-result.json` schema 2.1 và ledger; để score một task dùng `npm run eval:score -- DF-001 path/to/ledger.csv --run-result path/to/run-result.json`. Để so sánh bản cũ/mới dùng `score-all --runs-dir` rồi `compare`. Đây không phải leaderboard và không ship điểm số per-agent. Xem `docs/eval.md`.
- Anti-bot fallback chain cho nguồn public quan trọng bị Cloudflare, JS challenge, captcha, 403, 429 hoặc lỗi browser/fetch lặp lại: thử đúng một chuỗi hợp pháp API/static form -> public archive -> cache/snippet nếu có -> fetch-only/no-JS -> blocker report. Không dùng để bypass access control; attempt fail được ghi như process row confidence thấp. Xem `references/anti-bot-fallback.md`.
- Vietnamese source discovery companion: hướng dẫn opt-in cho research nguồn Việt Nam, gồm alias có dấu/không dấu, ma trận báo chí/official/archive/public-community, và kỷ luật ngày-tháng/danh tính. Xem `references/vietnamese-source-discovery.md`.
- Register & jargon expansion companion: lớp recall opt-in cho khi nguồn chứng cứ dùng register khác với truy vấn (lâm sàng vs. dân dã, pháp lý vs. tiếng lóng, chuẩn kỹ thuật vs. cách nói nghề, học thuật vs. jargon cộng đồng, slang mới nổi). Đi register ladder hai chiều — formal → vernacular để mở recall, vernacular → formal để neo mọi thuật ngữ cộng đồng về một primary source. Harvest từ kết quả search tươi (không lấy từ bộ nhớ model), chỉ giữ term lặp ≥2 nguồn cộng đồng độc lập, và coi vocabulary là lớp discovery — không bao giờ là evidence; mọi claim vẫn qua source-quality rubric và contradiction pass. Audit-grade ghi vào `templates/register-vocab-log.csv`. Xem `references/register-and-jargon-expansion.md`.
- Lập kế hoạch subagent portable: slot, context length, max parallel, task budget, không khóa cứng vào CLI/IDE cụ thể.
- Chống tràn context: task phải fit `execution.context_budget`, findings phải ghi ra file ngay.

## Cài đặt

### Cách A: Nhờ LLM agent cài giúp

Paste đoạn này vào Claude Code, OpenCode, Cursor, Windsurf hoặc agent bạn dùng:

```text
Install the D Research skill from https://github.com/d-init-d/d-research-skill.git into this project so you can use it for deep research. Prefer vendoring it at .agents/skills/d-research, keep it read-only by default, copy research.config.example.json to research.config.json only if I want project-specific settings, and run the optional self-tests if Node/Python are available.
```

### Cách B: Cài thủ công

Chọn đúng thư mục discovery của runtime; đường dẫn cuối luôn phải kết thúc bằng
`d-research/SKILL.md`:

| Runtime | Trong project | Dùng cho cá nhân |
|---|---|---|
| Agent Skills portable | `.agents/skills/d-research` | `~/.agents/skills/d-research` |
| Codex | `.agents/skills/d-research` | `$CODEX_HOME/skills/d-research` (mặc định: `~/.codex/skills/d-research`) |
| Claude Code | `.claude/skills/d-research` | `~/.claude/skills/d-research` |
| Grok Build | `.agents/skills/d-research` | `~/.grok/skills/d-research` |
| OpenCode | `.opencode/skills/d-research` (cũng nhận `.agents/skills`) | `~/.config/opencode/skills/d-research` |

Các lệnh dưới đây dùng layout portable trong project. Khi chỉ cài cho một
runtime, thay destination bằng đường dẫn tương ứng trong bảng.

Với Bash:

```bash
mkdir -p .agents/skills
git clone https://github.com/d-init-d/d-research-skill.git .agents/skills/d-research
```

Với PowerShell:

```powershell
New-Item -ItemType Directory -Force .agents/skills | Out-Null
git clone https://github.com/d-init-d/d-research-skill.git .agents/skills/d-research
```

Thư mục cuối phải là `d-research` để khớp với `name` trong frontmatter.

Trỏ agent/IDE của bạn tới:

```text
.agents/skills/d-research/SKILL.md
```

Nếu muốn chỉnh config theo project:

```bash
cp .agents/skills/d-research/research.config.example.json research.config.json
```

```powershell
Copy-Item .agents/skills/d-research/research.config.example.json research.config.json
```

Nếu muốn dùng các script helper:

```bash
cd .agents/skills/d-research
npm ci
npx --no-install playwright install chromium
# Tùy chọn: backend semantic và language detection chất lượng production
python -m pip install -e ".[embeddings,language-detection]"
npm run self-test
```

`npm run self-test` là chuỗi helper test offline. Release CI chạy thêm adversarial
matrix và đúng một lần Chromium smoke dùng fixture local trên mỗi hệ điều hành.

## Config quan trọng

- `research.intake.enabled`: bật Step 0 phân loại request trước khi mở nguồn.
- `research.intake.multiLabel`: cho phép nhiều nhãn cùng lúc, ví dụ academic review + dataset extraction.
- `research.intake.defaultToConservativeBranch`: khi mơ hồ thì chọn nhánh an toàn/chặt hơn.
- `research.intake.defaultDepth`: độ sâu mặc định, thường là `standard`.
- `research.intake.allowCompletenessFirst`: cho phép agent ưu tiên độ chắc, recall và auditability hơn tốc độ.
- `research.intake.completenessFirstOnRiskOrAudit`: tự nâng lên completeness-first cho due diligence, red flag, audit-grade, high-stakes hoặc task nhiều rủi ro.
- `research.executionGates.enabled`: bật quality gates trước khi tổng hợp các task không tầm thường.
- `research.executionGates.lowRecallGuard`: chạy recall pass khi nguồn còn mỏng.
- `research.executionGates.noSingleBasinStop`: tránh kết luận "đủ rộng" nếu mới có một source basin.
- `research.executionGates.subagentsOptional`: subagent là tùy chọn, không phải dependency bắt buộc.
- `researchPlan.workspace.baseDir`: thư mục cha để tạo workspace nghiên cứu. Mặc định là thư mục hiện tại.
- `researchPlan.workspace.fallbackToCwdOnError`: nếu output dir lỗi, fallback về thư mục hiện tại và báo cho user.
- `researchPlan.context.mainContextLength`: context length của main agent.
- `researchPlan.context.taskBudgetRatio`: tỷ lệ context dùng cho mỗi task.
- `researchPlan.context.writeFindingsImmediately`: bắt agent ghi findings ra file ngay.
- `researchPlan.subagents.slots[]`: danh sách slot subagent. Mặc định có một slot disabled.
- `researchPlan.subagents.slots[].agent`: tên subagent trong runtime/CLI/IDE của bạn.
- `researchPlan.subagents.slots[].contextLength`: context length của slot đó.
- `researchPlan.subagents.slots[].maxParallel`: số luồng song song tối đa cho slot đó.
- `researchPlan.approval.requireHuman`: yêu cầu user duyệt plan trước khi chạy.
- `researchPlan.finalResponse.reportWorkspacePath`: bắt agent báo workspace path trong kết quả cuối.

Lưu ý: skill không quản lý API key, model, provider, login hay cách gọi subagent thật. Những phần đó nên cấu hình trong OpenCode, Claude Code, Cursor, IDE hoặc CLI bạn dùng.

## Workflow long-horizon mẫu

```bash
node scripts/run_python.mjs scripts/research_plan.py init --slug topic
cd research-topic-2026-05-16
node ../scripts/run_python.mjs ../scripts/research_plan.py configure-execution --file research-plan.json
node ../scripts/run_python.mjs ../scripts/research_plan.py render --file research-plan.json
node ../scripts/run_python.mjs ../scripts/research_plan.py gate --file research-plan.json --gate plan_ready
node ../scripts/run_python.mjs ../scripts/research_plan.py approve --file research-plan.json --by "Reviewer"
node ../scripts/run_python.mjs ../scripts/research_plan.py gate --file research-plan.json --gate execute_ready
```

`run_python.mjs` tự chọn launcher Python phù hợp trên Windows, macOS và Linux.

## An toàn

Mặc định read-only. Không bypass login, paywall, captcha, rate limit, robots restriction hoặc access control. Nếu nguồn bị chặn, agent phải dừng và tạo blocker report thay vì cố truy cập.

## License

D Research là source-available cho mục đích phi thương mại theo giấy
phép **Creative Commons Attribution-NonCommercial 4.0 International**
(`CC-BY-NC-4.0`). Xem `LICENSE`.

Bạn có thể dùng, sao chép, chia sẻ và chỉnh sửa cho mục đích phi
thương mại nếu ghi attribution phù hợp. Không được dùng thương mại nếu
chưa có sự cho phép bằng văn bản từ chủ sở hữu bản quyền.

Commercial use bao gồm nhưng không giới hạn ở: bán lại, phân phối trả
phí, đóng gói thành SaaS, đưa lên marketplace, bán kèm agent bundle,
hoặc nhúng skill này vào sản phẩm/dịch vụ trả phí.
