from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

from projectdash.models import CiCheck, PullRequest
from projectdash.views.github_dashboard import GitHubDashboardView


def _pr(
    pr_id: str,
    *,
    state: str = "open",
    issue_id: str | None = None,
    head_branch: str | None = "feature/x",
) -> PullRequest:
    return PullRequest(
        id=pr_id,
        provider="github",
        repository_id="github:acme/api",
        number=12,
        title="Update API",
        state=state,
        author_id="alice",
        head_branch=head_branch,
        base_branch="main",
        url="https://github.com/acme/api/pull/12",
        issue_id=issue_id,
        opened_at="2026-02-20T00:00:00Z",
        merged_at=None,
        closed_at=None,
        updated_at="2026-02-24T00:00:00Z",
    )


def _check(
    check_id: str,
    pull_request_id: str,
    *,
    status: str,
    conclusion: str | None,
    url: str | None = None,
) -> CiCheck:
    return CiCheck(
        id=check_id,
        provider="github",
        pull_request_id=pull_request_id,
        name="ci",
        status=status,
        conclusion=conclusion,
        url=url,
        started_at=None,
        completed_at=None,
        updated_at="2026-02-24T01:00:00Z",
    )


def test_pull_request_filters_match_state_link_and_failing_checks() -> None:
    view = GitHubDashboardView()
    open_linked = _pr("pr-1", state="open", issue_id="PD-10")
    merged_unlinked = _pr("pr-2", state="merged", issue_id=None)
    checks_by_pr = {
        open_linked.id: [_check("c1", open_linked.id, status="completed", conclusion="failure")],
        merged_unlinked.id: [_check("c2", merged_unlinked.id, status="completed", conclusion="success")],
    }

    view.state_filter = "open"
    assert view._pull_request_matches_filters(open_linked, checks_by_pr) is True
    assert view._pull_request_matches_filters(merged_unlinked, checks_by_pr) is False

    view.state_filter = "all"
    view.link_filter = "linked"
    assert view._pull_request_matches_filters(open_linked, checks_by_pr) is True
    assert view._pull_request_matches_filters(merged_unlinked, checks_by_pr) is False

    view.link_filter = "all"
    view.failing_only = True
    assert view._pull_request_matches_filters(open_linked, checks_by_pr) is True
    assert view._pull_request_matches_filters(merged_unlinked, checks_by_pr) is False


def test_move_selection_uses_pull_request_order_in_pr_mode(monkeypatch) -> None:
    view = GitHubDashboardView()
    monkeypatch.setattr(view, "refresh_view", lambda: None)
    view.visual_mode = "prs"
    view._pull_request_order = ["pr-1", "pr-2"]
    view._filtered_pull_requests_by_id = {
        "pr-1": _pr("pr-1"),
        "pr-2": _pr("pr-2"),
    }

    view.selected_pull_request_id = None
    view.move_selection(1)
    assert view.selected_pull_request_id == "pr-1"

    view.move_selection(1)
    assert view.selected_pull_request_id == "pr-2"


def test_copy_selected_branch_uses_clipboard_helper(monkeypatch) -> None:
    view = GitHubDashboardView()
    pull_request = _pr("pr-clipboard", head_branch="feature/copy-me")
    view._pull_request_order = [pull_request.id]
    view._filtered_pull_requests_by_id = {pull_request.id: pull_request}
    view.selected_pull_request_id = pull_request.id
    monkeypatch.setattr(view, "_copy_to_clipboard", lambda value: value == "feature/copy-me")

    ok, message = view.copy_selected_branch()

    assert ok is True
    assert "feature/copy-me" in message


def test_move_selection_uses_check_order_in_check_mode(monkeypatch) -> None:
    view = GitHubDashboardView()
    monkeypatch.setattr(view, "refresh_view", lambda: None)
    view.visual_mode = "checks"
    check_one = _check("c1", "pr-1", status="completed", conclusion="success")
    check_two = _check("c2", "pr-2", status="completed", conclusion="failure")
    view._check_order = [check_one.id, check_two.id]
    view._visible_checks_by_id = {
        check_one.id: check_one,
        check_two.id: check_two,
    }
    view._filtered_pull_requests_by_id = {
        "pr-1": _pr("pr-1"),
        "pr-2": _pr("pr-2"),
    }

    view.selected_check_id = None
    view.move_selection(1)
    assert view.selected_check_id == "c1"
    assert view.selected_pull_request_id == "pr-1"

    view.move_selection(1)
    assert view.selected_check_id == "c2"
    assert view.selected_pull_request_id == "pr-2"


def test_focus_issue_sets_drilldown_and_pr_mode(monkeypatch) -> None:
    view = GitHubDashboardView()

    def fake_refresh() -> None:
        view._pull_request_order = ["pr-1"]
        view._filtered_pull_requests_by_id = {
            "pr-1": _pr("pr-1", issue_id="PD-33"),
        }
        view.selected_pull_request_id = "pr-1"

    monkeypatch.setattr(view, "refresh_view", fake_refresh)
    ok, message = view.focus_issue("PD-33")

    assert ok is True
    assert "PD-33" in message
    assert view.drilldown_issue_id == "PD-33"
    assert view.link_filter == "linked"
    assert view.visual_mode == "prs"


def test_clear_issue_drilldown_restores_prior_context(monkeypatch) -> None:
    view = GitHubDashboardView()
    view.state_filter = "open"
    view.link_filter = "all"
    view.failing_only = True
    view.visual_mode = "checks"
    view.selected_repository_id = "github:acme/api"
    view.selected_pull_request_id = "pr-2"
    view.selected_check_id = "c2"
    view.detail_open = False

    def fake_refresh() -> None:
        if view.drilldown_issue_id:
            view._pull_request_order = ["pr-1"]
            view._filtered_pull_requests_by_id = {"pr-1": _pr("pr-1", issue_id=view.drilldown_issue_id)}
            view.selected_pull_request_id = "pr-1"

    monkeypatch.setattr(view, "refresh_view", fake_refresh)
    ok, _message = view.focus_issue("PD-90")
    assert ok is True
    assert view.drilldown_issue_id == "PD-90"
    assert view.link_filter == "linked"
    assert view.visual_mode == "prs"

    ok, message = view.clear_issue_drilldown()

    assert ok is True
    assert "PD-90" in message
    assert view.drilldown_issue_id is None
    assert view.state_filter == "open"
    assert view.link_filter == "all"
    assert view.failing_only is True
    assert view.visual_mode == "checks"
    assert view.selected_repository_id == "github:acme/api"
    assert view.selected_pull_request_id == "pr-2"
    assert view.selected_check_id == "c2"


def test_close_detail_second_escape_restores_drilldown_context(monkeypatch) -> None:
    view = GitHubDashboardView()
    view.state_filter = "all"
    view.link_filter = "all"
    view.visual_mode = "repos"
    view.detail_open = True

    def fake_refresh() -> None:
        if view.drilldown_issue_id:
            view._pull_request_order = ["pr-1"]
            view._filtered_pull_requests_by_id = {"pr-1": _pr("pr-1", issue_id=view.drilldown_issue_id)}
            view.selected_pull_request_id = "pr-1"

    monkeypatch.setattr(view, "refresh_view", fake_refresh)
    ok, _message = view.focus_issue("PD-91")
    assert ok is True

    view.close_detail()
    assert view.detail_open is False
    assert view.drilldown_issue_id == "PD-91"

    view.close_detail()
    assert view.drilldown_issue_id is None
    assert view.visual_mode == "repos"
    assert view.link_filter == "all"


def test_open_selected_check_prefers_failing_check_for_selected_pr(monkeypatch) -> None:
    view = GitHubDashboardView()
    pr = _pr("pr-1", issue_id="PD-10")
    passing = _check("c-pass", pr.id, status="completed", conclusion="success", url="https://ci/pass")
    failing = _check("c-fail", pr.id, status="completed", conclusion="failure", url="https://ci/fail")
    view.visual_mode = "prs"
    view._pull_request_order = [pr.id]
    view._filtered_pull_requests_by_id = {pr.id: pr}
    view._filtered_checks_by_pr = {pr.id: [passing, failing]}
    view.selected_pull_request_id = pr.id

    opened_urls: list[str] = []
    monkeypatch.setattr("projectdash.views.github_dashboard.webbrowser.open_new_tab", lambda url: opened_urls.append(url) or True)

    ok, message = view.open_selected_check()

    assert ok is True
    assert "Opened check" in message
    assert opened_urls == ["https://ci/fail"]


def test_open_selected_check_reports_missing_checks_for_pr_mode() -> None:
    view = GitHubDashboardView()
    pr = _pr("pr-1", issue_id="PD-10")
    view.visual_mode = "prs"
    view._pull_request_order = [pr.id]
    view._filtered_pull_requests_by_id = {pr.id: pr}
    view._filtered_checks_by_pr = {pr.id: []}
    view.selected_pull_request_id = pr.id

    ok, message = view.open_selected_check()

    assert ok is False
    assert message == "No checks available for PR #12"


def test_triage_filters_match_mine_blocked_and_stale(monkeypatch) -> None:
    view = GitHubDashboardView()
    mine_blocked_stale = _pr(
        "pr-triage",
        issue_id="PD-70",
        state="open",
    )
    mine_blocked_stale.updated_at = (datetime.now() - timedelta(days=10)).isoformat()
    not_mine = _pr("pr-other", issue_id="PD-71", state="open")
    not_mine.updated_at = mine_blocked_stale.updated_at
    not_blocked = _pr("pr-clear", issue_id="PD-72", state="open")
    not_blocked.updated_at = mine_blocked_stale.updated_at
    fresh = _pr("pr-fresh", issue_id="PD-73", state="open")
    fresh.updated_at = datetime.now().isoformat()

    issue_map = {
        "PD-70": SimpleNamespace(status="Blocked", assignee=SimpleNamespace(name="Dylan")),
        "PD-71": SimpleNamespace(status="Blocked", assignee=SimpleNamespace(name="Alex")),
        "PD-72": SimpleNamespace(status="In Progress", assignee=SimpleNamespace(name="Dylan")),
        "PD-73": SimpleNamespace(status="Blocked", assignee=SimpleNamespace(name="Dylan")),
    }
    fake_app = SimpleNamespace(data_manager=SimpleNamespace(get_issue_by_id=lambda issue_id: issue_map.get(issue_id)))
    monkeypatch.setattr(GitHubDashboardView, "app", property(lambda self: fake_app))
    monkeypatch.setenv("PD_ME", "Dylan")
    monkeypatch.setenv("PD_TRIAGE_STALE_DAYS", "7")

    checks_by_pr = {
        mine_blocked_stale.id: [_check("c1", mine_blocked_stale.id, status="completed", conclusion="failure")],
        not_mine.id: [_check("c2", not_mine.id, status="completed", conclusion="failure")],
        not_blocked.id: [_check("c3", not_blocked.id, status="completed", conclusion="failure")],
        fresh.id: [_check("c4", fresh.id, status="completed", conclusion="failure")],
    }

    view.mine_only = True
    view.blocked_only = True
    view.stale_only = True
    view.failing_only = True

    assert view._pull_request_matches_filters(mine_blocked_stale, checks_by_pr) is True
    assert view._pull_request_matches_filters(not_mine, checks_by_pr) is False
    assert view._pull_request_matches_filters(not_blocked, checks_by_pr) is False
    assert view._pull_request_matches_filters(fresh, checks_by_pr) is False


def test_clear_and_restore_github_triage_filters(monkeypatch) -> None:
    view = GitHubDashboardView()
    monkeypatch.setattr(view, "refresh_view", lambda: None)
    view.mine_only = True
    view.blocked_only = True
    view.failing_only = True
    view._sync_triage_filters_from_flags()

    ok, message = view.clear_triage_filters()
    assert ok is True
    assert "cleared" in message
    assert view.triage_filters == set()

    ok, message = view.restore_triage_filters()
    assert ok is True
    assert "restored" in message
    assert view.triage_filters == {"mine", "blocked", "failing"}
