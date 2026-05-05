import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import tempfile
import unittest
from pathlib import Path

from extractor import _md5, _load_cache, _save_cache, _extract_python


class TestCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_md5_deterministic(self):
        f = self.dir / "file.py"
        f.write_text("hello")
        self.assertEqual(_md5(f), _md5(f))
        self.assertEqual(len(_md5(f)), 8)

    def test_md5_changes_on_content_change(self):
        f = self.dir / "file.py"
        f.write_text("hello")
        h1 = _md5(f)
        f.write_text("world")
        self.assertNotEqual(h1, _md5(f))

    def test_md5_missing_file_returns_fallback(self):
        result = _md5(self.dir / "nonexistent.py")
        self.assertEqual(result, "00000000")

    def test_load_cache_missing_returns_empty(self):
        cache = _load_cache(self.dir / "nonexistent.json")
        self.assertEqual(cache["version"], 1)
        self.assertEqual(cache["entries"], {})

    def test_load_cache_wrong_version_returns_empty(self):
        p = self.dir / "cache.json"
        p.write_text(json.dumps({"version": 99, "entries": {"x": "y"}}))
        cache = _load_cache(p)
        self.assertEqual(cache["entries"], {})

    def test_save_load_roundtrip(self):
        p = self.dir / "cache.json"
        data = {
            "version": 1,
            "entries": {"apps/models.py": {"hash": "abcd1234", "shallow": "# models.py"}},
        }
        _save_cache(p, data)
        loaded = _load_cache(p)
        self.assertEqual(loaded["entries"]["apps/models.py"]["shallow"], "# models.py")


SIMPLE_PY = """\
import os
from pathlib import Path

class MyModel(BaseModel):
    name = CharField(max_length=100)
    active = BooleanField()
    owner = ForeignKey(User, on_delete=CASCADE)

    def greet(self):
        return f"Hello {self.name}"

    def is_active_user(self):
        return self.active
"""


class TestPythonShallow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.f = self.dir / "models.py"
        self.f.write_text(SIMPLE_PY)

    def tearDown(self):
        self.tmp.cleanup()

    def test_header_contains_filename_and_depth(self):
        result = _extract_python(self.f, "shallow")
        self.assertIn("models.py", result)
        self.assertIn("shallow", result)

    def test_imports_listed(self):
        result = _extract_python(self.f, "shallow")
        self.assertIn("imports:", result)
        self.assertIn("os", result)

    def test_class_present(self):
        result = _extract_python(self.f, "shallow")
        self.assertIn("class MyModel", result)
        self.assertIn("BaseModel", result)

    def test_fields_summarised(self):
        result = _extract_python(self.f, "shallow")
        self.assertIn("fields:", result)
        self.assertIn("name", result)

    def test_fk_shows_target(self):
        result = _extract_python(self.f, "shallow")
        self.assertIn("FK→User", result)

    def test_methods_listed_without_body(self):
        result = _extract_python(self.f, "shallow")
        self.assertIn("greet()", result)
        self.assertIn("is_active_user()", result)
        # Body must NOT appear in shallow
        self.assertNotIn("Hello {self.name}", result)

    def test_syntax_error_falls_back_to_regex(self):
        bad = self.dir / "broken.py"
        bad.write_text("class Foo(\n    incomplete")
        result = _extract_python(bad, "shallow")
        self.assertIn("Foo", result)


if __name__ == "__main__":
    unittest.main()
