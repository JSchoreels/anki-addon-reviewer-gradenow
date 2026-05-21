#!/usr/bin/env python3

import os
import sys
import unittest
from unittest.mock import Mock, patch


sys.path.insert(0, os.path.dirname(__file__))

from mecab import MecabAnalyzer, contains_cjk, is_cjk_char


def analyzer_with_base_cmd():
    analyzer = object.__new__(MecabAnalyzer)
    analyzer._commands = ["mecab"]
    analyzer.base_cmd = ["mecab"]
    analyzer.encoding = "utf-8"
    return analyzer


class TestMecabAnalyzer(unittest.TestCase):
    def test_extract_lemmas_japanese_verb_conjugated(self):
        completed_process = Mock(
            returncode=0,
            stdout=(
                "食べ\t動詞,自立,*,*,一段,連用形,食べる,タベ,タベ\n"
                "て\t助詞,接続助詞,*,*,*,*,て,テ,テ\n"
                "いる\t動詞,非自立,*,*,一段,基本形,いる,イル,イル\n"
                "EOS\n"
            ),
        )

        with patch("mecab.subprocess.run", return_value=completed_process):
            result, positions = analyzer_with_base_cmd().extract_lemmas_with_positions("食べている")

        for lemma in ["食べ", "食べる", "て", "いる"]:
            self.assertIn(lemma, result)
        self.assertEqual(positions["食べる"], 0)

    def test_extract_lemmas_empty_or_whitespace_string(self):
        completed_process = Mock(returncode=0, stdout="EOS\n")

        with patch("mecab.subprocess.run", return_value=completed_process):
            self.assertEqual(
                analyzer_with_base_cmd().extract_lemmas_with_positions(""),
                ([], {}),
            )
            self.assertEqual(
                analyzer_with_base_cmd().extract_lemmas_with_positions("   \t\n"),
                ([], {}),
            )

    def test_extract_lemmas_mecab_unavailable(self):
        analyzer = analyzer_with_base_cmd()
        analyzer.base_cmd = None

        result, positions = analyzer.extract_lemmas_with_positions("食べている")

        self.assertEqual(result, [])
        self.assertEqual(positions, {})

    def test_extract_lemmas_filters_asterisk(self):
        completed_process = Mock(
            returncode=0,
            stdout="test\t名詞,一般,*,*,*,*,*,*,*\nEOS\n",
        )

        with patch("mecab.subprocess.run", return_value=completed_process):
            result, positions = analyzer_with_base_cmd().extract_lemmas_with_positions("test")

        self.assertNotIn("*", result)
        self.assertEqual(result, ["test"])
        self.assertEqual(positions["test"], 0)

    def test_extract_lemmas_handles_parsing_error(self):
        with self.assertLogs("mecab", level="WARNING"):
            with patch("mecab.subprocess.run", side_effect=Exception("MeCab parsing error")):
                result, positions = analyzer_with_base_cmd().extract_lemmas_with_positions("test")

        self.assertEqual(result, [])
        self.assertEqual(positions, {})

    def test_extract_terms_returns_surface_lemma_and_reading_without_duplicates(self):
        completed_process = Mock(
            returncode=0,
            stdout=(
                "難しかっ\t難しい\tムズカシイ\t形容詞\n"
                "た\tた\tタ\t助動詞\n"
            ),
        )

        with patch("mecab.subprocess.run", return_value=completed_process):
            result = analyzer_with_base_cmd().extract_terms("難しかった")

        self.assertEqual(result, ["難しかっ", "難しい", "ムズカシイ", "た", "タ"])

    def test_extract_terms_skips_symbols(self):
        completed_process = Mock(
            returncode=0,
            stdout="。\t。\t。\t記号\n猫\t猫\tネコ\t名詞\n",
        )

        with patch("mecab.subprocess.run", return_value=completed_process):
            result = analyzer_with_base_cmd().extract_terms("。猫")

        self.assertEqual(result, ["猫", "ネコ"])


class TestCjkDetection(unittest.TestCase):
    def test_contains_cjk_japanese(self):
        self.assertTrue(contains_cjk("こんにちは"))
        self.assertTrue(contains_cjk("カタカナ"))
        self.assertTrue(contains_cjk("漢字"))

    def test_contains_cjk_english(self):
        self.assertFalse(contains_cjk("hello world"))

    def test_contains_cjk_mixed(self):
        self.assertTrue(contains_cjk("hello こんにちは"))

    def test_is_cjk_char_ranges(self):
        self.assertTrue(is_cjk_char("あ"))
        self.assertTrue(is_cjk_char("ン"))
        self.assertTrue(is_cjk_char("漢"))
        self.assertFalse(is_cjk_char("a"))
        self.assertFalse(is_cjk_char("1"))
        self.assertFalse(is_cjk_char(" "))


if __name__ == "__main__":
    unittest.main()
