"""Focus field width and concise note regressions."""

from PyQt6.QtWidgets import QFormLayout, QFrame, QLabel, QSizePolicy

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


def test_focus_and_map_cards_share_width(window):
    app, widget, _workspace = window
    mapping = widget.pages["Intensity map"]
    widget.tabs.setCurrentWidget(mapping)
    for width in (800, 1400):
        widget.resize(width, 700)
        app.processEvents()
        cards = {}
        for card in mapping.centralWidget().findChildren(QFrame, "studioCard"):
            title = card.findChild(QLabel, "cardTitle")
            if title is not None:
                cards[title.text()] = card
        widths = [cards[name].width() for name in ("Scan", "Z focus stack", "Counter", "Output")]
        assert max(widths) - min(widths) <= 1, widths
