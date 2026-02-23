import argparse
import asyncio
import os
import sys
import subprocess
from pathlib import Path
from dotenv import load_dotenv
from projectdash.data import DataManager
from projectdash.database import DB_PATH

def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="ProjectDash CLI")
    subparsers = parser.add_subparsers(dest="command")
    
    # Subcommands
    subparsers.add_parser("sync", help="Sync with Linear")
    subparsers.add_parser("doctor", help="Check setup and environment")
    subparsers.add_parser("stats", help="Show project statistics")
    subparsers.add_parser("test", help="Run project tests")
    subparsers.add_parser("build", help="Build the project")
    
    args = parser.parse_args()
    
    if args.command == "sync":
        asyncio.run(sync())
    elif args.command == "doctor":
        doctor()
    elif args.command == "stats":
        asyncio.run(stats())
    elif args.command == "test":
        run_tests()
    elif args.command == "build":
        build_project()
    else:
        # Default: run the TUI
        from projectdash.app import run
        run()

async def sync():
    """Manually trigger a Linear sync."""
    print("🔄 Syncing with Linear...")
    dm = DataManager()
    await dm.initialize()
    if not os.getenv("LINEAR_API_KEY"):
        print("❌ Error: LINEAR_API_KEY not found in environment.")
        return
    
    await dm.sync_with_linear()
    print("✅ Sync complete.")

def doctor():
    """Check for necessary environment variables and files."""
    print("🩺 Running ProjectDash Doctor...")
    
    # 1. Check .env
    env_exists = Path(".env").exists()
    print(f"[{'✓' if env_exists else '✕'}] .env file")
    
    # 2. Check API Key
    api_key = os.getenv("LINEAR_API_KEY")
    print(f"[{'✓' if api_key else '✕'}] LINEAR_API_KEY")
    
    # 3. Check DB
    db_exists = DB_PATH.exists()
    print(f"[{'✓' if db_exists else '✕'}] projectdash.db cache")
    
    # 4. Check Connection (optional)
    if api_key:
        print("   - Testing Linear API connection...")
        # A quick ping could go here
    
    print("\nDoctor check complete.")

async def stats():
    """Quick project statistics."""
    print("📊 ProjectDash Stats")
    dm = DataManager()
    await dm.initialize()
    
    projects = dm.get_projects()
    issues = dm.get_issues()
    
    print(f"Projects: {len(projects)}")
    print(f"Issues:   {len(issues)}")
    
    # Simple breakdown by status
    statuses = {}
    for i in issues:
        statuses[i.status] = statuses.get(i.status, 0) + 1
    
    print("\nIssue Status:")
    for status, count in statuses.items():
        print(f"  {status:12}: {count}")

def run_tests():
    """Run pytest suite."""
    print("🧪 Running tests...")
    try:
        subprocess.run(["pytest"], check=True)
    except subprocess.CalledProcessError:
        print("❌ Tests failed.")
        sys.exit(1)
    except FileNotFoundError:
        print("❌ Error: pytest not found. Run 'uv sync' or 'uv add --dev pytest'.")

def build_project():
    """Build the project using uv."""
    print("🏗️ Building project...")
    try:
        subprocess.run(["uv", "build"], check=True)
    except subprocess.CalledProcessError:
        print("❌ Build failed.")
        sys.exit(1)

if __name__ == "__main__":
    main()
