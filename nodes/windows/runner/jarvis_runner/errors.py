from __future__ import annotations


class RunnerError(Exception):
    """A narrow, safe error intended for a CLI response."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class OutputValidationError(ValueError):
    pass
