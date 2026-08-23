"""Agent A: the Scribe.

Its only job is to look at the screenshot and report what's there. It never
suggests what to do, never speculates about the plot, and never gets asked
about the game's identity. Ally never sees this prompt or this image --
only what comes out the other end.
"""

from PIL import Image

from llm.gemini_provider import GeminiProvider
from schema.schema import ScribeOutput

SCRIBE_MODEL = "gemini-3.5-flash-lite"

SCRIBE_PROMPT_GENRE_GUESS = (
    "Also provide your best guess at the game's genre (e.g. 'action RPG', "
    "'point-and-click adventure', 'turn-based strategy'), plus a confidence "
    "score from 0.0 to 1.0 for that guess. Base confidence strictly on visual "
    "evidence in *this* frame alone: a title screen or clear genre-defining "
    "HUD (e.g. a skill/cooldown bar, a hand of cards) warrants high "
    "confidence; an ambiguous cutscene or establishing shot warrants low "
    "confidence, even if you personally suspect you know the game."
)

SCRIBE_PROMPT_SCREEN_NAME_GUESS = (
    "Also provide a short (1-3 word) functional label for what kind of "
    "screen this is (e.g. 'combat', 'map', 'shop', 'title screen', "
    "'inventory'), based on what's visually distinguishable about it. "
    "This label is used to automatically name and recognize the screen "
    "later, so prefer a generic functional name over a flavorful one."
)

# Shared between UI and NO_UI prompts: how to name an element when it
# represents a named character/crew member vs. anything else. Split out
# because both prompts extract characters, and a companion should be
# able to say "Dolan," not parrot back "Crew Member Dolan" -- fixing the
# naming at the source here means every downstream consumer (Entity
# Registry's canonical_name, Ally's prompt) gets the natural form for
# free, rather than needing string surgery at each of those layers.
SCRIBE_PROMPT_NAMING_RULE = (
    "Naming rule for `label`: if the element is a named character, crew "
    "member, or NPC, `label` must be their proper name ALONE (e.g. "
    "'Dolan', never 'Crew Member Dolan' or 'Pilot Dolan') -- put their "
    "role or job in `description` instead. For anything else (an item, a "
    "button, a stat), use a short plain functional tag (e.g. 'Jump "
    "Button', 'Hull Value')."
)

SCRIBE_PROMPT_NO_UI = (
    "You are analysing a single screenshot from a game."
    "Only use information visible in this image. Do not draw on any "
    "prior knowledge you may have of this specific game -- treat it as "
    "entirely unfamiliar, even if you recognise it.\n\n"
    
    "Given what you see, take an educated guess in the genre of the game. This will"
    "help inform what you are looking for in the scene."
    
    "Ignore all UI elements. Do not include: character portraits, buttons, meters,"
    "text boxes, or icons. Instead, focus only on entities within the scene itself: "
    "Characters, set pieces, structures, and any visually distinct points of interest."
    "For each, provide:\n"
    "- id: a short unique id (e.g. 'el_01')\n"
    f"- label: a 1-3 word label. {SCRIBE_PROMPT_NAMING_RULE}\n"
    "- description: one plain sentence describing it\n"
    "- box_2d: a bounding box as [y_min, x_min, y_max, x_max], normalized "
    "0-1000\n\n"
    "Do not interpret what anything means. Do not suggest actions. "
    "Description only."
    + "\n\n" + SCRIBE_PROMPT_GENRE_GUESS
    + "\n\n" + SCRIBE_PROMPT_SCREEN_NAME_GUESS
#
)

SCRIBE_PROMPT_UI = (
    "You are analysing a single screenshot from a game. "
    "Only use information visible in this image. Do not draw on any "
    "prior knowledge you may have of this specific game -- treat it as "
    "entirely unfamiliar, even if you recognise it.\n\n"
    "Extract every interactable UI element, including every "
    "label, inventory item, and distinct physical object visible in the scene "
    "including UI elements like verb "
    "buttons if present. For each, provide:\n"
    "- id: a short unique id (e.g. 'el_01')\n"
    f"- label: a 1-3 word label. {SCRIBE_PROMPT_NAMING_RULE}\n"
    "- description: this field's job depends on what the element IS. "
    "If the element's content is text visible on screen -- dialogue, an "
    "event or narrative passage, a button's or choice's label text, a "
    "menu item, the displayed value of a stat -- transcribe that text "
    "VERBATIM, in full, exactly as written. Do not summarize, shorten, "
    "or paraphrase it, even if it's several sentences long. If the "
    "element is purely visual with no on-screen text of its own (a "
    "character sprite, a background object, an icon), write one plain "
    "sentence describing what it is instead.\n"
    "- box_2d: a bounding box as [y_min, x_min, y_max, x_max], normalized "
    "0-1000\n\n"
    "If the screen shows a block of narrative or dialogue text separately "
    "from the choice buttons that respond to it (e.g. an event's "
    "description above two response options), extract the narrative "
    "block as its OWN element -- verbatim, per the rule above -- in "
    "addition to each individual choice. Never fold the narrative into "
    "the choice elements, and never drop it in favor of only the "
    "choices: the player needs the actual text to react to, not just the "
    "buttons.\n\n"
    "IMPORTANT for box_2d: if an element combines an icon/graphic with "
    "a text or number value (e.g. a heart icon next to an HP number, or "
    "a coin icon next to a gold count), box_2d must bound ONLY the text "
    "or number -- exclude the icon entirely. This box will be used to "
    "crop exactly this region for text recognition, so a loose box that "
    "includes non-text pixels will hurt accuracy.\n\n"
    "Do not interpret what anything means. Do not suggest actions."
    + "\n\n" + SCRIBE_PROMPT_GENRE_GUESS
    + "\n\n" + SCRIBE_PROMPT_SCREEN_NAME_GUESS
)

class Scribe:
    def __init__(self, provider: GeminiProvider):
        self.provider = provider

    def extract(self, image: Image.Image, include_ui: bool = True) -> ScribeOutput:
        prompt = SCRIBE_PROMPT_UI if include_ui else SCRIBE_PROMPT_NO_UI
        return self.provider.generate_structured(
            model=SCRIBE_MODEL,
            contents=[image, prompt],
            schema=ScribeOutput,
            thinking_level="minimal"
        )