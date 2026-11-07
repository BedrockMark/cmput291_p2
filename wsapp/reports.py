"""Operations 3-4: popular tags for a date and top-rated workshops.

Both are aggregation pipelines that group, count/average, sort and limit in
MongoDB, and return at most n (<= 20) rows, so returning a list is fine.
"""

from . import db


def popular_tags(coll, day, n):
    """Operation 3: the n most common tags among workshops active on `day`.

    A workshop qualifies if it is active and has at least one session that
    starts on UTC day `day` (db.utc_day_bounds) with seats_remaining >= 1.
    Both conditions must hold for the same session ($elemMatch).
    Each qualifying workshop counts once per tag, even with several
    qualifying sessions (tags are unique within a workshop, so unwinding
    `tags` -- not `sessions` -- gives one row per (workshop, tag)).
    Workshops with no tags contribute nothing.

    Parameters
        coll  the workshops collection
        day   datetime.date
        n     int in 1..20

    Returns a list of at most n dicts {"tag": str, "count": int}, ordered by
    count descending, then tag ascending. Extra ties beyond n are cut off.
    """
    raise NotImplementedError("popular_tags")


def top_rated(coll, min_reviews, n):
    """Operation 4: active workshops with >= min_reviews reviews, best average first.

    Workshops with no reviews never qualify (min_reviews is >= 1). Review
    timestamps and session dates are ignored.

    Parameters
        coll         the workshops collection
        min_reviews  positive int
        n            int in 1..20

    Returns a list of at most n dicts:
        {"_id": str, "title": str, "review_count": int, "avg_rating": float}
    ordered by the UNROUNDED avg_rating descending, review_count descending,
    _id ascending. Rounding to two decimals happens only when displaying
    (ui.fmt_average).

    Hints: $match active, $addFields review_count = {$size: "$reviews"},
    $match review_count >= min_reviews, avg_rating = {$avg: "$reviews.rating"},
    $sort, $limit n, $project.
    """
    raise NotImplementedError("top_rated")
