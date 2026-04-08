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


def test_load_form_empty_fields_raises(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text("name: X\ncategory: Y\nfields: []\nsubject_template: s\nbody_template: b\n")
    with pytest.raises(FormLoadError, match="fields"):
        load_form(f)


def test_load_form_fields_not_a_list(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text("name: X\ncategory: Y\nfields: oops\nsubject_template: s\nbody_template: b\n")
    with pytest.raises(FormLoadError, match="fields"):
        load_form(f)


def test_load_form_field_type_preserved(tmp_path):
    f = tmp_path / "form.yaml"
    f.write_text(
        "name: X\ncategory: Y\n"
        "fields:\n  - name: msg\n    label: Message\n    type: textarea\n"
        "subject_template: s\nbody_template: b\n"
    )
    form = load_form(f)
    assert form.fields[0].type == "textarea"
