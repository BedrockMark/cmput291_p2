"""Database access helpers: connection, collection, and shared query pieces.

Timestamp convention (spec "Shared conventions"):
    * Stored timestamps are fixed-width UTC strings "YYYY-MM-DDTHH:MM:SSZ".
      Their lexical order is chronological, so range filters compare strings
      directly; we never convert them to BSON dates or local time.
    * A calendar day D is the half-open string range
      ["DT00:00:00Z", "<D+1>T00:00:00Z").
"""

import re
from datetime import datetime, timedelta, timezone

from pymongo import MongoClient

DB_NAME = "291db_workshops"
COLLECTION_NAME = "workshops"

ACTIVE = "active"  # the only workshop status visible to any operation

TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
DATE_FORMAT = "%Y-%m-%d"

CONNECT_TIMEOUT_MS = 3000  # fail fast with a clear message if mongod is down


def connect(port, host="localhost", timeout_ms=CONNECT_TIMEOUT_MS):
    """Return a MongoClient connected to the local server on `port`.

    MongoClient connects lazily, so we send a `ping` to surface a connection
    failure immediately. Raises pymongo.errors.PyMongoError (typically
    ServerSelectionTimeoutError) if the server cannot be reached.
    """
    client = MongoClient(host, port, serverSelectionTimeoutMS=timeout_ms)
    try:
        client.admin.command("ping")
    except Exception:
        client.close()
        raise
    return client


def get_database(client, name=DB_NAME):
    """Return the project database (291db_workshops by default)."""
    return client[name]


def get_collection(client, db_name=DB_NAME, name=COLLECTION_NAME):
    """Return the workshops collection (291db_workshops.workshops by default)."""
    return client[db_name][name]


def literal_regex(text):
    """$regex condition: case-insensitive *literal substring* match of `text`.

    re.escape makes every punctuation character literal, so "C++" matches
    "C++" and "a.b" does not match "axb".
    """
    return {"$regex": re.escape(text), "$options": "i"}


def exact_ci_regex(text):
    """$regex condition: case-insensitive match of the *entire* value `text`."""
    return {"$regex": f"^{re.escape(text)}$", "$options": "i"}


def active_filter(**conditions):
    """Query filter for active workshops, plus any extra field conditions."""
    return {"status": ACTIVE, **conditions}


def utc_day_bounds(day):
    """Return (start, end) timestamp strings for UTC calendar day `day`.

    `day` is a datetime.date. Use as {"$gte": start, "$lt": end}: midnight at
    the start of `day` is included, midnight of the next day is excluded.
    date.isoformat() always gives a zero-padded 4-digit year, so the bounds
    compare correctly with the stored fixed-width strings.
    """
    start = f"{day.isoformat()}T00:00:00Z"
    try:
        end = f"{(day + timedelta(days=1)).isoformat()}T00:00:00Z"
    except OverflowError:  # 9999-12-31 has no next day; "T24" sorts after T23:59:59
        end = f"{day.isoformat()}T24:00:00Z"
    return start, end


def format_timestamp(moment):
    """Format an aware or naive-UTC datetime as "YYYY-MM-DDTHH:MM:SSZ"."""
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc)
    return moment.strftime(TIMESTAMP_FORMAT)


def now_utc_str():
    """Current UTC time as a stored-format timestamp string (for created_at)."""
    return format_timestamp(datetime.now(timezone.utc))
