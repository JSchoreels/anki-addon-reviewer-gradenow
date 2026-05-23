# Reviewer Grade Now

Reviewer Grade Now lets you grade matching cards directly from selected text in
Anki's reviewer.

While reviewing, select text on the current card, right-click, and choose
`Grade matching cards: ...`. The add-on searches your collection for cards whose
configured note field matches that text, shows the matching cards in a dialog,
and lets you apply Anki's normal `Again`, `Hard`, `Good`, or `Easy` grade to the
checked cards.

## What It Is For

This is useful when a card reminds you of related cards that should receive the
same review outcome. For example, if you notice one expression should be marked
`Again`, you can quickly find cards with the same selected expression and grade
them together.

The add-on does not create cards, edit notes, or implement its own scheduling
logic. It passes the checked card ids to Anki's built-in grade-now scheduler
operation.

## Basic Usage

1. Review a card in Anki.
2. Select text on the card.
3. Right-click the selected text.
4. Choose `Grade matching cards: ...`.
5. Check the cards you want to update.
6. Click `Again`, `Hard`, `Good`, or `Easy`.

If exactly one card is found, it is checked by default. If multiple cards are
found, they start unchecked so you can choose the exact cards to update.

## Configuration

Open the add-on configuration from Anki's add-on manager.

- `target_deck`: limit searches to one deck. Leave empty to search all decks.
- `search_field`: note field to search. Default: `Front`.
- `exact_match`: when enabled, the configured field must match the selected text
  exactly. When disabled, wildcard matching is used.

## Japanese, Chinese, and Korean Text

The add-on can use MeCab for CJK morphology-aware searching. This helps selected
Japanese text match related surfaces, lemmas, and readings instead of only the
literal selected text.

MeCab is optional. If MeCab is not installed, the add-on still works, but CJK
morphology expansion is disabled.

The add-on looks for a `mecab` command in:

- your system `PATH`
- `/usr/local/bin/mecab`
- `/opt/homebrew/bin/mecab`

On macOS with Homebrew, a typical installation is:

```bash
brew install mecab mecab-ipadic
```

After installing MeCab, restart Anki so the add-on can detect it.

## Data And Scheduling

The add-on reads matching cards and note fields from your current Anki
collection. When you click a grade button, it updates the checked cards through
Anki's scheduler, the same scheduling system used by normal review actions.

The add-on does not store extra scheduling data. Review history, intervals, FSRS
updates, and card state changes are handled by Anki.

## Limitations

- Desktop Anki only.
- Matching depends on the configured field name.
- MeCab-based CJK search requires a working system MeCab installation.
- Always review the checked cards before grading multiple matches.

## Troubleshooting

If no cards are found, check:

- the selected text
- the configured `search_field`
- the `target_deck` setting
- whether `exact_match` is too strict for your notes

If CJK token matching is not working, confirm that `mecab --version` works in a
terminal and restart Anki.
