# Grading Data Flow

The add-on reads Anki card and note data to find matches, then updates Anki
scheduling data for the checked cards only.

Search reads selected reviewer text, add-on config (`target_deck`,
`search_field`, `exact_match`), and matching card ids through
`mw.col.find_cards()`. The dialog reads each matched card with
`mw.col.get_card()`, then reads the configured note field and optional `Reading`
field for display and sorting.

When the dialog contains exactly one matched card, that item starts checked by
default. When there are multiple matched cards, all items start unchecked so the
user must choose the cards to update.

`GradeDialog.grade_selected_cards()` reads checked card ids from the dialog list.
The grading helper resolves optional per-card desired retention overrides through
`dynamic_desired_retention.effective_desired_retention()` when that add-on is
available. It passes the checked card ids and any resolved per-card options to
Anki's `aqt.operations.scheduling.grade_now(parent, card_ids, ease,
card_options)` and runs the returned collection operation in the background.

The add-on does not compute or persist scheduling values itself. Review history,
card interval changes, stored card desired retention, and FSRS-related scheduling
updates are owned by Anki's scheduler operation.
