from typing import TypedDict


class NotebookEntry(TypedDict):
    id: str
    url: str
    name: str
    description: str
    topics: list
    content_types: list
    use_cases: list
    added_at: str
    last_used: str
    use_count: int
    tags: list


class Library(TypedDict):
    notebooks: list
    active_notebook_id: str | None
    last_modified: str
    version: str


class LibraryStats(TypedDict):
    total_notebooks: int
    active_notebook: str | None
    most_used_notebook: str | None
    total_queries: int
    last_modified: str


class AddNotebookInput(TypedDict, total=False):
    url: str
    name: str
    description: str
    topics: list
    content_types: list
    use_cases: list
    tags: list


class UpdateNotebookInput(TypedDict, total=False):
    id: str
    name: str
    description: str
    topics: list
    content_types: list
    use_cases: list
    tags: list
    url: str
