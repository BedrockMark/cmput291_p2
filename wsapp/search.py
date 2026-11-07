"""Operations 1-2: keyword search and available sessions (read-only).

Both functions return a pymongo cursor; ui.paginate consumes it 10 rows at a
time. Sorting must happen inside MongoDB (cursor.sort or an aggregation
$sort stage), never in Python.
"""

from . import db


def search_workshops(coll, keyword, category=None):
    """Operation 1: active workshops whose title OR description contains `keyword`.

    Parameters
        coll      the workshops collection
        keyword   nonempty, already-trimmed text; matched as a literal,
                  case-insensitive substring (use db.literal_regex), NOT as
                  a regular expression or a list of words
        category  None for "any category", otherwise an already-lowercased
                  string that must equal `category` exactly; an unknown
                  category simply yields no results

    Returns a cursor of documents with (at least) these fields:
        _id, title, category, venue.city, price_cents
    sorted by title ascending, then _id ascending.

    Hints: find() with db.active_filter(...), "$or" over title/description,
    a projection, and .sort([("title", 1), ("_id", 1)]).
    """
    raise NotImplementedError("search_workshops")


def available_sessions(coll, city, day, seats):
    """Operation 2: one row per qualifying session of an active workshop.

    Parameters
        coll   the workshops collection
        city   already-trimmed city name; the ENTIRE venue.city must match,
               ignoring case (use db.exact_ci_regex)
        day    datetime.date; the session's starts_at must fall on this UTC
               day (use db.utc_day_bounds: start inclusive, end exclusive)
        seats  positive int; the session's seats_remaining must be >= seats

    The date and seat conditions must hold for the SAME session: unwind the
    sessions array and filter the unwound session, rather than matching the
    workshop with two independent array conditions. Empty sessions arrays
    produce no rows.

    Returns a (command) cursor of flat documents:
        workshop_id, title, session_id, starts_at, seats_remaining,
        price_cents
    sorted by starts_at, workshop_id, session_id (all ascending).

    Hints: aggregate([$match (active + city + $elemMatch to use indexes),
    $unwind "$sessions", $match on the unwound session, $project, $sort]).
    """
    raise NotImplementedError("available_sessions")
