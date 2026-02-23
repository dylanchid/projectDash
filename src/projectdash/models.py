from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime

@dataclass
class User:
    id: str
    name: str
    avatar_url: Optional[str] = None

@dataclass
class Project:
    id: str
    name: str
    status: str
    issues_count: int
    in_progress_count: int
    blocked_count: int
    due_date: str
    cycle: str

@dataclass
class Issue:
    id: str
    title: str
    priority: str
    status: str
    assignee: Optional[User] = None
    points: int = 0
    created_at: datetime = field(default_factory=datetime.now)
