// Interactive client-side controller for DRS-1.1 dynamic site fixture
document.addEventListener("DOMContentLoaded", () => {
  const searchForm = document.getElementById("search-form");
  const searchInput = document.getElementById("search-input");
  const filterSection = document.getElementById("filter-section");
  const filterType = document.getElementById("filter-type");
  const applyFilterBtn = document.getElementById("apply-filter");
  const resultsSection = document.getElementById("results-section");
  const resultsContainer = document.getElementById("results-container");
  const threadSection = document.getElementById("thread-section");
  const threadPost = document.getElementById("thread-post");
  const threadActions = document.getElementById("thread-actions");
  const repliesContainer = document.getElementById("replies-container");
  const paginationControls = document.getElementById("pagination-controls");
  const mediaSection = document.getElementById("media-section");
  const toggleTranscriptBtn = document.getElementById("toggle-transcript-btn");
  const transcriptPanel = document.getElementById("transcript-panel");

  let currentSearchResults = [];
  let currentThreadData = null;
  let currentCommentPage = 1;

  // Step 1: Handle Search Form Submission
  searchForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const query = searchInput.value.trim();
    if (!query) return;

    try {
      const res = await fetch(`/api/search?query=${encodeURIComponent(query)}`);
      const data = await res.json();
      currentSearchResults = data.results || [];
      renderSearchResults(currentSearchResults);

      // Reveal filter and results sections
      filterSection.classList.remove("hidden");
      resultsSection.classList.remove("hidden");
    } catch (err) {
      console.error("Search failed:", err);
    }
  });

  // Step 2: Handle Filter Selection
  applyFilterBtn.addEventListener("click", async () => {
    const selectedFilter = filterType.value;
    try {
      const res = await fetch(`/api/filter?type=${encodeURIComponent(selectedFilter)}`);
      const data = await res.json();
      renderSearchResults(data.results || []);
    } catch (err) {
      console.error("Filter failed:", err);
    }
  });

  function renderSearchResults(items) {
    resultsContainer.innerHTML = "";
    if (items.length === 0) {
      resultsContainer.innerHTML = "<p class='no-results'>Không tìm thấy tài liệu phù hợp.</p>";
      return;
    }

    items.forEach((item) => {
      const card = document.createElement("div");
      card.className = "result-card";
      card.id = `result-${item.id}`;
      card.innerHTML = `
        <div class="result-title">${item.title} <span class="badge badge-${item.status}">${item.status_label}</span></div>
        <div class="result-date">Ngày công bố: <strong>${item.release_date}</strong></div>
        <div class="result-summary">${item.summary}</div>
        <button type="button" class="open-thread-btn" data-id="${item.id}" style="margin-top:8px;">Mở xem chi tiết & thảo luận</button>
      `;
      resultsContainer.appendChild(card);
    });

    // Attach listeners to newly created Open Thread buttons
    document.querySelectorAll(".open-thread-btn").forEach((btn) => {
      btn.addEventListener("click", () => openThread(btn.getAttribute("data-id")));
    });
  }

  // Step 3: Open Thread Details
  async function openThread(threadId) {
    try {
      const res = await fetch(`/api/thread?id=${encodeURIComponent(threadId)}`);
      const data = await res.json();
      currentThreadData = data;
      currentCommentPage = 1;

      // Render initial truncated post
      threadPost.innerHTML = `
        <h3>${data.title}</h3>
        <div class="post-meta">Tác giả: <strong>${data.author}</strong> | Thời gian: ${data.created_at}</div>
        <div id="post-body-container" class="comment-body">${data.preview_text}</div>
      `;

      threadActions.innerHTML = `
        <button type="button" id="expand-post-btn" class="expand-btn">Xem toàn bộ bài viết (Show More)</button>
        <button type="button" id="view-replies-btn" class="view-replies-btn" style="margin-left:10px;">Xem ${data.reply_count} phản hồi (View Replies)</button>
      `;

      repliesContainer.classList.add("hidden");
      repliesContainer.innerHTML = "";
      threadSection.classList.remove("hidden");
      mediaSection.classList.remove("hidden");

      // Wire expand button
      document.getElementById("expand-post-btn").addEventListener("click", () => {
        const bodyElem = document.getElementById("post-body-container");
        bodyElem.innerHTML = currentThreadData.full_body;
        document.getElementById("expand-post-btn").classList.add("hidden");
      });

      // Wire view replies button
      document.getElementById("view-replies-btn").addEventListener("click", loadReplies);

    } catch (err) {
      console.error("Failed to load thread:", err);
    }
  }

  // Step 4 & 5: Load Nested Replies (Including Correction)
  async function loadReplies() {
    if (!currentThreadData) return;
    try {
      const res = await fetch(`/api/replies?thread_id=${encodeURIComponent(currentThreadData.id)}`);
      const data = await res.json();
      const replies = data.replies || [];

      repliesContainer.innerHTML = "<h4>Danh sách phản hồi & Thảo luận:</h4>";
      replies.forEach((rep) => {
        const repDiv = document.createElement("div");
        repDiv.className = `comment-box ${rep.is_correction ? "comment-correction" : ""}`;
        repDiv.id = `reply-${rep.id}`;
        repDiv.innerHTML = `
          <div class="comment-author">${rep.author} <span class="comment-time">${rep.created_at}</span></div>
          <div class="comment-body">${rep.body}</div>
        `;
        repliesContainer.appendChild(repDiv);
      });

      repliesContainer.classList.remove("hidden");

      // Render pagination container for additional comments
      renderPaginationControls(data.total_pages || 2);
    } catch (err) {
      console.error("Failed to load replies:", err);
    }
  }

  // Step 6: Paginate / Virtual Scroll Comments
  function renderPaginationControls(totalPages) {
    paginationControls.innerHTML = `
      <div style="margin-top:12px;">
        <span id="page-indicator">Trang ${currentCommentPage} / ${totalPages}</span>
        <button type="button" id="load-more-btn" style="margin-left:10px;">Tải thêm bình luận (Next Page)</button>
      </div>
      <div id="paged-comments-container"></div>
    `;
    paginationControls.classList.remove("hidden");

    document.getElementById("load-more-btn").addEventListener("click", async () => {
      currentCommentPage += 1;
      try {
        const res = await fetch(`/api/comments?page=${currentCommentPage}`);
        const data = await res.json();
        const container = document.getElementById("paged-comments-container");

        (data.comments || []).forEach((c) => {
          const cBox = document.createElement("div");
          cBox.className = "comment-box";
          cBox.id = `comment-${c.id}`;
          cBox.innerHTML = `
            <div class="comment-author">${c.author} <span class="comment-time">${c.created_at}</span></div>
            <div class="comment-body">${c.body}</div>
          `;
          container.appendChild(cBox);
        });

        document.getElementById("page-indicator").textContent = `Trang ${currentCommentPage} / ${totalPages}`;
        if (currentCommentPage >= totalPages) {
          document.getElementById("load-more-btn").disabled = true;
          document.getElementById("load-more-btn").textContent = "Đã tải hết bình luận";
        }
      } catch (err) {
        console.error("Pagination load failed:", err);
      }
    });
  }

  // Step 7: Toggle Video Transcript Panel
  toggleTranscriptBtn.addEventListener("click", async () => {
    if (!transcriptPanel.classList.contains("hidden")) {
      transcriptPanel.classList.add("hidden");
      return;
    }

    try {
      const res = await fetch("/api/transcript?video_id=vid_lumen_21_overview");
      const data = await res.json();
      const lines = data.cues || [];

      transcriptPanel.innerHTML = "<h4>Bản dịch / Phụ đề âm thanh (Transcript):</h4>";
      lines.forEach((cue) => {
        const lineDiv = document.createElement("div");
        lineDiv.className = "transcript-line";
        lineDiv.innerHTML = `<span class="cue-time">[${cue.timestamp}]</span> <span class="cue-speaker">${cue.speaker}:</span> <span class="cue-text">${cue.text}</span>`;
        transcriptPanel.appendChild(lineDiv);
      });

      transcriptPanel.classList.remove("hidden");
    } catch (err) {
      console.error("Failed to load transcript:", err);
    }
  });
});
