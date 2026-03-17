from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

GITHUB_API_URL = "https://api.github.com"


@dataclass(frozen=True)
class GitHubApiError(Exception):
    message: str
    status_code: int | None = None

    def __str__(self) -> str:
        if self.status_code is None:
            return self.message
        return f"{self.message} (status={self.status_code})"


class GitHubClient:
    PER_PAGE = 100

    def __init__(self, token: str | None = None):
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        if not self.token:
            raise ValueError("GITHUB_TOKEN is not set.")
        url = f"{GITHUB_API_URL}{path}"
        async with httpx.AsyncClient() as client:
            response = await client.request(method, url, params=params, json=json, headers=self.headers)
        if response.status_code >= 400:
            try:
                payload = response.json()
                message = payload.get("message", response.text)
            except Exception:
                message = response.text
            raise GitHubApiError(message=message, status_code=response.status_code)
        
        # Some endpoints return 204 No Content (like rerun)
        if response.status_code == 204:
            return {}
            
        return response.json()

    async def get_current_user(self) -> dict[str, Any]:
        payload = await self._request("GET", "/user")
        if not isinstance(payload, dict):
            raise GitHubApiError("Unexpected payload from /user")
        return payload

    async def get_repository(self, full_name: str) -> dict[str, Any]:
        payload = await self._request("GET", f"/repos/{full_name}")
        if not isinstance(payload, dict):
            raise GitHubApiError(f"Unexpected payload for repo {full_name}")
        return payload

    async def get_user_repositories(
        self,
        *,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        page = 1
        while len(results) < limit:
            payload = await self._request(
                "GET",
                "/user/repos",
                params={
                    "visibility": "all",
                    "affiliation": "owner,collaborator,organization_member",
                    "sort": "updated",
                    "direction": "desc",
                    "per_page": self.PER_PAGE,
                    "page": page,
                },
            )
            if not isinstance(payload, list):
                raise GitHubApiError("Unexpected repositories payload from /user/repos")
            if not payload:
                break
            for row in payload:
                if isinstance(row, dict):
                    results.append(row)
                    if len(results) >= limit:
                        break
            if len(payload) < self.PER_PAGE:
                break
            page += 1
        return results

    async def get_pull_requests(
        self,
        owner: str,
        repo: str,
        *,
        state: str = "all",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        page = 1
        while len(results) < limit:
            payload = await self._request(
                "GET",
                f"/repos/{owner}/{repo}/pulls",
                params={
                    "state": state,
                    "sort": "updated",
                    "direction": "desc",
                    "per_page": self.PER_PAGE,
                    "page": page,
                },
            )
            if not isinstance(payload, list):
                raise GitHubApiError(f"Unexpected pulls payload for {owner}/{repo}")
            if not payload:
                break
            for row in payload:
                if isinstance(row, dict):
                    results.append(row)
                    if len(results) >= limit:
                        break
            if len(payload) < self.PER_PAGE:
                break
            page += 1
        return results

    async def get_check_runs(
        self,
        owner: str,
        repo: str,
        head_sha: str,
    ) -> list[dict[str, Any]]:
        payload = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/commits/{head_sha}/check-runs",
            params={"per_page": self.PER_PAGE},
        )
        if not isinstance(payload, dict):
            raise GitHubApiError(f"Unexpected checks payload for {owner}/{repo} {head_sha}")
        rows = payload.get("check_runs", [])
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)]

    async def rerun_workflow(self, owner: str, repo: str, run_id: int) -> dict[str, Any]:
        return await self._request("POST", f"/repos/{owner}/{repo}/actions/runs/{run_id}/rerun")

    async def rerun_job(self, owner: str, repo: str, job_id: int) -> dict[str, Any]:
        return await self._request("POST", f"/repos/{owner}/{repo}/actions/jobs/{job_id}/rerun")

    async def rerequest_check_run(self, owner: str, repo: str, check_run_id: int) -> dict[str, Any]:
        return await self._request("POST", f"/repos/{owner}/{repo}/check-runs/{check_run_id}/rerequest")

    async def create_pr_review(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        event: str,
        body: str | None = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {"event": event}
        if body:
            data["body"] = body
        return await self._request("POST", f"/repos/{owner}/{repo}/pulls/{pull_number}/reviews", json=data)

    async def merge_pull_request(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        commit_title: str | None = None,
        commit_message: str | None = None,
        merge_method: str = "merge",
    ) -> dict[str, Any]:
        data: dict[str, Any] = {"merge_method": merge_method}
        if commit_title:
            data["commit_title"] = commit_title
        if commit_message:
            data["commit_message"] = commit_message
        return await self._request("PUT", f"/repos/{owner}/{repo}/pulls/{pull_number}/merge", json=data)
