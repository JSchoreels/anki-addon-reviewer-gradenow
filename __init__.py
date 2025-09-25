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
import subprocess
import functools

# MeCab integration for Japanese morphological analysis
_MECAB_NODE_PARTS = ["%f[6]", "%m", "%f[7]", "%f[0]", "%f[1]", "%f[10]"]  # lemma, surface, reading, pos, subpos, alt_lemma
_MECAB_ARGS = [
    "--node-format={}\t".format("\t".join(_MECAB_NODE_PARTS)),
    "--eos-format=\n",
    "--unk-format=",
]

MECAB_AVAILABLE = False
_mecab_base_cmd = None
_mecab_encoding = "utf-8"

def setup_mecab_subprocess():
    """Setup MeCab using subprocess (like the syntax highlighting addon)"""
    global MECAB_AVAILABLE, _mecab_base_cmd, _mecab_encoding

    try:
        # Try to find MeCab command
        mecab_commands = ["mecab", "/usr/local/bin/mecab", "/opt/homebrew/bin/mecab"]

        for cmd in mecab_commands:
            try:
                # Test if MeCab is available
                result = subprocess.run([cmd, "--version"],
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    _mecab_base_cmd = [cmd]

                    # Get encoding info
                    dict_info = subprocess.run([cmd, "-D"],
                                             capture_output=True, text=True, timeout=5)
                    if dict_info.returncode == 0:
                        charset_match = re.search(r"^charset:\s*(.*)$", dict_info.stdout, re.M)
                        if charset_match:
                            _mecab_encoding = charset_match.group(1).strip()

                    MECAB_AVAILABLE = True
                    print("MeCab subprocess setup successful with command: {}".format(cmd))
                    return
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue

        print("MeCab command not found. Japanese morphological analysis will be disabled.")

    except Exception as e:
        print("MeCab subprocess setup failed: {}. Japanese morphological analysis will be disabled.".format(e))

# Initialize MeCab using subprocess
setup_mecab_subprocess()

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
            # Merge configs without using ** unpacking for compatibility
            merged_config = default_config.copy()
            merged_config.update(config)
            return merged_config
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

            action = menu.addAction("Grade matching cards: '{}'".format(text_preview))
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
                showInfo("No cards found matching '{}' or its sub-portions in field '{}'".format(search_text, field_name))
                return

            # Show grading dialog
            self.show_grade_dialog(card_ids, search_text)

        except Exception as e:
            showInfo("Error searching cards: {}".format(str(e)))

    def build_search_queries(self, search_text, field_name, deck_filter):
        """Build search queries for original text and all sub-portions"""
        queries = []

        # Get all search terms (original + sub-portions + MeCab lemmas)
        all_terms = [search_text] + self.extract_sub_portions(search_text)

        # Add MeCab analysis if available and text contains Japanese
        if MECAB_AVAILABLE and self.contains_cjk(search_text):
            lemmas = self.extract_lemmas_with_mecab(search_text)
            all_terms.extend(lemmas)

            # Also get lemmas for sub-portions that contain Japanese
            for portion in self.extract_sub_portions(search_text):
                if self.contains_cjk(portion):
                    portion_lemmas = self.extract_lemmas_with_mecab(portion)
                    all_terms.extend(portion_lemmas)

        # Remove duplicates while preserving order
        seen = set()
        unique_terms = []
        for term in all_terms:
            if term not in seen and len(term.strip()) >= 1:
                seen.add(term)
                unique_terms.append(term)

        # Build queries for each term
        for term in unique_terms:
            query = self._build_single_query(term, field_name, deck_filter)
            queries.append(query)

        return queries

    def _build_single_query(self, term, field_name, deck_filter):
        """Build a single search query for a given term"""
        # Build the field search part
        if self.config["exact_match"]:
            field_query = '"{0}:{1}"'.format(field_name, term)
        else:
            field_query = '{0}:*{1}*'.format(field_name, term)

        # Add deck filter if specified
        if deck_filter:
            return 'deck:"{0}" {1}'.format(deck_filter, field_query)
        else:
            return field_query

    def extract_sub_portions(self, text):
        """Extract meaningful portions from text using MeCab parsing if available, fallback to substring extraction"""
        portions = []
        text = text.strip()

        # Use MeCab parsing if available and text contains CJK characters
        if MECAB_AVAILABLE and self.contains_cjk(text):
            portions = self.extract_morphemes_with_mecab(text)
            # If MeCab parsing succeeded, return the morphemes
            if portions:
                return portions

        # Fallback to substring extraction for non-CJK text or if MeCab fails
        portion_set = set()
        for start in range(len(text)):
            for end in range(start + 1, len(text) + 1):
                substring = text[start:end]
                if substring.strip():
                    portion_set.add(substring.strip())

        # Remove the original text from portions to avoid duplication
        portion_set.discard(text)
        return list(portion_set)

    def extract_morphemes_with_mecab(self, text):
        """Extract individual morphemes (words/particles) from Japanese text using MeCab"""
        if not MECAB_AVAILABLE or not _mecab_base_cmd:
            return []

        morphemes = []

        try:
            # Use MeCab to break down the sentence into morphemes
            cmd = _mecab_base_cmd + ["--node-format=%m\t%f[6]\t%f[7]\t%f[0]\n", "--eos-format=", "--unk-format=%m\t*\t*\t*\n"]

            result = subprocess.run(cmd, input=text.strip(),
                                  capture_output=True, text=True,
                                  encoding=_mecab_encoding, timeout=5)

            if result.returncode != 0:
                print("MeCab morpheme extraction error (code {}): {}".format(result.returncode, result.stderr))
                return []

            # Parse the output to extract morphemes
            lines = result.stdout.strip().split('\n')

            for line in lines:
                if not line.strip():
                    continue

                parts = line.split('\t')
                if len(parts) >= 4:
                    surface = parts[0]      # Original morpheme
                    reading = parts[1]      # Reading (position 6)
                    lemma = parts[2]        # Dictionary form (position 7)
                    pos = parts[3]          # Part of speech (position 0)

                    # Skip certain parts of speech that are less useful for searching
                    skip_pos = ['記号', '補助記号', '空白']  # symbols, auxiliary symbols, whitespace
                    if pos in skip_pos:
                        continue

                    # Add the surface form (original morpheme)
                    if surface and surface not in morphemes:
                        morphemes.append(surface)

                    # Add dictionary form if different and meaningful
                    if (lemma and
                        lemma != '*' and
                        lemma != surface and
                        lemma not in morphemes):
                        morphemes.append(lemma)

                    # Add reading for hiragana/katakana matching
                    if (reading and
                        reading != '*' and
                        reading != surface and
                        reading != lemma and
                        reading not in morphemes):
                        morphemes.append(reading)

        except subprocess.TimeoutExpired:
            print("MeCab morpheme extraction timed out")
        except Exception as e:
            print("MeCab morpheme extraction error: {}".format(e))

        return morphemes

    def extract_lemmas_with_mecab(self, text):
        """Extract lemmas (base forms) from Japanese text using MeCab subprocess"""
        if not MECAB_AVAILABLE or not _mecab_base_cmd:
            return []

        lemmas = []

        try:
            # Use detailed output format to get lemma information
            # Format: surface, features (POS, subPOS, etc.), lemma
            cmd = _mecab_base_cmd + ["--node-format=%m\t%f[6]\t%f[7]\n", "--eos-format=", "--unk-format=%m\t*\t*\n"]

            result = subprocess.run(cmd, input=text.strip(),
                                  capture_output=True, text=True,
                                  encoding=_mecab_encoding, timeout=5)

            if result.returncode != 0:
                print("MeCab subprocess error (code {}): {}".format(result.returncode, result.stderr))
                return []

            # Parse the output
            lines = result.stdout.strip().split('\n')

            for line in lines:
                if not line.strip():
                    continue

                parts = line.split('\t')
                if len(parts) >= 3:
                    surface = parts[0]  # Original word
                    reading = parts[1]  # Reading (position 6)
                    lemma = parts[2]    # Dictionary form (position 7)

                    # Add surface form
                    if surface and surface not in lemmas:
                        lemmas.append(surface)

                    # Add dictionary form if different and meaningful
                    if (lemma and
                        lemma != '*' and
                        lemma != surface and
                        lemma not in lemmas):
                        lemmas.append(lemma)

                    # Add reading if different and meaningful (for katakana/hiragana matching)
                    if (reading and
                        reading != '*' and
                        reading != surface and
                        reading != lemma and
                        reading not in lemmas):
                        lemmas.append(reading)

        except subprocess.TimeoutExpired:
            print("MeCab subprocess timed out")
        except Exception as e:
            print("MeCab parsing error: {}".format(e))

        return lemmas

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
        info_text = "Found {} cards matching '{}'".format(len(self.card_ids), self.search_text)
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
        # Get MeCab lemmas for the search text to identify base form matches
        mecab_lemmas = []
        if MECAB_AVAILABLE:
            # Get the reviewer instance to access the method
            reviewer = reviewer_grade_now
            if reviewer.contains_cjk(self.search_text):
                mecab_lemmas = reviewer.extract_lemmas_with_mecab(self.search_text)

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
            # Use format instead of f-string for compatibility
            if reading_content:
                display_text = "Card {}: {}{}| Reading: {}{}".format(
                    card_id,
                    field_content[:60],
                    '...' if len(field_content) > 60 else ' ',
                    reading_content[:30],
                    '...' if len(reading_content) > 30 else ''
                )
            else:
                display_text = "Card {}: {}{}".format(
                    card_id,
                    field_content[:80],
                    '...' if len(field_content) > 80 else ''
                )

            item = QListWidgetItem(display_text)
            item.setData(USER_ROLE, card_id)
            item.setFlags(item.flags() | ITEM_IS_USER_CHECKABLE)

            # Determine match type and highlight accordingly
            field_content_clean = field_content.strip()
            search_text_clean = self.search_text.strip()

            # Check for exact match with original search text
            is_exact_match = field_content_clean.lower() == search_text_clean.lower()

            # Check for MeCab base form match
            is_mecab_base_match = False
            if mecab_lemmas and field_content_clean:
                for lemma in mecab_lemmas:
                    if lemma != search_text_clean and field_content_clean == lemma:
                        is_mecab_base_match = True
                        break

            if is_exact_match:
                # Exact match with original search text - bright green
                item.setCheckState(CHECKED)
                item.setBackground(QColor("#2d5a2d"))  # Dark green
                item.setForeground(QColor("#ffffff"))
                item.setToolTip("Exact match with selected text: '{}'".format(search_text_clean))

            elif is_mecab_base_match:
                # MeCab base form match - golden/amber highlight
                item.setCheckState(CHECKED)
                item.setBackground(QColor("#8B6914"))  # Dark golden brown
                item.setForeground(QColor("#ffffff"))
                item.setToolTip("Base form match via MeCab analysis")

            else:
                # Fuzzy/sub-portion match - brownish
                item.setCheckState(UNCHECKED)
                item.setBackground(QColor("#5a4a2d"))  # Dark brown
                item.setForeground(QColor("#ffffff"))
                item.setToolTip("Partial match or sub-portion")

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

        if not askUser("Grade {} cards with grade {}?".format(len(selected_card_ids), grade)):
            return

        try:
            grade_now(parent=self, card_ids=selected_card_ids, ease=grade, dialog=self)
            showInfo("Successfully graded {} cards".format(len(selected_card_ids)))
            self.close()

        except Exception as e:
            showInfo("Error grading cards: {}".format(str(e)))
            # Show more detailed error for debugging
            import traceback
            showInfo("Detailed error: {}".format(traceback.format_exc()))


# Initialize the addon
reviewer_grade_now = ReviewerGradeNow()
