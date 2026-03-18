import aiosqlite
import json
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional
from projectdash.models import (
    AgentRun,
    CiCheck,
    LocalProject,
    PullRequest,
    Repository,
    User,
    Project,
    Issue,
    LinearWorkflowState,
)

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
                    cycle TEXT,
                    start_date TEXT,
                    description TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS issues (
                    id TEXT PRIMARY KEY,
                    linear_id TEXT,
                    title TEXT NOT NULL,
                    priority TEXT,
                    status TEXT,
                    state_id TEXT,
                    team_id TEXT,
                    assignee_id TEXT,
                    points INTEGER DEFAULT 0,
                    due_date TEXT,
                    project_id TEXT,
                    description TEXT,
                    labels_json TEXT,
                    FOREIGN KEY (assignee_id) REFERENCES users (id),
                    FOREIGN KEY (project_id) REFERENCES projects (id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS workflow_states (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    team_id TEXT NOT NULL,
                    team_key TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sync_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    result TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    diagnostics_json TEXT NOT NULL
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS repositories (
                    id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    organization TEXT,
                    name TEXT NOT NULL,
                    default_branch TEXT,
                    is_private INTEGER NOT NULL DEFAULT 0,
                    url TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS pull_requests (
                    id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    repository_id TEXT NOT NULL,
                    number INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    state TEXT NOT NULL,
                    author_id TEXT,
                    head_branch TEXT,
                    base_branch TEXT,
                    url TEXT,
                    issue_id TEXT,
                    opened_at TEXT,
                    merged_at TEXT,
                    closed_at TEXT,
                    updated_at TEXT NOT NULL,
                    UNIQUE(provider, repository_id, number),
                    FOREIGN KEY (repository_id) REFERENCES repositories (id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ci_checks (
                    id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    pull_request_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    conclusion TEXT,
                    url TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (pull_request_id) REFERENCES pull_requests (id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS work_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    source_provider TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    issue_id TEXT,
                    project_id TEXT,
                    pull_request_id TEXT,
                    actor_id TEXT,
                    occurred_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    UNIQUE(source_provider, source_id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS agent_runs (
                    id TEXT PRIMARY KEY,
                    actor_id TEXT,
                    issue_id TEXT,
                    project_id TEXT,
                    runtime TEXT NOT NULL,
                    session_ref TEXT,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    branch_name TEXT,
                    pr_id TEXT,
                    prompt_text TEXT,
                    prompt_fingerprint TEXT,
                    artifacts_json TEXT NOT NULL,
                    error_text TEXT,
                    trace_logs TEXT,
                    cost_usd REAL,
                    token_input INTEGER,
                    token_output INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS action_history (
                    id TEXT PRIMARY KEY,
                    action_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT,
                    timestamp TEXT NOT NULL,
                    payload_json TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sync_cursors (
                    provider TEXT PRIMARY KEY,
                    cursor TEXT,
                    updated_at TEXT NOT NULL
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS local_projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    path TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    tier TEXT NOT NULL DEFAULT 'C',
                    type TEXT NOT NULL DEFAULT 'unknown',
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    description TEXT,
                    last_commit_at TEXT,
                    has_readme INTEGER NOT NULL DEFAULT 0,
                    has_tests INTEGER NOT NULL DEFAULT 0,
                    has_ci INTEGER NOT NULL DEFAULT 0,
                    linked_linear_id TEXT,
                    linked_repo TEXT,
                    created_at TEXT
                )
            """)
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_pull_requests_issue_id ON pull_requests(issue_id)"
            )
            
            # Migrations
            async with db.execute("PRAGMA table_info(agent_runs)") as cursor:
                columns = [row[1] for row in await cursor.fetchall()]
                if "actor_id" not in columns:
                    await db.execute("ALTER TABLE agent_runs ADD COLUMN actor_id TEXT")
                if "prompt_fingerprint" not in columns:
                    await db.execute("ALTER TABLE agent_runs ADD COLUMN prompt_fingerprint TEXT")
                if "trace_logs" not in columns:
                    await db.execute("ALTER TABLE agent_runs ADD COLUMN trace_logs TEXT")
            
            async with db.execute("PRAGMA table_info(issues)") as cursor:
                columns = [row[1] for row in await cursor.fetchall()]
                if "description" not in columns:
                    await db.execute("ALTER TABLE issues ADD COLUMN description TEXT")
                if "labels_json" not in columns:
                    await db.execute("ALTER TABLE issues ADD COLUMN labels_json TEXT")
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_ci_checks_pr_id ON ci_checks(pull_request_id)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_work_events_issue_id ON work_events(issue_id)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_work_events_project_id ON work_events(project_id)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_runs_issue_id ON agent_runs(issue_id)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_runs_status ON agent_runs(status)"
            )
            try:
                await db.execute("ALTER TABLE issues ADD COLUMN due_date TEXT")
            except aiosqlite.OperationalError:
                pass
            try:
                await db.execute("ALTER TABLE issues ADD COLUMN linear_id TEXT")
            except aiosqlite.OperationalError:
                pass
            try:
                await db.execute("ALTER TABLE issues ADD COLUMN state_id TEXT")
            except aiosqlite.OperationalError:
                pass
            try:
                await db.execute("ALTER TABLE issues ADD COLUMN team_id TEXT")
            except aiosqlite.OperationalError:
                pass
            try:
                await db.execute("ALTER TABLE projects ADD COLUMN start_date TEXT")
            except aiosqlite.OperationalError:
                pass
            try:
                await db.execute("ALTER TABLE projects ADD COLUMN description TEXT")
            except aiosqlite.OperationalError:
                pass
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
                "INSERT OR REPLACE INTO projects (id, name, status, issues_count, in_progress_count, blocked_count, due_date, cycle, start_date, description) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        p.id,
                        p.name,
                        p.status,
                        p.issues_count,
                        p.in_progress_count,
                        p.blocked_count,
                        p.due_date,
                        p.cycle,
                        p.start_date,
                        p.description,
                    )
                    for p in projects
                ]
            )
            await db.commit()

    async def save_issues(self, issues: List[Issue], project_id: Optional[str] = None):
        async with aiosqlite.connect(self.db_path) as db:
            await db.executemany(
                "INSERT OR REPLACE INTO issues (id, linear_id, title, priority, status, state_id, team_id, assignee_id, points, due_date, project_id, description, labels_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        i.id,
                        i.linear_id,
                        i.title,
                        i.priority,
                        i.status,
                        i.state_id,
                        i.team_id,
                        i.assignee.id if i.assignee else None,
                        i.points,
                        i.due_date,
                        i.project_id or project_id,
                        i.description,
                        json.dumps(i.labels, sort_keys=True),
                    )
                    for i in issues
                ]
            )
            await db.commit()

    async def save_workflow_states(self, workflow_states: List[LinearWorkflowState]):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM workflow_states")
            if workflow_states:
                await db.executemany(
                    "INSERT OR REPLACE INTO workflow_states (id, name, type, team_id, team_key) VALUES (?, ?, ?, ?, ?)",
                    [(s.id, s.name, s.type, s.team_id, s.team_key) for s in workflow_states],
                )
            await db.commit()

    async def save_actions(self, actions: List[ActionRecord]):
        async with aiosqlite.connect(self.db_path) as db:
            for action in actions:
                timestamp = action.timestamp or datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
                payload_json = json.dumps(action.payload)
                await db.execute(
                    "INSERT OR REPLACE INTO action_history (id, action_type, target_id, status, message, timestamp, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (action.id, action.action_type, action.target_id, action.status, action.message, timestamp, payload_json),
                )
            await db.commit()

    async def get_action_history(self, limit: int = 50) -> List[ActionRecord]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM action_history ORDER BY timestamp DESC LIMIT ?", (limit,)
            ) as cursor:
                rows = await cursor.fetchall()
                history = []
                for row in rows:
                    payload = {}
                    try:
                        payload = json.loads(row["payload_json"])
                    except Exception:
                        pass
                    history.append(
                        ActionRecord(
                            id=row["id"],
                            action_type=row["action_type"],
                            target_id=row["target_id"],
                            status=row["status"],
                            message=row["message"],
                            timestamp=row["timestamp"],
                            payload=payload,
                        )
                    )
                return history

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
                        points=row["points"],
                        due_date=row["due_date"],
                        project_id=row["project_id"],
                        linear_id=row["linear_id"],
                        team_id=row["team_id"],
                        state_id=row["state_id"],
                        description=row["description"],
                        labels=json.loads(row["labels_json"] or "[]"),
                    ))
                    
                return issues

    async def get_workflow_states(self) -> List[LinearWorkflowState]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT id, name, type, team_id, team_key FROM workflow_states") as cursor:
                rows = await cursor.fetchall()
                return [LinearWorkflowState(**dict(row)) for row in rows]

    async def save_repositories(self, repositories: List[Repository]) -> None:
        if not repositories:
            return
        async with aiosqlite.connect(self.db_path) as db:
            await db.executemany(
                """
                INSERT OR REPLACE INTO repositories (
                    id, provider, organization, name, default_branch, is_private, url, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        repository.id,
                        repository.provider,
                        repository.organization,
                        repository.name,
                        repository.default_branch,
                        1 if repository.is_private else 0,
                        repository.url,
                        repository.created_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        repository.updated_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    )
                    for repository in repositories
                ],
            )
            await db.commit()

    async def get_repositories(self, provider: str | None = None) -> List[Repository]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = """
                SELECT id, provider, organization, name, default_branch, is_private, url, created_at, updated_at
                FROM repositories
            """
            params: tuple[object, ...] = ()
            if provider:
                query += " WHERE provider = ?"
                params = (provider,)
            query += " ORDER BY provider, organization, name"
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [
                    Repository(
                        id=row["id"],
                        provider=row["provider"],
                        organization=row["organization"],
                        name=row["name"],
                        default_branch=row["default_branch"],
                        is_private=bool(row["is_private"]),
                        url=row["url"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                    )
                    for row in rows
                ]

    async def save_pull_requests(self, pull_requests: List[PullRequest]) -> None:
        if not pull_requests:
            return
        async with aiosqlite.connect(self.db_path) as db:
            await db.executemany(
                """
                INSERT OR REPLACE INTO pull_requests (
                    id, provider, repository_id, number, title, state, author_id, head_branch,
                    base_branch, url, issue_id, opened_at, merged_at, closed_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        pull_request.id,
                        pull_request.provider,
                        pull_request.repository_id,
                        pull_request.number,
                        pull_request.title,
                        pull_request.state,
                        pull_request.author_id,
                        pull_request.head_branch,
                        pull_request.base_branch,
                        pull_request.url,
                        pull_request.issue_id,
                        pull_request.opened_at,
                        pull_request.merged_at,
                        pull_request.closed_at,
                        pull_request.updated_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    )
                    for pull_request in pull_requests
                ],
            )
            await db.commit()

    async def get_pull_requests(
        self,
        *,
        issue_id: str | None = None,
        repository_id: str | None = None,
        provider: str | None = None,
        limit: int = 500,
    ) -> List[PullRequest]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            filters: list[str] = []
            values: list[object] = []
            if issue_id:
                filters.append("issue_id = ?")
                values.append(issue_id)
            if repository_id:
                filters.append("repository_id = ?")
                values.append(repository_id)
            if provider:
                filters.append("provider = ?")
                values.append(provider)
            query = """
                SELECT
                    id, provider, repository_id, number, title, state, author_id, head_branch,
                    base_branch, url, issue_id, opened_at, merged_at, closed_at, updated_at
                FROM pull_requests
            """
            if filters:
                query += " WHERE " + " AND ".join(filters)
            query += " ORDER BY updated_at DESC, id DESC LIMIT ?"
            values.append(limit)
            async with db.execute(query, tuple(values)) as cursor:
                rows = await cursor.fetchall()
                return [PullRequest(**dict(row)) for row in rows]

    async def save_ci_checks(self, checks: List[CiCheck]) -> None:
        if not checks:
            return
        async with aiosqlite.connect(self.db_path) as db:
            await db.executemany(
                """
                INSERT OR REPLACE INTO ci_checks (
                    id, provider, pull_request_id, name, status, conclusion, url,
                    started_at, completed_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        check.id,
                        check.provider,
                        check.pull_request_id,
                        check.name,
                        check.status,
                        check.conclusion,
                        check.url,
                        check.started_at,
                        check.completed_at,
                        check.updated_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    )
                    for check in checks
                ],
            )
            await db.commit()

    async def get_ci_checks(
        self,
        *,
        pull_request_id: str | None = None,
        provider: str | None = None,
        limit: int = 1000,
    ) -> List[CiCheck]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            filters: list[str] = []
            values: list[object] = []
            if pull_request_id:
                filters.append("pull_request_id = ?")
                values.append(pull_request_id)
            if provider:
                filters.append("provider = ?")
                values.append(provider)
            query = """
                SELECT
                    id, provider, pull_request_id, name, status, conclusion, url,
                    started_at, completed_at, updated_at
                FROM ci_checks
            """
            if filters:
                query += " WHERE " + " AND ".join(filters)
            query += " ORDER BY updated_at DESC, id DESC LIMIT ?"
            values.append(limit)
            async with db.execute(query, tuple(values)) as cursor:
                rows = await cursor.fetchall()
                return [CiCheck(**dict(row)) for row in rows]

    async def get_sync_cursor(self, provider: str) -> str | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT cursor FROM sync_cursors WHERE provider = ?",
                (provider,),
            ) as cursor:
                row = await cursor.fetchone()
                if row is None:
                    return None
                return row["cursor"]

    async def save_sync_cursor(self, provider: str, cursor_value: str | None) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO sync_cursors(provider, cursor, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(provider) DO UPDATE SET
                    cursor=excluded.cursor,
                    updated_at=excluded.updated_at
                """,
                (provider, cursor_value, timestamp),
            )
            await db.commit()

    async def save_agent_run(self, run: AgentRun) -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        created_at = run.created_at or now
        updated_at = run.updated_at or now
        artifacts_json = json.dumps(run.artifacts, sort_keys=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO agent_runs (
                    id, actor_id, issue_id, project_id, runtime, session_ref, status, started_at, finished_at,
                    branch_name, pr_id, prompt_text, prompt_fingerprint, artifacts_json, error_text, trace_logs, cost_usd,
                    token_input, token_output, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    actor_id=excluded.actor_id,
                    issue_id=excluded.issue_id,
                    project_id=excluded.project_id,
                    runtime=excluded.runtime,
                    session_ref=excluded.session_ref,
                    status=excluded.status,
                    started_at=excluded.started_at,
                    finished_at=excluded.finished_at,
                    branch_name=excluded.branch_name,
                    pr_id=excluded.pr_id,
                    prompt_text=excluded.prompt_text,
                    prompt_fingerprint=excluded.prompt_fingerprint,
                    artifacts_json=excluded.artifacts_json,
                    error_text=excluded.error_text,
                    trace_logs=excluded.trace_logs,
                    cost_usd=excluded.cost_usd,
                    token_input=excluded.token_input,
                    token_output=excluded.token_output,
                    created_at=excluded.created_at,
                    updated_at=excluded.updated_at
                """,
                (
                    run.id,
                    run.actor_id,
                    run.issue_id,
                    run.project_id,
                    run.runtime,
                    run.session_ref,
                    run.status,
                    run.started_at,
                    run.finished_at,
                    run.branch_name,
                    run.pr_id,
                    run.prompt_text,
                    run.prompt_fingerprint,
                    artifacts_json,
                    run.error_text,
                    run.trace_logs,
                    run.cost_usd,
                    run.token_input,
                    run.token_output,
                    created_at,
                    updated_at,
                ),
            )
            await db.commit()

    def _agent_run_from_row(self, row: aiosqlite.Row) -> AgentRun:
        raw_artifacts = row["artifacts_json"]
        try:
            artifacts = json.loads(raw_artifacts) if raw_artifacts else {}
        except json.JSONDecodeError:
            artifacts = {}
        return AgentRun(
            id=row["id"],
            actor_id=row["actor_id"],
            issue_id=row["issue_id"],
            project_id=row["project_id"],
            runtime=row["runtime"],
            session_ref=row["session_ref"],
            status=row["status"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            branch_name=row["branch_name"],
            pr_id=row["pr_id"],
            prompt_text=row["prompt_text"],
            prompt_fingerprint=row["prompt_fingerprint"],
            artifacts=artifacts,
            error_text=row["error_text"],
            trace_logs=row["trace_logs"],
            cost_usd=row["cost_usd"],
            token_input=row["token_input"],
            token_output=row["token_output"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def get_agent_run(self, run_id: str) -> AgentRun | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT
                    id, actor_id, issue_id, project_id, runtime, session_ref, status, started_at, finished_at,
                    branch_name, pr_id, prompt_text, prompt_fingerprint, artifacts_json, error_text, trace_logs, cost_usd, token_input,
                    token_output, created_at, updated_at
                FROM agent_runs
                WHERE id = ?
                LIMIT 1
                """,
                (run_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if row is None:
                    return None
                return self._agent_run_from_row(row)

    async def get_agent_runs(self, limit: int = 50) -> List[AgentRun]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT
                    id, actor_id, issue_id, project_id, runtime, session_ref, status, started_at, finished_at,
                    branch_name, pr_id, prompt_text, prompt_fingerprint, artifacts_json, error_text, trace_logs, cost_usd, token_input,
                    token_output, created_at, updated_at
                FROM agent_runs
                ORDER BY started_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._agent_run_from_row(row) for row in rows]

    async def append_sync_history(
        self,
        *,
        created_at: str,
        result: str,
        summary: str,
        diagnostics: dict[str, str],
        max_entries: int = 20,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO sync_history (created_at, result, summary, diagnostics_json) VALUES (?, ?, ?, ?)",
                (created_at, result, summary, json.dumps(diagnostics, sort_keys=True)),
            )
            if max_entries > 0:
                await db.execute(
                    """
                    DELETE FROM sync_history
                    WHERE id NOT IN (
                        SELECT id FROM sync_history
                        ORDER BY id DESC
                        LIMIT ?
                    )
                    """,
                    (max_entries,),
                )
            await db.commit()

    async def get_sync_history(self, limit: int = 20) -> List[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT id, created_at, result, summary, diagnostics_json
                FROM sync_history
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()
                history: list[dict[str, Any]] = []
                for row in rows:
                    raw = row["diagnostics_json"]
                    try:
                        diagnostics = json.loads(raw) if raw else {}
                    except json.JSONDecodeError:
                        diagnostics = {}
                    history.append(
                        {
                            "id": row["id"],
                            "created_at": row["created_at"],
                            "result": row["result"],
                            "summary": row["summary"],
                            "diagnostics": diagnostics,
                        }
                    )
                return history

    async def save_local_projects(self, projects: list[LocalProject]) -> None:
        if not projects:
            return
        async with aiosqlite.connect(self.db_path) as db:
            await db.executemany(
                """
                INSERT OR REPLACE INTO local_projects (
                    id, name, path, status, tier, type, tags_json, description,
                    last_commit_at, has_readme, has_tests, has_ci,
                    linked_linear_id, linked_repo, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        p.id,
                        p.name,
                        p.path,
                        p.status,
                        p.tier,
                        p.type,
                        json.dumps(p.tags, sort_keys=True),
                        p.description,
                        p.last_commit_at,
                        1 if p.has_readme else 0,
                        1 if p.has_tests else 0,
                        1 if p.has_ci else 0,
                        p.linked_linear_id,
                        p.linked_repo,
                        p.created_at,
                    )
                    for p in projects
                ],
            )
            await db.commit()

    async def get_local_projects(self) -> list[LocalProject]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM local_projects ORDER BY tier, name"
            ) as cursor:
                rows = await cursor.fetchall()
                return [
                    LocalProject(
                        id=row["id"],
                        name=row["name"],
                        path=row["path"],
                        status=row["status"],
                        tier=row["tier"],
                        type=row["type"],
                        tags=json.loads(row["tags_json"] or "[]"),
                        description=row["description"],
                        last_commit_at=row["last_commit_at"],
                        has_readme=bool(row["has_readme"]),
                        has_tests=bool(row["has_tests"]),
                        has_ci=bool(row["has_ci"]),
                        linked_linear_id=row["linked_linear_id"],
                        linked_repo=row["linked_repo"],
                        created_at=row["created_at"],
                    )
                    for row in rows
                ]
