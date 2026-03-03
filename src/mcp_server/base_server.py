from abc import ABC, abstractmethod

from ..config import ServerConfig


class BaseMCPServer(ABC):
    def __init__(self, server_config: ServerConfig) -> None:
        self._server_config = server_config

    @abstractmethod
    def run(self) -> None: ...
