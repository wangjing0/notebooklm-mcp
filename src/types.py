from typing import Any, Awaitable, Callable, Optional, TypedDict


class SessionInfo(TypedDict):
    id: str
    created_at: float
    last_activity: float
    age_seconds: float
    inactive_seconds: float
    message_count: int
    notebook_url: str


class AskQuestionResult(TypedDict):
    status: str
    question: str
    answer: str
    session_id: str
    notebook_url: str
    session_info: dict


class ToolResult(TypedDict, total=False):
    success: bool
    data: Any
    error: str


ProgressCallback = Callable[[str, Optional[int], Optional[int]], Awaitable[None]]
