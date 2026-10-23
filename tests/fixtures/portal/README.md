# Portal fixtures (PLAN_V2 §7)

One JSON file per portal endpoint, hand-written from the §7 shapes. Two uses, both in tests only:

1. `tests/test_portal_api.py`: the real endpoint must return exactly these keys (every level), both on an
   empty database and on a seeded one.
2. `tests/test_portal_widgets.py`: every widget is rendered with these payloads in Node to prove it draws.

The numbers are made up for tests. They are never served; the real endpoints return `null` / `[]`
when there is no data (the page then shows an empty state).
