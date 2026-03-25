def _label_text(label) -> str:
    if hasattr(label, "renderable"):
        return str(label.renderable)
    return str(label.content)
