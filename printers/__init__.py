from config import PRINTER_BACKEND, PRINTER_NAME, PRINTER_OPTIONS
from printers.base import Printer
from printers.cups_printer import CupsPrinter
from printers.stub_printer import StubPrinter

_BACKENDS = {
    "stub": lambda: StubPrinter(),
    "cups": lambda: CupsPrinter(PRINTER_NAME, PRINTER_OPTIONS),
}


def get_printer() -> Printer:
    try:
        factory = _BACKENDS[PRINTER_BACKEND]
    except KeyError:
        raise ValueError(
            f"Неизвестный PRINTER_BACKEND={PRINTER_BACKEND!r}, доступны варианты: {list(_BACKENDS)}"
        ) from None
    return factory()
