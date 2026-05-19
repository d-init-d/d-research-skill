# D Research (Tiếng Việt)

Tài liệu tiếng Anh chính và đầy đủ nhất: [README.md](README.md). Bản tiếng Việt này là bản tóm tắt nhanh; bảng tính năng và bảng config đầy đủ nằm trong README tiếng Anh.

D Research là một skill dạng markdown cho AI agent. Nó dạy agent cách làm nghiên cứu chuyên sâu, thu thập dữ liệu công khai hợp pháp, ghi chứng cứ, tạo báo cáo có trích dẫn và giữ toàn bộ đầu ra trong một workspace có thể bàn giao lại.

Đây không phải app, API server hay package Python. Agent đọc `SKILL.md` và làm theo workflow; các script trong `scripts/` chỉ là helper tùy chọn.

## Vòng đời research (v3.0)

Skill được tổ chức theo bảy trụ vòng đời. Mỗi trụ là một bước nhỏ, kết quả của trụ này là đầu vào cho trụ kế tiếp.

| # | Trụ | Việc gì xảy ra | File chính |
|---|---|---|---|
| 1 | **discover** | Hiểu mục tiêu, chia câu hỏi, tạo source map, sinh fanout query. | `references/topic-decomposition.md`, `references/source-discovery.md`, `references/query-patterns.md` |
| 2 | **fetch** | Probe browser-first + lawful fallback; HTTP cache opt-in dùng chung; resolve canonical ID (DOI/PMID/arXiv/ISBN) trước khi search rộng. | `adapters/playwright.md`, `references/anti-bot-fallback.md`, `references/http-cache.md`, `scripts/citation_resolver.py` |
| 3 | **extract** | Lấy text, table, structured data (JSON-LD, microdata, RDFa), PDF / DOCX / EPUB / XLSX / mbox, OCR ảnh. | `references/data-extraction-toolbox.md`, `references/multi-format-extraction.md`, `scripts/multi_extract.py`, `scripts/pdf_extract.py`, `scripts/ocr.py` |
| 4 | **analyze** | Clean, dedup, score nguồn, đi citation graph, semantic retrieval, dò contradiction. | `scripts/data_clean.py`, `scripts/dedup_near.py`, `scripts/score_source.py`, `scripts/citation_graph.py`, `scripts/embed_corpus.py` |
| 5 | **synthesize** | Tổng hợp claim atomic; apply synthesis pattern; render citation theo style yêu cầu. | `references/synthesis-patterns.md`, `references/citation-management.md`, `scripts/citation_render.py` |
| 6 | **report** | Render báo cáo (Markdown / PDF / DOCX / HTML); lint claim coverage. | `references/report-generation.md`, `scripts/report_render.py` |
| 7 | **audit** | Ký ledger (HMAC-SHA256), export PROV-O JSON-LD, kiểm tra reproducibility, ghi run metadata. | `references/evidence-ledger.md`, `scripts/evidence_ledger.py`, `scripts/run_metadata.py` |

Lịch sử release đầy đủ (PR #1–#10) xem [CHANGELOG.md](CHANGELOG.md).

## Tính năng chính

- Workflow nghiên cứu cốt lõi: hiểu mục tiêu, chia câu hỏi, tìm nguồn, trích xuất, ledger chứng cứ, kiểm tra mâu thuẫn, tổng hợp.
- Browser-first research với Playwright mặc định, nhưng vẫn có adapter generic browser/fetch/search.
- Evidence ledger dạng CSV, có thể ký/verify bằng HMAC-SHA256.
- Citation export/render: BibTeX, RIS, APA, MLA, IEEE, Chicago, Vancouver, Harvard, Nature, Science, ACM, AMA.
- Citation resolver cho academic identifiers: DOI, PMID, arXiv ID, ISBN. `scripts/citation_resolver.py` resolve qua các API công khai miễn phí (CrossRef, Datacite, NCBI, arXiv, Open Library, Unpaywall), emit BibTeX hoặc evidence-ledger row. Là Step 0 fast path khi user paste sẵn DOI/PMID/arXiv ID/ISBN — bỏ qua workflow research đầy đủ vì đã có canonical metadata trong 1 request. Xem `adapters/citation-resolver.md`.
- Report generator: `scripts/report_render.py` tạo báo cáo Markdown có cấu trúc từ workspace nghiên cứu (plan + evidence ledger + screening log). Hỗ trợ init skeleton, render final report, lint kiểm tra claim coverage, và export PDF/DOCX/HTML qua pandoc. Xem `references/report-generation.md`.
- Semantic retrieval: `scripts/embed_corpus.py` tìm kiếm ngữ nghĩa trên corpus text hoặc evidence ledger bằng cosine similarity. Hỗ trợ stub/sentence-transformers/cohere/llama-cli backends. Xem `references/semantic-retrieval.md`.
- PRISMA 2020 systematic review và template flow diagram.
- Data extraction toolbox: HTML tables, JSON-LD, embedded JSON, sitemaps, RSS, OAI-PMH, REST/GraphQL, PDFs.
- Long-horizon research protocol: tạo workspace riêng, `research-plan.json`, `PLAN.md`, approval gate, notes, sections, report, checklist.
- Frontier search cho follow-up theo evidence gap: khi pass đầu để lại sub-question chưa đủ chứng cứ hoặc thông tin obscure/long-tail, agent dựng một priority queue nhỏ trên các node ứng viên (query, URL, file, API, citation, repo, alias, archive), chấm điểm theo gap còn lại, đào nhánh ưu tiên cao trước, và dừng khi evidence saturation. Không phải pathfinding theo nghĩa CS (không A*/Dijkstra); chỉ là best-first search có ràng buộc. Có `frontier-ledger.csv` và `coverage-map.json` đi kèm `evidence-ledger.csv`. Vẫn không bypass access control. Xem `references/frontier-search.md`.
- Fact-verification fast path cho câu hỏi atomic (1 entity, 1 attribute, có primary source xác định, đáp án 1 câu/1 quote): SHA commit, version package, giới hạn pagination của API, 1 điều khoản license. Bỏ qua decompose/source map/query fanout/crawl; gọi primary source 1 lần, quote nguyên văn, ghi 1 dòng ledger với 1 lần re-check độc lập, rồi report. Nếu primary source trả non-2xx, hai mirror mâu thuẫn, hoặc user hỏi tiếp "tại sao/như thế nào" thì bail về workflow broad. Không nhảy sang `references/frontier-search.md` từ branch này. Xem `references/fact-verification.md`.
- Person aggregation cho yêu cầu tìm thông tin public-role về 1 người cụ thể (maintainer, tác giả, speaker, nhà báo, public figure): anchor vào 1 nguồn canonical (GitHub profile, ORCID, package author, faculty page, byline đã xác minh), cross-aggregate các claim public-role có ít nhất 1 nguồn, disambiguate homonym bằng tín hiệu positive. **Privacy boundary là hard stop, không phải hướng dẫn trừu tượng**: địa chỉ nhà, người thân/gia đình, tài khoản social riêng tư, số điện thoại / email cá nhân, ảnh cá nhân, thông tin y tế / tài chính / pháp lý / xu hướng / hành trình, re-identify pseudonym sang real name, và mọi item người đó đã đánh dấu private đều OUT-OF-SCOPE bất kể có tìm được trên web hay không. Refuse với minors, private individuals, và mọi framing harassment / stalking / doxxing. Saturate ở 25 dòng ledger hoặc khi 3 nguồn liên tiếp không add claim mới đã verified. Xem `references/person-aggregation.md`.
- Eval harness offline hai tầng để bắt regression và đo upgrade: `examples/evals/dogfood-bench.json` là Tier 1 regression guard (12 task), `examples/evals/frontier-bench.json` là Tier 2 frontier probe bench 2.1 (50 task, 25 class), harness stdlib-only là `scripts/run_dogfood.py` với `self-test`, `validate`, `list`, `render`, `score`, `score-all`, `compare`, `baseline`. CI chỉ chạy schema/self-test offline. Để score 1 ledger chạy `npm run eval:score -- DF-001 path/to/ledger.csv`; để so sánh bản cũ/mới dùng `score-all` rồi `compare`. Đây không phải leaderboard và không ship điểm số per-agent. Xem `docs/eval.md`.
- Anti-bot fallback chain cho nguồn public quan trọng bị Cloudflare, JS challenge, captcha, 403, 429 hoặc lỗi browser/fetch lặp lại: thử đúng một chuỗi hợp pháp API/static form -> public archive -> cache/snippet nếu có -> fetch-only/no-JS -> blocker report. Không dùng để bypass access control; attempt fail được ghi như process row confidence thấp. Xem `references/anti-bot-fallback.md`.
- Lập kế hoạch subagent portable: slot, context length, max parallel, task budget, không khóa cứng vào CLI/IDE cụ thể.
- Chống tràn context: task phải fit `execution.context_budget`, findings phải ghi ra file ngay.

## Cài đặt

### Cách A: Nhờ LLM agent cài giúp

Paste đoạn này vào Claude Code, OpenCode, Cursor, Windsurf hoặc agent bạn dùng:

```text
Install the D Research skill from https://github.com/d-init-d/d-research-skill.git into this project so you can use it for deep research. Prefer vendoring it at .agents/skills/d-research, keep it read-only by default, copy research.config.example.json to research.config.json only if I want project-specific settings, and run the optional self-tests if Node/Python are available.
```

### Cách B: Cài thủ công

```bash
mkdir -p .agents/skills
git clone https://github.com/d-init-d/d-research-skill.git .agents/skills/d-research
```

Trỏ agent/IDE của bạn tới:

```text
.agents/skills/d-research/SKILL.md
```

Nếu muốn chỉnh config theo project:

```bash
cp .agents/skills/d-research/research.config.example.json research.config.json
```

Nếu muốn dùng các script helper:

```bash
cd .agents/skills/d-research
npm install
npx playwright install
npm run self-test
```

## Config quan trọng

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
python3 scripts/research_plan.py init --slug topic
cd research-topic-2026-05-16
python3 ../scripts/research_plan.py configure-execution --file research-plan.json
python3 ../scripts/research_plan.py render --file research-plan.json
python3 ../scripts/research_plan.py gate --file research-plan.json --gate plan_ready
python3 ../scripts/research_plan.py approve --file research-plan.json --by "Reviewer"
python3 ../scripts/research_plan.py gate --file research-plan.json --gate execute_ready
```

Trên Windows, dùng `python` thay cho `python3` nếu cần.

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
