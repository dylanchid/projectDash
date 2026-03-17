from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from projectdash.enums import CiConclusion, ConnectorFreshness, SyncResult
from projectdash.errors import AuthenticationError, ApiResponseError, PersistenceError, SyncError
from projectdash.github import GitHubApiError, GitHubClient
from projectdash.linear import LinearApiError
from projectdash.models import CiCheck, PullRequest, Repository

if TYPE_CHECKING:
    from projectdash.data import DataManager


class SyncService:
    def __init__(self, data_manager: DataManager):
        self.data_manager = data_manager

    async def sync_with_linear(self) -> None:
        data = self.data_manager
        data.sync_in_progress = True
        self.mark_connector_attempt("linear")
        data.last_sync_error = None
        data.last_sync_result = SyncResult.SYNCING
        data.sync_diagnostics = {}
        data.last_sync_counts = {}
        try:
            api_key = os.getenv("LINEAR_API_KEY")
            if not api_key:
                data.last_sync_error = "LINEAR_API_KEY not set"
                data.last_sync_result = SyncResult.FAILED
                data.sync_diagnostics["auth"] = "failed: LINEAR_API_KEY not set"
                return

            print("   - Testing connection...")
            try:
                me = await data.linear.get_me()
                print(f"   - Authenticated as: {me['viewer']['name']}")
                data.sync_diagnostics["auth"] = f"ok: {me['viewer']['name']}"
                await self.save_sync_checkpoint("linear", "auth", {"viewer_id": me["viewer"].get("id", "")})
            except Exception as error:
                sync_error = self.coerce_sync_error(error, connector="linear", step="auth")
                print(f"   - Connection failed: {sync_error}")
                data.last_sync_error = f"auth failed: {sync_error}"
                data.last_sync_result = SyncResult.FAILED
                data.sync_diagnostics["auth"] = f"failed: {sync_error}"
                return

            print("   - Fetching projects...")
            try:
                raw_projects = await data.linear.get_projects()
            except Exception as error:
                sync_error = self.coerce_sync_error(error, connector="linear", step="projects")
                data.last_sync_error = f"projects fetch failed: {sync_error}"
                data.last_sync_result = SyncResult.FAILED
                data.sync_diagnostics["projects"] = f"failed: {sync_error}"
                return
            data.sync_diagnostics["projects"] = f"ok: {len(raw_projects)}"
            await self.save_sync_checkpoint(
                "linear",
                "projects",
                [{"id": row.get("id"), "targetDate": row.get("targetDate"), "state": row.get("state")} for row in raw_projects],
            )

            print("   - Fetching workflow states...")
            try:
                raw_teams = await data.linear.get_team_workflow_states()
            except Exception as error:
                sync_error = self.coerce_sync_error(error, connector="linear", step="workflow_states")
                data.last_sync_error = f"workflow states fetch failed: {sync_error}"
                data.last_sync_result = SyncResult.FAILED
                data.sync_diagnostics["workflow_states"] = f"failed: {sync_error}"
                return
            data.sync_diagnostics["workflow_states"] = f"ok: {len(raw_teams)} teams"
            await self.save_sync_checkpoint(
                "linear",
                "workflow_states",
                [
                    {
                        "id": team.get("id"),
                        "states": sorted(str(node.get("id")) for node in team.get("states", {}).get("nodes", [])),
                    }
                    for team in raw_teams
                ],
            )

            print("   - Fetching issues...")
            try:
                raw_issues = await data.linear.get_issues()
            except Exception as error:
                sync_error = self.coerce_sync_error(error, connector="linear", step="issues")
                data.last_sync_error = f"issues fetch failed: {sync_error}"
                data.last_sync_result = SyncResult.FAILED
                data.sync_diagnostics["issues"] = f"failed: {sync_error}"
                return
            data.sync_diagnostics["issues"] = f"ok: {len(raw_issues)}"
            await self.save_sync_checkpoint(
                "linear",
                "issues",
                [
                    {
                        "id": row.get("id"),
                        "identifier": row.get("identifier"),
                        "state_id": (row.get("state") or {}).get("id"),
                        "assignee_id": (row.get("assignee") or {}).get("id"),
                        "estimate": row.get("estimate"),
                    }
                    for row in raw_issues
                ],
            )

            entities = data.linear_connector.build_entities(
                raw_projects=raw_projects,
                raw_teams=raw_teams,
                raw_issues=raw_issues,
            )
            data.workflow_states_by_team = data.linear_connector.workflow_states_by_team(raw_teams)

            projects = self.merge_projects_with_policy(data.projects, entities.projects)
            issues = self.merge_issues_with_policy(data.issues, entities.issues)

            try:
                await data.db.save_users(entities.users)
                await data.db.save_projects(projects)
                await data.db.save_issues(issues)
                await data.db.save_workflow_states(entities.workflow_states)
            except Exception as error:
                persistence_error = self.coerce_persistence_error(error, operation="linear.persist")
                data.last_sync_error = f"persist failed: {persistence_error}"
                data.last_sync_result = SyncResult.FAILED
                data.sync_diagnostics["persist"] = f"failed: {persistence_error}"
                return
            data.sync_diagnostics["persist"] = "ok"
            await self.save_sync_checkpoint(
                "linear",
                "persist",
                {
                    "users": len(entities.users),
                    "projects": len(entities.projects),
                    "issues": len(entities.issues),
                    "workflow_states": len(entities.workflow_states),
                },
            )

            try:
                await data.load_from_cache()
            except Exception as error:
                persistence_error = self.coerce_persistence_error(error, operation="linear.reload")
                data.last_sync_error = f"reload failed: {persistence_error}"
                data.last_sync_result = SyncResult.FAILED
                data.sync_diagnostics["reload"] = f"failed: {persistence_error}"
                return
            data.sync_diagnostics["reload"] = "ok"
            await self.save_sync_checkpoint(
                "linear",
                "reload",
                {
                    "users": len(data.users),
                    "projects": len(data.projects),
                    "issues": len(data.issues),
                    "teams": len(data.workflow_states_by_team),
                },
            )
            data.last_sync_counts = {
                "users": len(data.users),
                "projects": len(data.projects),
                "issues": len(data.issues),
                "teams": len(data.workflow_states_by_team),
            }
            data.last_sync_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            data.last_sync_result = SyncResult.SUCCESS
        finally:
            self.finalize_connector_sync("linear")
            await self.record_sync_history()
            data.sync_in_progress = False

    async def sync_with_github(self) -> None:
        data = self.data_manager
        data.sync_in_progress = True
        self.mark_connector_attempt("github")
        data.last_sync_error = None
        data.last_sync_result = SyncResult.SYNCING
        data.sync_diagnostics = {}
        data.last_sync_counts = {}
        try:
            token = os.getenv("GITHUB_TOKEN")
            if not token:
                data.last_sync_error = "GITHUB_TOKEN not set"
                data.last_sync_result = SyncResult.FAILED
                data.sync_diagnostics["github_auth"] = "failed: GITHUB_TOKEN not set"
                return
            if data.github.token != token:
                data.github = GitHubClient(token=token)
            github_client = data.github

            targets = self.github_repository_targets()
            if not targets:
                try:
                    discovered = await github_client.get_user_repositories(limit=500)
                except Exception as error:
                    sync_error = self.coerce_sync_error(error, connector="github", step="targets")
                    data.last_sync_error = f"GitHub repository discovery failed: {sync_error}"
                    data.last_sync_result = SyncResult.FAILED
                    data.sync_diagnostics["github_targets"] = f"failed: discovery error: {sync_error}"
                    return
                discovered_targets: list[str] = []
                seen_discovered: set[str] = set()
                for row in discovered:
                    full_name = str(row.get("full_name") or "").strip()
                    if full_name.count("/") != 1:
                        continue
                    if full_name in seen_discovered:
                        continue
                    seen_discovered.add(full_name)
                    discovered_targets.append(full_name)
                targets = discovered_targets

            if not targets:
                data.last_sync_error = "No GitHub repositories configured (PD_GITHUB_REPOS or config.github_repositories)"
                data.last_sync_result = SyncResult.FAILED
                data.sync_diagnostics["github_targets"] = "failed: no repositories configured"
                return
            data.sync_diagnostics["github_targets"] = f"ok: {len(targets)}"
            await self.save_sync_checkpoint("github", "targets", sorted(targets))

            print("   - Testing GitHub connection...")
            try:
                viewer = await github_client.get_current_user()
                login = viewer.get("login", "unknown")
                data.sync_diagnostics["github_auth"] = f"ok: {login}"
                await self.save_sync_checkpoint("github", "auth", {"login": login})
            except Exception as error:
                sync_error = self.coerce_sync_error(error, connector="github", step="auth")
                data.last_sync_error = f"github auth failed: {sync_error}"
                data.last_sync_result = SyncResult.FAILED
                data.sync_diagnostics["github_auth"] = f"failed: {sync_error}"
                return

            repositories: list[Repository] = []
            pull_requests: list[PullRequest] = []
            checks: list[CiCheck] = []
            repository_cursor_rows: list[dict[str, Any]] = []
            pull_request_cursor_rows: list[dict[str, Any]] = []
            check_cursor_rows: list[dict[str, Any]] = []
            for target in targets:
                owner, repo_name = target.split("/", 1)
                print(f"   - Fetching {target}...")
                try:
                    raw_repository = await github_client.get_repository(target)
                except Exception as error:
                    sync_error = self.coerce_sync_error(error, connector="github", step="repository")
                    data.last_sync_error = f"github repository fetch failed for {target}: {sync_error}"
                    data.last_sync_result = SyncResult.FAILED
                    data.sync_diagnostics[f"github_repo:{target}"] = f"failed: {sync_error}"
                    return
                try:
                    raw_pull_requests = await github_client.get_pull_requests(
                        owner,
                        repo_name,
                        state="all",
                        limit=data.config.github_pr_limit,
                    )
                except Exception as error:
                    sync_error = self.coerce_sync_error(error, connector="github", step="pull_requests")
                    data.last_sync_error = f"github pull request fetch failed for {target}: {sync_error}"
                    data.last_sync_result = SyncResult.FAILED
                    data.sync_diagnostics[f"github_prs:{target}"] = f"failed: {sync_error}"
                    return

                checks_by_pr_number: dict[int, list[dict]] = {}
                if data.config.github_sync_checks:
                    for raw_pr in raw_pull_requests:
                        pr_number = int(raw_pr.get("number", 0))
                        head_sha = (raw_pr.get("head") or {}).get("sha")
                        if pr_number <= 0 or not head_sha:
                            continue
                        try:
                            checks_by_pr_number[pr_number] = await github_client.get_check_runs(
                                owner,
                                repo_name,
                                head_sha,
                            )
                        except Exception as error:
                            sync_error = self.coerce_sync_error(error, connector="github", step="checks")
                            data.sync_diagnostics[f"github_checks:{target}#{pr_number}"] = f"warn: {sync_error}"
                            checks_by_pr_number[pr_number] = []

                entities = data.github_connector.build_entities(
                    raw_repository=raw_repository,
                    raw_pull_requests=raw_pull_requests,
                    raw_checks_by_pr_number=checks_by_pr_number,
                )
                repositories.extend(entities.repositories)
                pull_requests.extend(entities.pull_requests)
                checks.extend(entities.ci_checks)
                repository_cursor_rows.append(
                    {
                        "target": target,
                        "repo_updated_at": raw_repository.get("updated_at"),
                    }
                )
                pull_request_cursor_rows.extend(
                    {
                        "target": target,
                        "number": row.get("number"),
                        "updated_at": row.get("updated_at"),
                        "state": row.get("state"),
                        "merged_at": row.get("merged_at"),
                    }
                    for row in raw_pull_requests
                )
                check_cursor_rows.extend(
                    {
                        "target": target,
                        "pr_number": number,
                        "check_id": row.get("id"),
                        "updated_at": row.get("updated_at"),
                        "status": row.get("status"),
                    }
                    for number, rows in checks_by_pr_number.items()
                    for row in rows
                )
                data.sync_diagnostics[f"github_repo:{target}"] = (
                    f"ok: prs={len(entities.pull_requests)} checks={len(entities.ci_checks)}"
                )
            await self.save_sync_checkpoint("github", "repositories", repository_cursor_rows)
            await self.save_sync_checkpoint("github", "pull_requests", pull_request_cursor_rows)
            if data.config.github_sync_checks:
                await self.save_sync_checkpoint("github", "checks", check_cursor_rows)

            repositories = self.merge_repositories_with_policy(data.repositories, repositories)
            pull_requests = self.merge_pull_requests_with_policy(data.pull_requests, pull_requests)
            checks = self.merge_ci_checks_with_policy(data.ci_checks, checks)

            try:
                await data.db.save_repositories(repositories)
                await data.db.save_pull_requests(pull_requests)
                await data.db.save_ci_checks(checks)
            except Exception as error:
                persistence_error = self.coerce_persistence_error(error, operation="github.persist")
                data.last_sync_error = f"github persist failed: {persistence_error}"
                data.last_sync_result = SyncResult.FAILED
                data.sync_diagnostics["github_persist"] = f"failed: {persistence_error}"
                return
            data.sync_diagnostics["github_persist"] = "ok"
            await self.save_sync_checkpoint(
                "github",
                "persist",
                {
                    "repositories": len(repositories),
                    "pull_requests": len(pull_requests),
                    "checks": len(checks),
                },
            )

            try:
                await data.load_from_cache()
            except Exception as error:
                persistence_error = self.coerce_persistence_error(error, operation="github.reload")
                data.last_sync_error = f"github reload failed: {persistence_error}"
                data.last_sync_result = SyncResult.FAILED
                data.sync_diagnostics["github_reload"] = f"failed: {persistence_error}"
                return
            data.sync_diagnostics["github_reload"] = "ok"
            await self.save_sync_checkpoint(
                "github",
                "reload",
                {
                    "repositories": len(data.repositories),
                    "pull_requests": len(data.pull_requests),
                    "checks": len(data.ci_checks),
                },
            )

            data.last_sync_counts = {
                "repositories": len(data.repositories),
                "pull_requests": len(data.pull_requests),
                "checks": len(data.ci_checks),
            }
            data.last_sync_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            data.last_sync_result = SyncResult.SUCCESS
        finally:
            self.finalize_connector_sync("github")
            await self.record_sync_history()
            data.sync_in_progress = False

    def sync_status_summary(self) -> str:
        if self.data_manager.sync_in_progress:
            return SyncResult.SYNCING
        return self.sync_status_summary_core()

    def sync_diagnostic_lines(self) -> list[str]:
        return [f"{step}: {status}" for step, status in self.data_manager.sync_diagnostics.items()]

    def get_sync_history(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.data_manager.sync_history[:limit]

    def available_connectors(self) -> list[str]:
        return sorted(self.data_manager.connectors.keys())

    async def save_sync_cursor(self, provider: str, cursor: str | None) -> None:
        await self.data_manager.db.save_sync_cursor(provider, cursor)

    async def get_sync_cursor(self, provider: str) -> str | None:
        return await self.data_manager.db.get_sync_cursor(provider)

    def latest_sync_history_lines(self, limit: int = 3) -> list[str]:
        entries = self.get_sync_history(limit=limit)
        lines: list[str] = []
        for entry in entries:
            timestamp = entry.get("created_at", "?")
            result = entry.get("result", "?")
            summary = entry.get("summary", "")
            lines.append(f"{timestamp} | {result} | {summary}")
        return lines

    def connector_freshness_snapshot(
        self,
        connector: str,
        *,
        reference_time: datetime | None = None,
    ) -> dict[str, Any]:
        data = self.data_manager
        now = reference_time or datetime.now()
        meta = data._connector_freshness.get(connector, {})
        status = str(meta.get("status") or ConnectorFreshness.IDLE).casefold()
        last_success_at = self.parse_sync_time(meta.get("last_success_at"))
        last_attempt_at = self.parse_sync_time(meta.get("last_attempt_at"))
        last_error = meta.get("last_error")
        stale_after = max(1, data.sync_stale_minutes)

        age_minutes: int | None = None
        if last_success_at is not None:
            age_minutes = max(0, int((now - last_success_at).total_seconds() // 60))

        is_stale = age_minutes is not None and age_minutes >= stale_after
        if status == ConnectorFreshness.FAILED:
            state = ConnectorFreshness.FAILED
        elif status == ConnectorFreshness.SYNCING:
            state = ConnectorFreshness.SYNCING
        elif last_success_at is None:
            state = ConnectorFreshness.NEVER
        elif is_stale:
            state = ConnectorFreshness.STALE
        else:
            state = ConnectorFreshness.FRESH

        if age_minutes is not None:
            recency = f"{age_minutes}m"
        elif last_attempt_at is not None:
            recency = "no success yet"
        else:
            recency = "never"

        return {
            "connector": connector,
            "state": state,
            "status": status,
            "age_minutes": age_minutes,
            "is_stale": is_stale,
            "last_success_at": meta.get("last_success_at"),
            "last_attempt_at": meta.get("last_attempt_at"),
            "last_error": last_error,
            "recovery_hint": self.sync_recovery_hint(connector, last_error),
            "recency": recency,
        }

    def freshness_summary_line(self, connectors: tuple[str, ...] = ("linear", "github")) -> str:
        parts: list[str] = []
        for connector in connectors:
            snapshot = self.connector_freshness_snapshot(connector)
            label = connector.title()
            state = str(snapshot["state"]).upper()
            recency = snapshot["recency"]
            if snapshot["state"] == ConnectorFreshness.FAILED:
                hint = snapshot["recovery_hint"]
                if hint:
                    parts.append(f"{label} {state} ({hint})")
                else:
                    parts.append(f"{label} {state}")
            else:
                parts.append(f"{label} {state} {recency}")
        return f"Freshness (stale>{self.data_manager.sync_stale_minutes}m): " + " | ".join(parts)

    def should_show_sync_freshness(self, connectors: tuple[str, ...] = ("linear", "github")) -> bool:
        for connector in connectors:
            snapshot = self.connector_freshness_snapshot(connector)
            if snapshot["state"] in {
                ConnectorFreshness.FAILED,
                ConnectorFreshness.STALE,
                ConnectorFreshness.SYNCING,
                ConnectorFreshness.NEVER,
            }:
                return True
        return False

    def github_repository_targets(self) -> list[str]:
        configured = [value.strip() for value in self.data_manager.config.github_repositories if value.strip()]
        if not configured:
            env_repos = os.getenv("PD_GITHUB_REPOS", "")
            configured = [value.strip() for value in env_repos.split(",") if value.strip()]

        targets: list[str] = []
        seen: set[str] = set()
        for candidate in configured:
            normalized = candidate.strip().strip("/")
            if normalized.count("/") != 1:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            targets.append(normalized)
        return targets

    def coerce_sync_error(self, error: Exception, *, connector: str, step: str) -> SyncError:
        if isinstance(error, SyncError):
            return error
        message = str(error)
        if isinstance(error, ValueError) and self.looks_like_missing_credentials(message):
            return AuthenticationError(message, connector, step)
        if isinstance(error, LinearApiError):
            if error.code in {"FORBIDDEN", "UNAUTHORIZED"} or "permission" in error.message.casefold():
                return AuthenticationError(message, connector, step)
            return ApiResponseError(message, connector, step)
        if isinstance(error, GitHubApiError):
            if error.status_code in {401, 403}:
                return AuthenticationError(message, connector, step)
            return ApiResponseError(message, connector, step)
        return SyncError(message, connector, step)

    def coerce_persistence_error(self, error: Exception, *, operation: str) -> PersistenceError:
        if isinstance(error, PersistenceError):
            return error
        return PersistenceError(str(error), operation)

    @staticmethod
    def looks_like_missing_credentials(message: str) -> bool:
        lowered = message.casefold()
        return "api_key is not set" in lowered or "token is not set" in lowered

    async def record_sync_history(self) -> None:
        data = self.data_manager
        if data.last_sync_result == SyncResult.SYNCING:
            return
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        summary = self.sync_status_summary_core()
        try:
            await data.db.append_sync_history(
                created_at=created_at,
                result=data.last_sync_result,
                summary=summary,
                diagnostics=data.sync_diagnostics,
            )
            data.sync_history = await data.db.get_sync_history()
        except Exception:
            pass

    def sync_status_summary_core(self) -> str:
        data = self.data_manager
        if data.last_sync_result == SyncResult.SUCCESS:
            has_linear_counts = any(key in data.last_sync_counts for key in ("users", "projects", "issues", "teams"))
            has_github_counts = any(
                key in data.last_sync_counts for key in ("repositories", "pull_requests", "checks")
            )
            if has_linear_counts and not has_github_counts:
                users = data.last_sync_counts.get("users", len(data.users))
                projects = data.last_sync_counts.get("projects", len(data.projects))
                issues = data.last_sync_counts.get("issues", len(data.issues))
                teams = data.last_sync_counts.get("teams", len(data.workflow_states_by_team))
                return f"success u:{users} p:{projects} i:{issues} t:{teams}"
            if has_github_counts and not has_linear_counts:
                repositories = data.last_sync_counts.get("repositories", len(data.repositories))
                pull_requests = data.last_sync_counts.get("pull_requests", len(data.pull_requests))
                checks = data.last_sync_counts.get("checks", len(data.ci_checks))
                return f"success r:{repositories} pr:{pull_requests} c:{checks}"

            users = data.last_sync_counts.get("users", len(data.users))
            projects = data.last_sync_counts.get("projects", len(data.projects))
            issues = data.last_sync_counts.get("issues", len(data.issues))
            teams = data.last_sync_counts.get("teams", len(data.workflow_states_by_team))
            repositories = data.last_sync_counts.get("repositories", len(data.repositories))
            pull_requests = data.last_sync_counts.get("pull_requests", len(data.pull_requests))
            checks = data.last_sync_counts.get("checks", len(data.ci_checks))
            return f"success u:{users} p:{projects} i:{issues} t:{teams} r:{repositories} pr:{pull_requests} c:{checks}"
        if data.last_sync_error:
            return f"failed: {data.last_sync_error}"
        return data.last_sync_result

    async def save_sync_checkpoint(self, connector: str, resource_class: str, payload: Any) -> None:
        key = f"{connector}:{resource_class}"
        value = self.payload_checkpoint(payload)
        try:
            await self.save_sync_cursor(key, value)
        except Exception as error:
            self.data_manager.sync_diagnostics[f"{connector}_cursor:{resource_class}"] = f"warn: {error}"

    def payload_checkpoint(self, payload: Any) -> str:
        if isinstance(payload, str):
            return payload
        try:
            normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        except TypeError:
            normalized = repr(payload)
        digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]
        return f"sha1:{digest}"

    def merge_repositories_with_policy(
        self,
        existing: list[Repository],
        incoming: list[Repository],
    ) -> list[Repository]:
        merged: dict[str, Repository] = {repository.id: repository for repository in existing}
        for candidate in incoming:
            current = merged.get(candidate.id)
            if current is None:
                merged[candidate.id] = candidate
                continue
            merged[candidate.id] = self.preferred_repository(current, candidate)
        return list(merged.values())

    def merge_pull_requests_with_policy(
        self,
        existing: list[PullRequest],
        incoming: list[PullRequest],
    ) -> list[PullRequest]:
        merged: dict[str, PullRequest] = {pull_request.id: pull_request for pull_request in existing}
        for candidate in incoming:
            current = merged.get(candidate.id)
            if current is None:
                merged[candidate.id] = candidate
                continue
            merged[candidate.id] = self.preferred_pull_request(current, candidate)
        return list(merged.values())

    def merge_ci_checks_with_policy(
        self,
        existing: list[CiCheck],
        incoming: list[CiCheck],
    ) -> list[CiCheck]:
        merged: dict[str, CiCheck] = {check.id: check for check in existing}
        for candidate in incoming:
            current = merged.get(candidate.id)
            if current is None:
                merged[candidate.id] = candidate
                continue
            merged[candidate.id] = self.preferred_ci_check(current, candidate)
        return list(merged.values())

    def merge_issues_with_policy(
        self,
        existing: list[Issue],
        incoming: list[Issue],
    ) -> list[Issue]:
        merged: dict[str, Issue] = {issue.id: issue for issue in existing}
        for candidate in incoming:
            current = merged.get(candidate.id)
            if current is None:
                merged[candidate.id] = candidate
                continue
            merged[candidate.id] = self.preferred_issue(current, candidate)
        return list(merged.values())

    def merge_projects_with_policy(
        self,
        existing: list[Project],
        incoming: list[Project],
    ) -> list[Project]:
        merged: dict[str, Project] = {project.id: project for project in existing}
        for candidate in incoming:
            current = merged.get(candidate.id)
            if current is None:
                merged[candidate.id] = candidate
                continue
            merged[candidate.id] = self.preferred_project(current, candidate)
        return list(merged.values())

    def preferred_issue(self, existing: Issue, incoming: Issue) -> Issue:
        # Note: Issue doesn't have updated_at yet in the model, but it has created_at
        # Let's assume we want incoming to win for issues unless we add updated_at
        return incoming

    def preferred_project(self, existing: Project, incoming: Project) -> Project:
        return incoming

    def preferred_repository(self, existing: Repository, incoming: Repository) -> Repository:
        winner = self.prefer_newer_by_timestamp(existing, incoming, existing.updated_at, incoming.updated_at)
        if winner is not None:
            return winner
        # Tie-breaker or missing timestamps: prefer incoming for fresh data
        return incoming

    def preferred_pull_request(self, existing: PullRequest, incoming: PullRequest) -> PullRequest:
        winner = self.prefer_newer_by_timestamp(existing, incoming, existing.updated_at, incoming.updated_at)
        if winner is not None:
            return winner
        # Tie-breaker or missing timestamps: prefer incoming for fresh data
        return incoming

    def preferred_ci_check(self, existing: CiCheck, incoming: CiCheck) -> CiCheck:
        winner = self.prefer_newer_by_timestamp(existing, incoming, existing.updated_at, incoming.updated_at)
        if winner is not None:
            return winner
        # Tie-breaker or missing timestamps: prefer incoming for fresh data
        return incoming

    def prefer_newer_by_timestamp(
        self,
        existing: Any,
        incoming: Any,
        existing_value: str | None,
        incoming_value: str | None,
    ) -> Any | None:
        existing_ts = self.parse_connector_timestamp(existing_value)
        incoming_ts = self.parse_connector_timestamp(incoming_value)
        if existing_ts is not None and incoming_ts is not None:
            # Deterministic: incoming wins on ties
            if incoming_ts >= existing_ts:
                return incoming
            return existing
        if incoming_ts is not None:
            return incoming
        if existing_ts is not None:
            return existing
        return None

    @staticmethod
    def parse_connector_timestamp(value: str | None) -> float | None:
        if not value:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp()
        except ValueError:
            pass
        try:
            parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            return parsed.timestamp()
        except ValueError:
            return None

    @staticmethod
    def sync_stale_threshold_minutes() -> int:
        value = os.getenv("PD_SYNC_STALE_MINUTES", "30").strip()
        try:
            parsed = int(value)
        except ValueError:
            parsed = 30
        return max(1, parsed)

    @staticmethod
    def parse_sync_time(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None

    def mark_connector_attempt(self, connector: str) -> None:
        meta = self.data_manager._connector_freshness.setdefault(
            connector,
            {"status": ConnectorFreshness.IDLE, "last_success_at": None, "last_attempt_at": None, "last_error": None},
        )
        meta["status"] = ConnectorFreshness.SYNCING
        meta["last_attempt_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        meta["last_error"] = None

    def finalize_connector_sync(self, connector: str) -> None:
        data = self.data_manager
        meta = data._connector_freshness.setdefault(
            connector,
            {"status": ConnectorFreshness.IDLE, "last_success_at": None, "last_attempt_at": None, "last_error": None},
        )
        if data.last_sync_result == SyncResult.SUCCESS:
            meta["status"] = SyncResult.SUCCESS
            meta["last_success_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            meta["last_error"] = None
            return
        if data.last_sync_result == SyncResult.FAILED:
            meta["status"] = ConnectorFreshness.FAILED
            meta["last_error"] = data.last_sync_error
            return
        meta["status"] = data.last_sync_result

    @staticmethod
    def sync_recovery_hint(connector: str, error: str | None) -> str:
        if not error:
            return ""
        lowered = error.casefold()
        if connector == "linear":
            if "linear_api_key not set" in lowered:
                return "set LINEAR_API_KEY and run pd sync"
            if "auth failed" in lowered:
                return "verify LINEAR_API_KEY and network access"
        if connector == "github":
            if "github_token not set" in lowered:
                return "set GITHUB_TOKEN and run pd sync-github"
            if "no github repositories configured" in lowered:
                return "set PD_GITHUB_REPOS (owner/repo)"
            if "github auth failed" in lowered:
                return "verify GITHUB_TOKEN scopes and network access"
        if "rate limit" in lowered:
            return "retry after provider rate-limit window"
        if "persist failed" in lowered or "reload failed" in lowered:
            return "verify local DB write permissions and retry"
        return "inspect sync diagnostics and retry"
