"""Integration tests for the loader and the six operations.

These need a running MongoDB server. They use a SEPARATE database
(291db_workshops_test) so the real 291db_workshops data is never touched.
The port defaults to 27017; override with the MONGO_PORT environment
variable. If no server is reachable, the whole module is skipped.

Two kinds of fixtures are used:
    * small hand-built documents (workshop()/session()/review()) that
      isolate one rule per test;
    * the course's datas/workshops-small.jsonl edge-case file
      (SmallFixtureTests), whose expected answers were worked out by hand
      from the file. Skipped if the file is missing.

Run from the repo root:  python3 -m unittest discover tests
"""

import io
import json
import os
import unittest
from datetime import date
from pathlib import Path

from pymongo.errors import PyMongoError

from test_helpers import load_loader_module
from wsapp import db, reports, search, updates

TEST_DB = "291db_workshops_test"
PORT = int(os.environ.get("MONGO_PORT", "27017"))

DATA_DIR = Path(__file__).resolve().parent.parent / "datas"
SMALL_FILE = DATA_DIR / "workshops-small.jsonl"
MANIFEST_FILE = DATA_DIR / "manifest.json"

NO_ROOM = object()  # sentinel: omit venue.room entirely (it is optional)


# --------------------------------------------------------------------------
# Fixture builders
# --------------------------------------------------------------------------


def session(session_id, starts_at, seats_remaining=5, capacity=10):
    return {"session_id": session_id, "starts_at": starts_at,
            "capacity": capacity, "seats_remaining": seats_remaining}


def review(review_id, rating):
    return {"review_id": review_id, "reviewer": "Tester", "rating": rating,
            "comment": "ok", "created_at": "2026-10-01T12:00:00Z"}


def workshop(_id, title="Workshop", description="", category="computing",
             status="active", city="Edmonton", price_cents=1500,
             tags=(), sessions=(), reviews=(), room=None):
    """Build a schema-valid workshop. room may be a string, None, or NO_ROOM."""
    venue = {"city": city, "building": "Hall"}
    if room is not NO_ROOM:
        venue["room"] = room
    return {
        "_id": _id, "title": title, "description": description,
        "category": category, "status": status,
        "organizer": {"organizer_id": "O1", "name": "Org"},
        "venue": venue,
        "price_cents": price_cents, "tags": list(tags),
        "sessions": list(sessions), "reviews": list(reviews),
    }


class MongoTestCase(unittest.TestCase):
    """Gives each test a fresh, empty test collection in self.coll."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.client = db.connect(PORT, timeout_ms=1000)
        except PyMongoError as err:
            raise unittest.SkipTest(f"MongoDB not reachable on port {PORT}: {err}")

    @classmethod
    def tearDownClass(cls):
        cls.client.drop_database(TEST_DB)
        cls.client.close()

    def setUp(self):
        self.coll = db.get_collection(self.client, db_name=TEST_DB)
        self.coll.drop()

    def insert(self, *docs):
        self.coll.insert_many(list(docs))


# --------------------------------------------------------------------------
# Phase 1
# --------------------------------------------------------------------------


class LoaderTests(MongoTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.loader = load_loader_module()

    def test_replaces_collection_and_keeps_string_ids(self):
        self.insert(workshop("OLD"))
        lines = io.StringIO('{"_id": "W1", "starts": "2026-11-01T00:00:00Z"}\n\n'
                            '{"_id": "W2"}\n')
        self.assertEqual(self.loader.load_workshops(self.coll, lines), 2)
        self.assertEqual(sorted(d["_id"] for d in self.coll.find()), ["W1", "W2"])
        self.assertEqual(self.coll.find_one({"_id": "W1"})["starts"], "2026-11-01T00:00:00Z")

    def test_empty_file_gives_empty_collection(self):
        self.insert(workshop("OLD"))
        self.assertEqual(self.loader.load_workshops(self.coll, io.StringIO("\n")), 0)
        self.assertEqual(self.coll.count_documents({}), 0)
        self.assertIn(self.coll.name, self.coll.database.list_collection_names())

    def test_small_batches(self):
        lines = io.StringIO("".join(f'{{"_id": "W{i}"}}\n' for i in range(7)))
        self.assertEqual(self.loader.load_workshops(self.coll, lines, batch_size=3), 7)

    def test_malformed_json_raises(self):
        with self.assertRaises(self.loader.LoadError):
            self.loader.load_workshops(self.coll, io.StringIO('{"_id": "W1"}\n{oops\n'))

    @unittest.skipUnless(SMALL_FILE.exists(), "datas/workshops-small.jsonl not found")
    def test_small_file_count_matches_manifest(self):
        manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
        expected = next(f["documents"] for f in manifest["files"]
                        if f["file"] == SMALL_FILE.name)
        with open(SMALL_FILE, encoding="utf-8") as lines:
            self.assertEqual(self.loader.load_workshops(self.coll, lines), expected)
        # optional venue.room: absent in W00007, null in W00006 -- stored as-is
        self.assertNotIn("room", self.coll.find_one({"_id": "W00007"})["venue"])
        self.assertIsNone(self.coll.find_one({"_id": "W00006"})["venue"]["room"])

    def test_duplicate_id_raises(self):
        with self.assertRaises(self.loader.LoadError):
            self.loader.load_workshops(self.coll, io.StringIO('{"_id": "W1"}\n{"_id": "W1"}\n'))


# --------------------------------------------------------------------------
# Operation 1
# --------------------------------------------------------------------------


class SearchWorkshopsTests(MongoTestCase):
    def ids(self, keyword, category=None):
        return [d["_id"] for d in search.search_workshops(self.coll, keyword, category)]

    def test_literal_punctuation(self):
        self.insert(workshop("W1", title="Intro to C++"),
                    workshop("W2", title="axb tricks"),
                    workshop("W3", title="a.b notes"),
                    workshop("W4", title="C programming"))
        self.assertEqual(self.ids("C++"), ["W1"])
        self.assertEqual(self.ids("a.b"), ["W3"])

    def test_case_insensitive_title_or_description(self):
        self.insert(workshop("W1", title="Technology Night"),
                    workshop("W2", title="Lab", description="Basic biotechnology"),
                    workshop("W3", title="Pottery"))
        self.assertEqual(self.ids("tech"), ["W2", "W1"])  # "Lab" < "Technology Night"

    def test_category_filter_and_unknown_category(self):
        self.insert(workshop("W1", title="Bread", category="cooking"),
                    workshop("W2", title="Bread code", category="computing"))
        self.assertEqual(self.ids("bread", "cooking"), ["W1"])
        self.assertEqual(self.ids("bread", "cook"), [])

    def test_only_active_and_sorted_by_title_then_id(self):
        self.insert(workshop("W3", title="Yoga"),
                    workshop("W2", title="Yoga"),
                    workshop("W1", title="Advanced yoga"),
                    workshop("W0", title="Yoga", status="cancelled"))
        self.assertEqual(self.ids("yoga"), ["W1", "W2", "W3"])

    def test_returns_display_fields(self):
        self.insert(workshop("W1", title="Knitting", city="Calgary", price_cents=0))
        doc = next(iter(search.search_workshops(self.coll, "knit")))
        self.assertEqual((doc["title"], doc["category"], doc["venue"]["city"],
                          doc["price_cents"]), ("Knitting", "computing", "Calgary", 0))

    def test_no_results_and_empty_collection(self):
        self.assertEqual(self.ids("anything"), [])


# --------------------------------------------------------------------------
# Operation 2
# --------------------------------------------------------------------------


class AvailableSessionsTests(MongoTestCase):
    DAY = date(2026, 11, 1)

    def rows(self, city="Edmonton", day=DAY, seats=1):
        return [(r["workshop_id"], r["session_id"])
                for r in search.available_sessions(self.coll, city, day, seats)]

    def test_utc_day_boundaries(self):
        self.insert(workshop("W1", sessions=[
            session("before", "2026-10-31T23:59:59Z"),
            session("start", "2026-11-01T00:00:00Z"),
            session("late", "2026-11-01T23:59:59Z"),
            session("next", "2026-11-02T00:00:00Z"),
        ]))
        self.assertEqual(self.rows(), [("W1", "start"), ("W1", "late")])

    def test_date_and_seats_from_same_session(self):
        self.insert(workshop("W1", sessions=[
            session("S1", "2026-11-01T10:00:00Z", seats_remaining=1),
            session("S2", "2026-11-05T10:00:00Z", seats_remaining=9),
        ]))
        self.assertEqual(self.rows(seats=5), [])

    def test_one_row_per_session_sorted(self):
        self.insert(
            workshop("W2", sessions=[session("S9", "2026-11-01T09:00:00Z"),
                                     session("S1", "2026-11-01T09:00:00Z")]),
            workshop("W1", sessions=[session("S5", "2026-11-01T09:00:00Z"),
                                     session("S0", "2026-11-01T08:00:00Z")]),
        )
        self.assertEqual(self.rows(), [("W1", "S0"), ("W1", "S5"),
                                       ("W2", "S1"), ("W2", "S9")])

    def test_city_whole_name_case_insensitive(self):
        self.insert(workshop("W1", city="St. Albert",
                             sessions=[session("S1", "2026-11-01T10:00:00Z")]))
        self.assertEqual(self.rows(city="st. albert"), [("W1", "S1")])
        self.assertEqual(self.rows(city="St"), [])
        self.assertEqual(self.rows(city="StX Albert"), [])

    def test_excludes_cancelled_full_and_empty_sessions(self):
        self.insert(
            workshop("W1", status="cancelled", sessions=[session("S1", "2026-11-01T10:00:00Z")]),
            workshop("W2", sessions=[session("S1", "2026-11-01T10:00:00Z", seats_remaining=0)]),
            workshop("W3", sessions=[]),
        )
        self.assertEqual(self.rows(), [])

    def test_row_fields(self):
        self.insert(workshop("W1", title="T", price_cents=250,
                             sessions=[session("S1", "2026-11-01T10:00:00Z", seats_remaining=3)]))
        row = next(iter(search.available_sessions(self.coll, "edmonton", self.DAY, 3)))
        self.assertEqual({k: row[k] for k in ("workshop_id", "title", "session_id",
                                              "starts_at", "seats_remaining", "price_cents")},
                         {"workshop_id": "W1", "title": "T", "session_id": "S1",
                          "starts_at": "2026-11-01T10:00:00Z", "seats_remaining": 3,
                          "price_cents": 250})


# --------------------------------------------------------------------------
# Operation 3
# --------------------------------------------------------------------------


class PopularTagsTests(MongoTestCase):
    DAY = date(2026, 11, 1)
    ON_DAY = "2026-11-01T10:00:00Z"

    def tags(self, n=20):
        return [(r["tag"], r["count"]) for r in reports.popular_tags(self.coll, self.DAY, n)]

    def test_counts_workshop_once_per_tag(self):
        self.insert(workshop("W1", tags=["art"], sessions=[session("S1", self.ON_DAY),
                                                           session("S2", self.ON_DAY)]))
        self.assertEqual(self.tags(), [("art", 1)])

    def test_order_ties_and_limit(self):
        self.insert(
            workshop("W1", tags=["b", "a", "c"], sessions=[session("S1", self.ON_DAY)]),
            workshop("W2", tags=["b", "c"], sessions=[session("S1", self.ON_DAY)]),
            workshop("W3", tags=["c"], sessions=[session("S1", self.ON_DAY)]),
        )
        self.assertEqual(self.tags(), [("c", 3), ("b", 2), ("a", 1)])
        self.assertEqual(self.tags(n=2), [("c", 3), ("b", 2)])

    def test_alphabetical_tie_break_cuts_extra_ties(self):
        self.insert(workshop("W1", tags=["z", "m", "a"], sessions=[session("S1", self.ON_DAY)]))
        self.assertEqual(self.tags(n=2), [("a", 1), ("m", 1)])

    def test_excludes_non_qualifying_workshops(self):
        self.insert(
            workshop("W1", tags=["full"], sessions=[session("S1", self.ON_DAY, seats_remaining=0)]),
            workshop("W2", tags=["other-day"], sessions=[session("S1", "2026-11-02T00:00:00Z")]),
            workshop("W3", tags=["cancelled"], status="cancelled",
                     sessions=[session("S1", self.ON_DAY)]),
            workshop("W4", tags=[], sessions=[session("S1", self.ON_DAY)]),
            # seats on another day must not combine with a full session today
            workshop("W5", tags=["mixed"], sessions=[
                session("S1", self.ON_DAY, seats_remaining=0),
                session("S2", "2026-11-03T10:00:00Z", seats_remaining=5)]),
        )
        self.assertEqual(self.tags(), [])


# --------------------------------------------------------------------------
# Operation 4
# --------------------------------------------------------------------------


class TopRatedTests(MongoTestCase):
    def top(self, min_reviews=1, n=20):
        return [(r["_id"], r["review_count"], r["avg_rating"])
                for r in reports.top_rated(self.coll, min_reviews, n)]

    def test_order_avg_then_count_then_id(self):
        self.insert(
            workshop("W3", reviews=[review("R1", 5), review("R2", 4)]),   # 4.5, 2
            workshop("W2", reviews=[review("R1", 5), review("R2", 4)]),   # 4.5, 2
            workshop("W1", reviews=[review("R1", 4), review("R2", 5),
                                    review("R3", 5), review("R4", 4)]),   # 4.5, 4
            workshop("W4", reviews=[review("R1", 5)]),                    # 5.0, 1
        )
        self.assertEqual(self.top(), [("W4", 1, 5.0), ("W1", 4, 4.5),
                                      ("W2", 2, 4.5), ("W3", 2, 4.5)])
        self.assertEqual([r[0] for r in self.top(n=2)], ["W4", "W1"])

    def test_min_reviews_and_exclusions(self):
        self.insert(
            workshop("W1", reviews=[]),
            workshop("W2", reviews=[review("R1", 3)]),
            workshop("W3", reviews=[review("R1", 2), review("R2", 3)]),
            workshop("W4", status="cancelled", reviews=[review("R1", 5), review("R2", 5)]),
        )
        self.assertEqual(self.top(min_reviews=2), [("W3", 2, 2.5)])
        self.assertEqual(self.top(min_reviews=3), [])

    def test_unrounded_average_used_for_ranking(self):
        self.insert(
            workshop("W1", reviews=[review("R1", 5), review("R2", 4), review("R3", 4)]),  # 4.333
            workshop("W2", reviews=[review(f"R{i}", r) for i, r in
                                    enumerate([5, 5, 4, 4, 4, 4], start=1)]),          # 4.333
        )
        # equal averages -> more reviews first
        self.assertEqual([r[0] for r in self.top()], ["W2", "W1"])


# --------------------------------------------------------------------------
# Operation 5
# --------------------------------------------------------------------------


class ReserveSeatsTests(MongoTestCase):
    def setUp(self):
        super().setUp()
        self.insert(
            workshop("W1", sessions=[session("S1", "2026-11-01T10:00:00Z", seats_remaining=3),
                                     session("S2", "2026-11-02T10:00:00Z", seats_remaining=5)]),
            workshop("W2", status="cancelled",
                     sessions=[session("S1", "2026-11-01T10:00:00Z", seats_remaining=3)]),
        )

    def sessions(self, workshop_id="W1"):
        return {s["session_id"]: (s["seats_remaining"], s["capacity"])
                for s in self.coll.find_one({"_id": workshop_id})["sessions"]}

    def test_reserve_only_target_session(self):
        self.assertTrue(updates.reserve_seats(self.coll, "W1", "S1", 2))
        self.assertEqual(self.sessions(), {"S1": (1, 10), "S2": (5, 10)})

    def test_last_seats_then_insufficient(self):
        self.assertTrue(updates.reserve_seats(self.coll, "W1", "S1", 3))
        self.assertFalse(updates.reserve_seats(self.coll, "W1", "S1", 1))
        self.assertEqual(self.sessions()["S1"], (0, 10))

    def test_insufficient_seats_changes_nothing(self):
        self.assertFalse(updates.reserve_seats(self.coll, "W1", "S1", 4))
        self.assertEqual(self.sessions(), {"S1": (3, 10), "S2": (5, 10)})

    def test_unknown_ids_and_cancelled(self):
        self.assertFalse(updates.reserve_seats(self.coll, "W9", "S1", 1))
        self.assertFalse(updates.reserve_seats(self.coll, "W1", "S9", 1))
        self.assertFalse(updates.reserve_seats(self.coll, "w1", "S1", 1))  # case-sensitive
        self.assertFalse(updates.reserve_seats(self.coll, "W2", "S1", 1))
        self.assertEqual(self.coll.count_documents({}), 2)
        self.assertEqual(self.sessions("W2")["S1"], (3, 10))


# --------------------------------------------------------------------------
# Operation 6
# --------------------------------------------------------------------------


class AddReviewTests(MongoTestCase):
    def test_first_review_on_empty_array_affects_top_rated(self):
        self.insert(workshop("W1", reviews=[]))
        self.assertEqual(reports.top_rated(self.coll, 1, 5), [])
        review_id = updates.add_review(self.coll, "W1", "Ann", 4, "Great")
        self.assertIsInstance(review_id, str)
        stored = self.coll.find_one({"_id": "W1"})["reviews"]
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["review_id"], review_id)
        self.assertRegex(stored[0]["created_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertEqual([r["_id"] for r in reports.top_rated(self.coll, 1, 5)], ["W1"])

    def test_preserves_existing_reviews(self):
        self.insert(workshop("W1", reviews=[review("R1", 2)]))
        updates.add_review(self.coll, "W1", "Ann", 5, "Nice")
        self.assertEqual([r["rating"] for r in self.coll.find_one({"_id": "W1"})["reviews"]],
                         [2, 5])

    def test_unknown_or_cancelled_workshop(self):
        self.insert(workshop("W2", status="cancelled"))
        self.assertIsNone(updates.add_review(self.coll, "W9", "Ann", 5, "x"))
        self.assertIsNone(updates.add_review(self.coll, "W2", "Ann", 5, "x"))
        self.assertEqual(self.coll.find_one({"_id": "W2"})["reviews"], [])
        self.assertEqual(self.coll.count_documents({}), 1)



# --------------------------------------------------------------------------
# Course edge-case file: datas/workshops-small.jsonl (24 workshops)
# --------------------------------------------------------------------------


@unittest.skipUnless(SMALL_FILE.exists(), "datas/workshops-small.jsonl not found")
class SmallFixtureTests(MongoTestCase):
    """End-to-end answers on the supplied edge-case file, reloaded per test.

    Relevant traits of the file: W00003/W00021 cancelled; W00004 has no
    sessions; W00006 has no tags; W00001-1 and W00005-1 are full;
    W00002-1 starts at midnight, W00018-1 at 2026-10-31T23:59:59Z,
    W00019-1 at 2026-11-01T23:59:59Z; W00007 has two sessions on the same
    day; W00008 is "C++: Practical Patterns" with "a.b" in its description;
    W00009/W00010 share the title "Bread Baking"; W00012-W00017 all average
    5.0 over 3 reviews; W00022-W00024 have single tags zebra/alpha/omega.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.loader = load_loader_module()

    def setUp(self):
        super().setUp()
        with open(SMALL_FILE, encoding="utf-8") as lines:
            for _, _, docs in self.loader.iter_batches(lines):
                self.coll.insert_many(docs)

    def search_ids(self, keyword, category=None):
        return [d["_id"] for d in search.search_workshops(self.coll, keyword, category)]

    def session_rows(self, city, day, seats):
        return [(r["workshop_id"], r["session_id"])
                for r in search.available_sessions(self.coll, city, day, seats)]

    # operation 1
    def test_search_punctuation(self):
        self.assertEqual(self.search_ids("C++"), ["W00008"])
        self.assertEqual(self.search_ids("a.b"), ["W00008"])
        self.assertEqual(self.search_ids("a*b"), [])

    def test_search_same_title_and_cancelled(self):
        self.assertEqual(self.search_ids("bread"), ["W00009", "W00010", "W00015"])
        self.assertEqual(self.search_ids("BREAD", "cooking"), ["W00009", "W00015"])
        self.assertEqual(self.search_ids("bread", "baking"), [])

    def test_search_pagination_size(self):
        # 23 of 24 share one description; 21 of them are active -> 3 pages
        self.assertEqual(len(self.search_ids("friendly")), 21)

    # operation 2
    def test_sessions_midnight_and_full_sessions(self):
        self.assertEqual(self.session_rows("edmonton", date(2026, 11, 1), 1),
                         [("W00002", "S00002-1"), ("W00009", "S00009-1"),
                          ("W00013", "S00013-1"), ("W00017", "S00017-1")])

    def test_sessions_seats_not_borrowed_from_other_day(self):
        # W00001-2 has 8 seats but is on 2026-11-02; W00002-1 has only 3
        self.assertEqual(self.session_rows("Edmonton", date(2026, 11, 1), 4),
                         [("W00009", "S00009-1"), ("W00013", "S00013-1"),
                          ("W00017", "S00017-1")])

    def test_sessions_last_second_of_day(self):
        self.assertEqual(self.session_rows("CALGARY", date(2026, 10, 31), 1),
                         [("W00018", "S00018-1")])
        self.assertEqual(self.session_rows("Red Deer", date(2026, 11, 1), 1),
                         [("W00007", "S00007-1"), ("W00011", "S00011-1"),
                          ("W00015", "S00015-1"), ("W00023", "S00023-1"),
                          ("W00007", "S00007-2"), ("W00019", "S00019-1")])

    def test_sessions_unknown_city(self):
        self.assertEqual(self.session_rows("Vancouver", date(2026, 11, 1), 1), [])

    # operation 3
    def test_popular_tags(self):
        rows = [(r["tag"], r["count"])
                for r in reports.popular_tags(self.coll, date(2026, 11, 1), 20)]
        self.assertEqual(rows, [
            ("beginner", 8), ("coding", 3), ("creative", 3), ("social", 3),
            ("food", 2), ("hands-on", 2), ("nature", 2), ("sustainability", 2),
            ("alpha", 1), ("health", 1), ("omega", 1), ("zebra", 1),
        ])

    def test_popular_tags_cuts_ties_at_n(self):
        rows = [(r["tag"], r["count"])
                for r in reports.popular_tags(self.coll, date(2026, 11, 1), 3)]
        self.assertEqual(rows, [("beginner", 8), ("coding", 3), ("creative", 3)])

    def test_popular_tags_empty_day(self):
        self.assertEqual(reports.popular_tags(self.coll, date(2030, 1, 1), 5), [])

    # operation 4
    def test_top_rated_ties_by_id(self):
        rows = [(r["_id"], r["review_count"], r["avg_rating"])
                for r in reports.top_rated(self.coll, 3, 5)]
        self.assertEqual(rows, [(f"W000{i}", 3, 5.0) for i in range(12, 17)])

    def test_top_rated_count_breaks_average_tie(self):
        ids = [r["_id"] for r in reports.top_rated(self.coll, 1, 7)]
        self.assertEqual(ids, ["W00012", "W00013", "W00014", "W00015",
                               "W00016", "W00017", "W00005"])

    def test_top_rated_none_qualify(self):
        self.assertEqual(reports.top_rated(self.coll, 4, 5), [])

    # operation 5
    def test_reserve_on_fixture(self):
        self.assertFalse(updates.reserve_seats(self.coll, "W00002", "S00002-1", 4))
        self.assertTrue(updates.reserve_seats(self.coll, "W00002", "S00002-1", 3))
        self.assertFalse(updates.reserve_seats(self.coll, "W00001", "S00001-1", 1))  # full
        self.assertFalse(updates.reserve_seats(self.coll, "W00003", "S00003-1", 1))  # cancelled
        self.assertFalse(updates.reserve_seats(self.coll, "W00004", "S00004-1", 1))  # no sessions
        sessions = self.coll.find_one({"_id": "W00002"})["sessions"]
        self.assertEqual([(s["seats_remaining"], s["capacity"]) for s in sessions],
                         [(0, 10), (9, 10)])

    # operation 6
    def test_review_on_fixture(self):
        self.assertIsNotNone(updates.add_review(self.coll, "W00004", "Ann", 5, "Fun"))
        self.assertIsNone(updates.add_review(self.coll, "W00003", "Ann", 5, "Fun"))
        # W00004 and W00011 now average 5.0 over 1 review, tying W00005;
        # equal average and count -> ordered by _id after the 3-review 5.0s.
        updates.add_review(self.coll, "W00011", "Ann", 5, "Fun")
        ids = [r["_id"] for r in reports.top_rated(self.coll, 1, 9)]
        self.assertEqual(ids[-3:], ["W00004", "W00005", "W00011"])

if __name__ == "__main__":
    unittest.main()
