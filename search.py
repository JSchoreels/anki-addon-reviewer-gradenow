import re

try:
    from .mecab import contains_cjk, mecab_analyzer
except ImportError:
    from mecab import contains_cjk, mecab_analyzer


WORD_RE = re.compile(r"\w+", re.UNICODE)


def ordered_unique(values):
    terms = []
    seen = set()
    for value in values:
        term = value.strip()
        if term and term not in seen:
            seen.add(term)
            terms.append(term)
    return terms


def extract_search_terms(search_text, analyzer=mecab_analyzer):
    """Return deterministic search terms for selected text."""
    text = search_text.strip()
    if not text:
        return []

    terms = [text]
    if contains_cjk(text):
        if analyzer and analyzer.available:
            terms.extend(analyzer.extract_terms(text))
    else:
        terms.extend(match.group(0) for match in WORD_RE.finditer(text))

    return ordered_unique(terms)


def escape_query_value(value):
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def build_single_query(term, field_name, deck_filter="", exact_match=True):
    escaped_field = escape_query_value(field_name)
    escaped_term = escape_query_value(term)

    if exact_match:
        field_query = '"{0}:{1}"'.format(escaped_field, escaped_term)
    else:
        field_query = '"{0}:*{1}*"'.format(escaped_field, escaped_term)

    if deck_filter:
        return 'deck:"{0}" {1}'.format(escape_query_value(deck_filter), field_query)
    return field_query


def build_search_queries(search_text, field_name, deck_filter="", exact_match=True):
    return [
        build_single_query(term, field_name, deck_filter, exact_match)
        for term in extract_search_terms(search_text)
    ]
