"""בדיקות ללוח העברי ולזמנים החסומים (מול hdate ו-pyluach אמיתיים)."""

from datetime import date, time, timedelta

from daypilot.domain.intervals import Interval
from daypilot.jewish_calendar.calendar import JewishCalendar, day_info, gregorian_to_hebrew, hebrew_to_gregorian
from daypilot.jewish_calendar.cities import city_by_key
from daypilot.utils.clock import local_datetime, to_local

TZ = "Asia/Jerusalem"
JERUSALEM = city_by_key("jerusalem")


def test_rosh_hashana_5787_conversion_both_ways():
    assert hebrew_to_gregorian(5787, 7, 1) == date(2026, 9, 12)
    assert gregorian_to_hebrew(date(2026, 9, 12)) == (5787, 7, 1)


def test_sukkot_5787_in_israel():
    assert day_info(date(2026, 9, 26)).is_yom_tov  # א' סוכות, גם שבת
    assert day_info(date(2026, 9, 26)).is_shabbat
    assert day_info(date(2026, 9, 29)).is_chol_hamoed
    assert not day_info(date(2026, 9, 29)).is_yom_tov
    assert day_info(date(2026, 10, 3)).is_yom_tov  # שמיני עצרת
    assert not day_info(date(2026, 10, 4)).is_yom_tov  # אין יום טוב שני בארץ


def test_jerusalem_sunset_and_candle_lighting_are_plausible():
    cal = JewishCalendar(JERUSALEM, TZ)
    friday = date(2026, 11, 27)
    candles = to_local(cal.candle_lighting(friday), TZ)
    assert time(15, 45) <= candles.time() <= time(16, 10), candles
    night = to_local(cal.nightfall(friday + timedelta(days=1)), TZ)
    assert time(16, 35) <= night.time() <= time(17, 25), night


def test_shabbat_block_includes_buffer_and_ends_after_nightfall():
    cal = JewishCalendar(JERUSALEM, TZ, buffer_minutes=180)
    friday = date(2026, 11, 27)
    blocks = cal.blocked_intervals(friday - timedelta(days=1), friday + timedelta(days=2))
    assert len(blocks) == 1
    block = blocks[0]
    assert block.start == cal.candle_lighting(friday) - timedelta(minutes=180)
    assert block.end == cal.nightfall(friday + timedelta(days=1))


def test_sukkot_is_one_continuous_block_when_chol_hamoed_blocked():
    cal = JewishCalendar(JERUSALEM, TZ, buffer_minutes=180, block_chol_hamoed=True)
    blocks = cal.blocked_intervals(date(2026, 9, 24), date(2026, 10, 5))
    covering = [b for b in blocks if b.start <= local_datetime(date(2026, 9, 29), time(12), TZ) < b.end]
    assert covering
    whole = covering[0]
    assert whole.start <= cal.candle_lighting(date(2026, 9, 25)) - timedelta(minutes=180)
    assert whole.end >= cal.nightfall(date(2026, 10, 3))


def test_chol_hamoed_free_when_not_blocked():
    cal = JewishCalendar(JERUSALEM, TZ, block_chol_hamoed=False)
    blocks = cal.blocked_intervals(date(2026, 9, 24), date(2026, 10, 5))
    noon = local_datetime(date(2026, 9, 29), time(12), TZ)
    assert not any(b.start <= noon < b.end for b in blocks)
    probe = Interval(noon, noon + timedelta(hours=1))
    assert not any(b.overlaps(probe) for b in blocks)
