"""Operations 5-6: seat reservation and adding a review (writes).

Update discipline:
    * Each operation is exactly ONE update_one call whose filter contains
      every precondition (active workshop, existing session, enough seats),
      so the check and the change are atomic on the server. There is never
      a separate "read, then decide, then write" step.
    * upsert is never used: an unknown ID must not create anything.
"""

import uuid

from . import db


def new_review(reviewer, rating, comment):
    """Build the embedded review document for a new review.

    review_id is a fresh UUID string; created_at is the current UTC time in
    the stored "YYYY-MM-DDTHH:MM:SSZ" format. Inputs must already be
    validated (trimmed name 1-80 chars, rating 1-5, trimmed comment 1-500).
    """
    return {
        "review_id": str(uuid.uuid4()),
        "reviewer": reviewer,
        "rating": rating,
        "comment": comment,
        "created_at": db.now_utc_str(),
    }


def reserve_seats(coll, workshop_id, session_id, seats):
    """Operation 5: atomically take `seats` seats from one session.

    Parameters
        coll         the workshops collection
        workshop_id  exact, case-sensitive, already-trimmed workshop _id
        session_id   exact, case-sensitive, already-trimmed session_id
        seats        positive int (validated by the caller)

    Decrements sessions.$.seats_remaining by `seats` only if the workshop is
    active AND that session exists AND it has seats_remaining >= seats.
    capacity and all other sessions are unchanged.

    Returns True if a session was updated, False otherwise (unknown/inactive
    workshop, unknown session, or not enough seats).

    Hints: update_one(
        db.active_filter(_id=..., sessions={"$elemMatch": {session_id, seats_remaining >= seats}}),
        {"$inc": {"sessions.$.seats_remaining": -seats}})
    and check result.modified_count.
    """
    raise NotImplementedError("reserve_seats")


def add_review(coll, workshop_id, reviewer, rating, comment):
    """Operation 6: append a new review to an existing active workshop.

    Parameters
        coll         the workshops collection
        workshop_id  exact, case-sensitive, already-trimmed workshop _id
        reviewer     validated display name (1-80 chars, trimmed)
        rating       validated int in 1..5
        comment      validated comment (1-500 chars, trimmed)

    Uses new_review(...) to build the review and $push to append it, so all
    existing reviews and other fields are preserved and an empty reviews
    array accepts its first review.

    Returns the new review_id (str) on success, or None if no active
    workshop has that _id.
    """
    raise NotImplementedError("add_review")
