"""Operations 3-4: popular tags for a date and top-rated workshops.

Both are aggregation pipelines that group, count/average, sort and limit in
MongoDB, and return at most n (<= 20) rows, so returning a list is fine.
"""

from . import db


def popular_tags(coll, date, n):
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
        date   datetime.date
        n     int in 1..20

    Returns a list of at most n dicts {"tag": str, "count": int}, ordered by
    count descending, then tag ascending. Extra ties beyond n are cut off.
    """
    start, end = db.utc_day_bounds(date)
    
    pipeline = [
        {
            "$match":{
                "status": db.ACTIVE,
                "sessions":{
                    "$elemMatch":{
                        "starts_at": {"$gte": start, "$lt":end},
                        "seats_remaining": {"$gte": 1}
                    }
                }
            }
        },
        {
            "$unwind": "$tags"
        },
        {"$group": {"_id": "$tags", "count": {"$sum": 1}}},
        {"$sort": {"count": -1, "_id": 1}},
        {"$limit": n},
        {"$project": {"_id": 0, "tag": "$_id", "count": 1}}
    ]
    
    return coll.aggregate(pipeline)


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
    """
    pipeline = [
        {"$match":{"status": db.ACTIVE}},
        {"$unwind": "$reviews"},
        {"$group": {"_id": "$_id", "title": {"$first": "$title"}, "review_count": {"$sum": 1}, "avg_rating":{"$avg":"$reviews.rating"}}},
        {"$match": {"review_count": {"$gte": min_reviews}}},
        {"$sort": {"avg_rating": -1, "review_count": -1, "_id": 1}},
        {"$limit": n},
        {"$project": {"_id": 1, "title": 1, "review_count": 1, "avg_rating": 1}}
    ]
    
    return list(coll.aggregate(pipeline))
