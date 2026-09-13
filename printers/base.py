from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class PrintResult:
    success: bool
    error: Optional[str] = None


class Printer(ABC):
    @abstractmethod
    async def print_photo(self, photo_path: str) -> PrintResult:
        """Отправить файл на печать."""
        raise NotImplementedError
