"""
Dynamic Mock Web Server for DRS-1.1 Interactive Evaluation (W03.03, W03.04).
Requires zero external dependencies (Python standard library only).
Serves initial HTML with zero precomputed answers; content is generated dynamically
in response to legitimate user DOM actions (search, filter, expand, replies, pagination, transcript).
"""

import json
import sys
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path

DIR_PATH = Path(__file__).parent.resolve()

class DynamicSiteHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Quiet mode by default
        if os.environ.get("VERBOSE_FIXTURE_SERVER"):
            super().log_message(format, *args)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            self._serve_file(DIR_PATH / "index.html", "text/html; charset=utf-8")
        elif path == "/style.css":
            self._serve_file(DIR_PATH / "style.css", "text/css; charset=utf-8")
        elif path == "/app.js":
            self._serve_file(DIR_PATH / "app.js", "application/javascript; charset=utf-8")
        elif path == "/api/search":
            q_str = query.get("query", [""])[0]
            self._handle_api_search({"query": q_str})
        elif path == "/api/filter":
            self._handle_api_filter(query)
        elif path == "/api/thread":
            self._handle_api_thread(query)
        elif path == "/api/replies":
            self._handle_api_replies(query)
        elif path == "/api/comments":
            self._handle_api_comments(query)
        elif path == "/api/transcript":
            self._handle_api_transcript(query)
        elif path == "/healthz":
            self._send_json({"status": "healthy", "server": "dynamic_mock_fixture_v1"})
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/search":
            content_length = int(self.headers.get("Content-Length", 0))
            body_bytes = self.rfile.read(content_length)
            try:
                data = json.loads(body_bytes.decode("utf-8"))
            except Exception:
                data = {}
            self._handle_api_search(data)
        else:
            self.send_error(404, "Not Found")

    def _serve_file(self, filepath, content_type):
        if not filepath.exists():
            self.send_error(404, "File Not Found")
            return
        content = filepath.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _handle_api_search(self, data):
        q = data.get("query", "").lower()
        if "lumen" in q or "2.1" in q or "csv" in q:
            results = [
                {
                    "id": "doc_v20",
                    "title": "Lumen 2.0.4 Maintenance Release",
                    "status": "draft",
                    "status_label": "Bản thảo",
                    "release_date": "2026-05-10",
                    "summary": "Bản vá sửa lỗi đồng bộ cũ cho các dòng thiết bị thế hệ trước."
                },
                {
                    "id": "doc_v21_draft",
                    "title": "Lumen 2.1 Release Candidate Draft",
                    "status": "draft",
                    "status_label": "Bản thảo",
                    "release_date": "2026-08-15",
                    "summary": "Đề xuất cải tiến giao diện thanh công cụ và thử nghiệm menu động."
                },
                {
                    "id": "doc_v21_final",
                    "title": "Lumen 2.1 Final Official Release",
                    "status": "final",
                    "status_label": "Bản chính thức",
                    "release_date": "2026-08-28",
                    "summary": "Bản phát hành chính thức toàn cầu với kiến trúc xuất dữ liệu bảo mật mới."
                }
            ]
        else:
            results = []
        self._send_json({"results": results, "query": q})

    def _handle_api_filter(self, query):
        filter_type = query.get("type", ["all"])[0]
        all_results = [
            {
                "id": "doc_v20",
                "title": "Lumen 2.0.4 Maintenance Release",
                "status": "draft",
                "status_label": "Bản thảo",
                "release_date": "2026-05-10",
                "summary": "Bản vá sửa lỗi đồng bộ cũ cho các dòng thiết bị thế hệ trước."
            },
            {
                "id": "doc_v21_draft",
                "title": "Lumen 2.1 Release Candidate Draft",
                "status": "draft",
                "status_label": "Bản thảo",
                "release_date": "2026-08-15",
                "summary": "Đề xuất cải tiến giao diện thanh công cụ và thử nghiệm menu động."
            },
            {
                "id": "doc_v21_final",
                "title": "Lumen 2.1 Final Official Release",
                "status": "final",
                "status_label": "Bản chính thức",
                "release_date": "2026-08-28",
                "summary": "Bản phát hành chính thức toàn cầu với kiến trúc xuất dữ liệu bảo mật mới."
            }
        ]

        if filter_type == "final":
            filtered = [r for r in all_results if r["status"] == "final"]
        elif filter_type == "draft":
            filtered = [r for r in all_results if r["status"] == "draft"]
        else:
            filtered = all_results

        self._send_json({"results": filtered, "filter": filter_type})

    def _handle_api_thread(self, query):
        thread_id = query.get("id", ["doc_v21_final"])[0]
        data = {
            "id": thread_id,
            "title": "Lumen 2.1 Final: Thảo luận cộng đồng & Ghi chú phát hành",
            "author": "tech_lead_alex",
            "created_at": "2026-08-28T08:15:00Z",
            "reply_count": 3,
            "preview_text": "Sau khi cập nhật bản 2.1 Final, nhiều người dùng phản ánh không tìm thấy nút xuất CSV ở thanh công cụ chính...",
            "full_body": "Sau khi cập nhật bản 2.1 Final, nhiều người dùng phản ánh không tìm thấy nút xuất CSV ở thanh công cụ chính. Tính năng này đóng vai trò cốt lõi trong quy trình phân tích số liệu hàng ngày. Đội ngũ kỹ thuật đã rà soát toàn bộ thay đổi và xác nhận vị trí cấu hình mới trong menu Cài đặt."
        }
        self._send_json(data)

    def _handle_api_replies(self, query):
        thread_id = query.get("thread_id", ["doc_v21_final"])[0]
        data = {
            "thread_id": thread_id,
            "total_pages": 2,
            "replies": [
                {
                    "id": "rep_01",
                    "author": "user_danang_01",
                    "created_at": "2026-08-28T08:30:00Z",
                    "is_correction": False,
                    "body": "Tôi cũng tìm khắp nơi trên màn hình chính mà không thấy nút CSV đâu cả!"
                },
                {
                    "id": "rep_02_correction",
                    "author": "minh_quan_lead_eng",
                    "created_at": "2026-08-28T09:10:00Z",
                    "is_correction": True,
                    "body": "Đính chính: Tính năng xuất CSV không bị loại bỏ mà được chuyển vào Settings > Data Management > Export CSV trên Desktop; chỉ bản Mobile là tạm ẩn nút chờ update 2.1.1."
                },
                {
                    "id": "rep_03",
                    "author": "tester_hcm",
                    "created_at": "2026-08-28T09:25:00Z",
                    "is_correction": False,
                    "body": "Đã vào Cài đặt và xuất file thành công, tốc độ nhanh hơn bản 2.0."
                }
            ]
        }
        self._send_json(data)

    def _handle_api_comments(self, query):
        page = int(query.get("page", ["1"])[0])
        if page == 2:
            comments = [
                {
                    "id": "c_13_reproduce",
                    "author": "kernel_hacker_vn",
                    "created_at": "2026-08-28T11:00:00Z",
                    "body": "Phương pháp tái hiện lỗi sync EX-21: Xảy ra khi đồng bộ thư mục chứa dấu tiếng Việt với cờ --strict-ascii."
                },
                {
                    "id": "c_16_contrary",
                    "author": "senior_devops_sg",
                    "created_at": "2026-08-28T11:45:00Z",
                    "body": "Phản bác: Ở chế độ mặc định UTF-8 auto-detect thì hoàn toàn không bị lỗi EX-21."
                }
            ]
        else:
            comments = [
                {
                    "id": "c_01",
                    "author": "dev_hanoi_99",
                    "created_at": "2026-08-28T08:40:00Z",
                    "body": "Tôi bị lỗi trên Android."
                }
            ]
        self._send_json({"page": page, "total_pages": 2, "comments": comments})

    def _handle_api_transcript(self, query):
        data = {
            "video_id": query.get("video_id", ["vid_lumen_21_overview"])[0],
            "title": "Video Hướng Dẫn Cập Nhật Tính Năng Lumen 2.1",
            "cues": [
                {
                    "timestamp": "00:18",
                    "speaker": "Người dẫn chương trình",
                    "text": "Liệu có phải bản cập nhật Lumen 2.1 đã gỡ bỏ hoàn toàn tính năng xuất tệp CSV?"
                },
                {
                    "timestamp": "00:54",
                    "speaker": "Khách mời",
                    "text": "Nhiều người dùng tại Việt Nam đã lên diễn đàn bày tỏ lo ngại về việc không thấy nút bấm."
                },
                {
                    "timestamp": "01:42",
                    "speaker": "Kỹ sư trưởng",
                    "text": "Đính chính chính thức: Tính năng xuất CSV vẫn còn nguyên vẹn trên desktop, chỉ được chuyển vị trí vào Settings để tối ưu bảo mật."
                }
            ]
        }
        self._send_json(data)

def run_server(port=8765):
    server_address = ("127.0.0.1", port)
    httpd = HTTPServer(server_address, DynamicSiteHandler)
    print(f"Dynamic mock fixture server running on http://127.0.0.1:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        httpd.server_close()

if __name__ == "__main__":
    port = 8765
    if len(sys.argv) > 1:
        if sys.argv[1] == "--port" and len(sys.argv) > 2:
            port = int(sys.argv[2])
        else:
            try:
                port = int(sys.argv[1])
            except ValueError:
                port = 8765
    run_server(port)
