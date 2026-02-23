import aiosqlite
import asyncio
from pathlib import Path
from typing import List, Optional
from projectdash.models import User, Project, Issue

DB_PATH = Path("projectdash.db")

class Database:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    avatar_url TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT,
                    issues_count INTEGER,
                    in_progress_count INTEGER,
                    blocked_count INTEGER,
                    due_date TEXT,
                    cycle TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS issues (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    priority TEXT,
                    status TEXT,
                    assignee_id TEXT,
                    points INTEGER DEFAULT 0,
                    project_id TEXT,
                    FOREIGN KEY (assignee_id) REFERENCES users (id),
                    FOREIGN KEY (project_id) REFERENCES projects (id)
                )
            """)
            await db.commit()

    async def save_users(self, users: List[User]):
        async with aiosqlite.connect(self.db_path) as db:
            await db.executemany(
                "INSERT OR REPLACE INTO users (id, name, avatar_url) VALUES (?, ?, ?)",
                [(u.id, u.name, u.avatar_url) for u in users]
            )
            await db.commit()

    async def save_projects(self, projects: List[Project]):
        async with aiosqlite.connect(self.db_path) as db:
            await db.executemany(
                "INSERT OR REPLACE INTO projects (id, name, status, issues_count, in_progress_count, blocked_count, due_date, cycle) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(p.id, p.name, p.status, p.issues_count, p.in_progress_count, p.blocked_count, p.due_date, p.cycle) for p in projects]
            )
            await db.commit()

    async def save_issues(self, issues: List[Issue], project_id: Optional[str] = None):
        async with aiosqlite.connect(self.db_path) as db:
            await db.executemany(
                "INSERT OR REPLACE INTO issues (id, title, priority, status, assignee_id, points, project_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(i.id, i.title, i.priority, i.status, i.assignee.id if i.assignee else None, i.points, project_id) for i in issues]
            )
            await db.commit()

    async def get_users(self) -> List[User]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users") as cursor:
                rows = await cursor.fetchall()
                return [User(id=row["id"], name=row["name"], avatar_url=row["avatar_url"]) for row in rows]

    async def get_projects(self) -> List[Project]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM projects") as cursor:
                rows = await cursor.fetchall()
                return [Project(**dict(row)) for row in rows]

    async def get_issues(self) -> List[Issue]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            # Join with users to get assignee details
            query = """
                SELECT i.*, u.name as user_name, u.avatar_url as user_avatar 
                FROM issues i 
                LEFT JOIN users u ON i.assignee_id = u.id
            """
            async with db.execute(query) as cursor:
                rows = await cursor.fetchall()
                issues = []
                for row in rows:
                    assignee = None
                    if row["assignee_id"]:
                        assignee = User(id=row["assignee_id"], name=row["user_name"], avatar_url=row["user_avatar"])
                    issues.append(Issue(
                        id=row["id"],
                        title=row["title"],
                        priority=row["priority"],
                        status=row["status"],
                        assignee=assignee,
                        points=row["points"]
                    ))
                return issues
