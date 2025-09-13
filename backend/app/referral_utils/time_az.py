# utils/time_az.py
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

BAKU_TZ = ZoneInfo("Asia/Baku")

def baku_now():
    return datetime.now(BAKU_TZ)

def baku_today():
    return baku_now().date()

def baku_end_of_today_dt():
    # конец дня: 23:59:59.999 по Баку
    today = baku_today()
    # делаем конец дня как начало следующего дня минус микросекунда
    start_next = datetime.combine(today + timedelta(days=1), time(0, 0, 0), tzinfo=BAKU_TZ)
    return start_next - timedelta(microseconds=1)
