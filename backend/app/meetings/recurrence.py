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
            assert self.weekday is not None
            local_date = period_date + timedelta(
                days=(self.weekday - period_date.weekday()) % 7
            )
            return self._utc_slot(local_date)
        if self.frequency == RecurrenceFrequency.monthly:
            assert self.month_day is not None
            local_date = period_date.replace(
                day=min(self.month_day, self._last_day(period_date.year, period_date.month))
            )
            return self._utc_slot(local_date)
        assert self.frequency == RecurrenceFrequency.yearly
        assert self.month is not None and self.month_day is not None
        local_date = date(
            period_date.year,
            self.month,
            min(self.month_day, self._last_day(period_date.year, self.month)),
        )
        return self._utc_slot(local_date)

    def slots_through(self, now: datetime) -> list[datetime]:
        """Return all due slots from the anchor through an instant, ordered in UTC."""
        if now.tzinfo is None or now.utcoffset() is None:
            now = now.replace(tzinfo=timezone.utc)
        now = now.astimezone(timezone.utc)
        slots: list[datetime] = []

        if self.frequency == RecurrenceFrequency.daily:
            local_date = self.anchor_date
            while True:
                slot = self._utc_slot(local_date)
                if slot > now:
                    break
                slots.append(slot)
                local_date += timedelta(days=self.interval)
            return slots

        if self.frequency == RecurrenceFrequency.weekly:
            assert self.weekday is not None
            first = self.anchor_date + timedelta(
                days=(self.weekday - self.anchor_date.weekday()) % 7
            )
            local_date = first
            while True:
                slot = self._utc_slot(local_date)
                if slot > now:
                    break
                slots.append(slot)
                local_date += timedelta(days=7 * self.interval)
            return slots

        if self.frequency == RecurrenceFrequency.monthly:
            assert self.month_day is not None
            month = _month_start(self.anchor_date)
            while True:
                local_date = month.replace(
                    day=min(self.month_day, self._last_day(month.year, month.month))
                )
                if local_date >= self.anchor_date:
                    slot = self._utc_slot(local_date)
                    if slot > now:
                        break
                    slots.append(slot)
                month = _add_months(month, self.interval)
            return slots

        assert self.frequency == RecurrenceFrequency.yearly
        assert self.month is not None and self.month_day is not None
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
                slots.append(slot)
            year += self.interval
        return slots
