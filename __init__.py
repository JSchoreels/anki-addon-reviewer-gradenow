import logging

from aqt import gui_hooks, mw
from aqt.utils import showInfo

try:
    from .grade_dialog import GradeDialog, CHECKED, UNCHECKED, exec_dialog
    from .search import build_search_queries
except ImportError:
    from grade_dialog import GradeDialog, CHECKED, UNCHECKED, exec_dialog
    from search import build_search_queries


logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "target_deck": "",
    "search_field": "Front",
    "exact_match": True,
}


class ReviewerGradeNow:
    def __init__(self):
        self.config = self.load_config()
        self.setup_reviewer_hook()

    def load_config(self):
        """Load supported add-on configuration keys."""
        config = DEFAULT_CONFIG.copy()

        try:
            stored_config = mw.addonManager.getConfig(__name__) or {}
        except Exception:
            logger.exception("failed to load reviewer grade-now config")
            return config

        for key in DEFAULT_CONFIG:
            if key in stored_config:
                config[key] = stored_config[key]
        return config

    def setup_reviewer_hook(self):
        """Add the selected-text grading action to the reviewer context menu."""
        gui_hooks.webview_will_show_context_menu.append(self.on_webview_context_menu)

    def on_webview_context_menu(self, webview, menu):
        """Handle right-clicks in the reviewer webview."""
        if not hasattr(mw, "reviewer") or not mw.reviewer or mw.state != "review":
            return

        selected_text = webview.selectedText()
        if not selected_text or not selected_text.strip():
            return

        if not menu.isEmpty():
            menu.addSeparator()

        search_text = selected_text.strip()
        text_preview = search_text[:30]
        if len(search_text) > 30:
            text_preview += "..."

        action = menu.addAction("Grade matching cards: '{}'".format(text_preview))
        action.triggered.connect(lambda: self.search_and_grade_cards(search_text))

    def search_and_grade_cards(self, search_text):
        """Find matching cards and open the grading dialog."""
        try:
            field_name = self.config["search_field"]
            search_queries = build_search_queries(
                search_text=search_text,
                field_name=field_name,
                deck_filter=self.config["target_deck"],
                exact_match=self.config["exact_match"],
            )

            seen_card_ids = set()
            card_ids = []
            for query in search_queries:
                for card_id in mw.col.find_cards(query):
                    if card_id not in seen_card_ids:
                        seen_card_ids.add(card_id)
                        card_ids.append(card_id)

            if not card_ids:
                showInfo(
                    "No cards found matching '{}' in field '{}'".format(
                        search_text, field_name
                    )
                )
                return

            self.show_grade_dialog(card_ids, search_text)

        except Exception:
            logger.exception("failed to search cards for selected text")
            showInfo("Error searching cards. See logs for details.")

    def show_grade_dialog(self, card_ids, search_text):
        """Show dialog to grade the matching cards."""
        exec_dialog(GradeDialog(mw, card_ids, search_text, self.config))


reviewer_grade_now = ReviewerGradeNow()
