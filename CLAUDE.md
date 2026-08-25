# Repository Guidelines for Claude

## Where to look first

- **Architecture / how the pipeline currently works:** `docs/ARCHITECTURE.md`
- **Why a decision was made, and what it superseded:** `docs/ally_decision_log.md`
- **Adding a new game:** `docs/adding_a_new_game.md`
- **Open items / not-yet-built:** `docs/roadmap.md`
- **MTGA-specific research and gotchas:** `plugins/mtga/integration_notes.md`

If a doc referenced above doesn't exist yet, it's mid-migration — check
`docs/ally_decision_log.md` in the meantime, it's the fallback source of
truth.

## Python

- This project uses **type hints/annotations** throughout, intentionally,
  and is checked with **Pylance**. When you see an "error" reported in an
  editor or CI, check whether it's a type/annotation strictness complaint
  before assuming it's a logic bug — a large fraction of them are.
- Match the existing style: parameters and return types are annotated on
  new functions/methods, `Optional[...]` / `| None` is used explicitly
  rather than left implicit, and `dataclass`/`Pydantic` models are
  preferred over loose dicts for structured data crossing a module
  boundary.
- Don't silently loosen typing (e.g. adding `# type: ignore` or widening
  a type to `Any`) to make a Pylance complaint go away — fix the actual
  type mismatch, or ask if the annotation itself is wrong.

## Markdown Formatting

- You must follow all rules defined in the local `.markdownlint.yaml` file.
- Pay close attention to rules that are turned off (like line lengths and duplicate headings) so you do not break them unnecessarily.
- Never include trailing spaces or missing empty lines around headers and code blocks.
