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
