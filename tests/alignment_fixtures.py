"""SYNTHETIC interval-alignment fixtures (Stage 22): not ERCOT data, not evidence of ERCOT behavior.

Every label below was written by hand to exercise one diagnostic case. Document ids start with
"SYN-" and publish times are fixed strings, so nothing here can be mistaken for a download.
"""

from mambo_explorer.ercot.alignment import DamHour, DamObservation, RtInterval, RtObservation

DAY = "01/15/2030"  # synthetic date, chosen to be outside any downloaded file
SPRING = "03/10/2030"  # synthetic dates standing in for transition days (labels only)
FALL = "11/03/2030"
PUB = "2030-01-14T12:30:00-06:00"


def dam(hour="05:00", flag="N", day=DAY, point="HB_NORTH", typ="hub", rev=1, present=True):
    return DamObservation(DamHour(day, hour, point, typ, flag), rev, f"SYN-DAM-{rev}", PUB, present)


def rt(
    hour="5",
    interval="1",
    flag="N",
    day=DAY,
    point="HB_NORTH",
    typ="HU",
    rev=1,
    present=True,
    doc=None,
):
    return RtObservation(
        RtInterval(day, hour, interval, point, typ, flag),
        rev,
        doc or f"SYN-RT-{hour}-{interval}-{flag}-{rev}",
        PUB,
        present,
    )


def hour_of(hour="5", flag="N", day=DAY, intervals=("1", "2", "3", "4"), **kw):
    return [rt(hour, i, flag, day, **kw) for i in intervals]


# Named cases (section 10 of the Stage 22 prompt).
ORDINARY = (dam(), hour_of())
MISSING_ONE = (dam(), hour_of(intervals=("1", "2", "4")))
DUPLICATE = (dam(), hour_of() + [rt("5", "3", doc="SYN-RT-dup")])
CONFLICTING_REVISIONS = (dam(), hour_of() + [rt("5", "2", rev=2)])
MISMATCHED_TYPE = (dam(), hour_of(typ="LZ"))
MISMATCHED_POINT = (dam(), hour_of(point="HB_SOUTH"))
MISMATCHED_DATE = (dam(), hour_of(day="01/16/2030"))
HOUR_24 = (dam("24:00"), hour_of("24"))
SPRING_MISSING_HOUR = (dam("03:00", day=SPRING), [])  # a day-ahead label with no real-time hour
SPRING_NEIGHBOURS = (dam("04:00", day=SPRING), hour_of("4", day=SPRING))
FALL_REPEATED_N = (
    dam("02:00", "N", day=FALL),
    hour_of("2", "N", day=FALL) + hour_of("2", "Y", day=FALL),
)
FALL_REPEATED_Y = (
    dam("02:00", "Y", day=FALL),
    hour_of("2", "N", day=FALL) + hour_of("2", "Y", day=FALL),
)
DIFFERENT_FLAGS = (dam("02:00", "N", day=FALL), hour_of("2", "Y", day=FALL))
UNKNOWN_FLAG = (dam(flag="X"), hour_of(flag="X"))
UNKNOWN_RT_FLAG = (dam(), hour_of(flag="?"))
MISSING_DAM_PRICE = (dam(present=False), hour_of())
MISSING_ALL_RT = (dam(), [])
BLANK_RT_PRICE = (dam(), hour_of()[:3] + [rt("5", "4", present=False)])
