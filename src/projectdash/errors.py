class ProjectDashError(Exception):
    """Base for all ProjectDash exceptions."""


class SyncError(ProjectDashError):
    """Raised when a sync operation fails."""

    def __init__(self, message: str, connector: str, step: str):
        self.connector = connector
        self.step = step
        super().__init__(message)


class AuthenticationError(SyncError):
    """Missing or invalid API credentials."""


class ApiResponseError(SyncError):
    """API returned an unexpected response."""


class PersistenceError(ProjectDashError):
    """Database write failure."""

    def __init__(self, message: str, operation: str):
        self.operation = operation
        super().__init__(message)
