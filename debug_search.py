#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Debug script to test why 難しかった doesn't find cards with 難しい
"""

import sys
import os

# Add the addon directory to the path
sys.path.insert(0, os.path.dirname(__file__))

def test_search_issue():
    """Debug the search issue with 難しかった -> 難しい"""

    try:
        import MeCab
        tagger = MeCab.Tagger()
        print("✓ MeCab is available")
    except ImportError:
        print("✗ MeCab not available")
        return

    # Test the MeCab analysis first
    text = "難しかった"
    result = tagger.parse(text)
    print(f"\n=== MeCab Analysis for '{text}' ===")
    print("Raw output:")
    print(result)

    # Extract lemmas manually
    lemmas = []
    lines = result.strip().split('\n')

    for line in lines:
        if line == 'EOS' or not line.strip():
            continue

        parts = line.split('\t')
        if len(parts) >= 2:
            surface = parts[0]
            features = parts[1]
            feature_parts = features.split(',')

            print(f"\nSurface: '{surface}'")
            print(f"Feature parts (first 12):")
            for i in range(min(12, len(feature_parts))):
                print(f"  [{i}]: '{feature_parts[i]}'")

            # Add surface form
            if surface and surface not in lemmas:
                lemmas.append(surface)

            # Check position 7 (dictionary form in UniDic)
            if len(feature_parts) > 7:
                dictionary_form = feature_parts[7]
                print(f"Position [7] (dictionary form): '{dictionary_form}'")
                if (dictionary_form and
                    dictionary_form != '*' and
                    dictionary_form != '""' and
                    dictionary_form != surface and
                    dictionary_form not in lemmas):
                    lemmas.append(dictionary_form)
                    print(f"  -> Added '{dictionary_form}' to lemmas")

    print(f"\nExtracted lemmas: {lemmas}")

    # Check if 難しい is in the lemmas
    if "難しい" in lemmas:
        print("✅ SUCCESS: '難しい' found in lemmas")
    else:
        print("❌ PROBLEM: '難しい' NOT found in lemmas")

    # Test search query building
    print(f"\n=== Search Query Building ===")

    # Simulate the sub-portion extraction
    text = "難しかった"
    portions = set()

    for start in range(len(text)):
        for end in range(start + 1, len(text) + 1):
            substring = text[start:end]
            if substring.strip():
                portions.add(substring.strip())

    portions.discard(text)  # Remove original
    sub_portions = list(portions)

    print(f"Sub-portions: {sub_portions}")

    # All search terms
    all_terms = [text] + sub_portions + lemmas
    unique_terms = []
    seen = set()

    for term in all_terms:
        if term not in seen and len(term.strip()) >= 1:
            seen.add(term)
            unique_terms.append(term)

    print(f"All unique search terms: {unique_terms}")

    # Generate search queries
    print(f"\nSearch queries that would be generated:")
    for i, term in enumerate(unique_terms, 1):
        query = f"Front:*{term}*"
        print(f"  {i}: {query}")
        if term == "難しい":
            print(f"     ✅ This query should find cards with '難しい' in Front field")

    # Final check
    if "難しい" in unique_terms:
        print(f"\n✅ CONCLUSION: The search should work - '難しい' is in the search terms")
        print(f"   Query 'Front:*難しい*' should find cards with '難しい' in the Front field")
    else:
        print(f"\n❌ CONCLUSION: There's a problem - '難しい' is missing from search terms")

if __name__ == '__main__':
    test_search_issue()
