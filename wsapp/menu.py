"""Console screens. Each screen handles I/O only and calls the logic modules.

Convention: pressing Enter on an empty line at any prompt cancels the
current operation and returns to the main menu.
"""

from pymongo.errors import PyMongoError

from . import reports, search, ui, updates, validation

RESERVATION_FAILED = "Reservation failed: unavailable workshop, session, or seats."

SEARCH_HEADINGS = ["Workshop ID", "Title", "Category", "City", "Price"]
SESSION_HEADINGS = ["Workshop ID", "Title", "Session ID", "Starts at (UTC)",
                    "Seats left", "Price"]
TAG_HEADINGS = ["Tag", "Workshops"]
TOP_RATED_HEADINGS = ["Workshop ID", "Title", "Reviews", "Avg rating"]


def main_menu(coll):
    """Show the main menu until the user chooses to exit."""
    screens = {
        "1": search_screen,
        "2": sessions_screen,
        "3": popular_tags_screen,
        "4": top_rated_screen,
        "5": reserve_screen,
        "6": review_screen,
    }
    while True:
        choice = ui.show_menu(
            "Community Workshops",
            [
                ("1", "Search workshops"),
                ("2", "Find available sessions"),
                ("3", "Most popular tags for a date"),
                ("4", "Top-rated workshops"),
                ("5", "Reserve seats"),
                ("6", "Add a review"),
                ("x", "Exit"),
            ],
        )
        if choice == "x":
            print("Goodbye.")
            return
        run_screen(screens[choice], coll)


def run_screen(screen, coll):
    """Run one screen; report database errors instead of crashing the app."""
    try:
        screen(coll)
    except NotImplementedError as err:
        print(f"Not implemented yet: {err}")
    except PyMongoError as err:
        print(f"Database error: {err}")


# --------------------------------------------------------------------------
# Row renderers (document -> list of cell strings)
# --------------------------------------------------------------------------


def render_workshop(doc):
    return [doc["_id"], doc["title"], doc["category"], doc["venue"]["city"],
            ui.fmt_price(doc["price_cents"])]


def render_session(doc):
    return [doc["workshop_id"], doc["title"], doc["session_id"], doc["starts_at"],
            str(doc["seats_remaining"]), ui.fmt_price(doc["price_cents"])]


def render_tag(doc):
    return [doc["tag"], str(doc["count"])]


def render_top_rated(doc):
    return [doc["_id"], doc["title"], str(doc["review_count"]),
            ui.fmt_average(doc["avg_rating"])]


# --------------------------------------------------------------------------
# Screens
# --------------------------------------------------------------------------


def search_screen(coll):
    """Operation 1: keyword (+ optional category) search, 10 per page."""
    keyword = ui.prompt("Keyword (empty to cancel): ")
    if not keyword:
        return
    category = validation.parse_category(ui.prompt(
        f"Category ({', '.join(validation.CATEGORIES)}; empty for any): "))
    ui.paginate(
        search.search_workshops(coll, keyword, category),
        render_workshop,
        title=f"Workshops matching '{keyword}'",
        headings=SEARCH_HEADINGS,
        empty_message="No active workshops match that keyword/category.",
    )


def sessions_screen(coll):
    """Operation 2: sessions in a city on a date with enough seats, 10 per page."""
    city = ui.prompt("City (empty to cancel): ")
    if not city:
        return
    day = ui.prompt_parsed("Date (YYYY-MM-DD): ", validation.parse_date)
    if day is None:
        return
    seats = ui.prompt_parsed("Number of seats: ", validation.parse_positive_int)
    if seats is None:
        return
    ui.paginate(
        search.available_sessions(coll, city, day, seats),
        render_session,
        title=f"Sessions in {city} on {day.isoformat()} with >= {seats} seats",
        headings=SESSION_HEADINGS,
        empty_message="No sessions match that city, date and seat count.",
    )


def popular_tags_screen(coll):
    """Operation 3: top n tags among workshops with open seats on a date."""
    day = ui.prompt_parsed("Date (YYYY-MM-DD, empty to cancel): ", validation.parse_date)
    if day is None:
        return
    n = ui.prompt_parsed("How many tags (1-20): ", validation.parse_top_n)
    if n is None:
        return
    ui.show_rows(
        reports.popular_tags(coll, day, n),
        render_tag,
        title=f"Most popular tags on {day.isoformat()}",
        headings=TAG_HEADINGS,
        empty_message="No active workshop has a session with open seats on that date.",
    )


def top_rated_screen(coll):
    """Operation 4: top n active workshops by average rating."""
    min_reviews = ui.prompt_parsed("Minimum number of reviews (empty to cancel): ",
                                   validation.parse_positive_int)
    if min_reviews is None:
        return
    n = ui.prompt_parsed("How many workshops (1-20): ", validation.parse_top_n)
    if n is None:
        return
    ui.show_rows(
        reports.top_rated(coll, min_reviews, n),
        render_top_rated,
        title=f"Top-rated workshops (>= {min_reviews} reviews)",
        headings=TOP_RATED_HEADINGS,
        empty_message="No active workshop has that many reviews.",
    )


def reserve_screen(coll):
    """Operation 5: atomically reserve seats in one session."""
    workshop_id = ui.prompt("Workshop ID (empty to cancel): ")
    if not workshop_id:
        return
    session_id = ui.prompt("Session ID: ")
    if not session_id:
        return
    seats = ui.prompt_parsed("Number of seats: ", validation.parse_positive_int)
    if seats is None:
        return
    if updates.reserve_seats(coll, workshop_id, session_id, seats):
        print(f"Reserved {seats} seat(s) in session {session_id} of workshop {workshop_id}.")
    else:
        print(RESERVATION_FAILED)


def review_screen(coll):
    """Operation 6: append a review to an active workshop."""
    workshop_id = ui.prompt("Workshop ID (empty to cancel): ")
    if not workshop_id:
        return
    reviewer = ui.prompt_parsed("Your name (1-80 characters): ", validation.parse_reviewer)
    if reviewer is None:
        return
    rating = ui.prompt_parsed("Rating (1-5): ", validation.parse_rating)
    if rating is None:
        return
    comment = ui.prompt_parsed("Comment (1-500 characters): ", validation.parse_comment)
    if comment is None:
        return
    review_id = updates.add_review(coll, workshop_id, reviewer, rating, comment)
    if review_id is None:
        print(f"Review failed: no active workshop with ID '{workshop_id}'.")
    else:
        print(f"Review added with ID {review_id}.")
