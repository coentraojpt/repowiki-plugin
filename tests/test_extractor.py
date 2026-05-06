import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import tempfile
import unittest
from pathlib import Path

from extractor import _md5, _load_cache, _save_cache, _extract_python, _extract_regex, extract_file, extract_repo


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

    def test_nested_class_not_emitted_as_top_level(self):
        src = (
            "class Outer:\n"
            "    class Inner:\n"
            "        pass\n"
            "    def method(self):\n"
            "        pass\n"
        )
        f = self.dir / "nested.py"
        f.write_text(src)
        result = _extract_python(f, "shallow")
        self.assertIn("class Outer", result)
        self.assertNotIn("class Inner", result)

    def test_annotated_field_extracted(self):
        src = "class Foo:\n    age: int\n    name: str\n"
        f = self.dir / "ann.py"
        f.write_text(src)
        result = _extract_python(f, "shallow")
        self.assertIn("age: int", result)
        self.assertIn("name: str", result)


MEDIUM_PY = """\
class Viagem(BaseModel):
    empresa = ForeignKey(Empresa, on_delete=CASCADE)
    origem = CharField(max_length=100)
    destino = CharField(max_length=100)

    def get_duracao(self):
        \"\"\"Duração em minutos.\"\"\"
        if not self.data_chegada:
            return None
        return (self.data_chegada - self.data_partida).seconds // 60

    def is_disponivel(self):
        return self.lugares_disponiveis > 0
"""


class TestPythonMedium(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.f = self.dir / "models.py"
        self.f.write_text(MEDIUM_PY)

    def tearDown(self):
        self.tmp.cleanup()

    def test_header_shows_medium(self):
        result = _extract_python(self.f, "medium")
        self.assertIn("medium", result)

    def test_no_imports_block_in_medium(self):
        src = "import os\n\nclass Foo:\n    pass\n"
        f = self.dir / "imp.py"
        f.write_text(src)
        result = _extract_python(f, "medium")
        self.assertNotIn("imports:", result)

    def test_field_with_type_present(self):
        result = _extract_python(self.f, "medium")
        self.assertIn("origem", result)
        self.assertIn("CharField", result)

    def test_method_signature_present(self):
        result = _extract_python(self.f, "medium")
        self.assertIn("def get_duracao", result)

    def test_docstring_present(self):
        result = _extract_python(self.f, "medium")
        self.assertIn("Duração em minutos", result)

    def test_body_preview_present(self):
        result = _extract_python(self.f, "medium")
        self.assertIn("data_chegada", result)

    def test_body_preview_capped_at_5_lines(self):
        long_body = "class X:\n    def foo(self):\n" + "\n".join(
            f"        x{i} = {i}" for i in range(20)
        ) + "\n"
        f = self.dir / "long.py"
        f.write_text(long_body)
        result = _extract_python(f, "medium")
        self.assertNotIn("x10 =", result)

    def test_decorator_emitted(self):
        src = (
            "class Foo:\n"
            "    @staticmethod\n"
            "    def bar():\n"
            "        return 1\n"
            "\n"
            "    @some_module.cached\n"
            "    def baz(self):\n"
            "        return 2\n"
        )
        f = self.dir / "dec.py"
        f.write_text(src)
        result = _extract_python(f, "medium")
        self.assertIn("@staticmethod", result)
        self.assertIn("@cached", result)

    def test_args_truncated_at_4(self):
        src = (
            "class Foo:\n"
            "    def many(self, a, b, c, d, e, f):\n"
            "        pass\n"
        )
        f = self.dir / "args.py"
        f.write_text(src)
        result = _extract_python(f, "medium")
        self.assertIn("def many", result)
        self.assertNotIn("e,", result)
        self.assertNotIn("f)", result)

    def test_body_cap_shows_early_lines(self):
        long_body = "class X:\n    def foo(self):\n" + "\n".join(
            f"        x{i} = {i}" for i in range(20)
        ) + "\n"
        f = self.dir / "early.py"
        f.write_text(long_body)
        result = _extract_python(f, "medium")
        self.assertIn("x0 =", result)
        self.assertIn("x4 =", result)
        self.assertNotIn("x5 =", result)


SIMPLE_JS = """\
import React from 'react';

class UserCard extends Component {
  render() { return null; }
}

function fetchUser(id) {
  return fetch('/api/users/' + id);
}

const handleSubmit = async (event) => {
  event.preventDefault();
};

export default UserCard;
"""

SIMPLE_TS = """\
import { Injectable } from '@angular/core';

export interface User {
  id: number;
  name: string;
}

export class UserService {
  getUser(id: number): User {
    return { id, name: '' };
  }
}
"""

SIMPLE_GO = """\
package main

type User struct {
    Name string
    Age  int
}

type Repository interface {
    Find(id int) User
}

func GetUser(id int) User {
    return User{}
}

func (r *UserRepo) Save(u User) error {
    return nil
}
"""

SIMPLE_RB = """\
module Billing
  class Invoice < ApplicationRecord
    def total
      items.sum(&:price)
    end

    def paid?
      status == 'paid'
    end
  end
end
"""


class TestRegexExtraction(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name, content):
        p = self.dir / name
        p.write_text(content)
        return p

    def test_js_class_found(self):
        f = self._write("UserCard.js", SIMPLE_JS)
        result = _extract_regex(f, "shallow", "js")
        self.assertIn("UserCard", result)

    def test_js_function_found(self):
        f = self._write("UserCard.js", SIMPLE_JS)
        result = _extract_regex(f, "shallow", "js")
        self.assertIn("fetchUser", result)

    def test_js_arrow_found(self):
        f = self._write("UserCard.js", SIMPLE_JS)
        result = _extract_regex(f, "shallow", "js")
        self.assertIn("handleSubmit", result)

    def test_ts_interface_found(self):
        f = self._write("service.ts", SIMPLE_TS)
        result = _extract_regex(f, "shallow", "ts")
        self.assertIn("User", result)

    def test_ts_class_found(self):
        f = self._write("service.ts", SIMPLE_TS)
        result = _extract_regex(f, "shallow", "ts")
        self.assertIn("UserService", result)

    def test_go_struct_found(self):
        f = self._write("main.go", SIMPLE_GO)
        result = _extract_regex(f, "shallow", "go")
        self.assertIn("User", result)

    def test_go_interface_found(self):
        f = self._write("main.go", SIMPLE_GO)
        result = _extract_regex(f, "shallow", "go")
        self.assertIn("Repository", result)

    def test_go_func_found(self):
        f = self._write("main.go", SIMPLE_GO)
        result = _extract_regex(f, "shallow", "go")
        self.assertIn("GetUser", result)

    def test_go_method_receiver_found(self):
        f = self._write("main.go", SIMPLE_GO)
        result = _extract_regex(f, "shallow", "go")
        self.assertIn("Save", result)

    def test_rb_class_found(self):
        f = self._write("invoice.rb", SIMPLE_RB)
        result = _extract_regex(f, "shallow", "rb")
        self.assertIn("Invoice", result)

    def test_rb_method_found(self):
        f = self._write("invoice.rb", SIMPLE_RB)
        result = _extract_regex(f, "shallow", "rb")
        self.assertIn("total", result)

    def test_generic_fallback_finds_symbols(self):
        f = self._write("app.unknown", "class Foo:\n  def bar():\n    pass\n")
        result = _extract_regex(f, "shallow", "generic")
        self.assertIn("Foo", result)

    def test_header_contains_lang_and_depth(self):
        f = self._write("main.go", SIMPLE_GO)
        result = _extract_regex(f, "shallow", "go")
        self.assertIn("[go · shallow]", result)


SIMPLE_JAVA = """\
package com.example;

public class UserController {
    private UserService service;

    public User getUser(int id) {
        return service.find(id);
    }

    private void validate(User u) {}
}
"""

SIMPLE_RS = """\
pub struct User {
    pub name: String,
    pub age: u32,
}

pub enum Status {
    Active,
    Inactive,
}

impl User {
    pub fn new(name: String) -> Self {
        User { name, age: 0 }
    }
}

pub fn create_user(name: &str) -> User {
    User::new(name.to_string())
}
"""

SIMPLE_PHP = """\
<?php
class UserRepository {
    private $db;

    public function find(int $id): User {
        return $this->db->find($id);
    }

    protected function validate(User $u): bool {
        return true;
    }
}

interface Cacheable {
    public function getCacheKey(): string;
}
"""


class TestRegexExtensionLangs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name, content):
        p = self.dir / name
        p.write_text(content)
        return p

    def test_java_class_found(self):
        f = self._write("UserController.java", SIMPLE_JAVA)
        result = _extract_regex(f, "shallow", "java")
        self.assertIn("UserController", result)

    def test_java_method_found(self):
        f = self._write("UserController.java", SIMPLE_JAVA)
        result = _extract_regex(f, "shallow", "java")
        self.assertIn("getUser", result)

    def test_rust_struct_found(self):
        f = self._write("models.rs", SIMPLE_RS)
        result = _extract_regex(f, "shallow", "rs")
        self.assertIn("User", result)

    def test_rust_enum_found(self):
        f = self._write("models.rs", SIMPLE_RS)
        result = _extract_regex(f, "shallow", "rs")
        self.assertIn("Status", result)

    def test_rust_fn_found(self):
        f = self._write("models.rs", SIMPLE_RS)
        result = _extract_regex(f, "shallow", "rs")
        self.assertIn("create_user", result)

    def test_rust_impl_found(self):
        f = self._write("models.rs", SIMPLE_RS)
        result = _extract_regex(f, "shallow", "rs")
        self.assertIn("User", result)

    def test_php_class_found(self):
        f = self._write("UserRepository.php", SIMPLE_PHP)
        result = _extract_regex(f, "shallow", "php")
        self.assertIn("UserRepository", result)

    def test_php_interface_found(self):
        f = self._write("UserRepository.php", SIMPLE_PHP)
        result = _extract_regex(f, "shallow", "php")
        self.assertIn("Cacheable", result)

    def test_php_method_found(self):
        f = self._write("UserRepository.php", SIMPLE_PHP)
        result = _extract_regex(f, "shallow", "php")
        self.assertIn("find", result)


class TestExtractFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_py_shallow_uses_ast_header(self):
        f = self.dir / "models.py"
        f.write_text("class Foo:\n    pass\n")
        result = extract_file(f, "shallow")
        self.assertIn("python", result)

    def test_js_routes_to_regex(self):
        f = self.dir / "app.js"
        f.write_text("function hello() { return 1; }\n")
        result = extract_file(f, "shallow")
        self.assertIn("[js", result)

    def test_ts_routes_to_regex(self):
        f = self.dir / "service.ts"
        f.write_text("export class MyService {}\n")
        result = extract_file(f, "shallow")
        self.assertIn("[ts", result)

    def test_go_routes_to_regex(self):
        f = self.dir / "main.go"
        f.write_text("type User struct {}\n")
        result = extract_file(f, "shallow")
        self.assertIn("[go", result)

    def test_deep_returns_raw_content(self):
        f = self.dir / "models.py"
        content = "class Foo:\n    pass\n"
        f.write_text(content)
        self.assertEqual(extract_file(f, "deep"), content)

    def test_unknown_extension_uses_generic(self):
        f = self.dir / "Makefile"
        f.write_text("build:\n\tgo build .\n")
        result = extract_file(f, "shallow")
        self.assertIn("generic", result)


class TestExtractRepo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "repo"
        self.output = Path(self.tmp.name) / "output"
        self.repo.mkdir()
        self.output.mkdir()
        (self.repo / "models.py").write_text(
            "class User:\n    name = CharField(max_length=100)\n"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _arch(self, key_files=None):
        return {"sections": [{"id": "database", "key_files": key_files or ["models.py"]}]}

    def test_section_text_contains_class(self):
        result = extract_repo(self.repo, self._arch(), "shallow", self.output)
        self.assertIn("User", result["sections"]["database"])

    def test_returns_dict_with_required_keys(self):
        result = extract_repo(self.repo, self._arch(), "shallow", self.output)
        self.assertIn("sections", result)
        self.assertIn("cache_hits", result)
        self.assertIn("cache_misses", result)

    def test_first_run_all_misses(self):
        result = extract_repo(self.repo, self._arch(), "shallow", self.output)
        self.assertEqual(result["cache_misses"], 1)
        self.assertEqual(result["cache_hits"], 0)

    def test_second_run_all_hits(self):
        extract_repo(self.repo, self._arch(), "shallow", self.output)
        result = extract_repo(self.repo, self._arch(), "shallow", self.output)
        self.assertEqual(result["cache_hits"], 1)
        self.assertEqual(result["cache_misses"], 0)

    def test_cache_invalidated_on_file_change(self):
        extract_repo(self.repo, self._arch(), "shallow", self.output)
        (self.repo / "models.py").write_text("class Product:\n    price = DecimalField()\n")
        result = extract_repo(self.repo, self._arch(), "shallow", self.output)
        self.assertEqual(result["cache_misses"], 1)
        self.assertIn("Product", result["sections"]["database"])

    def test_missing_file_skipped_gracefully(self):
        arch = self._arch(["models.py", "nonexistent.py"])
        result = extract_repo(self.repo, arch, "shallow", self.output)
        self.assertIn("User", result["sections"]["database"])
        self.assertEqual(result["cache_misses"], 1)  # nonexistent.py not counted
        self.assertNotIn("nonexistent", result["sections"]["database"])

    def test_deep_mode_never_cached(self):
        extract_repo(self.repo, self._arch(), "deep", self.output)
        result = extract_repo(self.repo, self._arch(), "deep", self.output)
        self.assertEqual(result["cache_hits"], 0)
        self.assertIn("User", result["sections"]["database"])

    def test_cache_file_written_to_output_dir(self):
        extract_repo(self.repo, self._arch(), "shallow", self.output)
        self.assertTrue((self.output / ".extract_cache.json").exists())


if __name__ == "__main__":
    unittest.main()
