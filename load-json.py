"""Phase 1 loader: load a JSON Lines file into 291db_workshops.workshops.

Usage: python3 load-json.py <file.jsonl> <port>

Order of steps (spec Phase 1):
    1. open the input file FIRST, so a bad path never erases existing data;
    2. connect to MongoDB;
    3. replace the workshops collection (other collections/databases are
       untouched) and insert the documents in batches of <= 1000, reading
       the file incrementally (never the whole file at once);
    4. print the number of inserted documents.
On malformed JSON or an insertion error, report the line/batch and exit
with a nonzero status. A partial collection may remain; re-running on valid
input replaces it.
"""

import json
import sys

from bson.errors import BSONError
from pymongo.errors import PyMongoError

from wsapp import db, validation

BATCH_SIZE = 600


class LoadError(Exception):
    """Raised for malformed input or a failed batch insert (message says where)."""


def parse_args(argv):
    """Return (path, port) from the command line, or raise LoadError."""
    if len(argv) != 3:
        raise LoadError(f"Usage: python3 {argv[0]} <file.jsonl> <port>")
    try:
        port = validation.parse_port(argv[2])
    except ValueError as err:
        raise LoadError(f"Invalid port: {err}") from None
    return argv[1], port


def iter_batches(lines, batch_size=BATCH_SIZE):
    """Parse JSON Lines lazily and yield (first_line, last_line, docs) batches.

    `lines` is any iterable of text lines (e.g. an open file). Blank lines
    are skipped; line numbers are 1-based and refer to the input file. Each
    batch holds at most `batch_size` documents; only one batch is in memory
    at a time. Raises LoadError naming the line for malformed JSON or a
    line that is not a JSON object.
    """
    batch, first_line = [], None
    for line_no, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            doc = json.loads(line)
        except ValueError as err:  # JSONDecodeError (or bad UTF-8 in bytes input)
            raise LoadError(f"Malformed JSON on line {line_no}: {err}") from None
        if not isinstance(doc, dict):
            raise LoadError(f"Line {line_no} is not a JSON object.")
        if first_line is None:
            first_line = line_no
        batch.append(doc)
        last_line = line_no
        if len(batch) == batch_size:
            yield first_line, last_line, batch
            batch, first_line = [], None
    if batch:
        yield first_line, last_line, batch


def load_workshops(coll, lines, batch_size=BATCH_SIZE):
    """Replace `coll` with the documents in `lines`; return the inserted count.

    Steps:
        * drop the collection, then (re)create it so that an input file with
          no documents still leaves an EMPTY collection behind;
        * for each batch from iter_batches(lines, batch_size), call
          coll.insert_many(docs) (the supplied string _id values are kept;
          no ObjectIds are generated because every document has an _id);
        * (optional) create indexes and describe them in the README.

    On a pymongo error during insert_many, raise LoadError that names the
    batch's line range (first_line-last_line). LoadError from iter_batches
    propagates unchanged.
    """
    coll.drop()
    coll.database.create_collection(coll.name)
    count = 0
    for first_line, last_line, docs in iter_batches(lines, batch_size):
        try:
            coll.insert_many(docs)
        except (PyMongoError, BSONError) as err:
            raise LoadError(
                f"Database error inserting lines {first_line}-{last_line}: {err}"
            ) from None
        count += len(docs)
    return count


def main(argv):
    try:
        path, port = parse_args(argv)
    except LoadError as err:
        print(err)
        return 1

    # Open the file before touching the database (spec requirement).
    try:
        # Binary mode: json.loads decodes each line itself (UTF-8, optional
        # BOM), so an invalid byte sequence is reported with its line number.
        infile = open(path, "rb")
    except OSError as err:
        print(f"Cannot open {path}: {err}")
        return 1

    with infile:
        try:
            client = db.connect(port)
        except PyMongoError as err:
            print(f"Could not connect to MongoDB on localhost:{port}: {err}")
            return 1
        try:
            count = load_workshops(db.get_collection(client), infile)
        except LoadError as err:
            print(f"Load failed: {err}")
            return 1
        except PyMongoError as err:
            print(f"Load failed: database error: {err}")
            return 1
        finally:
            client.close()

    print(f"Inserted {count} documents.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
