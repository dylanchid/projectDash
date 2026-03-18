from __future__ import annotations

from datetime import datetime

from projectdash.models import AgentRun, CiCheck, Issue, PullRequest, User
from projectdash.views.issue_flow import FlowEntry, IssueFlowScreen


def _pr(pr_id: str, number: int) -> PullRequest:
    return PullRequest(
        id=pr_id,
        provider="github",
        repository_id="github:acme/api",
        number=number,
        title=f"PR {number}",
        state="open",
        author_id="alice",
        head_branch=f"feature/{number}",
        base_branch="main",
        url=f"https://github.com/acme/api/pull/{number}",
        issue_id="PD-7",
        opened_at="2026-02-20T00:00:00Z",
        merged_at=None,
        closed_at=None,
        updated_at="2026-02-24T00:00:00Z",
    )


def _issue(issue_id: str = "PD-7") -> Issue:
    return Issue(
        id=issue_id,
        title="Improve issue flow drilldown",
        priority="High",
        status="In Progress",
        assignee=User("u1", "Alice"),
        points=5,
        due_date="2026-03-05",
        created_at=datetime(2026, 2, 20, 9, 30, 0),
    )


def test_selected_pull_request_uses_agent_entry_run_pr_id() -> None:
    screen = IssueFlowScreen("PD-7")
    primary = _pr("pr-1", 1)
    secondary = _pr("pr-2", 2)
    screen._prs_by_id = {primary.id: primary, secondary.id: secondary}
    screen._agent_runs = [
        AgentRun(
            id="run-1",
            runtime="issue-flow",
            status="queued",
            started_at="2026-02-25 10:00:00",
            pr_id=secondary.id,
            issue_id="PD-7",
        )
    ]
    screen._entries = [
        FlowEntry(
            kind="agent",
            label="Agent queued",
            timestamp="2026-02-25 10:00:00",
            sort_key=None,
            run_id="run-1",
        )
    ]
    screen.selected_index = 0

    selected = screen._selected_pull_request()

    assert selected is not None
    assert selected.id == secondary.id


def test_review_status_for_pr_uses_check_health() -> None:
    screen = IssueFlowScreen("PD-7")
    pr = _pr("pr-3", 3)

    failing = CiCheck(
        id="c-1",
        provider="github",
        pull_request_id=pr.id,
        name="ci",
        status="completed",
        conclusion="failure",
        updated_at="2026-02-24T01:00:00Z",
    )
    pending = CiCheck(
        id="c-2",
        provider="github",
        pull_request_id=pr.id,
        name="ci",
        status="in_progress",
        conclusion=None,
        updated_at="2026-02-24T01:00:00Z",
    )
    passing = CiCheck(
        id="c-3",
        provider="github",
        pull_request_id=pr.id,
        name="ci",
        status="completed",
        conclusion="success",
        updated_at="2026-02-24T01:00:00Z",
    )

    assert screen._review_status_for_pr(pr, [failing]) == "changes-required"
    assert screen._review_status_for_pr(pr, [pending]) == "awaiting-checks"
    assert screen._review_status_for_pr(pr, [passing]) == "ready"


def test_selected_pull_request_falls_back_to_first_pr_for_issue_entry() -> None:
    screen = IssueFlowScreen("PD-7")
    primary = _pr("pr-1", 1)
    secondary = _pr("pr-2", 2)
    screen._prs_by_id = {primary.id: primary, secondary.id: secondary}
    screen._entries = [
        FlowEntry(
            kind="issue",
            label="Issue created",
            timestamp="2026-02-25 10:00:00",
            sort_key=None,
            issue_id="PD-7",
        )
    ]
    screen.selected_index = 0

    selected = screen._selected_pull_request()

    assert selected is not None
    assert selected.id == primary.id


def test_pull_request_health_counts_include_state_failing_and_stale(monkeypatch) -> None:
    screen = IssueFlowScreen("PD-7")
    monkeypatch.setenv("PD_TRIAGE_STALE_DAYS", "7")
    stale_open = _pr("pr-open-stale", 10)
    stale_open.updated_at = "2026-02-10T00:00:00Z"
    merged = _pr("pr-merged", 11)
    merged.state = "merged"
    merged.merged_at = "2026-02-24T00:00:00Z"
    closed = _pr("pr-closed", 12)
    closed.state = "closed"
    closed.closed_at = "2026-02-24T00:00:00Z"

    failing = CiCheck(
        id="c-fail",
        provider="github",
        pull_request_id=stale_open.id,
        name="ci",
        status="completed",
        conclusion="failure",
        updated_at="2026-02-24T01:00:00Z",
    )

    counts = screen._pull_request_health_counts(
        [stale_open, merged, closed],
        {
            stale_open.id: [failing],
            merged.id: [],
            closed.id: [],
        },
    )

    assert counts == {
        "open": 1,
        "merged": 1,
        "closed": 1,
        "failing_prs": 1,
        "stale_reviews": 1,
    }


def test_refresh_summary_renders_whole_block_snapshot() -> None:
    screen = IssueFlowScreen("PD-7")
    screen._issue = _issue()
    open_pr = _pr("pr-open", 7)
    open_pr.updated_at = datetime.now().isoformat()
    merged_pr = _pr("pr-merged", 8)
    merged_pr.state = "merged"
    merged_pr.merged_at = "2026-02-24T00:00:00Z"

    failing = CiCheck(
        id="c-fail",
        provider="github",
        pull_request_id=open_pr.id,
        name="ci/fail",
        status="completed",
        conclusion="failure",
        updated_at="2026-02-24T01:00:00Z",
    )
    passing = CiCheck(
        id="c-pass",
        provider="github",
        pull_request_id=open_pr.id,
        name="ci/pass",
        status="completed",
        conclusion="success",
        updated_at="2026-02-24T01:00:00Z",
    )
    checks_by_pr = {
        open_pr.id: [failing, passing],
        merged_pr.id: [],
    }
    captured: list[str] = []

    class _SummaryWidget:
        def update(self, value) -> None:
            captured.append(value)

    screen.query_one = lambda selector, _type=None: _SummaryWidget()  # type: ignore[method-assign]

    screen._refresh_summary([open_pr, merged_pr], checks_by_pr)

    assert captured == [
        (
            "PD-7 · In Progress\n"
            "Improve issue flow drilldown\n\n"
            "Assignee: Alice\n"
            "Priority: High  Points: 5\n"
            "Readiness Score: 40/100\n"
            "Linked PRs: 2  Checks: 2 (fail 1)\n"
            "PR states: open 1  merged 1  closed 0\n"
            "Review: ready/merged 1  attention 1\n"
            "Risk: failing PRs 1  stale reviews 0"
        )
    ]

def test_refresh_detail_for_pr_renders_whole_block_snapshot() -> None:
    screen = IssueFlowScreen("PD-7")
    screen._issue = _issue()
    pull_request = _pr("pr-42", 42)
    pull_request.updated_at = "2026-02-24T00:00:00Z"
    screen._prs_by_id = {pull_request.id: pull_request}
    screen._entries = [
        FlowEntry(
            kind="pr",
            label=f"PR #{pull_request.number} [{pull_request.state}] {pull_request.title}",
            timestamp=pull_request.updated_at,
            sort_key=None,
            pr_id=pull_request.id,
        )
    ]
    screen.selected_index = 0
    screen.detail_open = True

    failing = CiCheck(
        id="c-fail",
        provider="github",
        pull_request_id=pull_request.id,
        name="ci-fail",
        status="completed",
        conclusion="failure",
        updated_at="2026-02-24T01:00:00Z",
    )
    pending = CiCheck(
        id="c-pending",
        provider="github",
        pull_request_id=pull_request.id,
        name="ci-pending",
        status="in_progress",
        conclusion=None,
        updated_at="2026-02-24T01:00:00Z",
    )
    passing = CiCheck(
        id="c-pass",
        provider="github",
        pull_request_id=pull_request.id,
        name="ci-pass",
        status="completed",
        conclusion="success",
        updated_at="2026-02-24T01:00:00Z",
    )
    checks_by_pr = {
        pull_request.id: [passing, pending, failing],
    }
    captured: dict[str, str] = {}

    class _Widget:
        def __init__(self, key: str) -> None:
            self.key = key

        def update(self, value) -> None:
            captured[self.key] = value

    widgets = {
        "#issue-flow-detail": _Widget("detail"),
        "#issue-flow-hint": _Widget("hint"),
    }
    screen.query_one = lambda selector, _type=None: widgets[selector]  # type: ignore[method-assign]

    screen._refresh_detail([pull_request], checks_by_pr)

    assert captured["detail"] == (
        "PR #42 [open]\n"
        "PR 42\n\n"
        "Branch: feature/42 -> main\n"
        "Updated: 2026-02-24T00:00:00Z\n"
        "Linked issue: PD-7\n"
        "Checks: 3 | pass 1 | pend 1 | fail 1\n"
        "Health: failing checks\n"
        "Review status: changes-required\n"
        "Failing: ci-fail\n\n"
        "ACTIONS\n"
        "[o] Open PR  [b] Copy branch\n"
        "[c] Open failing check  [a] Run agent"
    )
    assert captured["hint"] == "j/k move • o/b/c/a actions • Esc close"


def test_close_screen_collapses_detail_then_dismisses(monkeypatch) -> None:
    screen = IssueFlowScreen("PD-7")
    screen.detail_open = True
    dismissed: list[dict[str, object]] = []

    monkeypatch.setattr(
        screen,
        "_refresh_detail",
        lambda pull_requests, checks_by_pr: None,
    )
    monkeypatch.setattr(
        screen,
        "dismiss",
        lambda payload=None: dismissed.append(payload or {}),
    )

    class _FakeDataManager:
        def get_pull_requests(self, issue_id):
            return []

        def get_ci_checks(self):
            return []

    class _FakeApp:
        data_manager = _FakeDataManager()

    monkeypatch.setattr(IssueFlowScreen, "app", property(lambda self: _FakeApp()))

    screen.action_close_screen()
    assert screen.detail_open is False
    assert dismissed == []

    screen.action_close_screen()
    assert dismissed == [{"issue_id": "PD-7", "selected_index": 0}]
