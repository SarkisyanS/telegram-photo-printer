import asyncio
import os
import re
import sqlite3
import subprocess
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from urllib.parse import unquote, urlparse

import pandas as pd
import streamlit as st

from config import CASSETTE_CAPACITY, DB_PATH, GROUP_CHAT_ID, HEARTBEAT_PATH, PRINTER_BACKEND, PRINTER_NAME
from db import count_prints_since, get_cassette_reset_at, reset_cassette
from printers import get_printer

HEARTBEAT_STALE_SECONDS = 90

st.set_page_config(page_title="Бабушкин фотопринтер", page_icon="🖨️", layout="wide")


def load_photos() -> pd.DataFrame:
    columns = [
        "id", "file_unique_id", "message_id", "sender_name",
        "saved_path", "received_at", "printed_at", "status",
    ]
    if not os.path.exists(DB_PATH):
        return pd.DataFrame(columns=columns)
    conn = sqlite3.connect(DB_PATH)
    try:
        return pd.read_sql_query("SELECT * FROM photos ORDER BY id DESC", conn)
    finally:
        conn.close()


def bot_status() -> Tuple[Optional[bool], str]:
    if not os.path.exists(HEARTBEAT_PATH):
        return False, "нет файла heartbeat — бот ни разу не запускался с этой настройкой"
    with open(HEARTBEAT_PATH) as f:
        raw = f.read().strip()
    try:
        last = datetime.fromisoformat(raw)
    except ValueError:
        return False, "не удалось прочитать heartbeat"
    age = (datetime.now(timezone.utc) - last).total_seconds()
    if age < HEARTBEAT_STALE_SECONDS:
        return True, f"последний отклик {int(age)} сек назад"
    return False, f"нет отклика {int(age)} сек — бот, вероятно, не запущен"


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", unquote(text).lower())


def _device_identity(printer_name: str) -> Optional[str]:
    """Опознавательная строка устройства (модель/имя) из его device-uri в CUPS."""
    try:
        result = subprocess.run(["lpstat", "-v", printer_name], capture_output=True, text=True, timeout=5)
    except Exception:
        return None
    if result.returncode != 0 or ":" not in result.stdout:
        return None
    uri = result.stdout.split(":", 1)[1].strip()
    parsed = urlparse(uri)
    identity = _normalize(parsed.netloc + parsed.path)[:20]
    return identity if len(identity) >= 6 else None


def is_device_reachable(printer_name: str) -> Optional[bool]:
    """Активно проверяет, виден ли принтер прямо сейчас (USB/сеть) — в отличие от
    `lpstat -p`, который просто показывает последний известный статус очереди
    и не замечает, что устройство физически отключили, пока не попробует печатать.
    """
    identity = _device_identity(printer_name)
    if not identity:
        return None
    try:
        # lpinfo -v активно опрашивает сеть/USB и может занимать 10-15+ сек
        discovered = subprocess.run(["lpinfo", "-v"], capture_output=True, text=True, timeout=25)
    except Exception:
        return None
    return identity in _normalize(discovered.stdout)


def printer_status() -> dict:
    if PRINTER_BACKEND != "cups":
        return {"ok": None, "text": f"backend = {PRINTER_BACKEND} (реальный принтер не используется)"}
    if not PRINTER_NAME:
        return {"ok": False, "text": "PRINTER_NAME не задан в .env"}
    try:
        result = subprocess.run(
            ["lpstat", "-p", PRINTER_NAME, "-l"], capture_output=True, text=True, timeout=5
        )
    except FileNotFoundError:
        return {"ok": False, "text": "команда lpstat не найдена (нет CUPS в системе?)"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "text": "lpstat не ответил за 5 сек"}

    if result.returncode != 0:
        return {"ok": False, "text": (result.stderr or result.stdout).strip() or "принтер не найден в CUPS"}

    queue_text = result.stdout.strip()
    queue_ok = "idle" in queue_text.lower() or "printing" in queue_text.lower()

    queue_len = None
    try:
        pending = subprocess.run(["lpstat", "-o", PRINTER_NAME], capture_output=True, text=True, timeout=5)
        queue_len = len([line for line in pending.stdout.splitlines() if line.strip()])
    except Exception:
        pass

    reachable = is_device_reachable(PRINTER_NAME)
    if reachable is False:
        return {
            "ok": False,
            "text": f"устройство не отвечает — офлайн или отключено (очередь CUPS думает: «{queue_text}»)",
            "queue_len": queue_len,
        }
    if reachable is None:
        return {
            "ok": queue_ok,
            "text": f"{queue_text} (не удалось активно проверить, включено ли устройство)",
            "queue_len": queue_len,
        }

    return {"ok": queue_ok, "text": queue_text, "queue_len": queue_len}


st.title("🖨️ Бабушкин фотопринтер")

status_col1, status_col2 = st.columns(2)

with status_col1:
    st.subheader("Бот")
    online, detail = bot_status()
    if online:
        st.success(f"🟢 Подключён · {detail}")
    else:
        st.error(f"🔴 Не отвечает · {detail}")
    st.caption(f"Группа: `{GROUP_CHAT_ID}`")

with status_col2:
    st.subheader("Принтер")
    pstat = printer_status()
    if pstat["ok"] is None:
        st.info(f"⚪ {pstat['text']}")
    elif pstat["ok"]:
        st.success(f"🟢 {pstat['text']}")
    else:
        st.error(f"🔴 {pstat['text']}")
    if pstat.get("queue_len") is not None:
        st.caption(f"Заданий в очереди CUPS: {pstat['queue_len']}")

st.divider()

st.subheader("Расходники")
reset_at = get_cassette_reset_at()
used = count_prints_since(reset_at)
remaining = max(CASSETTE_CAPACITY - used, 0)
fraction_used = min(used / CASSETTE_CAPACITY, 1.0) if CASSETTE_CAPACITY else 0.0

cassette_col1, cassette_col2 = st.columns([3, 1])
with cassette_col1:
    st.progress(fraction_used, text=f"Использовано {used} из {CASSETTE_CAPACITY} (осталось ~{remaining})")
    if remaining <= 0:
        st.error("Кассета, вероятно, пуста — пора менять.")
    elif remaining <= 10:
        st.warning(f"Осталось мало — примерно {remaining} отпечатков.")
    reset_label = "с начала времён" if reset_at == "0000-01-01 00:00:00" else reset_at
    st.caption(f"Текущая кассета считается установленной с: {reset_label}")
with cassette_col2:
    if st.button("🔄 Новая кассета"):
        reset_cassette()
        st.rerun()

st.divider()

df = load_photos()
total = len(df)
printed = int((df["status"] == "printed").sum()) if total else 0
pending = total - printed
today_str = datetime.now().strftime("%Y-%m-%d")
today_count = int(df["received_at"].str.startswith(today_str).sum()) if total else 0

m1, m2, m3, m4 = st.columns(4)
m1.metric("Всего фото", total)
m2.metric("Напечатано", printed)
m3.metric("Ожидают / не удалось", pending)
m4.metric("Сегодня", today_count)

if total:
    st.subheader("Фото по дням (последние 14 дней)")
    df["date"] = pd.to_datetime(df["received_at"]).dt.date
    date_range = [(datetime.now().date() - timedelta(days=i)) for i in range(13, -1, -1)]
    daily = df.groupby("date").size().reindex(date_range, fill_value=0)
    daily.index = [d.strftime("%d.%m") for d in daily.index]
    st.bar_chart(daily, color="#3B82F6")

    left, right = st.columns(2)
    with left:
        st.subheader("Топ отправителей")
        counts = (
            df["sender_name"].value_counts().rename_axis("Отправитель").reset_index(name="Фото")
        )
        st.dataframe(counts, use_container_width=True, hide_index=True)

    with right:
        st.subheader("Ожидают повторной печати")
        retryable = df[(df["status"] != "printed") & df["saved_path"].apply(os.path.exists)]
        if retryable.empty:
            st.caption("Нет фото, ожидающих повторной печати.")
        else:
            for _, row in retryable.iterrows():
                cols = st.columns([1, 3, 2])
                with cols[0]:
                    st.image(row["saved_path"], width=60)
                with cols[1]:
                    st.write(f"{row['sender_name']}")
                    st.caption(row["received_at"])
                with cols[2]:
                    if st.button("🔁 Повторить", key=f"retry_{row['id']}"):
                        result = asyncio.run(get_printer().print_photo(row["saved_path"]))
                        conn = sqlite3.connect(DB_PATH)
                        try:
                            if result.success:
                                conn.execute(
                                    "UPDATE photos SET status='printed', printed_at=datetime('now') WHERE id=?",
                                    (row["id"],),
                                )
                                conn.commit()
                                try:
                                    os.remove(row["saved_path"])
                                except OSError:
                                    pass
                                st.success("Напечатано!")
                            else:
                                st.error(f"Не удалось: {result.error}")
                        finally:
                            conn.close()
                        st.rerun()

st.divider()
st.subheader("Все фото в базе")

if total:
    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        status_filter = st.multiselect("Статус", options=sorted(df["status"].unique()))
    with filter_col2:
        sender_filter = st.multiselect("Отправитель", options=sorted(df["sender_name"].unique()))

    filtered = df.drop(columns=["date"], errors="ignore")
    if status_filter:
        filtered = filtered[filtered["status"].isin(status_filter)]
    if sender_filter:
        filtered = filtered[filtered["sender_name"].isin(sender_filter)]

    st.dataframe(filtered, use_container_width=True, hide_index=True)
else:
    st.caption("В базе пока нет ни одного фото.")

st.divider()
auto_refresh = st.checkbox("Автообновление каждые 15 сек")
if auto_refresh:
    time.sleep(15)
    st.rerun()
