from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from projectdash.models import Issue, LinearWorkflowState, Project, User


@dataclass
class ConnectorEntities:
    users: list[User] = field(default_factory=list)
    projects: list[Project] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    workflow_states: list[LinearWorkflowState] = field(default_factory=list)


class Connector(Protocol):
    name: str
    required_env: tuple[str, ...]

