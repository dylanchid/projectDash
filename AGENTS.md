# Agent Instructions - projectDash

This project is a Project Dashboard TUI. Use the following instructions for development and testing.

## Pilotty (Headless TUI Testing)

This project supports **Pilotty**, a "headless browser for the terminal." Use it for automated TUI testing and monitoring.

### Why use it?
- **Render Error Detection:** Catch `MountError` or layout crashes that only happen during TUI startup.
- **Data Sync Verification:** Use snapshots to confirm that Linear/GitHub sync results are correctly displayed in the UI widgets.
- **Automated Monitoring:** Run the dashboard in a headless session and use `pilotty snapshot --format full` to programmatically check project status.

### Key Commands
```bash
# Run the automated snapshot test (Checks for crashes on boot)
./tests/pilotty/snapshot_test.sh

# Manual inspection
pilotty spawn --name pd --cwd . uv run pd
pilotty snapshot -s pd --format text   # View the dashboard
pilotty snapshot -s pd --format full   # Get structured widget data
pilotty key -s pd s                    # Trigger a manual sync (if supported by TUI)
pilotty kill -s pd                     # Cleanup
```

## Development Workflow

### Running the App
- **Standard:** `uv run pd`
- **Dev Mode (Auto-restart):** `uv run pd-dev`

### Testing
- **Unit Tests:** `uv run pytest`
- **Linting:** `uv run ruff check .` (if available)

### Key Files
- `src/projectdash/app.py`: Main Textual App class
- `src/projectdash/cli.py`: CLI entry point and command logic
- `src/projectdash/data.py`: Data management and syncing
