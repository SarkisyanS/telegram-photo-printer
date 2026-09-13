import asyncio
import logging
import re
from typing import List, Optional

from printers.base import Printer, PrintResult

logger = logging.getLogger(__name__)

JOB_ID_RE = re.compile(r"request id is (\S+)")


class CupsPrinter(Printer):
    """Печать через системную очередь CUPS (команда `lp`).

    Работает с любым принтером, который добавлен в CUPS — включая Canon SELPHY
    через драйвер Gutenprint. Смена физического принтера обычно сводится
    к смене PRINTER_NAME/PRINTER_OPTIONS в .env, без изменений в коде.

    `lp` возвращает успех, как только CUPS принял задание в очередь — это не
    значит, что принтер физически напечатал лист. Поэтому после отправки мы
    дожидаемся, пока задание реально не покинет очередь принтера.
    """

    def __init__(
        self,
        printer_name: str,
        extra_options: Optional[List[str]] = None,
        completion_timeout: float = 180.0,
        poll_interval: float = 3.0,
    ) -> None:
        if not printer_name:
            raise ValueError(
                "PRINTER_NAME не задан. Посмотри имя очереди CUPS командой `lpstat -p`."
            )
        self.printer_name = printer_name
        self.extra_options = extra_options or []
        self.completion_timeout = completion_timeout
        self.poll_interval = poll_interval

    async def print_photo(self, photo_path: str) -> PrintResult:
        cmd = ["lp", "-d", self.printer_name]
        for option in self.extra_options:
            cmd += ["-o", option]
        cmd.append(photo_path)

        logger.info("Отправляю на печать: %s", " ".join(cmd))
        stdout, stderr, returncode = await self._run(cmd)

        if returncode != 0:
            error = stderr.strip() or f"lp завершился с кодом {returncode}"
            logger.error("CUPS отклонил задание: %s", error)
            return PrintResult(success=False, error=error)

        job_id_match = JOB_ID_RE.search(stdout)
        if not job_id_match:
            logger.warning(
                "Не удалось распознать ID задания в ответе CUPS, считаю успехом без подтверждения: %s",
                stdout.strip(),
            )
            return PrintResult(success=True)

        job_id = job_id_match.group(1)
        logger.info("Задание %s принято CUPS, жду физического завершения печати...", job_id)
        return await self._wait_for_completion(job_id)

    async def _wait_for_completion(self, job_id: str) -> PrintResult:
        elapsed = 0.0
        while elapsed < self.completion_timeout:
            pending, _, _ = await self._run(["lpstat", "-o", self.printer_name])
            if job_id not in pending:
                status, _, _ = await self._run(["lpstat", "-p", self.printer_name, "-l"])
                if "cancel" in status.lower():
                    reason = self._extract_reason(status)
                    logger.error("Принтер отменил задание %s: %s", job_id, reason)
                    return PrintResult(success=False, error=reason)
                logger.info("Задание %s физически напечатано", job_id)
                return PrintResult(success=True)

            await asyncio.sleep(self.poll_interval)
            elapsed += self.poll_interval

        error = f"принтер не подтвердил завершение печати за {self.completion_timeout:.0f} сек"
        logger.error("Задание %s: %s", job_id, error)
        return PrintResult(success=False, error=error)

    @staticmethod
    def _extract_reason(status: str) -> str:
        reason_lines = [
            line.strip()
            for line in status.splitlines()
            if line.strip() and not line.strip().startswith("printer ")
        ]
        return "; ".join(reason_lines) or "принтер отменил задание"

    @staticmethod
    async def _run(cmd: List[str]) -> tuple:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return stdout.decode(errors="replace"), stderr.decode(errors="replace"), proc.returncode
