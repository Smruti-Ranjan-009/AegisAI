from __future__ import annotations


class LifecycleError(RuntimeError):
    """Stable user-facing lifecycle failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")

    def as_dict(self) -> dict[str, str]:
        return {"status": "ERROR", "error_code": self.code, "message": self.message}
