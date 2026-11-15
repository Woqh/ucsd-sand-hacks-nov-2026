from __future__ import annotations


class ApiError(Exception):
    """Raised anywhere in a request; the app turns it into {"error": {"code", "message"}}."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
