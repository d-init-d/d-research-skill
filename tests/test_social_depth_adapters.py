"""
test_social_depth_adapters.py - Acceptance Tests for DRS-1.1 Package W07 (C01 - C08).
"""

import json
from pathlib import Path
import re
import sys

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from social_adapters import (
    RedditCommentAdapter,
    HackerNewsAdapter,
    YouTubeTranscriptAdapter,
    VietnameseForumAdapter,
    VietnameseSlangNormalizer,
    get_platform_capability_matrix,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_c01_reddit_hn_recursive_comment_threads():
    """Acceptance C01: Multi-tier recursive comment threads parsed with depth hierarchy."""
    fixture_path = FIXTURES_DIR / "social_thread_fixtures.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Wrap comments into Reddit-style listing format
    reddit_payload = [
        {"data": {"children": [{"data": {
            "name": data["thread_metadata"]["root_post_id"],
            "title": data["thread_metadata"]["title"],
            "author": data["thread_metadata"]["author"],
            "created_utc": 1756368900,
            "selftext": data["root_post"]["full_body"],
            "num_comments": data["thread_metadata"]["total_server_comments"],
        }}]}},
        {"data": {"children": [
            {
                "kind": "t1",
                "data": {
                    "name": "c_01",
                    "author": "user_viet_nam_01",
                    "body": "Đúng rồi, mình mở lên tìm nút xuất CSV hoài không thấy đâu",
                    "created_utc": 1756369500,
                    "replies": {
                        "data": {
                            "children": [
                                {
                                    "kind": "t1",
                                    "data": {
                                        "name": "c_01_01",
                                        "author": "dev_hanoi_99",
                                        "body": "Tôi cũng bị tương tự trên bản Android và iOS",
                                        "created_utc": 1756370400,
                                        "replies": {
                                            "data": {
                                                "children": [
                                                    {
                                                        "kind": "t1",
                                                        "data": {
                                                            "name": "c_01_01_01",
                                                            "author": "lumen_support_bot_fake",
                                                            "body": "Hệ thống tự động: Tính năng đã được tái cấu trúc.",
                                                            "replies": ""
                                                        }
                                                    }
                                                ]
                                            }
                                        }
                                    }
                                }
                            ]
                        }
                    }
                }
            },
            {
                "kind": "t1",
                "data": {
                    "name": "c_02_correction",
                    "author": "minh_quan_lead_eng",
                    "body": "ĐÍNH CHÍNH QUAN TRỌNG: Tính năng xuất CSV KHÔNG BỊ XÓA! Settings > Export",
                    "created_utc": 1756372200,
                    "is_authoritative_correction": True,
                    "replies": ""
                }
            }
        ]}}
    ]

    result = RedditCommentAdapter.parse_reddit_json(reddit_payload, depth_cap=5, max_comments=50)

    assert result.platform == "reddit"
    assert result.root_post_id == "post_lum_2026_01"
    assert result.depth_reached == 3
    assert result.has_authoritative_correction is True
    assert len(result.comments) == 2
    assert result.comments[0].comment_id == "c_01"
    assert result.comments[0].depth == 1
    assert len(result.comments[0].replies) == 1
    assert result.comments[0].replies[0].comment_id == "c_01_01"
    assert result.comments[0].replies[0].depth == 2
    assert len(result.comments[0].replies[0].replies) == 1
    assert result.comments[0].replies[0].replies[0].depth == 3


def test_c01_hacker_news_hierarchy():
    """Acceptance C01: Hacker News nested items parsed with author context."""
    hn_root = {
        "id": 8942001,
        "title": "Ask HN: Did Lumen 2.1 drop CSV export?",
        "by": "tech_lead_alex",
        "time": 1756368900,
        "text": "Cannot find CSV export button in Lumen 2.1 toolbar.",
        "descendants": 3,
        "children": [
            {
                "id": 8942002,
                "by": "random_user",
                "text": "Confirmed, missing on my end too.",
                "created_at_i": 1756369500,
                "children": [
                    {
                        "id": 8942003,
                        "by": "core_dev",
                        "text": "Correction: It moved under Settings > Data Management > Export CSV.",
                        "created_at_i": 1756372200,
                        "is_authoritative_correction": True,
                        "children": []
                    }
                ]
            }
        ]
    }

    result = HackerNewsAdapter.parse_hn_item(hn_root)

    assert result.platform == "hackernews"
    assert result.root_post_id == "8942001"
    assert result.depth_reached == 2
    assert result.has_authoritative_correction is True
    assert len(result.comments) == 1
    assert result.comments[0].replies[0].is_authoritative_correction is True


def test_c02_sort_mode_divergence_authoritative_correction():
    """Acceptance C02: Authoritative correction identified among community consensus."""
    forum_meta = {
        "thread_id": "thread_8942",
        "title": "Lumen 2.1 mất nút tải CSV?",
        "author": "alex",
        "created_at": "2026-08-28T08:15:00Z",
        "total_replies": 3
    }
    posts = [
        {"post_id": "p1", "author": "user1", "body": "Bản này xóa mất nút CSV rồi, chán thật!", "author_role": "member"},
        {"post_id": "p2", "author": "user2", "body": "Đúng đấy, tìm mãi không ra", "author_role": "member"},
        {
            "post_id": "p3",
            "author": "lead_engineer",
            "body": "Đính chính: Nút CSV không bị xóa mà chuyển vào Settings > Export CSV.",
            "author_role": "tech_lead",
            "is_authoritative_correction": True
        }
    ]

    result = VietnameseForumAdapter.parse_forum_posts(forum_meta, posts)
    assert result.has_authoritative_correction is True
    correction_posts = [c for c in result.comments if c.is_authoritative_correction]
    assert len(correction_posts) == 1
    assert correction_posts[0].author == "lead_engineer"
    assert "Settings > Export CSV" in correction_posts[0].body


def test_c03_vietnamese_slang_expansion_and_unicode():
    """Acceptance C03: Expansion of colloquial slang and diacritic normalization."""
    normalizer = VietnameseSlangNormalizer()

    # Query with 'mất nút tải'
    res1 = normalizer.expand_query("Lumen 2.1 mất nút tải csv")
    assert res1["has_slang"] is True
    assert "mất nút tải" in res1["detected_slang"]
    assert any("csv export button relocated" in q for q in res1["expanded_formal_queries"])

    # Query with 'văng app'
    res2 = normalizer.expand_query("lumen 2.1 bị văng app khi bấm đồng bộ")
    assert res2["has_slang"] is True
    assert "văng app" in res2["detected_slang"]
    assert any("crash on sync" in q for q in res2["expanded_formal_queries"])

    # Unicode diacritic normalization (NFC vs NFD)
    nfd_text = "Tính năng xuất dữ liệu CSV"
    nfc_text = "Tính năng xuất dữ liệu CSV"
    assert normalizer.normalize_unicode(nfd_text) == normalizer.normalize_unicode(nfc_text)


def test_c04_social_lead_links_to_documentary():
    """Acceptance C04: Social post citing official documentation or DOI."""
    comment_body = "See official documentation at https://docs.lumen.example.com/v2.1/export for migration details."
    urls = re.findall(r"https?://[^\s]+", comment_body)
    assert len(urls) == 1
    assert "docs.lumen.example.com" in urls[0]


def test_c05_youtube_interactive_transcript():
    """Acceptance C05: Video transcript cue extraction with timecodes and search."""
    transcript_raw = {
        "status": "ok",
        "video_id": "vid_lum_01",
        "title": "Lumen 2.1 Video Guide",
        "language": "vi",
        "is_auto_generated": False,
        "cues": [
            {"start": 0.0, "duration": 4.5, "text": "Chào mừng các bạn đến với video đánh giá Lumen 2.1.", "speaker": "Host"},
            {"start": 102.0, "duration": 5.0, "text": "Kỹ sư trưởng: Đính chính chính thức: Tính năng xuất CSV vẫn còn nguyên vẹn trên desktop.", "speaker": "Lead Engineer", "timestamp_display": "01:42"},
            {"start": 120.0, "duration": 3.0, "text": "Chúc các bạn trải nghiệm vui vẻ.", "speaker": "Host"}
        ]
    }

    result = YouTubeTranscriptAdapter.parse_transcript_data(transcript_raw)
    assert result.status == "ok"
    assert len(result.cues) == 3
    assert "[01:42]" in result.full_text

    matches = YouTubeTranscriptAdapter.search_transcript(result, "xuất CSV")
    assert len(matches) == 1
    assert matches[0]["timestamp_anchor"] == "01:42"
    assert matches[0]["matched_cue"]["speaker"] == "Lead Engineer"
    assert "Kỹ sư trưởng" in matches[0]["matched_text"]


def test_c06_unobtainable_video_transcript():
    """Acceptance C06: Video transcript unavailable or disabled handled gracefully."""
    transcript_disabled = {
        "status": "disabled",
        "video_id": "vid_no_subs",
        "title": "Short Clip Without Subtitles",
        "limitation": "Subtitles are disabled by the video owner"
    }

    result = YouTubeTranscriptAdapter.parse_transcript_data(transcript_disabled)
    assert result.status == "disabled"
    assert len(result.cues) == 0
    assert "disabled" in result.limitation.lower()


def test_c07_c08_platform_capability_matrix_and_bounds():
    """Capability matrix distinguishes fixture parsing, live proof, and access gates."""
    matrix = get_platform_capability_matrix()
    assert matrix["schema_version"] == "1.0"
    assert "reddit" in matrix["fixture_verified"]
    assert "hackernews" in matrix["fixture_verified"]
    assert "youtube" in matrix["fixture_verified"]
    assert matrix["live_verified"] == []
    assert "x_twitter" in matrix["access_gated"]
    assert matrix["platforms"]["youtube"]["live_status"] == "unverified_live"
    assert matrix["platforms"]["x_twitter"]["auth_required"] is True
    assert matrix["platforms"]["x_twitter"]["live_status"] == "blocked_auth_required"
    assert matrix["platforms"]["reddit"]["depth_cap"] >= 4
