"""The final response-quality gate (spec §26).

Before a composed reply is returned, one last deterministic check runs over it, so an
answer never slips past the house rules even if an upstream lane missed something. The
checks mirror the spec's pre-send list, limited to what can be verified deterministically:

- ``capability_claim`` - the reply claims a live-system lookup the assistant cannot make
  ("I checked", "tekshirdim", "topib beraman"). This is a hard safety violation: the
  caller replaces such a reply with an honest abstention rather than shipping it.
- ``unnecessary_menu`` - a topic menu is shown although the customer's current goal is
  already known, which the spec forbids (buttons are optional, not the default).

The gate only reports; the caller decides what to act on. It never rewrites wording on
its own, so a clean reply passes through unchanged.
"""

from __future__ import annotations

from app.services.status_capability import claims_live_check

CAPABILITY_CLAIM = "capability_claim"
UNNECESSARY_MENU = "unnecessary_menu"


def _is_menu(option_values: list[str]) -> bool:
    """A topic menu uses tree ids ("imei-register"); answer buttons use "outcome:..."."""
    return bool(option_values) and all("-" in value and ":" not in value for value in option_values)


def check_reply(
    reply: str,
    *,
    option_values: list[str],
    done: bool,
    current_intent: str | None,
) -> list[str]:
    """Return the quality issues in a finished reply, most important first (§26)."""
    issues: list[str] = []
    if claims_live_check(reply):
        issues.append(CAPABILITY_CLAIM)
    if current_intent is not None and not done and _is_menu(option_values):
        issues.append(UNNECESSARY_MENU)
    return issues
