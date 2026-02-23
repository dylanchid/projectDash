import asyncio
from typing import List, Optional, Any, Dict
from projectdash.models import Project, Issue, User
from projectdash.database import Database
from projectdash.linear import LinearClient
import os

class DataManager:
    def __init__(self):
        self.db = Database()
        self.linear = LinearClient()
        self.users: List[User] = []
        self.projects: List[Project] = []
        self.issues: List[Issue] = []
        self.is_initialized = False

    async def initialize(self):
        """Initializes the database and loads initial data from cache."""
        await self.db.init_db()
        await self.load_from_cache()
        self.is_initialized = True
        
        # If cache is empty, seed with mock data for now
        if not self.users:
            await self.seed_mock_data()
            await self.load_from_cache()

    async def seed_mock_data(self):
        """Seeds the database with initial mock data."""
        mock_users = [
            User("1", "Bob"),
            User("2", "Alice"),
            User("3", "Dave"),
            User("4", "Sarah"),
            User("5", "Me"),
        ]
        
        mock_projects = [
            Project("1", "Acme Corp", "Synced", 12, 5, 2, "2024-02-28", "Jan Q1"),
            Project("2", "DevTools", "Synced", 8, 3, 0, "2024-03-15", "Feb Q1"),
            Project("3", "Web Redesign", "Synced", 7, 2, 1, "2024-03-30", "Design"),
        ]
        
        mock_issues = [
            Issue("PROJ-245", "Fix Login Bug", "High", "In Progress", mock_users[1], 5),
            Issue("PROJ-234", "UI Fix", "Medium", "In Progress", mock_users[1], 3),
            Issue("PROJ-251", "CSS Bug", "Low", "Todo", mock_users[1], 2),
            Issue("PROJ-234-B", "Backend Sync", "High", "In Progress", mock_users[0], 5),
            Issue("PROJ-246", "Schema Update", "Medium", "Todo", mock_users[0], 2),
            Issue("PROJ-251-B", "API Refactor", "Medium", "In Progress", mock_users[2], 3),
            Issue("PROJ-243", "Write Tests", "Low", "Review", mock_users[2], 2),
            Issue("PROJ-246-B", "DB Setup", "Low", "Done", mock_users[3], 3),
            Issue("PROJ-250", "Migration", "Medium", "Todo", mock_users[3], 2),
            Issue("PROJ-244", "Doc Update", "Low", "Review", mock_users[3], 2),
            Issue("PROJ-245-B", "Core Refactor", "High", "In Progress", mock_users[4], 5),
            Issue("PROJ-235", "Plugin System", "Medium", "Todo", mock_users[4], 3),
            Issue("PROJ-233", "Fast Sync", "High", "Todo", mock_users[4], 2),
        ]
        
        await self.db.save_users(mock_users)
        await self.db.save_projects(mock_projects)
        await self.db.save_issues(mock_issues)

    async def load_from_cache(self):
        """Loads data from the local SQLite cache."""
        self.users = await self.db.get_users()
        self.projects = await self.db.get_projects()
        self.issues = await self.db.get_issues()

    async def sync_with_linear(self):
        """Fetches latest data from Linear and updates the cache."""
        api_key = os.getenv("LINEAR_API_KEY")
        if not api_key:
            return
            
        print("   - Testing connection...")
        try:
            me = await self.linear.get_me()
            print(f"   - Authenticated as: {me['viewer']['name']}")
        except Exception as e:
            print(f"   - Connection failed: {e}")
            return

        print("   - Fetching projects...")
        raw_projects = await self.linear.get_projects()
        projects = []
        for p in raw_projects:
            projects.append(Project(
                id=p["id"],
                name=p["name"],
                status="Active", # Default
                issues_count=0,  # Default
                in_progress_count=0,
                blocked_count=0,
                due_date="N/A",
                cycle="Current"
            ))
        
        print("   - Fetching issues...")
        raw_issues = await self.linear.get_issues()
        
        # Collect unique users
        users_dict = {}
        issues = []
        for i in raw_issues:
            assignee = None
            if i["assignee"]:
                u_id = i["assignee"]["id"]
                if u_id not in users_dict:
                    users_dict[u_id] = User(u_id, i["assignee"]["name"], i["assignee"]["avatarUrl"])
                assignee = users_dict[u_id]
            
            issues.append(Issue(
                id=i["identifier"],
                title=i["title"],
                priority=str(i["priority"]),
                status=i["state"]["name"] if i["state"] else "Todo",
                assignee=assignee,
                points=i["estimate"] or 0
            ))

        # Save to DB
        await self.db.save_users(list(users_dict.values()))
        await self.db.save_projects(projects)
        await self.db.save_issues(issues)
        
        # Reload local state
        await self.load_from_cache()

    def get_projects(self) -> List[Project]:
        return self.projects

    def get_issues(self) -> List[Issue]:
        return self.issues

    def get_issues_by_status(self, status: str) -> List[Issue]:
        return [i for i in self.issues if i.status == status]
