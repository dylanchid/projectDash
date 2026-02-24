from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

import httpx

LINEAR_API_URL = "https://api.linear.app/graphql"


@dataclass(frozen=True)
class LinearApiError(Exception):
    message: str
    code: str | None = None
    type: str | None = None

    def __str__(self) -> str:
        parts = [self.message]
        if self.code:
            parts.append(f"code={self.code}")
        if self.type:
            parts.append(f"type={self.type}")
        return " | ".join(parts)


class LinearClient:
    PAGE_SIZE = 100

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("LINEAR_API_KEY")
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": self.api_key if self.api_key else ""
        }

    async def _query(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.api_key:
            raise ValueError("LINEAR_API_KEY is not set.")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                LINEAR_API_URL,
                json={"query": query, "variables": variables},
                headers=self.headers
            )
            response.raise_for_status()
            result = response.json()
            if "errors" in result:
                first_error = result["errors"][0]
                extensions = first_error.get("extensions", {})
                raise LinearApiError(
                    message=first_error.get("message", "Unknown Linear API error"),
                    code=extensions.get("code"),
                    type=extensions.get("type"),
                )
            return result["data"]

    async def get_me(self) -> dict[str, Any]:
        query = """
        query {
          viewer {
            id
            name
            email
          }
        }
        """
        return await self._query(query)

    async def get_projects(self) -> list[dict[str, Any]]:
        query = """
        query($first: Int!, $after: String) {
          projects(first: $first, after: $after) {
            nodes {
              id
              name
              targetDate
              state
            }
            pageInfo {
              hasNextPage
              endCursor
            }
          }
        }
        """
        projects: list[dict[str, Any]] = []
        after: str | None = None
        while True:
            data = await self._query(query, {"first": self.PAGE_SIZE, "after": after})
            page = data["projects"]
            projects.extend(page["nodes"])
            page_info = page.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                break
            after = page_info.get("endCursor")
            if not after:
                break
        return projects

    async def get_issues(self) -> list[dict[str, Any]]:
        query = """
        query($first: Int!, $after: String) {
          issues(first: $first, after: $after) {
            nodes {
              id
              identifier
              title
              priority
              state {
                id
                name
                type
              }
              dueDate
              project {
                id
              }
              team {
                id
              }
              assignee {
                id
                name
                avatarUrl
              }
              estimate
            }
            pageInfo {
              hasNextPage
              endCursor
            }
          }
        }
        """
        issues: list[dict[str, Any]] = []
        after: str | None = None
        while True:
            data = await self._query(query, {"first": self.PAGE_SIZE, "after": after})
            page = data["issues"]
            issues.extend(page["nodes"])
            page_info = page.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                break
            after = page_info.get("endCursor")
            if not after:
                break
        return issues

    async def get_team_workflow_states(self) -> list[dict[str, Any]]:
        query = """
        query($first: Int!, $after: String) {
          teams(first: $first, after: $after) {
            nodes {
              id
              key
              name
              states {
                nodes {
                  id
                  name
                  type
                }
              }
            }
            pageInfo {
              hasNextPage
              endCursor
            }
          }
        }
        """
        teams: list[dict[str, Any]] = []
        after: str | None = None
        while True:
            data = await self._query(query, {"first": self.PAGE_SIZE, "after": after})
            page = data["teams"]
            teams.extend(page["nodes"])
            page_info = page.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                break
            after = page_info.get("endCursor")
            if not after:
                break
        return teams

    async def get_issue(self, issue_id: str) -> dict[str, Any] | None:
        query = """
        query($id: String!) {
          issue(id: $id) {
            id
            identifier
            title
            priority
            state {
              id
              name
              type
            }
            dueDate
            project {
              id
            }
            team {
              id
            }
            assignee {
              id
              name
              avatarUrl
            }
            estimate
          }
        }
        """
        data = await self._query(query, {"id": issue_id})
        return data.get("issue")

    async def update_issue_status(self, issue_id: str, state_id: str) -> dict[str, Any]:
        mutation = """
        mutation($id: String!, $stateId: String!) {
          issueUpdate(id: $id, input: { stateId: $stateId }) {
            success
            issue {
              id
              identifier
              state {
                id
                name
                type
              }
            }
          }
        }
        """
        data = await self._query(mutation, {"id": issue_id, "stateId": state_id})
        return data["issueUpdate"]

    async def update_issue_assignee(self, issue_id: str, assignee_id: str | None) -> dict[str, Any]:
        mutation = """
        mutation($id: String!, $assigneeId: String) {
          issueUpdate(id: $id, input: { assigneeId: $assigneeId }) {
            success
            issue {
              id
              identifier
              assignee {
                id
                name
              }
            }
          }
        }
        """
        data = await self._query(mutation, {"id": issue_id, "assigneeId": assignee_id})
        return data["issueUpdate"]

    async def update_issue_estimate(self, issue_id: str, estimate: int | None) -> dict[str, Any]:
        mutation = """
        mutation($id: String!, $estimate: Float) {
          issueUpdate(id: $id, input: { estimate: $estimate }) {
            success
            issue {
              id
              identifier
              estimate
            }
          }
        }
        """
        data = await self._query(mutation, {"id": issue_id, "estimate": estimate})
        return data["issueUpdate"]
