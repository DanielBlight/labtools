"""Focus field width and concise note regressions."""

from PyQt6.QtWidgets import QFormLayout, QLabel, QSizePolicy

pytest_plugins = ["test_experiment_panels"]


def test_focus_fields_expand_and_note_is_concise(window):
    _app, widget, _workspace = window
    focus = widget.pages["Intensity map"].focus_controls
    assert focus.levels.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert focus.sweeps.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
    form = focus.findChild(QFormLayout)
    assert form is not None
    assert form.fieldGrowthPolicy() == QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
    labels = [label.text() for label in focus.findChildren(QLabel)]
    notes = [text for text in labels if text.startswith("If value >1")]
    assert notes == ["If value >1, one 60V step is taken in +Z before repeating the DC sweep."]
    assert not any("controller direction" in text or "Completion/Stop" in text for text in labels)
