"""Entity mention highlighting and Markdown-to-HTML rendering for feed messages.
"""
import markdown
from brain.state.entity_highlighter import find_entity_mentions
from brain.state.entity_registry import EntityRegistry
from gui_qt.theming.palette_hash import color_for_key
from gui_qt.theming.theme import Theme


def format_message_html(text: str, registry: EntityRegistry | None, theme: Theme) -> str:
    """Formats raw message text by highlighting entity mentions using right-to-left
    span insertion and rendering markdown to HTML with output_format='html'
    to preserve inline <span> tags.
    """
    if not text:
        return ""

    if registry is not None:
        spans = find_entity_mentions(text, registry)
        # Sort spans right-to-left by start descending
        spans.sort(key=lambda s: s.start, reverse=True)

        working_text = text
        for span in spans:
            color = color_for_key(span.entity_id, theme.companion_palette)
            styled_replacement = f'<span style="color: {color}; font-weight: bold;" title="Entity: {span.entity_id}">{span.matched_text}</span>'
            working_text = working_text[:span.start] + styled_replacement + working_text[span.end:]
        processed_text = working_text
    else:
        processed_text = text

    # Render markdown to HTML preserving inline HTML span tags
    html = markdown.markdown(processed_text, output_format="html")
    return html
