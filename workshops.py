"""Phase 2 application entry point.

Usage: python3 workshops.py <port>
"""

import sys

from pymongo.errors import PyMongoError

from wsapp import db, menu, validation


def main(argv):
    if len(argv) != 2:
        print(f"Usage: python3 {argv[0]} <port>")
        return 1
    try:
        port = validation.parse_port(argv[1])
    except ValueError as err:
        print(f"Invalid port: {err}")
        return 1

    try:
        client = db.connect(port)
    except PyMongoError as err:
        print(f"Could not connect to MongoDB on localhost:{port}: {err}")
        return 1

    try:
        menu.main_menu(db.get_collection(client))
    except (KeyboardInterrupt, EOFError):
        print("\nGoodbye.")
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
