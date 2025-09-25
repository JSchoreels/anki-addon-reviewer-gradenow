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
            lemmas, _ = self.extract_lemmas_with_mecab(search_text)  # Only need lemmas here
            all_terms.extend(lemmas)

            # Also get lemmas for sub-portions that contain Japanese
            for portion in self.extract_sub_portions(search_text):
                if self.contains_cjk(portion):
                    portion_lemmas, _ = self.extract_lemmas_with_mecab(portion)  # Only need lemmas here
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
        """Extract lemmas (base forms) from Japanese text using MeCab subprocess and return position mapping"""
        if not MECAB_AVAILABLE or not _mecab_base_cmd:
            return [], {}

        lemmas = []
        positions = {}

        try:
            # Use MeCab default output format to get morphemes and positions in one call
            result = subprocess.run(_mecab_base_cmd, input=text.strip(),
                                  capture_output=True, text=True,
                                  encoding=_mecab_encoding, timeout=5)

            if result.returncode != 0:
                print("MeCab subprocess error (code {}): {}".format(result.returncode, result.stderr))
                return [], {}

            # Parse the output
            lines = result.stdout.strip().split('\n')
            position = 0

            for line in lines:
                if line == "EOS" or not line.strip():
                    continue

                parts = line.split('\t')
                if len(parts) >= 2:
                    surface = parts[0]  # Original word (今日, の, 試験, etc.)
                    features = parts[1].split(',')

                    # Extract lemma (base form) from features - it's at index 6
                    lemma = features[6] if len(features) > 6 and features[6] != '*' else surface

                    # Add surface form to lemmas list
                    if surface and surface not in lemmas:
                        lemmas.append(surface)

                    # Add dictionary form if different and meaningful
                    if (lemma and
                        lemma != '*' and
                        lemma != surface and
                        lemma not in lemmas):
                        lemmas.append(lemma)

                    # Store positions for both surface form and lemma
                    if surface and surface not in positions:
                        positions[surface] = position

                    if lemma and lemma != surface and lemma not in positions:
                        positions[lemma] = position

                    # Also store lowercase versions for case-insensitive matching
                    if surface.lower() not in positions:
                        positions[surface.lower()] = position
                    if lemma.lower() != surface.lower() and lemma.lower() not in positions:
                        positions[lemma.lower()] = position

                    position += 1

        except subprocess.TimeoutExpired:
            print("MeCab subprocess timed out")
        except Exception as e:
            print("MeCab parsing error: {}".format(e))

        return lemmas, positions

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
        # Get MeCab lemmas and positions for the search text in one call
        mecab_lemmas = []
        morpheme_positions = {}

        if MECAB_AVAILABLE:
            # Get the reviewer instance to access the method
            reviewer = reviewer_grade_now
            if reviewer.contains_cjk(self.search_text):
                mecab_lemmas, morpheme_positions = reviewer.extract_lemmas_with_mecab(self.search_text)

        # Create list of cards with their position information
        card_position_data = []

        for card_id in self.card_ids:
            card = mw.col.getCard(card_id)
            note = card.note()

            # Get the content of the search field
            try:
                field_content = note[self.config["search_field"]] if self.config["search_field"] in note else ""
            except (KeyError, IndexError):
                field_content = ""

            # Find position of this card's content in the selected text
            position = self.find_card_position_in_text(field_content, mecab_lemmas, morpheme_positions)

            card_position_data.append({
                'card_id': card_id,
                'card': card,
                'note': note,
                'field_content': field_content,
                'position': position
            })

        # Sort cards by their position in the selected text
        card_position_data.sort(key=lambda x: x['position'])

        # Now populate the list with sorted cards
        for card_data in card_position_data:
            card_id = card_data['card_id']
            card = card_data['card']
            note = card_data['note']
            field_content = card_data['field_content']

            try:
                reading_content = note["Reading"] if "Reading" in note else ""
            except (KeyError, IndexError):
                reading_content = ""

            # Get card interval information
            interval_info = self.get_card_interval_info(card)

            # Create display text with Front, Reading, and Interval
            # Use format instead of f-string for compatibility
            if reading_content:
                display_text = "Card {}: {}{}| Reading: {}{} | {}".format(
                    card_id,
                    field_content[:50],
                    '...' if len(field_content) > 50 else ' ',
                    reading_content[:25],
                    '...' if len(reading_content) > 25 else '',
                    interval_info
                )
            else:
                display_text = "Card {}: {}{} | {}".format(
                    card_id,
                    field_content[:65],
                    '...' if len(field_content) > 65 else '',
                    interval_info
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
                item.setToolTip("Exact match with selected text: '{}' | {}".format(search_text_clean, interval_info))

            elif is_mecab_base_match:
                # MeCab base form match - golden/amber highlight
                item.setCheckState(CHECKED)
                item.setBackground(QColor("#8B6914"))  # Dark golden brown
                item.setForeground(QColor("#ffffff"))
                item.setToolTip("Base form match via MeCab analysis | {}".format(interval_info))

            else:
                # Fuzzy/sub-portion match - brownish
                item.setCheckState(UNCHECKED)
                item.setBackground(QColor("#5a4a2d"))  # Dark brown
                item.setForeground(QColor("#ffffff"))
                item.setToolTip("Partial match or sub-portion | {}".format(interval_info))

            self.cards_list.addItem(item)

    def find_card_position_in_text(self, field_content, mecab_lemmas, morpheme_positions):
        """Find the position where this card's content appears in the selected text"""
        if not field_content or not field_content.strip():
            return float('inf')  # Cards with no content go to the end

        field_content_clean = field_content.strip()

        # If we have MeCab analysis, use the pre-computed morpheme positions
        if MECAB_AVAILABLE and reviewer_grade_now.contains_cjk(self.search_text) and morpheme_positions:
            # Check for exact matches in the morpheme position map
            for key in [field_content_clean, field_content_clean.lower()]:
                if key in morpheme_positions:
                    return morpheme_positions[key]

            # If no direct match, return high number but not infinity
            return 999999

        # For non-CJK text, simple substring search
        search_text_lower = self.search_text.lower()
        exact_pos = search_text_lower.find(field_content_clean.lower())
        return exact_pos if exact_pos != -1 else 999999

    def get_card_interval_info(self, card):
        """Get interval information for a card"""
        try:
            if card.type == 0:  # New card
                return "New (never reviewed)"
            elif card.type == 1:  # Learning card
                return "Learning ({}m left)".format(card.left // 60 if card.left else 0)
            elif card.type == 2:  # Review card
                if card.ivl == 0:
                    return "Review (same day)"
                elif card.ivl == 1:
                    return "Review (1 day)"
                else:
                    return "Review ({} days)".format(card.ivl)
            elif card.type == 3:  # Relearning card
                return "Relearning ({}m left)".format(card.left // 60 if card.left else 0)
            else:
                return "Unknown type"
        except Exception as e:
            return "Interval: unknown"

    def grade_selected_cards(self, grade):
        """Grade the selected cards"""
        try:
            # Get selected cards
            selected_cards = []
            for i in range(self.cards_list.count()):
                item = self.cards_list.item(i)
                if item.checkState() == CHECKED:
                    card_id = item.data(USER_ROLE)
                    selected_cards.append(card_id)

            if not selected_cards:
                showInfo("No cards selected. Please select cards to grade.")
                return

            # Grade each selected card
            graded_count = 0
            for card_id in selected_cards:
                try:
                    card = mw.col.getCard(card_id)
                    # Use Anki's reviewer grading system
                    mw.reviewer._answerCard(grade)
                    graded_count += 1
                except Exception as e:
                    print("Error grading card {}: {}".format(card_id, e))
                    continue

            # Show completion message
            grade_names = {1: "Again", 2: "Hard", 3: "Good", 4: "Easy"}
            grade_name = grade_names.get(grade, str(grade))
            showInfo("Graded {} cards as '{}'".format(graded_count, grade_name))

            # Close the dialog
            self.close()

        except Exception as e:
            showInfo("Error grading cards: {}".format(str(e)))
            # Show more detailed error for debugging
            import traceback
            showInfo("Detailed error: {}".format(traceback.format_exc()))


# Initialize the addon
reviewer_grade_now = ReviewerGradeNow()
