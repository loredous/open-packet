# Message Template Forms Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add YAML-defined message template forms with dynamic TUI modals and Jinja2-rendered subject/body output.

**Architecture:** A new `open_packet/forms/` module handles all non-UI logic (YAML loading, validation, Jinja2 rendering). Two new TUI screens (`FormPickerScreen`, `FormFillScreen`) consume it. The form flow terminates in the existing `ComposeScreen` with pre-filled subject and body. No engine or store involvement.

**Tech Stack:** PyYAML (YAML parsing), Jinja2 (templating), Textual (TUI widgets: Tree, Input, TextArea, Select), pytest (tests)

---

## File Map

**Create:**
- `open_packet/forms/__init__.py` — empty package marker
- `open_packet/forms/loader.py` — `FormField`, `FormDefinition` dataclasses; `load_form()`, `discover_forms()`; `FormLoadError`
- `open_packet/forms/validator.py` — `validate_field()`, `validate_form()`
- `open_packet/forms/renderer.py` — `render()`, `FormRenderError`
- `open_packet/ui/tui/screens/form_picker.py` — `FormPickerScreen` modal (Tree-based)
- `open_packet/ui/tui/screens/form_fill.py` — `FormFillScreen` modal (dynamic fields) + `_BypassConfirmScreen`
- `tests/test_forms/__init__.py` — empty
- `tests/test_forms/test_loader.py`
- `tests/test_forms/test_validator.py`
- `tests/test_forms/test_renderer.py`

**Modify:**
- `pyproject.toml` — add `jinja2` and `pyyaml` dependencies
- `open_packet/ui/tui/screens/compose.py` — add `body` init param; add "Use Form" button + form flow handler
- `open_packet/ui/tui/screens/main.py` — add `f` key binding → `action_form_message`
- `open_packet/ui/tui/app.py` — add `--forms-dir` CLI arg + env var; add `forms_dir` property; add `open_form_compose()` and callbacks; update `open_compose()` to accept `body`

---

## Task 1: Add jinja2 and pyyaml dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add dependencies to pyproject.toml**

Replace the dependencies block:

```toml
dependencies = [
    "textual>=0.60.0",
    "pyserial>=3.5",
    "textual-serve>=1.1.3",
    "pyyaml>=6.0",
    "jinja2>=3.1",
]
```

- [ ] **Step 2: Sync dependencies**

```bash
uv sync
```

Expected: resolves and installs pyyaml and jinja2 without error.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add pyyaml and jinja2 dependencies for forms feature"
```

---

## Task 2: forms/loader.py — dataclasses, load_form, discover_forms

**Files:**
- Create: `open_packet/forms/__init__.py`
- Create: `open_packet/forms/loader.py`
- Create: `tests/test_forms/__init__.py`
- Create: `tests/test_forms/test_loader.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_forms/__init__.py` (empty).

Create `tests/test_forms/test_loader.py`:

```python
import pytest
from pathlib import Path
from open_packet.forms.loader import (
    load_form, discover_forms, FormDefinition, FormField, FormLoadError
)

VALID_YAML = """\
name: Test Form
category: Test
fields:
  - name: greeting
    label: Greeting
    required: true
    max_length: 20
  - name: priority
    label: Priority
    choices: [Low, High]
  - name: ts
    label: Timestamp
    type: datetime
    format: "%Y-%m-%d"
    auto_populate: true
subject_template: "Hello {{ greeting }}"
body_template: "Priority: {{ priority }}"
"""


def test_load_form_valid(tmp_path):
    f = tmp_path / "test.yaml"
    f.write_text(VALID_YAML)
    form = load_form(f)
    assert form.name == "Test Form"
    assert form.category == "Test"
    assert len(form.fields) == 3
    assert form.fields[0].name == "greeting"
    assert form.fields[0].required is True
    assert form.fields[0].max_length == 20
    assert form.fields[1].choices == ["Low", "High"]
    assert form.fields[2].type == "datetime"
    assert form.fields[2].format == "%Y-%m-%d"
    assert form.fields[2].auto_populate is True
    assert form.subject_template == "Hello {{ greeting }}"
    assert form.source_path == f


def test_load_form_missing_category(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text("name: X\nfields: []\nsubject_template: s\nbody_template: b\n")
    with pytest.raises(FormLoadError, match="category"):
        load_form(f)


def test_load_form_missing_name(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text("category: X\nfields: []\nsubject_template: s\nbody_template: b\n")
    with pytest.raises(FormLoadError, match="name"):
        load_form(f)


def test_load_form_missing_fields(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text("name: X\ncategory: Y\nsubject_template: s\nbody_template: b\n")
    with pytest.raises(FormLoadError, match="fields"):
        load_form(f)


def test_load_form_missing_subject_template(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text("name: X\ncategory: Y\nfields: []\nbody_template: b\n")
    with pytest.raises(FormLoadError, match="subject_template"):
        load_form(f)


def test_load_form_missing_body_template(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text("name: X\ncategory: Y\nfields: []\nsubject_template: s\n")
    with pytest.raises(FormLoadError, match="body_template"):
        load_form(f)


def test_load_form_field_missing_name(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text(
        "name: X\ncategory: Y\n"
        "fields:\n  - label: Oops\n"
        "subject_template: s\nbody_template: b\n"
    )
    with pytest.raises(FormLoadError, match="name"):
        load_form(f)


def test_load_form_field_missing_label(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text(
        "name: X\ncategory: Y\n"
        "fields:\n  - name: foo\n"
        "subject_template: s\nbody_template: b\n"
    )
    with pytest.raises(FormLoadError, match="label"):
        load_form(f)


def test_load_form_invalid_yaml(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text(":\ninvalid: [yaml: content\n")
    with pytest.raises(FormLoadError):
        load_form(f)


def test_discover_forms_skips_bad_files(tmp_path):
    good = tmp_path / "good.yaml"
    good.write_text(VALID_YAML)
    bad = tmp_path / "bad.yaml"
    bad.write_text("not_a_form: true\n")
    forms = discover_forms(tmp_path)
    assert len(forms) == 1
    assert forms[0].name == "Test Form"


def test_discover_forms_empty_directory(tmp_path):
    assert discover_forms(tmp_path) == []


def test_discover_forms_missing_directory(tmp_path):
    assert discover_forms(tmp_path / "nonexistent") == []


def test_discover_forms_recursive(tmp_path):
    subdir = tmp_path / "ICS"
    subdir.mkdir()
    (subdir / "ics213.yaml").write_text(VALID_YAML)
    forms = discover_forms(tmp_path)
    assert len(forms) == 1


def test_discover_forms_ignores_non_yaml(tmp_path):
    (tmp_path / "readme.txt").write_text("ignore me")
    (tmp_path / "form.yaml").write_text(VALID_YAML)
    forms = discover_forms(tmp_path)
    assert len(forms) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_forms/test_loader.py -v
```

Expected: `ModuleNotFoundError: No module named 'open_packet.forms'`

- [ ] **Step 3: Create the forms package and loader module**

Create `open_packet/forms/__init__.py` (empty file).

Create `open_packet/forms/loader.py`:

```python
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


class FormLoadError(Exception):
    pass


@dataclass
class FormField:
    name: str
    label: str
    description: str = ""
    type: str = "text"
    choices: list[str] = field(default_factory=list)
    required: bool = False
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None
    format: Optional[str] = None
    auto_populate: bool = False


@dataclass
class FormDefinition:
    name: str
    category: str
    fields: list[FormField]
    subject_template: str
    body_template: str
    source_path: Optional[Path] = None


def _parse_field(raw: object) -> FormField:
    if not isinstance(raw, dict):
        raise FormLoadError("Each field must be a YAML mapping")
    if "name" not in raw:
        raise FormLoadError("Field missing required key 'name'")
    if "label" not in raw:
        raise FormLoadError(f"Field '{raw['name']}' missing required key 'label'")
    return FormField(
        name=raw["name"],
        label=raw["label"],
        description=raw.get("description", ""),
        type=raw.get("type", "text"),
        choices=raw.get("choices", []),
        required=raw.get("required", False),
        min_length=raw.get("min_length"),
        max_length=raw.get("max_length"),
        pattern=raw.get("pattern"),
        format=raw.get("format"),
        auto_populate=raw.get("auto_populate", False),
    )


def load_form(path: Path) -> FormDefinition:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise FormLoadError(f"Failed to read/parse {path}: {e}") from e

    if not isinstance(data, dict):
        raise FormLoadError(f"{path}: expected a YAML mapping at top level")

    for key in ("name", "category", "fields", "subject_template", "body_template"):
        if key not in data:
            raise FormLoadError(f"{path}: missing required key '{key}'")

    if not isinstance(data["fields"], list):
        raise FormLoadError(f"{path}: 'fields' must be a list")

    fields = [_parse_field(f) for f in data["fields"]]

    return FormDefinition(
        name=data["name"],
        category=data["category"],
        fields=fields,
        subject_template=data["subject_template"],
        body_template=data["body_template"],
        source_path=path,
    )


def discover_forms(forms_dir: Path) -> list[FormDefinition]:
    if not forms_dir.exists():
        return []
    results = []
    for yaml_path in sorted(forms_dir.rglob("*.yaml")):
        try:
            results.append(load_form(yaml_path))
        except FormLoadError as e:
            logger.warning("Skipping form %s: %s", yaml_path, e)
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_forms/test_loader.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add open_packet/forms/ tests/test_forms/
git commit -m "feat: add forms/loader.py with FormDefinition dataclasses and YAML loading"
```

---

## Task 3: forms/validator.py

**Files:**
- Create: `open_packet/forms/validator.py`
- Create: `tests/test_forms/test_validator.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_forms/test_validator.py`:

```python
import pytest
from open_packet.forms.loader import FormField, FormDefinition
from open_packet.forms.validator import validate_field, validate_form


def _field(**kwargs) -> FormField:
    return FormField(name="f", label="F", **kwargs)


def _form(*fields: FormField) -> FormDefinition:
    return FormDefinition(
        name="T", category="C",
        fields=list(fields),
        subject_template="x",
        body_template="y",
    )


# --- required ---

def test_required_fails_on_empty_string():
    errors = validate_field(_field(required=True), "")
    assert len(errors) == 1
    assert "required" in errors[0].lower()


def test_required_fails_on_whitespace_only():
    errors = validate_field(_field(required=True), "   ")
    assert len(errors) == 1


def test_required_passes_with_value():
    assert validate_field(_field(required=True), "hello") == []


# --- min_length ---

def test_min_length_fails():
    errors = validate_field(_field(min_length=5), "hi")
    assert len(errors) == 1
    assert "5" in errors[0]


def test_min_length_passes_exact():
    assert validate_field(_field(min_length=3), "abc") == []


def test_min_length_passes_longer():
    assert validate_field(_field(min_length=3), "abcdef") == []


# --- max_length ---

def test_max_length_fails():
    errors = validate_field(_field(max_length=3), "toolong")
    assert len(errors) == 1
    assert "3" in errors[0]


def test_max_length_passes_exact():
    assert validate_field(_field(max_length=3), "abc") == []


def test_max_length_passes_shorter():
    assert validate_field(_field(max_length=10), "ok") == []


# --- pattern ---

def test_pattern_fails():
    errors = validate_field(_field(pattern=r"^\d+$"), "abc")
    assert len(errors) == 1


def test_pattern_passes():
    assert validate_field(_field(pattern=r"^\d+$"), "123") == []


def test_pattern_must_match_full_value():
    errors = validate_field(_field(pattern=r"\d+"), "abc123")
    # fullmatch required — partial match not enough
    assert len(errors) == 1


# --- choices ---

def test_choices_fails_on_unknown_value():
    errors = validate_field(_field(choices=["Low", "High"]), "Medium")
    assert len(errors) == 1
    assert "Low" in errors[0] or "High" in errors[0]


def test_choices_passes_on_valid_value():
    assert validate_field(_field(choices=["Low", "High"]), "Low") == []


# --- empty non-required field skips other checks ---

def test_empty_non_required_skips_min_length():
    assert validate_field(_field(min_length=5), "") == []


def test_empty_non_required_skips_pattern():
    assert validate_field(_field(pattern=r"^\d+$"), "") == []


def test_empty_non_required_skips_choices():
    assert validate_field(_field(choices=["Low", "High"]), "") == []


# --- validate_form ---

def test_validate_form_returns_per_field_errors():
    form = _form(
        FormField(name="a", label="A", required=True),
        FormField(name="b", label="B", max_length=3),
    )
    errors = validate_form(form, {"a": "", "b": "toolong"})
    assert errors["a"]
    assert errors["b"]


def test_validate_form_no_errors():
    form = _form(
        FormField(name="a", label="A", required=True),
    )
    errors = validate_form(form, {"a": "hello"})
    assert errors == {"a": []}


def test_validate_form_missing_field_value_treated_as_empty():
    form = _form(FormField(name="a", label="A", required=True))
    errors = validate_form(form, {})
    assert errors["a"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_forms/test_validator.py -v
```

Expected: `ModuleNotFoundError: No module named 'open_packet.forms.validator'`

- [ ] **Step 3: Implement validator**

Create `open_packet/forms/validator.py`:

```python
from __future__ import annotations
import re
from open_packet.forms.loader import FormField, FormDefinition


def validate_field(field: FormField, value: str) -> list[str]:
    errors: list[str] = []

    stripped = value.strip()

    if field.required and not stripped:
        errors.append("This field is required.")
        return errors  # skip further checks on empty required field

    # Skip other checks if value is empty and field is not required
    if not stripped:
        return []

    if field.min_length is not None and len(value) < field.min_length:
        errors.append(f"Must be at least {field.min_length} characters.")

    if field.max_length is not None and len(value) > field.max_length:
        errors.append(f"Must be no more than {field.max_length} characters.")

    if field.pattern is not None and not re.fullmatch(field.pattern, value):
        errors.append("Value does not match the required format.")

    if field.choices and value not in field.choices:
        options = ", ".join(field.choices)
        errors.append(f"Must be one of: {options}.")

    return errors


def validate_form(
    form: FormDefinition, values: dict[str, str]
) -> dict[str, list[str]]:
    return {
        f.name: validate_field(f, values.get(f.name, ""))
        for f in form.fields
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_forms/test_validator.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add open_packet/forms/validator.py tests/test_forms/test_validator.py
git commit -m "feat: add forms/validator.py with per-field validation rules"
```

---

## Task 4: forms/renderer.py

**Files:**
- Create: `open_packet/forms/renderer.py`
- Create: `tests/test_forms/test_renderer.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_forms/test_renderer.py`:

```python
import pytest
from open_packet.forms.loader import FormDefinition, FormField
from open_packet.forms.renderer import render, FormRenderError


def _form(subject_template: str, body_template: str) -> FormDefinition:
    return FormDefinition(
        name="T", category="C",
        fields=[FormField(name="name", label="Name")],
        subject_template=subject_template,
        body_template=body_template,
    )


def test_render_produces_correct_subject_and_body():
    form = _form("Hello {{ name }}", "Dear {{ name }},\nMessage body.")
    subject, body = render(form, {"name": "W1AW"})
    assert subject == "Hello W1AW"
    assert body == "Dear W1AW,\nMessage body."


def test_render_multiple_fields():
    form = _form(
        "{{ priority }}: {{ incident }}",
        "Incident: {{ incident }}\nPriority: {{ priority }}",
    )
    subject, body = render(form, {"priority": "High", "incident": "Drill"})
    assert subject == "High: Drill"
    assert "High" in body
    assert "Drill" in body


def test_render_raises_on_undefined_variable_in_subject():
    form = _form("{{ undefined_var }}", "body")
    with pytest.raises(FormRenderError):
        render(form, {})


def test_render_raises_on_undefined_variable_in_body():
    form = _form("subject", "{{ no_such_field }}")
    with pytest.raises(FormRenderError):
        render(form, {})


def test_render_with_empty_optional_field():
    form = _form("Subject", "Note: {{ note }}")
    subject, body = render(form, {"note": ""})
    assert subject == "Subject"
    assert body == "Note: "
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_forms/test_renderer.py -v
```

Expected: `ModuleNotFoundError: No module named 'open_packet.forms.renderer'`

- [ ] **Step 3: Implement renderer**

Create `open_packet/forms/renderer.py`:

```python
from __future__ import annotations
from jinja2 import Environment, StrictUndefined, UndefinedError, TemplateError
from open_packet.forms.loader import FormDefinition

_env = Environment(undefined=StrictUndefined)


class FormRenderError(Exception):
    pass


def render(form: FormDefinition, values: dict[str, str]) -> tuple[str, str]:
    try:
        subject = _env.from_string(form.subject_template).render(**values)
        body = _env.from_string(form.body_template).render(**values)
        return subject, body
    except (UndefinedError, TemplateError) as e:
        raise FormRenderError(str(e)) from e
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_forms/test_renderer.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Run full test suite to confirm nothing broken**

```bash
uv run pytest -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add open_packet/forms/renderer.py tests/test_forms/test_renderer.py
git commit -m "feat: add forms/renderer.py with Jinja2 subject/body rendering"
```

---

## Task 5: FormPickerScreen

**Files:**
- Create: `open_packet/ui/tui/screens/form_picker.py`

- [ ] **Step 1: Create FormPickerScreen**

Create `open_packet/ui/tui/screens/form_picker.py`:

```python
from __future__ import annotations
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Tree
from textual.containers import Vertical

from open_packet.forms.loader import FormDefinition


class FormPickerScreen(ModalScreen):
    DEFAULT_CSS = """
    FormPickerScreen {
        align: center middle;
    }
    FormPickerScreen Vertical {
        width: 60;
        height: auto;
        max-height: 30;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    FormPickerScreen Tree {
        height: auto;
        max-height: 20;
    }
    """

    def __init__(self, forms: list[FormDefinition], **kwargs):
        super().__init__(**kwargs)
        self._forms = forms

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Select a Form", id="picker_title")
            if not self._forms:
                yield Label(
                    "No forms found. Create .yaml files in\n"
                    "~/.config/open-packet/forms/"
                )
                yield Button("Close", id="close_btn")
                return

            tree: Tree[FormDefinition] = Tree("Forms", id="form_tree")
            tree.root.expand()

            categories: dict[str, list[FormDefinition]] = {}
            for form in self._forms:
                categories.setdefault(form.category, []).append(form)

            for category in sorted(categories):
                cat_node = tree.root.add(category, expand=True)
                for form in sorted(categories[category], key=lambda f: f.name):
                    cat_node.add_leaf(form.name, data=form)

            yield tree
            yield Button("Cancel", id="cancel_btn")

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        if event.node.data is not None:
            self.dismiss(event.node.data)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
```

- [ ] **Step 2: Commit**

```bash
git add open_packet/ui/tui/screens/form_picker.py
git commit -m "feat: add FormPickerScreen with category-grouped Tree widget"
```

---

## Task 6: FormFillScreen

**Files:**
- Create: `open_packet/ui/tui/screens/form_fill.py`

- [ ] **Step 1: Create FormFillScreen**

Create `open_packet/ui/tui/screens/form_fill.py`:

```python
from __future__ import annotations
from datetime import datetime
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, TextArea
from textual.containers import Horizontal, Vertical

from open_packet.forms.loader import FormDefinition, FormField
from open_packet.forms.renderer import FormRenderError, render
from open_packet.forms.validator import validate_form


class _BypassConfirmScreen(ModalScreen):
    DEFAULT_CSS = """
    _BypassConfirmScreen { align: center middle; }
    _BypassConfirmScreen Vertical {
        width: 50; height: auto; border: solid $warning;
        background: $surface; padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("[b]Warning:[/b] Some fields have validation errors.")
            yield Label("Submit anyway?")
            with Horizontal():
                yield Button("Submit Anyway", variant="warning", id="confirm_btn")
                yield Button("Go Back", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm_btn")

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(False)


class FormFillScreen(ModalScreen):
    DEFAULT_CSS = """
    FormFillScreen {
        align: center middle;
    }
    FormFillScreen Vertical {
        width: 70;
        height: auto;
        max-height: 40;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    FormFillScreen TextArea {
        height: 6;
    }
    FormFillScreen .field-desc {
        color: $text-muted;
    }
    FormFillScreen .field-error {
        color: $error;
    }
    """

    def __init__(self, form: FormDefinition, **kwargs):
        super().__init__(**kwargs)
        self._form = form

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(f"[b]{self._form.name}[/b]", id="form_title")
            for f in self._form.fields:
                yield Label(f.label)
                if f.description:
                    yield Label(f.description, classes="field-desc")
                if f.choices:
                    opts = [(c, c) for c in f.choices]
                    yield Select(opts, allow_blank=True, id=f"field_{f.name}")
                elif f.type == "textarea":
                    yield TextArea(id=f"field_{f.name}")
                else:
                    initial = ""
                    if f.type == "datetime" and f.auto_populate and f.format:
                        initial = datetime.now().strftime(f.format)
                    yield Input(value=initial, id=f"field_{f.name}")
                yield Label("", id=f"error_{f.name}", classes="field-error")
            yield Label("", id="render_error", classes="field-error")
            with Horizontal():
                yield Button("Submit", variant="primary", id="submit_btn")
                yield Button("Submit Anyway", id="bypass_btn")
                yield Button("Cancel", id="cancel_btn")

    def on_mount(self) -> None:
        self._run_validation()

    def _get_values(self) -> dict[str, str]:
        values: dict[str, str] = {}
        for f in self._form.fields:
            fid = f"#field_{f.name}"
            if f.choices:
                widget = self.query_one(fid, Select)
                val = widget.value
                values[f.name] = "" if val is Select.BLANK else str(val)
            elif f.type == "textarea":
                values[f.name] = self.query_one(fid, TextArea).text
            else:
                values[f.name] = self.query_one(fid, Input).value
        return values

    def _run_validation(self) -> bool:
        values = self._get_values()
        errors = validate_form(self._form, values)
        has_errors = False
        for f in self._form.fields:
            field_errors = errors.get(f.name, [])
            self.query_one(f"#error_{f.name}", Label).update(
                field_errors[0] if field_errors else ""
            )
            if field_errors:
                has_errors = True
        self.query_one("#submit_btn", Button).disabled = has_errors
        return not has_errors

    def on_input_changed(self, event: Input.Changed) -> None:
        self._run_validation()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        self._run_validation()

    def on_select_changed(self, event: Select.Changed) -> None:
        self._run_validation()

    def _do_submit(self) -> None:
        values = self._get_values()
        try:
            subject, body = render(self._form, values)
            self.dismiss((subject, body))
        except FormRenderError as e:
            self.query_one("#render_error", Label).update(f"Template error: {e}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel_btn":
            self.dismiss(None)
        elif event.button.id == "submit_btn":
            if self._run_validation():
                self._do_submit()
        elif event.button.id == "bypass_btn":
            self.app.push_screen(_BypassConfirmScreen(), callback=self._on_bypass_confirmed)

    def _on_bypass_confirmed(self, confirmed: bool) -> None:
        if confirmed:
            self._do_submit()

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
```

- [ ] **Step 2: Commit**

```bash
git add open_packet/ui/tui/screens/form_fill.py
git commit -m "feat: add FormFillScreen with dynamic field rendering and inline validation"
```

---

## Task 7: Wire up compose screen, key binding, and app entry points

**Files:**
- Modify: `open_packet/ui/tui/screens/compose.py`
- Modify: `open_packet/ui/tui/screens/main.py`
- Modify: `open_packet/ui/tui/app.py`

- [ ] **Step 1: Update ComposeScreen to accept body param and "Use Form" button**

Replace `open_packet/ui/tui/screens/compose.py` with:

```python
from __future__ import annotations
from pathlib import Path
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, TextArea
from textual.containers import Vertical, Horizontal
from open_packet.engine.commands import SendMessageCommand


class ComposeScreen(ModalScreen):
    DEFAULT_CSS = """
    ComposeScreen {
        align: center middle;
    }
    ComposeScreen Vertical {
        width: 70;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    ComposeScreen TextArea {
        height: 10;
    }
    """

    def __init__(self, to_call: str = "", subject: str = "", body: str = "", **kwargs):
        super().__init__(**kwargs)
        self._to_call = to_call
        self._subject = subject
        self._body = body

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("New Message", id="compose_title")
            yield Label("To:")
            yield Input(value=self._to_call, placeholder="Callsign", id="to_field")
            yield Label("Subject:")
            yield Input(value=self._subject, placeholder="Subject", id="subject_field")
            yield Label("Body:")
            yield TextArea(self._body, id="body_field")
            with Horizontal():
                yield Button("Send", variant="primary", id="send_btn")
                yield Button("Use Form", id="use_form_btn")
                yield Button("Cancel", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel_btn":
            self.dismiss(None)
        elif event.button.id == "send_btn":
            to_call = self.query_one("#to_field", Input).value.strip()
            subject = self.query_one("#subject_field", Input).value.strip()
            body = self.query_one("#body_field", TextArea).text.strip()
            if to_call and subject:
                self.dismiss(SendMessageCommand(
                    to_call=to_call, subject=subject, body=body
                ))
        elif event.button.id == "use_form_btn":
            from open_packet.forms.loader import discover_forms
            from open_packet.ui.tui.screens.form_picker import FormPickerScreen
            forms_dir = getattr(self.app, "forms_dir", Path.home() / ".config/open-packet/forms")
            forms = discover_forms(forms_dir)
            self.app.push_screen(FormPickerScreen(forms), callback=self._on_form_picked)

    def _on_form_picked(self, form_def) -> None:
        if form_def is None:
            return
        from open_packet.ui.tui.screens.form_fill import FormFillScreen
        self.app.push_screen(FormFillScreen(form_def), callback=self._on_form_filled)

    def _on_form_filled(self, result) -> None:
        if result is None:
            return
        subject, body = result
        self.query_one("#subject_field", Input).value = subject
        self.query_one("#body_field", TextArea).load_text(body)
```

- [ ] **Step 2: Add form message key binding to MainScreen**

In `open_packet/ui/tui/screens/main.py`, add the binding and action:

In the `BINDINGS` list, add after `Binding("ctrl+b", "new_bulletin", "Bulletin", priority=True),`:
```python
        Binding("f", "form_message", "Form Msg", priority=True),
```

At the end of the class, add:
```python
    def action_form_message(self) -> None:
        self.app.open_form_compose()
```

- [ ] **Step 3: Add forms_dir support and open_form_compose to app.py**

In `open_packet/ui/tui/app.py`, make the following changes:

**a) Update `__init__` signature and body** — add `forms_dir` parameter:

```python
    def __init__(self, db_path: str, console_log: Optional[str] = None,
                 forms_dir: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self._db_path = db_path
        self._console_log = console_log
        self._forms_dir: Optional[str] = forms_dir
        # ... (keep all other existing assignments unchanged)
```

**b) Add `forms_dir` property** — add after `__init__`:

```python
    @property
    def forms_dir(self) -> Path:
        if self._forms_dir:
            return Path(self._forms_dir)
        env = os.environ.get("OPEN_PACKET_FORMS_DIR")
        if env:
            return Path(env)
        return Path.home() / ".config/open-packet/forms"
```

**c) Update `open_compose`** — add `body` parameter:

```python
    def open_compose(self, to_call: str = "", subject: str = "", body: str = "") -> None:
        self.push_screen(
            ComposeScreen(to_call=to_call, subject=subject, body=body),
            callback=self._on_compose_result,
        )
```

**d) Add `open_form_compose` and its callbacks** — add after `open_compose_bulletin`:

```python
    def open_form_compose(self) -> None:
        from open_packet.forms.loader import discover_forms
        from open_packet.ui.tui.screens.form_picker import FormPickerScreen
        forms = discover_forms(self.forms_dir)
        self.push_screen(FormPickerScreen(forms), callback=self._on_form_picker_result)

    def _on_form_picker_result(self, form_def) -> None:
        if form_def is None:
            return
        from open_packet.ui.tui.screens.form_fill import FormFillScreen
        self.push_screen(FormFillScreen(form_def), callback=self._on_form_fill_result)

    def _on_form_fill_result(self, result) -> None:
        if result is None:
            return
        subject, body = result
        self.open_compose(subject=subject, body=body)
```

**e) Update `main()`** — add `--forms-dir` argument and pass it to the app:

In `main()`, after the existing `parser.add_argument("--console-log", ...)` line, add:
```python
    parser.add_argument("--forms-dir", default=None, help="Path to forms directory")
```

After the existing `console_log = ...` line, add:
```python
    forms_dir = args.forms_dir or os.environ.get("OPEN_PACKET_FORMS_DIR")
```

Change the app instantiation line to:
```python
    app = OpenPacketApp(db_path=db_path, console_log=console_log, forms_dir=forms_dir)
```

- [ ] **Step 4: Run full test suite**

```bash
uv run pytest -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add open_packet/ui/tui/screens/compose.py \
        open_packet/ui/tui/screens/main.py \
        open_packet/ui/tui/app.py
git commit -m "feat: wire up form flow — compose body param, 'f' binding, app entry points"
```
