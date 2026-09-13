import asyncio
import logging
import mimetypes
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message

from config import BOT_TOKEN, DOWNLOAD_DIR, GROUP_CHAT_ID, HEARTBEAT_PATH, PRINT_MAX_DIMENSION
from db import init_db, mark_printed, photo_exists, save_photo_record
from image_processing import prepare_for_print
from printers import get_printer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
printer = get_printer()


@dataclass
class PrintJob:
    message: Message
    file_path: str
    file_unique_id: str


print_queue: "asyncio.Queue[PrintJob]" = asyncio.Queue()


def guess_extension(filename: Optional[str], mime_type: Optional[str]) -> str:
    if filename and "." in filename:
        return os.path.splitext(filename)[1]
    if mime_type:
        ext = mimetypes.guess_extension(mime_type)
        if ext:
            return ext
    return ".jpg"


async def process_incoming_photo(message: Message, file_id: str, file_unique_id: str, ext: str) -> None:
    if photo_exists(file_unique_id):
        return

    day_dir = os.path.join(DOWNLOAD_DIR, date.today().isoformat())
    os.makedirs(day_dir, exist_ok=True)
    file_path = os.path.join(day_dir, f"{message.message_id}_{file_unique_id}{ext}")

    await bot.download(file_id, destination=file_path)
    prepare_for_print(file_path, file_path, max_size=(PRINT_MAX_DIMENSION, PRINT_MAX_DIMENSION))

    sender_name = message.from_user.full_name if message.from_user else "unknown"
    save_photo_record(file_unique_id, message.message_id, sender_name, file_path)
    logger.info("Получено фото от %s -> %s, ставлю в очередь на печать", sender_name, file_path)

    await print_queue.put(PrintJob(message=message, file_path=file_path, file_unique_id=file_unique_id))


async def print_worker() -> None:
    """Печатает по одному заданию за раз, дожидаясь реального завершения перед следующим."""
    while True:
        job = await print_queue.get()
        try:
            result = await printer.print_photo(job.file_path)
            if result.success:
                mark_printed(job.file_unique_id)
                try:
                    os.remove(job.file_path)
                    logger.info("Файл удалён после печати: %s", job.file_path)
                except OSError as e:
                    logger.warning("Не удалось удалить файл после печати %s: %s", job.file_path, e)
                await job.message.reply("✅ Фото распечатано")
            else:
                logger.error("Печать не удалась: %s", result.error)
                details = f"\n{result.error}" if result.error else ""
                await job.message.reply(f"⚠️ Не удалось напечатать фото.{details}\nФайл сохранён для повтора.")
        except Exception as e:
            logger.exception("Ошибка при обработке задания печати %s", job.file_path)
            await job.message.reply(f"⚠️ Ошибка при печати: {e}\nФайл сохранён для повтора.")
        finally:
            print_queue.task_done()


@dp.message(F.chat.id == GROUP_CHAT_ID, F.photo)
async def handle_photo(message: Message) -> None:
    photo = message.photo[-1]  # наибольшее доступное разрешение среди сжатых версий
    await process_incoming_photo(message, photo.file_id, photo.file_unique_id, ".jpg")


@dp.message(F.chat.id == GROUP_CHAT_ID, F.document, F.document.mime_type.startswith("image/"))
async def handle_photo_document(message: Message) -> None:
    doc = message.document  # отправлено как "Файл" — оригинал без сжатия Telegram
    ext = guess_extension(doc.file_name, doc.mime_type)
    await process_incoming_photo(message, doc.file_id, doc.file_unique_id, ext)


async def heartbeat_writer() -> None:
    """Периодически отмечает, что процесс бота жив — для dashboard.py."""
    while True:
        os.makedirs(os.path.dirname(HEARTBEAT_PATH) or ".", exist_ok=True)
        with open(HEARTBEAT_PATH, "w") as f:
            f.write(datetime.now(timezone.utc).isoformat())
        await asyncio.sleep(30)


async def main() -> None:
    init_db()
    asyncio.create_task(print_worker())
    asyncio.create_task(heartbeat_writer())
    logger.info("Бот запущен, слушаю группу %s", GROUP_CHAT_ID)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
