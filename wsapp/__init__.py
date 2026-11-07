"""Community workshops application package for CMPUT 291 Mini-Project 2.

Module overview:
    db            MongoDB connection, collection access, shared query helpers
                  (active filter, literal/exact regexes, UTC day bounds,
                  UTC timestamps)
    ui            console input/output helpers (menus, cursor paging, tables,
                  price/average formatting)
    validation    parsing and validating user-entered values
    search        operations 1-2: keyword search, available sessions
    reports       operations 3-4: popular tags for a date, top-rated workshops
    updates       operations 5-6: atomic seat reservation, adding a review
    menu          console screens wiring the above together

Entry points (repo root):
    load-json.py  Phase 1 loader:      python3 load-json.py <file.jsonl> <port>
    workshops.py  Phase 2 application: python3 workshops.py <port>

Data-access convention used throughout the project:
    * Every operation function takes the `workshops` collection as its first
      argument, so tests can pass a collection in a separate test database.
    * All filtering, sorting, grouping, averaging and updating is done by
      MongoDB (find/aggregate/update_one). Python only validates input, builds
      query documents, paginates cursors and formats output.
    * User input is only ever placed into query documents as *values*
      (never as operators/field names), and keyword/city text is passed
      through re.escape, so input cannot change the meaning of a query.
"""
