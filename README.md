# Ally vertical slice

A minimal end-to-end pass through the pipeline discussed in planning:

    Scribe -> State Sandbox -> Entity Registry -> Ally

## Setup

    pip install -r requirements.txt
    export GEMINI_API_KEY=your_key_here   # genai.Client() picks this up

## Run

    python main.py images/monkey.png
    python main.py images/disco.jpg

## What's real vs. stubbed

Real:
- Scribe: structured extraction via response_schema (no more hoping the
  model returns clean JSON)
- State Sandbox: holds the current turn's facts
- Entity Registry: resolves repeat mentions via difflib string matching,
  append-only facts, survives across turns within a run
- Ally: genuinely blind to the raw image -- only sees sandbox + registry
  text

Stubbed, with the seam marked in code:
- Personality (ally/ally_agent.py: PERSONALITY_STUB) -- swap for
  MemoryManager.build_context() later
- Entity matching (state/entity_registry.py: marked TODO) -- swap difflib
  for an EmbeddingProvider + vector search once entity counts grow
- Collector -- this slice just opens a file; a real Collector interface
  (screen capture, CommunicationMod-style API) slots in ahead of Scribe
  without Scribe's code changing
- Cross-run persistence -- everything here lives in memory for one run;
  no SQLite yet
