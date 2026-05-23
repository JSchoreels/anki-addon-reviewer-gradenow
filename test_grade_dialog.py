#!/usr/bin/env python3

import importlib
import os
import sys
import types
import unittest
from unittest.mock import Mock


sys.path.insert(0, os.path.dirname(__file__))


class MockMW:
    state = "review"
    reviewer = object()

    class MockAddonManager:
        def getConfig(self, name):
            return None

    addonManager = MockAddonManager()


class MockQDialog:
    def __init__(self, *args, **kwargs):
        pass

    def close(self):
        pass


class MockGradeNowCardOptions:
    def __init__(self, card_id, desired_retention_override):
        self.card_id = card_id
        self.desired_retention_override = desired_retention_override

    def __eq__(self, other):
        return (
            isinstance(other, MockGradeNowCardOptions)
            and self.card_id == other.card_id
            and self.desired_retention_override == other.desired_retention_override
        )


class MockListWidgetItem:
    def __init__(self, text):
        self.text = text
        self._flags = 0

    def setData(self, role, value):
        self.data_role = role
        self.data_value = value

    def flags(self):
        return self._flags

    def setFlags(self, flags):
        self._flags = flags

    def setCheckState(self, check_state):
        self.check_state = check_state

    def setBackground(self, color):
        self.background = color

    def setForeground(self, color):
        self.foreground = color

    def setToolTip(self, tooltip):
        self.tooltip = tooltip


class MockQt:
    class ItemDataRole:
        UserRole = 32

    class CheckState:
        Checked = 2
        Unchecked = 0

    class ItemFlag:
        ItemIsUserCheckable = 16


def install_anki_mocks():
    mock_aqt = types.ModuleType("aqt")
    mock_aqt.mw = MockMW()

    mock_gui_hooks = types.SimpleNamespace(webview_will_show_context_menu=[])
    mock_aqt.gui_hooks = mock_gui_hooks

    mock_scheduling = types.ModuleType("aqt.operations.scheduling")
    mock_scheduling.grade_now = Mock()

    mock_operations = types.ModuleType("aqt.operations")
    mock_operations.scheduling = mock_scheduling

    mock_utils = types.ModuleType("aqt.utils")
    mock_utils.showInfo = Mock()

    mock_qt = types.ModuleType("aqt.qt")
    mock_qt.QDialog = MockQDialog
    mock_qt.QColor = Mock()
    mock_qt.QHBoxLayout = Mock()
    mock_qt.QLabel = Mock()
    mock_qt.QListWidget = Mock()
    mock_qt.QListWidgetItem = MockListWidgetItem
    mock_qt.QPushButton = Mock()
    mock_qt.QVBoxLayout = Mock()

    mock_anki = types.ModuleType("anki")
    mock_scheduler_pb2 = types.ModuleType("anki.scheduler_pb2")
    mock_scheduler_pb2.GradeNowRequest = types.SimpleNamespace(
        CardOptions=MockGradeNowCardOptions
    )

    mock_pyqt6 = types.ModuleType("PyQt6")
    mock_pyqt6_qtcore = types.ModuleType("PyQt6.QtCore")
    mock_pyqt6_qtcore.Qt = MockQt

    sys.modules.update(
        {
            "aqt": mock_aqt,
            "aqt.operations": mock_operations,
            "aqt.operations.scheduling": mock_scheduling,
            "aqt.utils": mock_utils,
            "aqt.qt": mock_qt,
            "anki": mock_anki,
            "anki.scheduler_pb2": mock_scheduler_pb2,
            "PyQt6": mock_pyqt6,
            "PyQt6.QtCore": mock_pyqt6_qtcore,
        }
    )


class MockItem:
    def __init__(self, checked, card_id):
        self._checked = checked
        self._card_id = card_id

    def checkState(self):
        return self._checked

    def setCheckState(self, check_state):
        self._checked = check_state

    def data(self, role):
        return self._card_id


class MockCardsList:
    def __init__(self, items):
        self._items = items

    def count(self):
        return len(self._items)

    def item(self, index):
        return self._items[index]


class FakeAnalyzer:
    def __init__(self, available=True, terms=None):
        self.available = available
        self.terms = terms or []

    def extract_terms(self, text):
        return self.terms


class TestReviewerGradeNow(unittest.TestCase):
    def setUp(self):
        self.module_names = [
            "__init__",
            "grade_dialog",
            "grading",
            "mecab",
            "search",
            "aqt",
            "aqt.operations",
            "aqt.operations.scheduling",
            "aqt.utils",
            "aqt.qt",
            "anki",
            "anki.scheduler_pb2",
            "PyQt6",
            "PyQt6.QtCore",
        ]
        self.previous_modules = {name: sys.modules.get(name) for name in self.module_names}
        install_anki_mocks()
        for name in ["__init__", "grade_dialog", "grading", "mecab", "search"]:
            sys.modules.pop(name, None)

        self.addon = importlib.import_module("__init__")
        self.grade_dialog = importlib.import_module("grade_dialog")
        self.grading = importlib.import_module("grading")
        self.search = importlib.import_module("search")

    def tearDown(self):
        sys.modules.pop("dynamic_desired_retention", None)
        for name in self.module_names:
            previous = self.previous_modules[name]
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous

    def test_load_config_uses_supported_defaults_and_ignores_case_sensitive(self):
        self.addon.mw.addonManager.getConfig = Mock(
            return_value={
                "target_deck": "Deck",
                "search_field": "Expression",
                "case_sensitive": True,
            }
        )

        reviewer = self.addon.ReviewerGradeNow()

        self.assertEqual(
            reviewer.config,
            {
                "target_deck": "Deck",
                "search_field": "Expression",
                "exact_match": True,
            },
        )

    def test_search_uses_current_anki_find_cards_api(self):
        reviewer = self.addon.ReviewerGradeNow()
        reviewer.config = {
            "target_deck": "",
            "search_field": "Front",
            "exact_match": False,
        }
        reviewer.show_grade_dialog = Mock()
        self.addon.mw.col = Mock()
        self.addon.mw.col.find_cards.return_value = [101]

        reviewer.search_and_grade_cards("x")

        self.addon.mw.col.find_cards.assert_called_once_with('"Front:*x*"')
        reviewer.show_grade_dialog.assert_called_once_with([101], "x")

    def test_grade_selected_cards_runs_anki_grade_operation(self):
        operation = Mock()
        self.grading.grade_now = Mock(return_value=operation)
        self.grading.mw.col = Mock()
        dialog = self.grade_dialog.GradeDialog.__new__(self.grade_dialog.GradeDialog)
        dialog.cards_list = MockCardsList(
            [
                MockItem(self.grade_dialog.CHECKED, 101),
                MockItem(self.grade_dialog.UNCHECKED, 202),
                MockItem(self.grade_dialog.CHECKED, 303),
            ]
        )
        dialog.close = Mock()

        dialog.grade_selected_cards(1)

        self.grading.grade_now.assert_called_once_with(
            parent=dialog, card_ids=[101, 303], ease=1, card_options=[]
        )
        operation.run_in_background.assert_called_once_with()
        dialog.close.assert_called_once_with()

    def test_grade_selected_cards_passes_dynamic_desired_retention_options(self):
        module = types.ModuleType("dynamic_desired_retention")
        module.effective_desired_retention = Mock(return_value=0.72)
        sys.modules["dynamic_desired_retention"] = module
        operation = Mock()
        self.grading.grade_now = Mock(return_value=operation)
        card = Mock()
        self.grading.mw.col = Mock()
        self.grading.mw.col.get_card.return_value = card
        dialog = self.grade_dialog.GradeDialog.__new__(self.grade_dialog.GradeDialog)
        dialog.cards_list = MockCardsList([MockItem(self.grade_dialog.CHECKED, 101)])
        dialog.close = Mock()

        dialog.grade_selected_cards(3)

        self.grading.grade_now.assert_called_once_with(
            parent=dialog,
            card_ids=[101],
            ease=3,
            card_options=[MockGradeNowCardOptions(101, 0.72)],
        )
        module.effective_desired_retention.assert_called_once_with(
            collection=self.grading.mw.col,
            card=card,
            current_desired_retention=None,
        )

    def test_grade_selected_cards_warns_when_none_are_checked(self):
        self.grade_dialog.showInfo.reset_mock()
        dialog = self.grade_dialog.GradeDialog.__new__(self.grade_dialog.GradeDialog)
        dialog.cards_list = MockCardsList([MockItem(self.grade_dialog.UNCHECKED, 101)])
        dialog.close = Mock()

        dialog.grade_selected_cards(1)

        self.grade_dialog.showInfo.assert_called_once_with(
            "No cards selected. Please select cards to grade."
        )
        dialog.close.assert_not_called()

    def test_populate_cards_list_uses_current_anki_get_card_api(self):
        class MockCard:
            type = 0
            left = 0
            ivl = 0

            def note(self):
                return {"Front": "x", "Reading": "reading"}

        dialog = self.grade_dialog.GradeDialog.__new__(self.grade_dialog.GradeDialog)
        dialog.card_ids = [101]
        dialog.search_text = "x"
        dialog.config = {"search_field": "Front"}
        dialog.cards_list = Mock()
        self.grade_dialog.mecab_analyzer = FakeAnalyzer(available=False)
        self.grade_dialog.mw.col = Mock()
        self.grade_dialog.mw.col.get_card.return_value = MockCard()

        dialog.populate_cards_list()

        self.grade_dialog.mw.col.get_card.assert_called_once_with(101)
        dialog.cards_list.addItem.assert_called_once()
        item = dialog.cards_list.addItem.call_args[0][0]
        self.assertEqual(item.check_state, self.grade_dialog.CHECKED)

    def test_populate_cards_list_leaves_multiple_matches_unchecked(self):
        class MockCard:
            type = 0
            left = 0
            ivl = 0

            def __init__(self, front):
                self.front = front

            def note(self):
                return {"Front": self.front, "Reading": ""}

        dialog = self.grade_dialog.GradeDialog.__new__(self.grade_dialog.GradeDialog)
        dialog.card_ids = [101, 202]
        dialog.search_text = "x"
        dialog.config = {"search_field": "Front"}
        dialog.cards_list = Mock()
        self.grade_dialog.mecab_analyzer = FakeAnalyzer(available=False)
        self.grade_dialog.mw.col = Mock()
        self.grade_dialog.mw.col.get_card.side_effect = [
            MockCard("x"),
            MockCard("x suffix"),
        ]

        dialog.populate_cards_list()

        added_items = [
            call_args[0][0] for call_args in dialog.cards_list.addItem.call_args_list
        ]
        self.assertEqual(
            [item.check_state for item in added_items],
            [self.grade_dialog.UNCHECKED, self.grade_dialog.UNCHECKED],
        )

    def test_select_all_cards_checks_every_item(self):
        dialog = self.grade_dialog.GradeDialog.__new__(self.grade_dialog.GradeDialog)
        item_one = MockItem(self.grade_dialog.UNCHECKED, 101)
        item_two = MockItem(self.grade_dialog.UNCHECKED, 202)
        dialog.cards_list = MockCardsList([item_one, item_two])

        dialog.select_all_cards()

        self.assertEqual(item_one.checkState(), self.grade_dialog.CHECKED)
        self.assertEqual(item_two.checkState(), self.grade_dialog.CHECKED)

    def test_extract_search_terms_for_non_cjk_is_ordered_and_not_substrings(self):
        terms = self.search.extract_search_terms("alpha beta alpha")

        self.assertEqual(terms, ["alpha beta alpha", "alpha", "beta"])
        self.assertNotIn("lph", terms)

    def test_extract_search_terms_for_cjk_uses_mecab_terms_when_available(self):
        terms = self.search.extract_search_terms(
            "難しかった",
            analyzer=FakeAnalyzer(available=True, terms=["難しかっ", "難しい"]),
        )

        self.assertEqual(terms, ["難しかった", "難しかっ", "難しい"])

    def test_extract_search_terms_for_cjk_falls_back_to_full_text_without_mecab(self):
        terms = self.search.extract_search_terms(
            "難しかった",
            analyzer=FakeAnalyzer(available=False, terms=["難しい"]),
        )

        self.assertEqual(terms, ["難しかった"])

    def test_build_query_handles_deck_exact_wildcard_and_quote_escaping(self):
        self.assertEqual(
            self.search.build_single_query('a "quote"', "Front", "Deck", True),
            'deck:"Deck" "Front:a \\"quote\\""',
        )
        self.assertEqual(
            self.search.build_single_query("alpha", "Front", "", False),
            '"Front:*alpha*"',
        )


if __name__ == "__main__":
    unittest.main()
