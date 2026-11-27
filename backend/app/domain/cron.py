"""Cron ifadelerini çözümleme ve bir sonraki çalışma zamanını hesaplama (ATOP-42).

Standart 5 alanlı cron:

    ┌──────── dakika        (0-59)
    │ ┌────── saat          (0-23)
    │ │ ┌──── ayın günü     (1-31)
    │ │ │ ┌── ay            (1-12)
    │ │ │ │ ┌ haftanın günü (0-6, 0 = Pazar; 7 de Pazar sayılır)
    │ │ │ │ │
    * * * * *

Desteklenenler: *  5  1,15  1-5  */10  0-30/5  ve kısayollar @hourly @daily @weekly @monthly
Örnekler:  */5 * * * *  (5 dakikada bir)   0 9 * * 1-5  (hafta içi 09:00)

Ayın günü ve haftanın günü ikisi birden kısıtlanırsa (ikisi de * değilse) standart cron gibi
"veya" ile birleştirilir: 0 0 13 * 5  -> ayın 13'ü VEYA cuma.

Saatler settings.timezone (varsayılan Europe/Istanbul) saatine göre yorumlanır.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

ALIASES = {
    "@hourly": "0 * * * *",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@weekly": "0 0 * * 0",
    "@monthly": "0 0 1 * *",
}
FIELDS = (
    ("dakika", 0, 59),
    ("saat", 0, 23),
    ("ayın günü", 1, 31),
    ("ay", 1, 12),
    ("haftanın günü", 0, 7),
)
# Ay başına atlamalar dahil ~5 yıllık arama; buna rağmen bulunamazsa ifade hiç çalışmaz
MAX_STEPS = 100_000


@dataclass(frozen=True)
class CronExpression:
    text: str
    minutes: frozenset[int]
    hours: frozenset[int]
    days: frozenset[int]
    months: frozenset[int]
    weekdays: frozenset[int]
    any_day: bool
    any_weekday: bool


def _parse_field(text: str, name: str, low: int, high: int) -> frozenset[int]:
    values: set[int] = set()
    for item in text.split(","):
        if not item:
            raise ValueError(f"{name} alanında boş değer var")
        base, _, step_text = item.partition("/")
        step = 1
        if step_text:
            if not step_text.isdigit() or int(step_text) == 0:
                raise ValueError(f"{name} alanında geçersiz adım: '{item}'")
            step = int(step_text)

        if base == "*":
            start, end = low, high
        elif "-" in base:
            first, _, last = base.partition("-")
            if not first.isdigit() or not last.isdigit():
                raise ValueError(f"{name} alanında geçersiz aralık: '{item}'")
            start, end = int(first), int(last)
            if start > end:
                raise ValueError(f"{name} alanında aralık ters: '{item}'")
        elif base.isdigit():
            start = int(base)
            end = high if step_text else start
        else:
            raise ValueError(f"{name} alanında geçersiz değer: '{item}'")

        if start < low or end > high:
            raise ValueError(f"{name} {low}-{high} arasında olmalı: '{item}'")
        values.update(range(start, end + 1, step))
    return frozenset(values)


def parse(text: str) -> CronExpression:
    cleaned = " ".join(text.split())
    expanded = ALIASES.get(cleaned.lower(), cleaned)
    parts = expanded.split(" ")
    if len(parts) != 5:
        raise ValueError(
            "Cron ifadesi 5 alandan oluşmalı: dakika saat gün ay haftanın-günü (ör. */5 * * * *)"
        )
    fields = [
        _parse_field(part, name, low, high)
        for part, (name, low, high) in zip(parts, FIELDS, strict=True)
    ]
    weekdays = frozenset(0 if day == 7 else day for day in fields[4])
    return CronExpression(
        text=cleaned,
        minutes=fields[0],
        hours=fields[1],
        days=fields[2],
        months=fields[3],
        weekdays=weekdays,
        any_day=parts[2] == "*",
        any_weekday=parts[4] == "*",
    )


def _day_matches(expr: CronExpression, moment: datetime) -> bool:
    day_ok = moment.day in expr.days
    # Python: pazartesi=0 ... pazar=6  ->  cron: pazar=0, pazartesi=1 ...
    weekday_ok = (moment.weekday() + 1) % 7 in expr.weekdays
    if expr.any_day and expr.any_weekday:
        return True
    if expr.any_day:
        return weekday_ok
    if expr.any_weekday:
        return day_ok
    return day_ok or weekday_ok


def next_after(
    expr: CronExpression, after: datetime, timezone: str = "Europe/Istanbul"
) -> datetime:
    """`after`dan sonraki ilk çalışma zamanı (UTC, saniyesiz)."""
    zone = ZoneInfo(timezone)
    if after.tzinfo is None:
        after = after.replace(tzinfo=UTC)
    moment = after.astimezone(zone).replace(second=0, microsecond=0) + timedelta(minutes=1)

    for _ in range(MAX_STEPS):
        if moment.month not in expr.months:
            year = moment.year + (1 if moment.month == 12 else 0)
            month = 1 if moment.month == 12 else moment.month + 1
            moment = moment.replace(year=year, month=month, day=1, hour=0, minute=0)
            continue
        if not _day_matches(expr, moment):
            moment = (moment + timedelta(days=1)).replace(hour=0, minute=0)
            continue
        if moment.hour not in expr.hours:
            moment = (moment + timedelta(hours=1)).replace(minute=0)
            continue
        if moment.minute not in expr.minutes:
            moment += timedelta(minutes=1)
            continue
        return moment.astimezone(UTC)
    raise ValueError(f"'{expr.text}' hiçbir zaman çalışmıyor (ör. 30 Şubat gibi bir tarih)")


def next_runs(
    expr: CronExpression, after: datetime, count: int = 5, timezone: str = "Europe/Istanbul"
) -> list[datetime]:
    times: list[datetime] = []
    moment = after
    for _ in range(count):
        moment = next_after(expr, moment, timezone)
        times.append(moment)
    return times


def validate(text: str, timezone: str = "Europe/Istanbul") -> str:
    """İfadeyi kontrol eder (hiç çalışmayan ifadeler dahil) ve temizlenmiş halini döndürür."""
    expr = parse(text)
    next_after(expr, datetime.now(UTC), timezone)
    return expr.text
