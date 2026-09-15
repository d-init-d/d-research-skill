#!/usr/bin/env python3
"""DRS-1.1 Research Controller & Adaptive Frontier Engine (Milestone G2 / Package W05).

Provides:
- Best-first adaptive priority frontier queue synchronized with frontier-ledger.csv and research-coverage.json
- Lightweight Research Move records logging (research-moves.jsonl)
- Evidence novelty & independence weighting with SimHash near-duplicate discounting
- Cross-branch handoff with lineage tracking (lineage_path) and anti-loop canonicalization
- Dynamic budget enforcement and stop controller across Fast, Standard, Deep profiles
- Checkpoint and resume support (cursor, visited IDs, pending leads, source revisions)
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

# Try importing dedup_near for SimHash, otherwise fallback
try:
    from dedup_near import simhash, hamming_distance
except ImportError:
    try:
        from scripts.dedup_near import simhash, hamming_distance
    except ImportError:
        def simhash(text: str) -> int:
            tokens = re.findall(r"\w+", text.lower())
            if not tokens:
                return 0
            v = [0] * 64
            for token in tokens:
                h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
                for i in range(64):
                    if (h >> i) & 1:
                        v[i] += 1
                    else:
                        v[i] -= 1
            fingerprint = 0
            for i in range(64):
                if v[i] > 0:
                    fingerprint |= (1 << i)
            return fingerprint

        def hamming_distance(a: int, b: int) -> int:
            return bin(a ^ b).count("1")


TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "fbclid", "gclid", "_ga", "trk", "spm", "source", "s",
}
SEMANTIC_PARAMS = {
    "id", "v", "version", "tab", "export", "format", "cursor", "page",
    "thread_id", "post_id", "q", "query", "lang", "locale",
}

BRANCH_TERMINAL_STATES = {
    "completed", "partial", "blocked", "no_relevant_results", "scope_excluded"
}


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def canonicalize_url(url: str) -> str:
    """Canonicalize a URL to prevent duplicate visits and loops while preserving semantic query params."""
    if not url:
        return ""
    # Unicode NFC normalization
    url = unicodedata.normalize("NFC", url.strip())
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url

    # Lowercase scheme and netloc
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path
    if path.endswith("/") and len(path) > 1:
        path = path.rstrip("/")

    # Filter query parameters: strip tracking params
    query_tuples = parse_qsl(parsed.query, keep_blank_values=True)
    filtered = [
        (k, v) for k, v in query_tuples
        if k.lower() not in TRACKING_PARAMS
    ]
    # Sort query params for deterministic canonical form
    filtered.sort(key=lambda x: x[0])
    query = urlencode(filtered)

    return urlunparse((scheme, netloc, path, parsed.params, query, ""))


@dataclass
class FrontierNode:
    node_id: str
    parent_id: str = ""
    branch: str = "social"  # "documentary" or "social"
    node_type: str = "query"  # "query", "url", "file", "api", "citation", "alias", "reply_thread"
    value: str = ""
    gap_id: str = "Q1"
    expansion_method: str = "seed"
    priority: float = 5.0
    status: str = "pending"  # "pending", "visited", "extracted", "blocked", "deferred", "dead_end"
    novelty_score: float = 3.0
    independence_score: float = 3.0
    lineage_path: list[str] = field(default_factory=list)
    branch_hops: int = 0
    access_status: str = "accessible"
    blocked_reason: str = ""
    claim_ids: list[str] = field(default_factory=list)
    date_visited: str = ""
    notes: str = ""
    content_snippet: str = ""


@dataclass
class BudgetProfile:
    name: str = "standard"
    max_queries_per_branch: int = 6
    max_sources_per_branch: int = 12
    max_comments_per_thread: int = 60
    thread_depth_cap: int = 4
    max_browser_actions_per_page: int = 30
    wall_time_cap_seconds: int = 1200
    consecutive_no_progress_actions: int = 3
    max_retries_per_error: int = 2


@dataclass
class StopEvaluation:
    should_stop: bool
    terminal_state: str
    stop_reason: str
    coverage_gaps: list[str] = field(default_factory=list)


@dataclass
class RevisionCheck:
    is_stale: bool
    cached_hash: str | None
    new_hash: str | None


@dataclass
class ResearchMoveRecord:
    move_id: str
    question_id: str
    branch_id: str
    timestamp: str
    source_ref: str
    finding: str
    gap: str
    decision: str
    next_action: str


class ResearchController:
    """Core adaptive research depth controller, priority frontier, and stop governor."""

    DEFAULT_PROFILES = {
        "fast": BudgetProfile(
            name="fast",
            max_queries_per_branch=2,
            max_sources_per_branch=3,
            max_comments_per_thread=12,
            thread_depth_cap=2,
            max_browser_actions_per_page=10,
            wall_time_cap_seconds=180,
            consecutive_no_progress_actions=2,
            max_retries_per_error=1,
        ),
        "standard": BudgetProfile(
            name="standard",
            max_queries_per_branch=6,
            max_sources_per_branch=12,
            max_comments_per_thread=60,
            thread_depth_cap=4,
            max_browser_actions_per_page=30,
            wall_time_cap_seconds=1200,
            consecutive_no_progress_actions=3,
            max_retries_per_error=2,
        ),
        "deep": BudgetProfile(
            name="deep",
            max_queries_per_branch=12,
            max_sources_per_branch=30,
            max_comments_per_thread=200,
            thread_depth_cap=6,
            max_browser_actions_per_page=60,
            wall_time_cap_seconds=3600,
            consecutive_no_progress_actions=3,
            max_retries_per_error=2,
        ),
    }

    def __init__(
        self,
        workspace_dir: Path | str,
        profile: str = "standard",
        run_id: str | None = None,
        execution_mode: str = "concurrent",
    ) -> None:
        self.workspace_dir = Path(workspace_dir).resolve()
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.profile = self.DEFAULT_PROFILES.get(profile, self.DEFAULT_PROFILES["standard"])
        self.profile_name = profile
        self.run_id = run_id or f"run-{datetime.now(timezone.utc).strftime('%Y%m%d')}-001"
        self.execution_mode = execution_mode
        self.plan_revision = 1

        # Frontier and state tracking
        self.frontier_nodes: dict[str, FrontierNode] = {}
        self.node_counter = 0
        self.visited_keys: set[str] = set()
        self.active_cursors: dict[str, str] = {}  # thread_id -> cursor
        self.cursor_history: dict[str, set[str]] = {}  # thread_id -> set of cursors
        self.source_revisions: dict[str, dict[str, Any]] = {}  # url -> {content_hash, etag, captured_at}
        self.seen_simhashes: list[int] = []

        # Budget consumption per branch
        self.consumed_budget: dict[str, dict[str, Any]] = {
            "documentary": {
                "queries": 0,
                "sources_visited": 0,
                "comments_extracted": 0,
                "browser_actions": 0,
                "elapsed_time": 0.0,
                "consecutive_no_progress": 0,
            },
            "social": {
                "queries": 0,
                "sources_visited": 0,
                "comments_extracted": 0,
                "browser_actions": 0,
                "elapsed_time": 0.0,
                "consecutive_no_progress": 0,
            },
        }

        # Branch states
        self.branch_states: dict[str, str] = {
            "documentary": "planned",
            "social": "planned",
        }
        self.branch_stop_reasons: dict[str, str | None] = {
            "documentary": None,
            "social": None,
        }

        # Move records
        self.moves: list[dict[str, Any]] = []

    @classmethod
    def init_workspace(
        cls,
        workspace_dir: Path | str,
        profile: str = "standard",
        run_id: str | None = None,
        execution_mode: str = "concurrent",
    ) -> ResearchController:
        controller = cls(workspace_dir, profile=profile, run_id=run_id, execution_mode=execution_mode)
        # Ensure directory structure
        (controller.workspace_dir / "research-output" / "notes").mkdir(parents=True, exist_ok=True)
        (controller.workspace_dir / "research-output" / "sections").mkdir(parents=True, exist_ok=True)
        return controller

    def _next_node_id(self) -> str:
        self.node_counter += 1
        return f"FN-{self.node_counter:03d}"

    def add_candidate(
        self,
        branch: str,
        node_type: str,
        value: str,
        gap_id: str,
        parent_id: str = "",
        expansion_method: str = "seed",
        priority: float | None = None,
        novelty_score: float = 3.0,
        independence_score: float = 3.0,
        content_snippet: str = "",
        notes: str = "",
    ) -> FrontierNode:
        """Add an exploratory lead to the frontier priority queue with lineage tracking and loop prevention."""
        node_id = self._next_node_id()

        # Build lineage path and compute branch hops
        parent_node = self.frontier_nodes.get(parent_id)
        lineage_path = []
        branch_hops = 0
        if parent_node:
            lineage_path = list(parent_node.lineage_path) + [parent_id]
            branch_hops = parent_node.branch_hops + (1 if parent_node.branch != branch else 0)

        # Canonicalize if URL
        canonical_val = canonicalize_url(value) if node_type == "url" else value.strip()
        canonical_key = canonical_val.lower()

        status = "pending"
        blocked_reason = ""

        # Loop and depth checks
        if branch_hops > 3:
            status = "blocked"
            blocked_reason = "cross_branch_depth_cap_exceeded"
        elif canonical_key in self.visited_keys or any(
            self.frontier_nodes.get(p_id) and self.frontier_nodes[p_id].value.lower() == canonical_key
            for p_id in lineage_path
        ):
            status = "dead_end"
            notes = "already_visited_in_lineage" if not notes else f"{notes}; already_visited_in_lineage"

        # Compute novelty discount via SimHash if snippet provided
        discounted_novelty = novelty_score
        if content_snippet:
            sh = simhash(content_snippet)
            dup_count = sum(1 for prev_sh in self.seen_simhashes if hamming_distance(sh, prev_sh) <= 3)
            discounted_novelty = max(0.5, novelty_score / (1.0 + 0.8 * dup_count))
            self.seen_simhashes.append(sh)

        # Compute priority score if not explicitly set
        computed_priority = priority
        if computed_priority is None:
            gap_prio = 4.0 if gap_id else 2.0
            relevance = 3.5
            authority = 3.0 if branch == "documentary" else 2.0
            access_cost = 1.0 if node_type in {"url", "api"} else 0.5
            computed_priority = 2.0 * gap_prio + 2.0 * relevance + 2.0 * discounted_novelty + 1.0 * authority - 1.0 * access_cost

        node = FrontierNode(
            node_id=node_id,
            parent_id=parent_id,
            branch=branch,
            node_type=node_type,
            value=canonical_val,
            gap_id=gap_id,
            expansion_method=expansion_method,
            priority=float(computed_priority),
            status=status,
            novelty_score=float(discounted_novelty),
            independence_score=float(independence_score),
            lineage_path=lineage_path,
            branch_hops=branch_hops,
            blocked_reason=blocked_reason,
            notes=notes,
            content_snippet=content_snippet,
        )
        self.frontier_nodes[node_id] = node
        self._sync_frontier_ledger()
        return node

    def pop_next_node(self, branch: str) -> FrontierNode | None:
        """Pop the highest priority pending node for the specified branch."""
        candidates = [
            n for n in self.frontier_nodes.values()
            if n.branch == branch and n.status == "pending"
        ]
        if not candidates:
            return None
        # Best-first: sort descending by priority
        candidates.sort(key=lambda n: n.priority, reverse=True)
        chosen = candidates[0]
        chosen.status = "visited"
        chosen.date_visited = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if chosen.node_type == "url":
            self.visited_keys.add(chosen.value.lower())
        self._sync_frontier_ledger()
        return chosen

    def record_move(
        self,
        question_id: str,
        branch_id: str,
        source_ref: str,
        finding: str,
        gap: str,
        decision: str,
        next_action: str,
    ) -> dict[str, Any]:
        """Record a research micro-decision move record and log to research-moves.jsonl."""
        digest = hashlib.md5(f"{question_id}:{branch_id}:{source_ref}:{finding}".encode("utf-8")).hexdigest()[:8]
        move_id = f"mv_{digest}"
        timestamp = _utc_now_iso()

        move_data = {
            "move_id": move_id,
            "question_id": question_id,
            "branch_id": branch_id,
            "timestamp": timestamp,
            "source_ref": source_ref,
            "finding": finding[:300],
            "gap": gap[:300],
            "decision": decision[:300],
            "next_action": next_action[:300],
        }
        self.moves.append(move_data)

        # Append to jsonl file
        moves_file = self.workspace_dir / "research-moves.jsonl"
        with moves_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(move_data, ensure_ascii=False) + "\n")

        return move_data

    def get_move_records(self, question_id: str | None = None) -> list[dict[str, Any]]:
        if question_id is None:
            return list(self.moves)
        return [m for m in self.moves if m.get("question_id") == question_id]

    def record_query_executed(self, branch: str, query_text: str) -> None:
        if branch in self.consumed_budget:
            self.consumed_budget[branch]["queries"] += 1

    def record_visited_url(self, url: str, content_hash: str | None = None, etag: str | None = None) -> None:
        can_url = canonicalize_url(url)
        self.visited_keys.add(can_url.lower())
        if content_hash:
            self.source_revisions[can_url] = {
                "content_hash": content_hash,
                "etag": etag,
                "captured_at": _utc_now_iso(),
            }

    def is_visited_url(self, url: str) -> bool:
        can_url = canonicalize_url(url)
        return can_url.lower() in self.visited_keys

    def record_comment_extracted(self, branch: str, count: int = 1) -> None:
        if branch in self.consumed_budget:
            self.consumed_budget[branch]["comments_extracted"] += count

    def record_browser_action(self, branch: str, action_type: str = "click") -> None:
        if branch in self.consumed_budget:
            self.consumed_budget[branch]["browser_actions"] += 1

    def record_cursor_seen(self, branch: str, thread_id: str, cursor: str) -> bool:
        """Record a cursor seen for pagination. Returns True if cursor was already seen (loop detected)."""
        history = self.cursor_history.setdefault(thread_id, set())
        if cursor in history:
            return True  # Loop detected
        history.add(cursor)
        self.active_cursors[thread_id] = cursor
        return False

    def set_active_cursor(self, thread_id: str, cursor: str) -> None:
        self.active_cursors[thread_id] = cursor
        self.cursor_history.setdefault(thread_id, set()).add(cursor)

    def get_active_cursor(self, thread_id: str) -> str | None:
        return self.active_cursors.get(thread_id)

    def set_branch_state(
        self,
        branch: str,
        state: str,
        stop_reason: str | None = None,
        scope_reference: str | None = None,
    ) -> None:
        self.branch_states[branch] = state
        self.branch_stop_reasons[branch] = stop_reason

    def get_branch_state(self, branch: str) -> str:
        return self.branch_states.get(branch, "planned")

    def evaluate_stop_condition(self, branch: str) -> StopEvaluation:
        """Evaluate stop conditions against budget caps, no-progress limits, and resolution criteria."""
        b_cons = self.consumed_budget.get(branch, {})
        queries = b_cons.get("queries", 0)
        sources = b_cons.get("sources_visited", 0)
        comments = b_cons.get("comments_extracted", 0)
        no_progress = b_cons.get("consecutive_no_progress", 0)

        # 1. Budget exhaustion check -> ALWAYS partial! Never completed!
        if queries >= self.profile.max_queries_per_branch:
            reason = f"budget_exhausted:max_queries_per_branch({queries}>={self.profile.max_queries_per_branch})"
            self.set_branch_state(branch, "partial", stop_reason=reason)
            return StopEvaluation(
                should_stop=True,
                terminal_state="partial",
                stop_reason=reason,
                coverage_gaps=["Q1"],
            )

        if sources >= self.profile.max_sources_per_branch:
            reason = f"budget_exhausted:max_sources_per_branch({sources}>={self.profile.max_sources_per_branch})"
            self.set_branch_state(branch, "partial", stop_reason=reason)
            return StopEvaluation(
                should_stop=True,
                terminal_state="partial",
                stop_reason=reason,
                coverage_gaps=["Q1"],
            )

        if comments >= self.profile.max_comments_per_thread:
            reason = f"budget_exhausted:max_comments_per_thread({comments}>={self.profile.max_comments_per_thread})"
            self.set_branch_state(branch, "partial", stop_reason=reason)
            return StopEvaluation(
                should_stop=True,
                terminal_state="partial",
                stop_reason=reason,
                coverage_gaps=["Q1"],
            )

        if no_progress >= self.profile.consecutive_no_progress_actions:
            reason = "no_progress_limit_reached"
            self.set_branch_state(branch, "completed", stop_reason=reason)
            return StopEvaluation(
                should_stop=True,
                terminal_state="completed",
                stop_reason=reason,
                coverage_gaps=[],
            )

        # Check if already terminal
        curr_state = self.get_branch_state(branch)
        if curr_state in BRANCH_TERMINAL_STATES:
            return StopEvaluation(
                should_stop=True,
                terminal_state=curr_state,
                stop_reason=self.branch_stop_reasons.get(branch) or "branch_terminal",
                coverage_gaps=[],
            )

        # Check pending frontier leads for this branch
        pending_leads = [
            n for n in self.frontier_nodes.values()
            if n.branch == branch and n.status == "pending"
        ]
        if not pending_leads and (queries > 0 or sources > 0):
            reason = "frontier_exhausted"
            self.set_branch_state(branch, "completed", stop_reason=reason)
            return StopEvaluation(
                should_stop=True,
                terminal_state="completed",
                stop_reason=reason,
                coverage_gaps=[],
            )

        return StopEvaluation(
            should_stop=False,
            terminal_state=curr_state,
            stop_reason="",
            coverage_gaps=[],
        )

    def can_proceed_to_reconciliation(self) -> bool:
        """Reconciliation barrier: only returns True when BOTH documentary and social branches are terminal."""
        doc_state = self.get_branch_state("documentary")
        soc_state = self.get_branch_state("social")
        return doc_state in BRANCH_TERMINAL_STATES and soc_state in BRANCH_TERMINAL_STATES

    def check_source_revision(self, url: str, new_content_hash: str) -> RevisionCheck:
        """Check if cached source content hash changed (detecting stale sources)."""
        can_url = canonicalize_url(url)
        cached = self.source_revisions.get(can_url)
        if not cached:
            return RevisionCheck(is_stale=False, cached_hash=None, new_hash=new_content_hash)
        old_hash = cached.get("content_hash")
        is_stale = (old_hash != new_content_hash)
        return RevisionCheck(is_stale=is_stale, cached_hash=old_hash, new_hash=new_content_hash)

    def save_checkpoint(self, path: Path | str) -> None:
        """Save execution checkpoint conforming to schemas/checkpoint.schema.json."""
        target = Path(path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)

        chk_id = f"chk_{hashlib.md5(f'{self.run_id}:{_utc_now_iso()}'.encode('utf-8')).hexdigest()[:8]}"
        total_queries = sum(b.get("queries", 0) for b in self.consumed_budget.values())
        total_sources = sum(b.get("sources_visited", 0) for b in self.consumed_budget.values())
        total_comments = sum(b.get("comments_extracted", 0) for b in self.consumed_budget.values())
        total_actions = sum(b.get("browser_actions", 0) for b in self.consumed_budget.values())
        elapsed_time = max(b.get("elapsed_time", 0.0) for b in self.consumed_budget.values())

        pending_frontier = [
            asdict(n) for n in self.frontier_nodes.values()
            if n.status == "pending"
        ]

        checkpoint_data = {
            "checkpoint_id": chk_id,
            "schema_version": "1.1.0",
            "run_id": self.run_id,
            "plan_revision": self.plan_revision,
            "timestamp": _utc_now_iso(),
            "profile_name": self.profile_name,
            "consumed_budget": {
                "total_queries": total_queries,
                "total_sources_visited": total_sources,
                "total_comments_extracted": total_comments,
                "total_browser_actions": total_actions,
                "elapsed_wall_time_seconds": float(elapsed_time),
            },
            "branch_states": dict(self.branch_states),
            "visited_keys": sorted(self.visited_keys),
            "source_revisions": dict(self.source_revisions),
            "pending_frontier": pending_frontier,
            "active_cursors": dict(self.active_cursors),
        }
        target.write_text(json.dumps(checkpoint_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    @classmethod
    def load_checkpoint(cls, path: Path | str) -> ResearchController:
        """Restore controller instance from checkpoint."""
        target = Path(path).resolve()
        data = json.loads(target.read_text(encoding="utf-8"))

        controller = cls(
            workspace_dir=target.parent,
            profile=data.get("profile_name", "standard"),
            run_id=data.get("run_id"),
        )
        controller.plan_revision = data.get("plan_revision", 1)
        controller.branch_states = dict(data.get("branch_states", {}))
        controller.visited_keys = set(data.get("visited_keys", []))
        controller.source_revisions = dict(data.get("source_revisions", {}))
        controller.active_cursors = dict(data.get("active_cursors", {}))

        # Restore pending frontier
        for n_dict in data.get("pending_frontier", []):
            node = FrontierNode(**n_dict)
            controller.frontier_nodes[node.node_id] = node
            match = re.search(r"FN-(\d+)", node.node_id)
            if match:
                controller.node_counter = max(controller.node_counter, int(match.group(1)))

        return controller

    def _sync_frontier_ledger(self) -> None:
        """Synchronize frontier nodes to frontier-ledger.csv in workspace."""
        csv_path = self.workspace_dir / "frontier-ledger.csv"
        fieldnames = [
            "node_id", "parent_id", "node_type", "value", "gap_id",
            "expansion_method", "priority", "status", "access_status",
            "blocked_reason", "claim_ids", "date_visited", "notes"
        ]
        rows = []
        for n in self.frontier_nodes.values():
            rows.append({
                "node_id": n.node_id,
                "parent_id": n.parent_id,
                "node_type": n.node_type,
                "value": n.value,
                "gap_id": n.gap_id,
                "expansion_method": n.expansion_method,
                "priority": f"{n.priority:.1f}",
                "status": n.status,
                "access_status": n.access_status,
                "blocked_reason": n.blocked_reason,
                "claim_ids": ";".join(n.claim_ids),
                "date_visited": n.date_visited,
                "notes": n.notes,
            })
        try:
            with csv_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        except OSError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="DRS-1.1 Research Depth Controller CLI")
    parser.add_argument("--workspace", default=".", help="Workspace directory")
    parser.add_argument("--profile", default="standard", choices=["fast", "standard", "deep"])
    args = parser.parse_args()
    controller = ResearchController.init_workspace(args.workspace, profile=args.profile)
    print(f"Initialized research controller in {controller.workspace_dir} (profile: {controller.profile_name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
