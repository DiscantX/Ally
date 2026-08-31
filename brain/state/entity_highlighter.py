"""Post-processing pass that finds entity mentions inside Ally's already-
generated spoken text, for GUI-side highlighting. Runs AFTER generation --
Ally is never asked to tag its own output (see ally_decision_log.md's
bracket-tagging lesson: asking a model to reliably self-delimit inside
natural prose hurt voice quality). Zero Qt/GUI dependency -- rendering
(color lookup, HTML wrapping) is entirely the GUI layer's job.
"""
import re
from dataclasses import dataclass

from brain.state.entity_registry import EntityRegistry

MIN_NAME_LENGTH = 3  # skip trivial/very short names to avoid false-positive substring matches


@dataclass
class HighlightSpan:
    start: int
    end: int
    entity_id: str
    matched_text: str


def find_entity_mentions(text: str, registry: EntityRegistry) -> list[HighlightSpan]:
    if not text:
        return []
    lookup = registry.name_lookup()  # lowercased name/alias -> entity_id
    candidates = [name for name in lookup if len(name) >= MIN_NAME_LENGTH]
    if not candidates:
        return []
    candidates.sort(key=len, reverse=True)  # longest-match-first, so "Marcus the Bold" wins over "Marcus" when both are known aliases
    pattern = re.compile(
        r"(?<!\w)(" + "|".join(re.escape(name) for name in candidates) + r")(?!\w)",
        re.IGNORECASE,
    )
    spans: list[HighlightSpan] = []
    for match in pattern.finditer(text):  # finditer's matches are already non-overlapping by construction
        entity_id = lookup.get(match.group(1).lower())
        if entity_id is None:
            continue
        spans.append(HighlightSpan(match.start(), match.end(), entity_id, match.group(1)))
    return spans
