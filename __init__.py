from aqt import mw
from aqt.operations.scheduling import (
    bury_cards,
    forget_cards,
    grade_now,
    reposition_new_cards_dialog,
    set_due_date_dialog,
    suspend_cards,
    unbury_cards,
    unsuspend_cards,
)
from aqt.reviewer import Reviewer
from aqt.utils import showInfo, askUser
from aqt.qt import *
from anki.utils import ids2str
from aqt import gui_hooks
import json
import re

# Qt compatibility fix
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

class ReviewerGradeNow:
    def __init__(self):
        self.config = self.load_config()
        self.setup_reviewer_hook()

    def load_config(self):
        """Load configuration from config.json"""
        default_config = {
            "target_deck": "",  # Empty means search all decks
            "search_field": "Front",
            "case_sensitive": False,
            "exact_match": False
        }

        try:
            config = mw.addonManager.getConfig(__name__)
            if config is None:
                return default_config
            return {**default_config, **config}
        except:
            return default_config

    def setup_reviewer_hook(self):
        """Setup the right-click context menu in reviewer"""
        # Use the webview context menu hook instead
        gui_hooks.webview_will_show_context_menu.append(self.on_webview_context_menu)

    def on_webview_context_menu(self, webview, menu):
        """Handle context menu in webview"""
        # Only add our option in the reviewer
        if not hasattr(mw, 'reviewer') or not mw.reviewer or mw.state != "review":
            return

        # Get selected text
        selected_text = webview.selectedText()

        if selected_text and selected_text.strip():
            # Add separator if menu has items
            if not menu.isEmpty():
                menu.addSeparator()

            # Add our custom action
            text_preview = selected_text.strip()[:30]
            if len(selected_text.strip()) > 30:
                text_preview += "..."

            action = menu.addAction(f"Grade matching cards: '{text_preview}'")
            action.triggered.connect(lambda: self.search_and_grade_cards(selected_text.strip()))

    def search_and_grade_cards(self, search_text):
        """Search for cards matching the text and show grading dialog"""
        try:
            # Build search query
            field_name = self.config["search_field"]
            deck_filter = self.config["target_deck"]

            # Get all search terms (original + sub-portions) and build queries
            search_queries = self.build_search_queries(search_text, field_name, deck_filter)

            # Search for matching cards using all queries
            all_card_ids = set()
            for query in search_queries:
                card_ids = mw.col.findCards(query)
                all_card_ids.update(card_ids)

            # Convert back to list
            card_ids = list(all_card_ids)

            if not card_ids:
                showInfo(f"No cards found matching '{search_text}' or its sub-portions in field '{field_name}'")
                return

            # Show grading dialog
            self.show_grade_dialog(card_ids, search_text)

        except Exception as e:
            showInfo(f"Error searching cards: {str(e)}")

    def build_search_queries(self, search_text, field_name, deck_filter):
        """Build search queries for original text and all sub-portions"""
        queries = []

        # Get all search terms (original + sub-portions)
        all_terms = [search_text] + self.extract_sub_portions(search_text)

        # Build queries for each term
        for term in all_terms:
            if len(term.strip()) >= 1:
                query = self._build_single_query(term, field_name, deck_filter)
                queries.append(query)

        return queries

    def _build_single_query(self, term, field_name, deck_filter):
        """Build a single search query for a given term"""
        # Build the field search part
        if self.config["exact_match"]:
            field_query = f'"{field_name}:{term}"'
        else:
            field_query = f'{field_name}:*{term}*'

        # Add deck filter if specified
        if deck_filter:
            return f'deck:"{deck_filter}" {field_query}'
        else:
            return field_query

    def extract_sub_portions(self, text):
        """Extract all possible consecutive sub-portions from text for searching"""
        portions = set()
        text = text.strip()

        # Generate all consecutive substrings (sliding window approach)
        # For "ABCDEF" this gives: A, AB, ABC, ABCD, ABCDE, ABCDEF, B, BC, BCD, BCDE, BCDEF, C, CD, CDE, CDEF, etc.
        for start in range(len(text)):
            for end in range(start + 1, len(text) + 1):
                substring = text[start:end]
                # Only add substrings that are meaningful (not just whitespace)
                if substring.strip():
                    portions.add(substring.strip())

        # Remove the original text from portions to avoid duplication
        portions.discard(text)

        return list(portions)

    def contains_cjk(self, text):
        """Check if text contains CJK (Chinese, Japanese, Korean) characters"""
        for char in text:
            if self.is_cjk_char(char):
                return True
        return False

    def is_cjk_char(self, char):
        """Check if a character is CJK"""
        code = ord(char)
        return (
            0x4E00 <= code <= 0x9FFF or    # CJK Unified Ideographs
            0x3400 <= code <= 0x4DBF or    # CJK Extension A
            0x20000 <= code <= 0x2A6DF or  # CJK Extension B
            0x3040 <= code <= 0x309F or    # Hiragana
            0x30A0 <= code <= 0x30FF or    # Katakana
            0xAC00 <= code <= 0xD7AF        # Hangul
        )
    def show_grade_dialog(self, card_ids, search_text):
        """Show dialog to grade the matching cards"""
        dialog = GradeDialog(mw, card_ids, search_text, self.config)
        # Qt compatibility - PyQt6 uses exec() while PyQt5 uses exec_()
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

        # Info label with better styling
        info_text = f"Found {len(self.card_ids)} cards matching '{self.search_text}'"
        info_label = QLabel(info_text)
        info_label.setStyleSheet("font-weight: bold; font-size: 12px; padding: 10px;")
        layout.addWidget(info_label)

        # Instructions label
        instructions = QLabel("Select cards to grade and click one of the grade buttons below:")
        instructions.setStyleSheet("color: #666; font-size: 11px; padding: 5px;")
        layout.addWidget(instructions)

        # Cards list
        self.cards_list = QListWidget()
        self.populate_cards_list()
        layout.addWidget(self.cards_list)

        # Grade buttons with better styling and spacing
        grade_label = QLabel("Choose Grade:")
        grade_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(grade_label)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        # Style buttons with colors
        again_btn = QPushButton("Again (1)")
        again_btn.setStyleSheet("QPushButton { background-color: #ff6b6b; color: white; font-weight: bold; padding: 8px 16px; }")
        again_btn.clicked.connect(lambda: self.grade_selected_cards(1))
        button_layout.addWidget(again_btn)

        hard_btn = QPushButton("Hard (2)")
        hard_btn.setStyleSheet("QPushButton { background-color: #ffa500; color: white; font-weight: bold; padding: 8px 16px; }")
        hard_btn.clicked.connect(lambda: self.grade_selected_cards(2))
        button_layout.addWidget(hard_btn)

        good_btn = QPushButton("Good (3)")
        good_btn.setStyleSheet("QPushButton { background-color: #4ecdc4; color: white; font-weight: bold; padding: 8px 16px; }")
        good_btn.clicked.connect(lambda: self.grade_selected_cards(3))
        button_layout.addWidget(good_btn)

        easy_btn = QPushButton("Easy (4)")
        easy_btn.setStyleSheet("QPushButton { background-color: #45b7d1; color: white; font-weight: bold; padding: 8px 16px; }")
        easy_btn.clicked.connect(lambda: self.grade_selected_cards(4))
        button_layout.addWidget(easy_btn)

        layout.addLayout(button_layout)

        # Add some spacing
        layout.addSpacing(10)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("padding: 6px 12px;")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

        self.setLayout(layout)

    def populate_cards_list(self):
        """Populate the list with matching cards"""
        for card_id in self.card_ids:
            card = mw.col.getCard(card_id)
            note = card.note()

            # Get the content of the search field and reading field
            # Use proper Anki Note field access with error handling
            try:
                field_content = note[self.config["search_field"]] if self.config["search_field"] in note else ""
            except (KeyError, IndexError):
                field_content = ""

            try:
                reading_content = note["Reading"] if "Reading" in note else ""
            except (KeyError, IndexError):
                reading_content = ""

            # Create display text with both Front and Reading
            if reading_content:
                display_text = f"Card {card_id}: {field_content[:60]}{'...' if len(field_content) > 60 else ''} | Reading: {reading_content[:30]}{'...' if len(reading_content) > 30 else ''}"
            else:
                display_text = f"Card {card_id}: {field_content[:80]}{'...' if len(field_content) > 80 else ''}"

            item = QListWidgetItem(display_text)
            item.setData(USER_ROLE, card_id)
            item.setFlags(item.flags() | ITEM_IS_USER_CHECKABLE)

            # Check if this is a perfect match
            is_perfect_match = field_content.strip().lower() == self.search_text.strip().lower()

            if is_perfect_match:
                item.setCheckState(CHECKED)
                # Use darker colors that work better in both light and dark modes
                item.setBackground(QColor("#2d5a2d"))  # Dark green background for perfect matches
                item.setForeground(QColor("#ffffff"))  # White text for better contrast
            else:
                item.setCheckState(UNCHECKED)  # Uncheck fuzzy matches by default
                item.setBackground(QColor("#5a4a2d"))  # Dark brown/orange background for fuzzy matches
                item.setForeground(QColor("#ffffff"))  # White text for better contrast

            self.cards_list.addItem(item)

    def grade_selected_cards(self, grade):
        """Grade the selected cards"""
        selected_card_ids = []

        for i in range(self.cards_list.count()):
            item = self.cards_list.item(i)
            if item.checkState() == CHECKED:
                card_id = item.data(USER_ROLE)
                selected_card_ids.append(card_id)

        if not selected_card_ids:
            showInfo("No cards selected")
            return

        if not askUser(f"Grade {len(selected_card_ids)} cards with grade {grade}?"):
            return

        try:
            grade_now(parent=self, card_ids=selected_card_ids, ease=grade, dialog=self)
            showInfo(f"Successfully graded {len(selected_card_ids)} cards")
            self.close()

        except Exception as e:
            showInfo(f"Error grading cards: {str(e)}")
            # Show more detailed error for debugging
            import traceback
            showInfo(f"Detailed error: {traceback.format_exc()}")


# Initialize the addon
reviewer_grade_now = ReviewerGradeNow()
