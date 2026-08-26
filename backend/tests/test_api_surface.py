"""The API's advertised surface, checked against its actual routes.

`GET /` publishes a list of endpoints and `GET /health` publishes a block per
optional subsystem. Both are hand-maintained lists next to the code they
describe, which is exactly the arrangement that drifts: a route gets renamed, the
list keeps naming the old one, and the only way to find out is for a client to
follow it and get a 404.

`app.main` cannot be imported here - it needs FastAPI, and the whole point of
this suite is that it runs with no dependencies installed - so the module is read
and parsed with `ast` instead. That is enough to see every `@app.get(...)`
decorator and every literal in the two lists, which is all these assertions are
about. It cannot catch a route that fails at runtime; the tradeoff is that it
costs nothing and runs everywhere.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

MAIN = Path(__file__).resolve().parent.parent / "app" / "main.py"

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


def _tree() -> ast.Module:
    return ast.parse(MAIN.read_text(encoding="utf-8"))


def declared_routes() -> list[str]:
    """Every `@app.<method>("<path>")` in main.py, as "METHOD /path"."""
    found: list[str] = []
    for node in ast.walk(_tree()):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            target = decorator.func
            if not isinstance(target, ast.Attribute) or target.attr not in HTTP_METHODS:
                continue
            if not isinstance(target.value, ast.Name) or target.value.id != "app":
                continue
            if not decorator.args or not isinstance(decorator.args[0], ast.Constant):
                continue
            found.append(f"{target.attr.upper()} {decorator.args[0].value}")
    return found


def _list_literal(function_name: str, key: str) -> list[str]:
    """The string list stored under `key` in a dict inside `function_name`."""
    for node in ast.walk(_tree()):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != function_name:
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Dict):
                continue
            for entry_key, entry_value in zip(sub.keys, sub.values):
                if isinstance(entry_key, ast.Constant) and entry_key.value == key:
                    if isinstance(entry_value, ast.List):
                        return [
                            element.value
                            for element in entry_value.elts
                            if isinstance(element, ast.Constant)
                        ]
    return []


def _dict_keys(function_name: str) -> set[str]:
    """Every string key of every dict literal in `function_name`."""
    keys: set[str] = set()
    for node in ast.walk(_tree()):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            for sub in ast.walk(node):
                if isinstance(sub, ast.Dict):
                    keys.update(
                        key.value
                        for key in sub.keys
                        if isinstance(key, ast.Constant) and isinstance(key.value, str)
                    )
    return keys


class TestTheAdvertisedEndpoints(unittest.TestCase):
    def setUp(self) -> None:
        self.declared = declared_routes()
        self.advertised = _list_literal("root", "endpoints")

    def test_the_parser_found_the_routes_at_all(self) -> None:
        """Guards the rest of this file: a silent parse failure would pass everything."""
        self.assertGreater(len(self.declared), 15)
        self.assertGreater(len(self.advertised), 10)
        self.assertIn("GET /health", self.declared)

    def test_every_advertised_endpoint_exists(self) -> None:
        """A published endpoint that 404s is worse than one that is undocumented."""
        declared = set(self.declared)
        for entry in self.advertised:
            with self.subTest(entry=entry):
                # `GET /search?q=` documents a query parameter; the route is the
                # part before the `?`.
                self.assertIn(entry.split("?")[0], declared)

    def test_every_advertised_entry_is_well_formed(self) -> None:
        for entry in self.advertised:
            with self.subTest(entry=entry):
                method, _, path = entry.partition(" ")
                self.assertIn(method.lower(), HTTP_METHODS)
                self.assertTrue(path.startswith("/"))

    def test_no_route_is_declared_twice(self) -> None:
        """Two handlers on one method and path: the second silently never runs."""
        duplicates = {route for route in self.declared if self.declared.count(route) > 1}
        self.assertEqual(duplicates, set())

    def test_the_feedback_endpoints_are_published(self) -> None:
        """The panel is built against these three; a rename has to break here."""
        for entry in ("GET /feedback", "POST /feedback", "GET /feedback/summary"):
            with self.subTest(entry=entry):
                self.assertIn(entry, self.declared)
                self.assertIn(entry, self.advertised)


class TestHealthReportsEverySubsystem(unittest.TestCase):
    """Each optional subsystem must be reportable as off, not merely absent.

    The rule this pins is written out in `health_status`: a feature that is
    switched off says `enabled: false`, so it can be told apart from one that is
    broken or still starting. A subsystem that stops appearing in /health becomes
    invisible, which is how a silent degradation survives to production.
    """

    def test_health_reports_pricing_places_and_feedback(self) -> None:
        keys = _dict_keys("health_status")
        for subsystem in ("pricing", "places", "feedback"):
            with self.subTest(subsystem=subsystem):
                self.assertIn(subsystem, keys)

    def test_health_still_reports_the_core_pipeline(self) -> None:
        keys = _dict_keys("health_status")
        for subsystem in ("status", "dishes", "search", "recommender"):
            with self.subTest(subsystem=subsystem):
                self.assertIn(subsystem, keys)


if __name__ == "__main__":
    unittest.main()
