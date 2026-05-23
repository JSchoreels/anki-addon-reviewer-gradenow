import logging

from aqt import mw
from aqt.qt import *
from aqt.utils import showInfo

try:
    from PyQt6.QtCore import Qt

    USER_ROLE = Qt.ItemDataRole.UserRole
    CHECKED = Qt.CheckState.Checked
    UNCHECKED = Qt.CheckState.Unchecked
    ITEM_IS_USER_CHECKABLE = Qt.ItemFlag.ItemIsUserCheckable
    QT6 = True
except ImportError:
    from PyQt5.QtCore import Qt

    USER_ROLE = Qt.UserRole
    CHECKED = Qt.Checked
    UNCHECKED = Qt.Unchecked
    ITEM_IS_USER_CHECKABLE = Qt.ItemIsUserCheckable
    QT6 = False

try:
    from .grading import run_grade_now
    from .mecab import contains_cjk, mecab_analyzer
except ImportError:
    from grading import run_grade_now
    from mecab import contains_cjk, mecab_analyzer


logger = logging.getLogger(__name__)


def exec_dialog(dialog):
    if QT6:
        dialog.exec()
    else:
        dialog.exec_()


class GradeDialog(QDialog):
    def __init__(self, parent, card_ids, search_text, config):
        super().__init__(parent)
        self.card_ids = card_ids
        self.search_text = search_text
        self.config = config
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("Grade Matching Cards")
        self.setMinimumSize(600, 500)
        self.resize(700, 600)

        layout = QVBoxLayout()

        info_text = "Found {} cards matching '{}'".format(
            len(self.card_ids), self.search_text
        )
        info_label = QLabel(info_text)
        info_label.setStyleSheet("font-weight: bold; font-size: 12px; padding: 10px;")
        layout.addWidget(info_label)

        instructions = QLabel(
            "Select cards to grade and click one of the grade buttons below:"
        )
        instructions.setStyleSheet("color: #666; font-size: 11px; padding: 5px;")
        layout.addWidget(instructions)

        self.cards_list = QListWidget()
        self.populate_cards_list()
        layout.addWidget(self.cards_list)

        select_all_btn = QPushButton("Select all")
        select_all_btn.setStyleSheet("padding: 6px 12px;")
        select_all_btn.clicked.connect(self.select_all_cards)
        layout.addWidget(select_all_btn)

        grade_label = QLabel("Choose Grade:")
        grade_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(grade_label)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        for grade, label, color in [
            (1, "Again (1)", "#ff6b6b"),
            (2, "Hard (2)", "#ffa500"),
            (3, "Good (3)", "#4ecdc4"),
            (4, "Easy (4)", "#45b7d1"),
        ]:
            button = QPushButton(label)
            button.setStyleSheet(
                "QPushButton { background-color: %s; color: white; "
                "font-weight: bold; padding: 8px 16px; }" % color
            )
            button.clicked.connect(
                lambda checked=False, grade=grade: self.grade_selected_cards(grade)
            )
            button_layout.addWidget(button)

        layout.addLayout(button_layout)
        layout.addSpacing(10)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("padding: 6px 12px;")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

        self.setLayout(layout)

    def populate_cards_list(self):
        """Populate the list with matching cards."""
        mecab_terms = []
        morpheme_positions = {}
        if mecab_analyzer.available and contains_cjk(self.search_text):
            mecab_terms, morpheme_positions = mecab_analyzer.extract_lemmas_with_positions(
                self.search_text
            )

        card_position_data = []
        for card_id in self.card_ids:
            card = mw.col.get_card(card_id)
            note = card.note()
            field_content = note_value(note, self.config["search_field"])
            card_position_data.append(
                {
                    "card_id": card_id,
                    "card": card,
                    "note": note,
                    "field_content": field_content,
                    "position": self.find_card_position_in_text(
                        field_content, morpheme_positions
                    ),
                }
            )

        card_position_data.sort(key=lambda item: item["position"])
        default_checked = len(card_position_data) == 1
        for card_data in card_position_data:
            self.cards_list.addItem(
                self.build_card_item(card_data, mecab_terms, default_checked)
            )

    def build_card_item(self, card_data, mecab_terms, default_checked=False):
        card_id = card_data["card_id"]
        card = card_data["card"]
        note = card_data["note"]
        field_content = card_data["field_content"]
        reading_content = note_value(note, "Reading")
        interval_info = self.get_card_interval_info(card)

        if reading_content:
            display_text = "Card {}: {}{}| Reading: {}{} | {}".format(
                card_id,
                field_content[:50],
                "..." if len(field_content) > 50 else " ",
                reading_content[:25],
                "..." if len(reading_content) > 25 else "",
                interval_info,
            )
        else:
            display_text = "Card {}: {}{} | {}".format(
                card_id,
                field_content[:65],
                "..." if len(field_content) > 65 else "",
                interval_info,
            )

        item = QListWidgetItem(display_text)
        item.setData(USER_ROLE, card_id)
        item.setFlags(item.flags() | ITEM_IS_USER_CHECKABLE)
        self.apply_match_style(
            item, field_content, mecab_terms, interval_info, default_checked
        )
        return item

    def apply_match_style(
        self, item, field_content, mecab_terms, interval_info, default_checked=False
    ):
        item.setCheckState(CHECKED if default_checked else UNCHECKED)
        field_content_clean = field_content.strip()
        search_text_clean = self.search_text.strip()
        is_exact_match = field_content_clean.lower() == search_text_clean.lower()
        is_mecab_base_match = (
            bool(field_content_clean)
            and field_content_clean != search_text_clean
            and field_content_clean in mecab_terms
        )

        if is_exact_match:
            item.setBackground(QColor("#2d5a2d"))
            item.setForeground(QColor("#ffffff"))
            item.setToolTip(
                "Exact match with selected text: '{}' | {}".format(
                    search_text_clean, interval_info
                )
            )
            return

        if is_mecab_base_match:
            item.setBackground(QColor("#8B6914"))
            item.setForeground(QColor("#ffffff"))
            item.setToolTip("Base form match via MeCab analysis | {}".format(interval_info))
            return

        item.setBackground(QColor("#5a4a2d"))
        item.setForeground(QColor("#ffffff"))
        item.setToolTip("Partial match or token match | {}".format(interval_info))

    def find_card_position_in_text(self, field_content, morpheme_positions):
        if not field_content or not field_content.strip():
            return float("inf")

        field_content_clean = field_content.strip()
        if contains_cjk(self.search_text) and morpheme_positions:
            for key in [field_content_clean, field_content_clean.lower()]:
                if key in morpheme_positions:
                    return morpheme_positions[key]
            return 999999

        position = self.search_text.lower().find(field_content_clean.lower())
        return position if position != -1 else 999999

    def get_card_interval_info(self, card):
        try:
            if card.type == 0:
                return "New (never reviewed)"
            if card.type == 1:
                return "Learning ({}m left)".format(card.left // 60 if card.left else 0)
            if card.type == 2:
                if card.ivl == 0:
                    return "Review (same day)"
                if card.ivl == 1:
                    return "Review (1 day)"
                return "Review ({} days)".format(card.ivl)
            if card.type == 3:
                return "Relearning ({}m left)".format(card.left // 60 if card.left else 0)
        except Exception:
            logger.warning("failed to read card interval information", exc_info=True)
            return "Interval: unknown"

        return "Unknown type"

    def selected_card_ids(self):
        selected_cards = []
        for i in range(self.cards_list.count()):
            item = self.cards_list.item(i)
            if item.checkState() == CHECKED:
                selected_cards.append(item.data(USER_ROLE))
        return selected_cards

    def select_all_cards(self):
        for i in range(self.cards_list.count()):
            self.cards_list.item(i).setCheckState(CHECKED)

    def grade_selected_cards(self, grade):
        """Grade the selected cards."""
        try:
            selected_cards = self.selected_card_ids()
            if not selected_cards:
                showInfo("No cards selected. Please select cards to grade.")
                return

            run_grade_now(self, selected_cards, grade)

            grade_names = {1: "Again", 2: "Hard", 3: "Good", 4: "Easy"}
            showInfo(
                "Graded {} cards as '{}'".format(
                    len(selected_cards), grade_names.get(grade, str(grade))
                )
            )
            self.close()

        except Exception:
            logger.exception("failed to grade selected cards")
            showInfo("Error grading cards. See logs for details.")


def note_value(note, field_name):
    try:
        return note[field_name] if field_name in note else ""
    except (KeyError, IndexError):
        return ""
