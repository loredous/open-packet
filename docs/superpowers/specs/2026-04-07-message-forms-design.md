# Message Template Forms — Design Spec

**Date:** 2026-04-07

## Overview

Users can define structured message forms as YAML files. Filling out a form produces a Jinja2-rendered subject and body that pre-fill the standard compose screen. This is modeled after ICS (Incident Command System) fillable forms from FEMA, enabling standardized packet radio messages for emergency and other structured communications.

## YAML Form Schema

Forms are `.yaml` files stored in a forms directory (default: `~/.config/open-packet/forms/`). Subdirectories are purely organizational and have no semantic meaning — category is always declared in the file itself. A file missing any required top-level key raises `FormLoadError` and is skipped.

### Required top-level keys

| Key | Type | Description |
|-----|------|-------------|
| `name` | string | Display name shown in the form picker |
| `category` | string | Groups forms in the picker UI |
| `fields` | list | One or more field definitions (see below) |
| `subject_template` | string | Jinja2 template for the message subject |
| `body_template` | string | Jinja2 template for the message body |

### Field definition keys

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `name` | string | yes | Template variable name (used in Jinja2 templates) |
| `label` | string | yes | Display label in the form UI |
| `description` | string | no | Dim helper text shown below the field |
| `type` | string | no | `text` (default), `textarea`, `datetime` |
| `choices` | list | no | If present, field renders as a `Select` widget |
| `required` | bool | no | Defaults to `false` |
| `min_length` | int | no | Minimum character count |
| `max_length` | int | no | Maximum character count |
| `pattern` | string | no | Regex the value must fully match |
| `format` | string | no | `strftime` format string; only valid on `datetime` fields |
| `auto_populate` | bool | no | Pre-fill with `datetime.now()` on open; only valid on `datetime` fields |

When `choices` is provided, the field renders as a `Select` regardless of the `type` value.

### Example

```yaml
name: ICS-213 General Message
category: ICS
fields:
  - name: incident_name
    label: Incident Name
    required: true
    max_length: 50

  - name: to_position
    label: To (Position)
    description: Recipient position or title
    required: true
    max_length: 40

  - name: priority
    label: Priority
    choices: [Routine, Priority, Immediate]
    required: true

  - name: message_text
    label: Message
    type: textarea
    required: true
    min_length: 1
    max_length: 500

  - name: message_date
    label: Date/Time
    type: datetime
    format: "%Y-%m-%d %H:%M"
    auto_populate: true

subject_template: "ICS-213 {{ priority }}: {{ incident_name }}"
body_template: |
  ICS-213 GENERAL MESSAGE
  To: {{ to_position }}
  Priority: {{ priority }}
  Date/Time: {{ message_date }}

  {{ message_text }}
```

## Architecture

This feature follows the existing layered pattern. All non-UI logic lives in a new `open_packet/forms/` module. TUI screens are thin consumers.

### `open_packet/forms/` module

```
open_packet/forms/
    __init__.py
    loader.py      # YAML loading, directory scanning, dataclasses
    validator.py   # per-field validation logic
    renderer.py    # Jinja2 subject + body rendering
```

**`loader.py`**

Defines dataclasses:
- `FormField` — mirrors field definition schema
- `FormDefinition` — top-level form with name, category, fields, templates

Exposes:
- `discover_forms(forms_dir: Path) -> list[FormDefinition]` — walks directory recursively, loads all `.yaml` files, skips malformed files with a warning, returns all valid definitions
- `load_form(path: Path) -> FormDefinition` — loads a single file; raises `FormLoadError` on schema violations

Forms directory resolution order:
1. CLI argument `--forms-dir`
2. Environment variable `OPEN_PACKET_FORMS_DIR`
3. Default: `~/.config/open-packet/forms/`

**`validator.py`**

- `validate_field(field: FormField, value: str) -> list[str]` — returns list of human-readable error strings (empty = valid). Checks `required`, `min_length`, `max_length`, `pattern`, `choices`.
- `validate_form(form: FormDefinition, values: dict[str, str]) -> dict[str, list[str]]` — returns per-field error map.

**`renderer.py`**

- `render(form: FormDefinition, values: dict[str, str]) -> tuple[str, str]` — returns `(subject, body)` rendered via Jinja2. Raises `FormRenderError` on template errors.

## TUI Screens

### `screens/form_picker.py` — `FormPickerScreen`

A modal showing all discovered forms grouped by category. Uses a `Tree` widget with categories as non-selectable branch nodes and form names as leaves. Selecting a form dismisses with the chosen `FormDefinition`.

If the forms directory is missing or empty, displays: "No forms found. Create `.yaml` files in `~/.config/open-packet/forms/`."

**Entry points:**
- New key binding in `main.py` (key `f`, description "Form message") — opens picker directly
- "Use Form" button added to `ComposeScreen` — opens picker, then form fill, and returns subject + body to the compose screen

### `screens/form_fill.py` — `FormFillScreen`

A modal that dynamically builds its widget tree from a `FormDefinition`:

| Field type | Widget |
|------------|--------|
| `text` (default) | `Input` |
| `textarea` | `TextArea` |
| `datetime` | `Input`, pre-filled if `auto_populate: true` |
| has `choices` | `Select` |

Each field shows its `label` above and `description` as dim text below. Validation errors appear as red `Label` widgets beneath each field, updated on every change event. The Submit button is disabled while any validation errors exist.

A "Submit anyway" key binding (`ctrl+s`) bypasses validation — shows a confirmation warning (reusing the `shorter_path_confirm.py` pattern) before proceeding.

On submit, calls `renderer.render()` and dismisses with `(subject, body)`.

### Compose screen changes

`ComposeScreen` gains a `body` init parameter (alongside existing `to_call` and `subject`) to accept pre-filled content from a form. A "Use Form" button is added to the compose UI that opens `FormPickerScreen → FormFillScreen` and replaces the subject and body fields with the rendered output.

### Flow

```
Key binding 'f'                      "Use Form" button in ComposeScreen
       │                                          │
       ▼                                          ▼
FormPickerScreen ──(FormDefinition)──► FormFillScreen ──(subject, body)──► ComposeScreen
```

## Error Handling

| Situation | Behavior |
|-----------|----------|
| Malformed/missing YAML keys | File skipped; warning logged to console panel; not shown in picker |
| Forms directory missing | `FormPickerScreen` shows help message; no crash |
| Jinja2 render error | Shown inline in `FormFillScreen`; submission blocked |
| Field validation failure | Inline red error per field; Submit disabled |
| User bypasses validation | Confirmation warning shown; proceeds only if confirmed |

## Testing

Tests live in `tests/test_forms/`:

- `test_loader.py` — valid and invalid YAML fixtures; verifies `FormDefinition` fields populated correctly; verifies malformed files are skipped without exception
- `test_validator.py` — tests each validation rule in isolation (required, min/max length, pattern, choices)
- `test_renderer.py` — verifies Jinja2 subject and body output given known field values

No Textual UI tests for the screens (consistent with the existing test suite).
