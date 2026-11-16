"""Collection-day metadata, shared by imports, labels and export names."""
import re

DAYS = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")
DAY_ALIASES = {day: day for day in DAYS}
DAY_ALIASES.update({day[:3]: day for day in DAYS})
DAY_ALIASES.update(TUES="TUESDAY", THUR="THURSDAY", THURS="THURSDAY")


def normalize_day(value):
    return DAY_ALIASES.get(str(value or "").strip().rstrip(".").upper(), "")


def day_in_label(value):
    words = re.findall(r"[A-Za-z]+", str(value or ""))
    days = {normalize_day(word) for word in words} - {""}
    return next(iter(days)) if len(days) == 1 else ""


def day_label(value):
    day = normalize_day(value)
    if not day:
        raise ValueError("Choose a valid collection day.")
    return day.title()
