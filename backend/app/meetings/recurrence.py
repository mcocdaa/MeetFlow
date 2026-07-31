from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.domain.enums import RecurrenceFrequency


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _add_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    return date(month_index // 12, month_index % 12 + 1, 1)


@dataclass(frozen=True)
class RecurrenceRule:
    """A stored local-time rule whose generated slots are normalized to UTC."""

    frequency: RecurrenceFrequency
    interval: int
    local_time: time
    timezone_name: str
    anchor_date: date
    weekday: int | None = None
    month_day: int | None = None
    month: int | None = None

    def __post_init__(self) -> None:
        if self.interval < 1:
            raise ValueError("recurrence interval must be positive")
        if self.frequency == RecurrenceFrequency.weekly and self.weekday is None:
            raise ValueError("weekly recurrence requires weekday")
        if self.frequency == RecurrenceFrequency.monthly and self.month_day is None:
            raise ValueError("monthly recurrence requires month_day")
        if self.frequency == RecurrenceFrequency.yearly and (
            self.month is None or self.month_day is None
        ):
            raise ValueError("yearly recurrence requires month and month_day")

    @classmethod
    def daily(
        cls,
        *,
        interval: int,
        local_time: time,
        timezone_name: str,
        anchor_date: date,
    ) -> "RecurrenceRule":
        return cls(
            frequency=RecurrenceFrequency.daily,
            interval=interval,
            local_time=local_time,
            timezone_name=timezone_name,
            anchor_date=anchor_date,
        )

    @classmethod
    def weekly(
        cls,
        *,
        interval: int,
        weekday: int,
        local_time: time,
        timezone_name: str,
        anchor_date: date,
    ) -> "RecurrenceRule":
        return cls(
            frequency=RecurrenceFrequency.weekly,
            interval=interval,
            weekday=weekday,
            local_time=local_time,
            timezone_name=timezone_name,
            anchor_date=anchor_date,
        )

    @classmethod
    def monthly(
        cls,
        *,
        interval: int,
        month_day: int,
        local_time: time,
        timezone_name: str,
        anchor_date: date,
    ) -> "RecurrenceRule":
        return cls(
            frequency=RecurrenceFrequency.monthly,
            interval=interval,
            month_day=month_day,
            local_time=local_time,
            timezone_name=timezone_name,
            anchor_date=anchor_date,
        )

    @classmethod
    def yearly(
        cls,
        *,
        interval: int,
        month: int,
        month_day: int,
        local_time: time,
        timezone_name: str,
        anchor_date: date,
    ) -> "RecurrenceRule":
        return cls(
            frequency=RecurrenceFrequency.yearly,
            interval=interval,
            month=month,
            month_day=month_day,
            local_time=local_time,
            timezone_name=timezone_name,
            anchor_date=anchor_date,
        )

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)

    def _utc_slot(self, local_date: date) -> datetime:
        # ZoneInfo selects the first autumn-fold occurrence and applies its UTC
        # offset rule for a nonexistent spring-gap local time.
        return datetime.combine(local_date, self.local_time, tzinfo=self.timezone).astimezone(
            timezone.utc
        )

    @staticmethod
    def _last_day(year: int, month: int) -> int:
        return calendar.monthrange(year, month)[1]

    def slot_for(self, period_date: date) -> datetime:
        """Return the rule's local-time slot in the supplied period as UTC."""
        if self.frequency == RecurrenceFrequency.daily:
            return self._utc_slot(period_date)
        if self.frequency == RecurrenceFrequency.weekly:
            if self.weekday is None:
                raise ValueError("weekly recurrence requires weekday")
            local_date = period_date + timedelta(
                days=(self.weekday - period_date.weekday()) % 7
            )
            return self._utc_slot(local_date)
        if self.frequency == RecurrenceFrequency.monthly:
            if self.month_day is None:
                raise ValueError("monthly recurrence requires month_day")
            local_date = period_date.replace(
                day=min(self.month_day, self._last_day(period_date.year, period_date.month))
            )
            return self._utc_slot(local_date)
        if self.frequency != RecurrenceFrequency.yearly:
            raise ValueError("unsupported recurrence frequency")
        if self.month is None or self.month_day is None:
            raise ValueError("yearly recurrence requires month and month_day")
        local_date = date(
            period_date.year,
            self.month,
            min(self.month_day, self._last_day(period_date.year, self.month)),
        )
        return self._utc_slot(local_date)

    def slots_through(
        self, now: datetime, *, earliest: datetime | None = None
    ) -> list[datetime]:
        """Return all due slots from the anchor through an instant, ordered in UTC."""
        if now.tzinfo is None or now.utcoffset() is None:
            now = now.replace(tzinfo=timezone.utc)
        now = now.astimezone(timezone.utc)
        if earliest is not None:
            if earliest.tzinfo is None or earliest.utcoffset() is None:
                earliest = earliest.replace(tzinfo=timezone.utc)
            earliest = earliest.astimezone(timezone.utc)
        slots: list[datetime] = []

        def append_if_due(slot: datetime) -> None:
            if earliest is None or slot >= earliest:
                slots.append(slot)

        if self.frequency == RecurrenceFrequency.daily:
            local_date = self.anchor_date
            while True:
                slot = self._utc_slot(local_date)
                if slot > now:
                    break
                append_if_due(slot)
                local_date += timedelta(days=self.interval)
            return slots

        if self.frequency == RecurrenceFrequency.weekly:
            if self.weekday is None:
                raise ValueError("weekly recurrence requires weekday")
            first = self.anchor_date + timedelta(
                days=(self.weekday - self.anchor_date.weekday()) % 7
            )
            local_date = first
            while True:
                slot = self._utc_slot(local_date)
                if slot > now:
                    break
                append_if_due(slot)
                local_date += timedelta(days=7 * self.interval)
            return slots

        if self.frequency == RecurrenceFrequency.monthly:
            if self.month_day is None:
                raise ValueError("monthly recurrence requires month_day")
            month = _month_start(self.anchor_date)
            while True:
                local_date = month.replace(
                    day=min(self.month_day, self._last_day(month.year, month.month))
                )
                if local_date >= self.anchor_date:
                    slot = self._utc_slot(local_date)
                    if slot > now:
                        break
                    append_if_due(slot)
                month = _add_months(month, self.interval)
            return slots

        if self.frequency != RecurrenceFrequency.yearly:
            raise ValueError("unsupported recurrence frequency")
        if self.month is None or self.month_day is None:
            raise ValueError("yearly recurrence requires month and month_day")
        year = self.anchor_date.year
        while True:
            local_date = date(
                year,
                self.month,
                min(self.month_day, self._last_day(year, self.month)),
            )
            if local_date >= self.anchor_date:
                slot = self._utc_slot(local_date)
                if slot > now:
                    break
                append_if_due(slot)
            year += self.interval
        return slots
