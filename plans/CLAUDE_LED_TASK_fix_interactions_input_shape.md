# CLAUDE_LED_TASK: Fix Interactions API `input=` Content Shape

> Handoff spec from Claude to ZooCode. This is a **bug-fix pass** on top of
> the prior `CLAUDE_LED_TASK_migrate_to_interactions_api.md` migration, not
> a new feature. Single phase, but Phase 0's verification step is still
> mandatory and non-negotiable — see §0.

---

## 0. What broke, and why guessing again is not acceptable

Real errors observed in production (pasted verbatim by the person running
this project):

```
Input should be a valid dictionary or instance of Turn [type=model_type, input_value="You are analysing a sing...e over a flavorful one.", input_type=str]
...union_name='Content'...
Value error, Content: expected object with 'type' field [type=value_error, input_value=[Part(
  inline_data=Blob... over a flavorful one."], input_type=list]
```

Two distinct failures, same underlying cause:

1. **Every plain-text call** (Ally's prompts, narrative/personality
   summarization, geneology) is passing a bare Python `str` somewhere
   `client.interactions.create`'s `input` field expects either a `Turn`
   object/dict, or a properly-typed `Content` item — not a raw string
   dropped into a list.
2. **Scribe's image+prompt call** is passing a **legacy `google.genai.
   types.Part`/`Blob`** object (the object shape `generate_content` used)
   instead of the new Interactions `ImageContent` type. The new `Content`
   union is discriminated on a `type` field (`"text"`, `"image"`,
   `"audio"`, `"document"`, `"video"`) — `Part`/`Blob` don't have one, so
   validation fails.

Net effect: whatever `contents`→`input` conversion exists right now in
`GeminiProvider` is passing old-API objects straight through to the new
API without translating them. This is precisely the failure mode the prior
spec's Phase 0 (§2.2, items 2 and 4) was written to catch *before* writing
integration code — either that verification wasn't run against enough real
cases, or its findings weren't reflected in the final `input=` construction.
**Do not repeat that pattern here.** Every claim below about field names
must be confirmed via live introspection first, exactly as required below,
and the real confirmed output must be pasted into the code as a comment —
not assumed from this document.

---

## 1. Mandatory Phase 0 — Confirm the real `Turn`/`Content` shapes

### 1.1 Introspect the actual classes

Run this against the real installed SDK and paste its full output into
your completion notes verbatim:

```python
from google.genai._gaos.types.interactions.turn import Turn
from google.genai._gaos.types.interactions.textcontent import TextContent
from google.genai._gaos.types.interactions.imagecontent import ImageContent

for cls in (Turn, TextContent, ImageContent):
    print(f"--- {cls.__name__} ---")
    print(cls.model_fields)
    print()
```

(If any of these import paths are wrong for the installed version, that's
useful information too — find the correct import paths via
`dir(client.interactions)` / `inspect.getmodule` / searching the installed
package for `class Turn`, `class TextContent`, `class ImageContent`, and
report the real paths you find, since the error message above already
confirms these classes exist somewhere under
`google.genai._gaos.types.interactions.*`.)

Pay specific attention to:

- `Turn.model_fields` — does it require a `role` field? What values are
  valid (`"user"`? an enum?)? Does `content` accept `list[Content]`,
  `str`, or both?
- `ImageContent.model_fields` — what's the actual field for image data?
  Candidates to check for: raw bytes, base64 string, a nested
  `source`/`data` object, a `mime_type` sibling field. Do not guess —
  read `model_fields` directly, and if the field's type annotation isn't
  self-explanatory, also check for a nested model (e.g.
  `ImageContent.model_fields["image"].annotation` might itself be another
  Pydantic model needing its own `model_fields` dump).
- `TextContent.model_fields` — almost certainly just `type` + `text`, but
  confirm.

### 1.2 Prove it with two real, live calls

Using what §1.1 revealed, hand-construct (do not use any existing
`GeminiProvider` code for this step — build it directly against the raw
classes) and make two **real** `client.interactions.create` calls:

1. **Text-only**: whatever shape correctly represents a single-string
   prompt as `input`. Confirm it returns successfully with a real
   response (not another validation error).
2. **Image + text** (mirroring Scribe's exact call: one image, one prompt
   string): load any real image (e.g. anything under `images/`, or
   generate one in-memory), convert it into the confirmed `ImageContent`
   shape from §1.1 (this will likely require base64-encoding the image
   bytes, or passing raw bytes — whatever `model_fields` showed), build a
   `TextContent` for the prompt, combine them into whatever `input` shape
   §1.1 confirmed (a single `Turn` with both content items, most likely),
   and confirm the call succeeds end-to-end with a real response.

**Do not proceed to §2 until both of these real calls succeed.** If either
still fails, iterate here — the fix must be proven against the live API in
isolation before it's wired into `GeminiProvider`, not debugged via the
production pipeline's error logs after the fact.

### 1.3 Record the confirmed shape in code

Wherever you implement the fix in §2, include a comment block with the
literal confirmed field names/shapes from §1.1 and a note that §1.2's live
calls were run and succeeded — same convention as the existing
`_extract_new_field_text` docstring's "Verified against
partial_json_parser==..." comment in `gemini_provider.py`.

---

## 2. Fix: centralize `contents` → `input` conversion

### 2.1 Add one conversion helper

In `infrastructure/llm/gemini_provider.py`, add a private method on
`GeminiProvider`:

```python
def _build_interactions_input(self, contents: list) -> Any:
    """Converts this project's existing `contents` list convention
    (a mix of PIL.Image.Image and str -- see every call site in Scribe/
    Ally/NarrativeMemoryManager/PersonalityMemoryManager/geneology.py)
    into the shape client.interactions.create's `input` parameter
    actually requires. See the confirmed shape notes below, from live
    verification against the real API (not assumed from docs) -- do not
    reintroduce a legacy types.Part/Blob object here, that was the exact
    bug this method fixes.

    <PASTE THE REAL CONFIRMED Turn/TextContent/ImageContent FIELD SHAPES
    HERE, FROM YOUR OWN LIVE §1.1/§1.2 VERIFICATION -- do not leave this
    placeholder text in the final code.>
    """
    ...
```

This is the **single place** in the codebase that should ever construct
`Turn`/`Content` objects. Every one of `generate_structured()`,
`generate_structured_stream()`, and `generate_structured_stream_field()`
must call this helper to build their `input=` argument, rather than each
having its own ad hoc conversion (if that's how the current bug happened —
duplicated/inconsistent conversion logic in more than one place is itself
worth eliminating here even if it isn't the direct cause).

Implementation requirements:

- Iterate `contents` in order. For each element:
  - If it's a `str` → build the confirmed `TextContent` shape.
  - If it's a `PIL.Image.Image` → encode it per §1.1's confirmed
    `ImageContent` shape (likely: save to an in-memory buffer as PNG,
    read bytes, then base64-encode or pass raw bytes depending on what
    §1.1 found; set the confirmed mime-type field to `"image/png"`).
  - Anything else → raise a clear `TypeError` naming the unsupported type,
    rather than silently mis-encoding it or passing it through. This
    project's `contents` lists are currently only ever strings or
    `PIL.Image.Image` instances (confirm this is still true by checking
    every call site: `Scribe.extract()`, `Ally.decide()`/`chat()` variants,
    `NarrativeMemoryManager`, `PersonalityMemoryManager`,
    `goodies/geneology.py`) — don't build speculative support for
    audio/document/video content that nothing currently sends.
- Wrap the resulting content items into whatever top-level shape §1.1
  confirmed `input` actually wants (most likely one `Turn` with a `role`
  field and a `content` list containing every item, but follow what you
  actually confirmed, not this guess).

### 2.2 Wire it into all three generation methods

Replace whatever currently builds `input=` in `generate_structured()`,
`generate_structured_stream()`, and `generate_structured_stream_field()`
with a call to `self._build_interactions_input(contents)`.

---

## 3. Tests

### 3.1 New unit test: shape correctness, not just mocked success

Add (or extend an existing provider test file with) a test that calls
`_build_interactions_input()` directly with representative inputs —
`["a plain prompt"]` and `[some_pil_image, "a prompt"]` — and asserts the
result is built from **real imported `Turn`/`TextContent`/`ImageContent`
classes** (`isinstance` checks against the real classes, not dicts,
unless §1.1 confirmed `input` genuinely accepts plain dicts, in which case
assert dict shape/keys match exactly what §1.1 confirmed). This is the
test that should have caught this bug before it reached production — a
test that only mocks `client.interactions.create` and checks call
arguments loosely (e.g. `assert_called_once()`) would NOT have caught a
malformed `input=` value, since the mock never actually validates it the
way the real pydantic-backed client does. Prefer constructing the real
classes in the test and comparing, or at minimum asserting on the exact
field names/values §1.1 confirmed, over a loose mock assertion.

### 3.2 Re-run the full suite

`python -m unittest discover tests` — zero regressions. Also re-run
whatever mocked tests exist for `generate_structured`/
`generate_structured_stream_field` (from the prior migration task) and
confirm their mocked `client.interactions.create` call sites still line up
with the new `input=` shape this fix produces (update the mocks' expected
`input=` assertions if they were asserting against the old, buggy shape).

---

## 4. Manual Verification

1. Run Scribe against a real screenshot (`python main.py
   images/<some_image>.png` or a live `--game` session) and confirm real
   `ScreenElement`s come back — not a validation error, not empty output.
2. Run a normal turn end-to-end (live `--game` session, a few turns) and
   confirm Ally's analysis streams normally with no `Turn`/`Content`
   validation errors in the logs.
3. Trigger a narrative flush (play enough turns to hit
   `medium_flush_interval`, or lower it temporarily in
   `configs/user_config.json` for the test) and confirm no validation
   errors there either — this exercises `NarrativeMemoryManager`'s
   text-only call path, distinct from Ally's.

---

## 5. Notes for Claude's Code Review

**ZooCode: ignore this section entirely — it is not part of your task.**

- Confirm §1's placeholder comment (`<PASTE THE REAL CONFIRMED...>`) was
  actually replaced with real findings, not left in verbatim — same check
  as every prior spec's review section, because this exact failure mode
  (claimed verification that wasn't really done) is what produced the bug
  being fixed here in the first place.
- Confirm there is exactly **one** place building `Turn`/`Content` objects
  (`_build_interactions_input`), and all three generation methods route
  through it — if any method still has its own inline conversion, that's
  a regression risk waiting to happen again.
- Confirm no `google.genai.types.Part`/`Blob` (legacy `generate_content`
  content types) remain anywhere in `gemini_provider.py` after this fix —
  their presence was the direct cause of Error 2.
- Spot-check the new unit test (§3.1) actually instantiates/compares
  against real SDK classes rather than only checking that a mock was
  called — a shape bug like this one is specifically the kind of thing a
  loose `assert_called()` test would miss.
