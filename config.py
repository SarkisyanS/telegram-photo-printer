import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
GROUP_CHAT_ID = int(os.environ["GROUP_CHAT_ID"])
DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", "photos/incoming")
DB_PATH = os.environ.get("DB_PATH", "data/bot.db")

PRINTER_BACKEND = os.environ.get("PRINTER_BACKEND", "stub")
PRINTER_NAME = os.environ.get("PRINTER_NAME", "")
PRINTER_OPTIONS = [
    opt.strip() for opt in os.environ.get("PRINTER_OPTIONS", "").split(",") if opt.strip()
]

# Максимальный размер (по большей стороне) для печати, px. 1800 хватает с запасом
# на 300dpi для отпечатка 10x15/4x6 — большие оригиналы не нужно слать как есть.
PRINT_MAX_DIMENSION = int(os.environ.get("PRINT_MAX_DIMENSION", "1800"))

# Файл-heartbeat: бот периодически пишет туда текущее время, чтобы dashboard.py
# мог определить, что процесс жив (а не просто упал молча).
HEARTBEAT_PATH = os.environ.get("HEARTBEAT_PATH", "data/bot_heartbeat.txt")

# Сколько отпечатков даёт одна кассета/картридж — принтер сам это не сообщает
# (см. README), поэтому считаем расход программно. Для Canon KP-108IN — 108.
CASSETTE_CAPACITY = int(os.environ.get("CASSETTE_CAPACITY", "108"))
