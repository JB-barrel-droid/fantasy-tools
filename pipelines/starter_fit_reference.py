"""JEG-1483 policy oracle, consuming existing engine starter/roster/noise facts.

This does not price players, choose a lineup, or replace the existing roster
construction algorithm. It independently specifies the approved four-entry
decision and published-source composition for cross-language contract tests.
"""
import math

PUBLISHED = ("usatoday", "fantasypros", "cbs")


def finite(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def published_quote(values):
    sources = [key for key in PUBLISHED if finite(values.get(key))]
    numbers = [values[key] for key in sources]
    value = sum(numbers) / len(numbers) if numbers else None
    return {"sources": sources, "value": value, "average": value if len(numbers) >= 2 else None,
            "fitAvailable": len(numbers) >= 2, "coverage": f"{len(numbers)} of 3"}


def minimum_check(value, noise, setting, *, ours):
    if not finite(value):
        return None
    setting = setting or {}
    tier = setting.get("tier", "any" if ours else "neutral")
    threshold, strict = 0, ours
    if tier == "noise":
        if not finite(noise):
            return None
        threshold = noise if ours else -noise
    elif tier == "gain" and not ours:
        strict = True
    elif tier == "custom":
        custom = setting.get("value")
        threshold = (max(0, custom) if ours else custom) if finite(custom) else 0
        strict = ours and threshold == 0
    return value > threshold if strict else value >= threshold


def classify(questions, settings, *, waivers=False):
    """Input quantities come from the original engine, never package totals."""
    us, our_roster, them, their_roster = questions
    ours = minimum_check(us.get("value"), us.get("tolerance"), settings.get("ourMinimum"), ours=True)
    theirs = minimum_check(them.get("value"), them.get("tolerance"), settings.get("theirMinimum"), ours=False)
    roster = lambda q: q.get("value") if q.get("status") == "known" and isinstance(q.get("value"), bool) else None
    predicates = [ours, roster(our_roster)] + ([] if waivers else [theirs, roster(their_roster)])
    natural = not waivers and all(value is True for value in predicates)
    return {"natural": natural, "label": "Pickup" if waivers else "Natural fit" if natural else "Not judged" if None in predicates else "Other",
            "predicates": predicates}
