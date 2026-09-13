import logging

from printers.base import Printer, PrintResult

logger = logging.getLogger(__name__)


class StubPrinter(Printer):
    """Ничего не печатает, только логирует — для разработки без подключённого принтера."""

    async def print_photo(self, photo_path: str) -> PrintResult:
        logger.info("PRINT STUB: поставил бы в очередь на печать %s", photo_path)
        return PrintResult(success=True)
