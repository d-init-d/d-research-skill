"""Test suite for DRS-1.1 Package W05: Adaptive Depth Research Controller (E01, E02, E07, E08).

Verifies:
- E01: Multi-step lead following (slang -> error code -> changelog -> correction)
- E02: Branch starvation prevention (documentary done does NOT starve social; reconciliation barrier)
- E07: Budget enforcement (budget exhaustion -> partial with coverage gaps) and cursor loop detection
- E08: Checkpoint & resume (cursor, visited IDs, pending leads, source revision staleness check)
- Additional: Evidence novelty discounting via SimHash, cross-branch depth capping, anti-ping-pong loops
"""

import json
from pathlib import Path
import sys

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from research_controller import (
    ResearchController,
    canonicalize_url,
)


def test_E01_multi_step_lead_following(tmp_path):
    """TP08 / E01: Slang lead -> error code -> docs/changelog -> correction -> updated conclusion."""
    controller = ResearchController.init_workspace(tmp_path, profile="standard")

    # Step 1: Initial colloquial query
    node1 = controller.add_candidate(
        branch="social",
        node_type="query",
        value="lumen 2.1 mất nút tải csv",
        gap_id="Q1",
        expansion_method="initial_dispatch",
    )
    pop1 = controller.pop_next_node("social")
    assert pop1 is not None
    assert pop1.node_id == node1.node_id

    # Step 2: Extract slang thread revealing error code EX-21
    controller.record_move(
        question_id="Q1",
        branch_id="social",
        source_ref="https://forum.example.com/t/991",
        finding="User reports button missing, mentions error code EX-21",
        gap="Need official error documentation and desktop vs mobile scope",
        decision="Follow error code to official changelog",
        next_action="Search documentary branch for EX-21 and CSV export",
    )

    # Cross-branch handoff: Social thread generates documentary candidate
    doc_node = controller.add_candidate(
        branch="documentary",
        node_type="query",
        value="Lumen 2.1 EX-21 CSV export settings",
        gap_id="Q1",
        parent_id=pop1.node_id,
        expansion_method="cross_branch_handoff",
    )
    assert doc_node.parent_id == pop1.node_id
    assert "cross_branch_handoff" in doc_node.expansion_method

    # Step 3: Documentary search finds official settings changelog
    pop_doc = controller.pop_next_node("documentary")
    assert pop_doc is not None
    assert pop_doc.node_id == doc_node.node_id
    controller.record_move(
        question_id="Q1",
        branch_id="documentary",
        source_ref="https://docs.example.com/changelog/2.1",
        finding="CSV export moved to Settings > Data Management on desktop; mobile hidden",
        gap="Resolved scope distinction",
        decision="Conclude feature relocated, not deleted",
        next_action="Stop expansion and synthesize",
    )

    # Verify move trail integrity
    moves = controller.get_move_records("Q1")
    assert len(moves) == 2
    assert moves[0]["branch_id"] == "social"
    assert moves[1]["branch_id"] == "documentary"
    assert moves[0]["next_action"] == "Search documentary branch for EX-21 and CSV export"

    # Verify research-moves.jsonl was written to workspace
    moves_file = tmp_path / "research-moves.jsonl"
    assert moves_file.is_file()
    lines = [json.loads(line) for line in moves_file.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 2


def test_E02_branch_starvation_prevention(tmp_path):
    """TP07 / E02: Documentary branch finishing early does NOT starve or cancel social branch."""
    controller = ResearchController.init_workspace(tmp_path, profile="standard")
    controller.set_branch_state("documentary", "completed", stop_reason="primary_saturated")

    # Social branch is still running with pending high-value leads
    controller.add_candidate(
        branch="social",
        node_type="url",
        value="https://community.example.com/t/correction/8942",
        gap_id="Q1",
        priority=8.5,
        expansion_method="reply_tree",
    )

    # Verify stop controller does NOT terminate social branch
    stop_eval = controller.evaluate_stop_condition("social")
    assert stop_eval.should_stop is False
    assert controller.can_proceed_to_reconciliation() is False

    # Social branch pops and finishes
    popped = controller.pop_next_node("social")
    assert popped is not None
    controller.set_branch_state("social", "completed", stop_reason="thread_read_complete")

    # Now reconciliation is unblocked
    assert controller.can_proceed_to_reconciliation() is True


def test_E07_budget_enforcement_and_loop_bounded(tmp_path):
    """TP03 / E07: Budget exhaustion transitions to 'partial', never 'completed' or 'saturation'."""
    controller = ResearchController.init_workspace(tmp_path, profile="fast")  # fast: max 2 queries

    controller.record_query_executed("social", "query 1")
    controller.record_query_executed("social", "query 2")

    # Try adding another query
    controller.add_candidate(
        branch="social",
        node_type="query",
        value="query 3",
        gap_id="Q1",
        expansion_method="query_fanout",
    )

    stop_eval = controller.evaluate_stop_condition("social")
    assert stop_eval.should_stop is True
    assert stop_eval.terminal_state == "partial"
    assert "budget_exhausted" in stop_eval.stop_reason
    assert "Q1" in stop_eval.coverage_gaps

    # Cursor loop test
    controller.record_cursor_seen("social", "thread_1", "cursor_A")
    controller.record_cursor_seen("social", "thread_1", "cursor_B")
    is_loop = controller.record_cursor_seen("social", "thread_1", "cursor_A")  # repeated cursor
    assert is_loop is True


def test_E08_checkpoint_and_resume(tmp_path):
    """TP14 / E08: Mid-thread pause -> resume from cursor without redundant fetch."""
    controller = ResearchController.init_workspace(tmp_path, profile="standard")
    controller.record_visited_url("https://example.com/page1", content_hash="hash_v1")
    controller.set_active_cursor("thread_01", "cursor_pg_2")

    # Add pending candidate
    controller.add_candidate(
        branch="social",
        node_type="url",
        value="https://example.com/page2",
        gap_id="Q1",
        expansion_method="reply_tree",
    )

    # Save checkpoint
    chk_path = tmp_path / "checkpoint.json"
    controller.save_checkpoint(chk_path)
    assert chk_path.is_file()

    # Resume in new controller instance
    resumed = ResearchController.load_checkpoint(chk_path)
    assert resumed.is_visited_url("https://example.com/page1") is True
    assert resumed.get_active_cursor("thread_01") == "cursor_pg_2"
    assert len(resumed.frontier_nodes) == 1

    # Source revision mutation check
    stale_check = resumed.check_source_revision(
        "https://example.com/page1",
        new_content_hash="hash_v2",
    )
    assert stale_check.is_stale is True

    same_check = resumed.check_source_revision(
        "https://example.com/page1",
        new_content_hash="hash_v1",
    )
    assert same_check.is_stale is False


def test_novelty_discounting_via_simhash(tmp_path):
    """Novelty weighting discounts near-duplicate snippets (SimHash Hamming distance <= 3)."""
    controller = ResearchController.init_workspace(tmp_path, profile="standard")

    text1 = "Lumen 2.1 update removes the CSV export button from the main navigation toolbar."
    node1 = controller.add_candidate(
        branch="social",
        node_type="url",
        value="https://forum1.example.com/p1",
        gap_id="Q1",
        novelty_score=4.0,
        content_snippet=text1,
    )

    # Near-duplicate repost with trivial punctuation change
    text2 = "Lumen 2.1 update removes the CSV export button from the main navigation toolbar!"
    node2 = controller.add_candidate(
        branch="social",
        node_type="url",
        value="https://forum2.example.com/p2",
        gap_id="Q1",
        novelty_score=4.0,
        content_snippet=text2,
    )

    # Novel, independent empirical study with completely different text
    text3 = "Empirical verification: CLI command lumen export --format csv succeeds on macOS desktop builds."
    node3 = controller.add_candidate(
        branch="social",
        node_type="url",
        value="https://study.example.com/report",
        gap_id="Q1",
        novelty_score=4.0,
        content_snippet=text3,
    )

    # Node 2 must have discounted novelty and lower priority than Node 1 and Node 3
    assert node2.novelty_score < node1.novelty_score
    assert node2.priority < node1.priority
    assert node3.novelty_score >= node1.novelty_score


def test_anti_loop_canonical_url_and_lineage_capping(tmp_path):
    """Tests URL canonicalization (stripping tracking params, NFC normalize) and depth capping."""
    # Tracking parameters stripped, semantic preserved
    raw_url = "https://example.com/thread?utm_source=twitter&id=8942&ref=social&page=2"
    can = canonicalize_url(raw_url)
    assert "utm_source" not in can
    assert "ref" not in can
    assert "id=8942" in can
    assert "page=2" in can

    controller = ResearchController.init_workspace(tmp_path, profile="standard")
    
    # Hop 0
    n0 = controller.add_candidate(branch="documentary", node_type="url", value="https://example.com/0", gap_id="Q1")
    # Hop 1
    n1 = controller.add_candidate(branch="social", node_type="url", value="https://example.com/1", gap_id="Q1", parent_id=n0.node_id)
    # Hop 2
    n2 = controller.add_candidate(branch="documentary", node_type="url", value="https://example.com/2", gap_id="Q1", parent_id=n1.node_id)
    # Hop 3
    n3 = controller.add_candidate(branch="social", node_type="url", value="https://example.com/3", gap_id="Q1", parent_id=n2.node_id)
    # Hop 4 -> Exceeds max 3 cross-branch hops
    n4 = controller.add_candidate(branch="documentary", node_type="url", value="https://example.com/4", gap_id="Q1", parent_id=n3.node_id)

    assert n4.status == "blocked"
    assert n4.blocked_reason == "cross_branch_depth_cap_exceeded"
