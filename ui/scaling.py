from PyQt6.QtWidgets import QSizePolicy


def set_text_button_min_width(button, width: int):
    button.setMinimumWidth(width)
    button.setSizePolicy(
        QSizePolicy.Policy.Minimum,
        QSizePolicy.Policy.Fixed,
    )
