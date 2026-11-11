"""Console input/output helpers shared by all screens."""

from itertools import islice

PAGE_SIZE = 10  # spec: operations 1 and 2 show at most 10 rows per page


def prompt(message):
    """Read one line of input, stripped of surrounding whitespace."""
    return input(message).strip()


def prompt_parsed(message, parser, *args, **kwargs):
    """Prompt repeatedly until `parser(text, ...)` succeeds.

    Returns the parsed value, or None if the user enters an empty line
    (used as "cancel / go back to the menu").
    """
    while True:
        text = prompt(message)
        if text == "":
            return None
        try:
            return parser(text, *args, **kwargs)
        except ValueError as err:
            print(f"Invalid input: {err}")


def prompt_choice(message, choices):
    """Prompt until the answer (lowercased) is one of `choices`; return it."""
    while True:
        answer = prompt(message).lower()
        if answer in choices:
            return answer
        print(f"Please enter one of: {', '.join(choices)}.")


def show_menu(title, options):
    """Print a menu and return the key the user picked (lowercased).

    `options` is a list of (key, label) pairs, e.g. [("1", "Search"), ...].
    Re-prompts until a valid key is entered.
    """
    keys = {key.lower() for key, _ in options}
    while True:
        print(f"\n=== {title} ===")
        for key, label in options:
            print(f"  {key}. {label}")
        choice = prompt("Choose an option: ").lower()
        if choice in keys:
            return choice
        print("Invalid option, please try again.")


def print_table(headings, rows):
    """Print `rows` (lists of cell strings) as an aligned text table."""
    widths = [len(h) for h in headings]
    for row in rows:
        widths = [max(w, len(cell)) for w, cell in zip(widths, row)]
    print(" | ".join(h.ljust(w) for h, w in zip(headings, widths)))
    print("-+-".join("-" * w for w in widths))
    for row in rows:
        print(" | ".join(cell.ljust(w) for cell, w in zip(row, widths)))


def paginate(results, render_row, title, headings, empty_message="No results found."):
    """Show `results` PAGE_SIZE rows at a time with next-page / menu navigation.

    results                  any iterable, typically a pymongo Cursor or
                             CommandCursor; it is consumed lazily, one page
                             (+ the following page) at a time, so the whole
                             result set is never loaded into memory.
    render_row(doc) -> list  the cells (strings) for one result row,
                             in the same order as `headings`.
                             
    DISCLAIMER: We see '... allow the user to request the next page or return to the menu', so did NOT make the 'previous page' option.
    """
    iterator = iter(results)
    page = list(islice(iterator, PAGE_SIZE))
    if not page:
        print(f"\n=== {title} ===")
        print(empty_message)
        return

    page_number = 1
    while True:
        print(f"\n=== {title} - Page {page_number} ===")
        print_table(headings, [render_row(doc) for doc in page])

        next_page = list(islice(iterator, PAGE_SIZE))
        if not next_page:
            print("(end of results)")
            return
        choice = prompt_choice("n = next page, m = return to menu: ", ("n", "m"))
        if choice == "m":
            return
        page = next_page
        page_number += 1


def show_rows(results, render_row, title, headings, empty_message="No results found."):
    """Print a short, already-limited result list (operations 3 and 4)."""
    rows = [render_row(doc) for doc in results]
    print(f"\n=== {title} ===")
    if not rows:
        print(empty_message)
        return
    print_table(headings, rows)


def fmt_price(cents):
    """Format an integer number of cents as dollars: 1500 -> "$15.00"."""
    return f"${cents // 100}.{cents % 100:02d}"


def fmt_average(value):
    """Format an (unrounded) average rating to two decimals, after ranking."""
    return f"{value:.2f}"
