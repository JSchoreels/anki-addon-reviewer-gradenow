import logging

from aqt import mw
from aqt.operations.scheduling import grade_now


logger = logging.getLogger(__name__)


def get_effective_desired_retention(card):
    """Return an optional dynamic desired retention override for a card."""
    try:
        from dynamic_desired_retention import effective_desired_retention
    except ModuleNotFoundError as exc:
        if exc.name != "dynamic_desired_retention":
            logger.warning("dynamic desired retention import failed: %s", exc)
        return None
    except ImportError as exc:
        logger.warning("dynamic desired retention is unavailable: %s", exc)
        return None

    try:
        return effective_desired_retention(
            collection=mw.col,
            card=card,
            current_desired_retention=None,
        )
    except Exception:
        logger.warning("dynamic desired retention resolver failed", exc_info=True)
        return None


def grade_now_card_options(selected_cards):
    """Build per-card options for Anki's grade-now operation."""
    from anki import scheduler_pb2

    card_options = []
    for card_id in selected_cards:
        card = mw.col.get_card(card_id)
        desired_retention = get_effective_desired_retention(card)
        if desired_retention is None:
            continue

        card_options.append(
            scheduler_pb2.GradeNowRequest.CardOptions(
                card_id=card_id,
                desired_retention_override=float(desired_retention),
            )
        )

    return card_options


def run_grade_now(parent, selected_cards, grade):
    grade_now(
        parent=parent,
        card_ids=selected_cards,
        ease=grade,
        card_options=grade_now_card_options(selected_cards),
    ).run_in_background()
