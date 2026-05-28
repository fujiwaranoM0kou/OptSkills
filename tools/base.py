from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Union


class BaseTool(ABC):
    name: str = ""
    description: str = ""
    parameters: Dict[str, Any] = {}

    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        self.config = config or {}
        if not self.name:
            raise ValueError("Tool must define a non-empty `name`.")

    @abstractmethod
    def call(self, params: Union[str, Dict[str, Any]], **kwargs: Any) -> Union[str, Dict[str, Any]]:
        raise NotImplementedError

    def validate_params(self, params: Dict[str, Any]) -> bool:
        required = self.parameters.get("required", [])
        return all(key in params for key in required)

