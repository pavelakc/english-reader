"""Simplified SM-2 spaced repetition (Anki-style). grade: 0=again 1=hard 2=good 3=easy."""
from datetime import datetime, timedelta, timezone

KNOWN_AFTER_DAYS = 30  # a card with an interval this long counts as learned


def review(card: dict, grade: int, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    ease = float(card.get("ease") or 2.5)
    interval = int(card.get("interval_days") or 0)
    reps = int(card.get("reps") or 0)
    lapses = int(card.get("lapses") or 0)

    if grade <= 0:  # again
        reps, lapses = 0, lapses + 1
        ease = max(1.3, ease - 0.2)
        interval = 0
        due = now + timedelta(minutes=10)
    else:
        if grade == 1:  # hard
            ease = max(1.3, ease - 0.15)
            interval = max(1, round(interval * 1.2))
        else:
            if reps == 0:
                interval = 1
            elif reps == 1:
                interval = 3
            else:
                interval = max(interval + 1, round(interval * ease))
            if grade >= 3:  # easy
                ease += 0.15
                interval = max(interval + 1, round(interval * 1.3))
        reps += 1
        due = now + timedelta(days=interval)

    out = {"ease": round(ease, 2), "interval_days": interval, "reps": reps, "lapses": lapses,
           "due_at": due.isoformat()}
    if interval >= KNOWN_AFTER_DAYS:
        out["status"] = "known"
    return out
