#!/usr/bin/env python3

"""Debug deterministic term extraction and query building for Japanese text."""

import os
import sys


sys.path.insert(0, os.path.dirname(__file__))

from search import build_search_queries, extract_search_terms


def test_search_issue():
    text = "難しかった"

    print("=== Search terms for '{}' ===".format(text))
    terms = extract_search_terms(text)
    for index, term in enumerate(terms, 1):
        print("  {}: {}".format(index, term))

    print("\n=== Search queries ===")
    for index, query in enumerate(build_search_queries(text, "Front", "", False), 1):
        print("  {}: {}".format(index, query))

    if "難しい" in terms:
        print("\nSUCCESS: '難しい' is included in the deterministic terms")
    else:
        print("\nNOTE: '難しい' was not returned by the configured MeCab dictionary")


if __name__ == "__main__":
    test_search_issue()
