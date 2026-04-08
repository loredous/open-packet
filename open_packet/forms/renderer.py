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
