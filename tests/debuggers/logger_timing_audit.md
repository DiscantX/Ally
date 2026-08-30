# Logger Timing Audit

This file documents every `log()` callsite across the codebase, identifying the file, function/method name, and whether it currently has the `@timed` decorator.

| File Path | Function / Method Name | Has `@timed` Decorator? (Yes / No / N/A - Lambda/Module-level) | Notes / Status |
|-----------|------------------------|---------------------------------------------------------------|----------------|
| utils/event_hook.py | EventHook.emit() | Yes | Logs error in subscriber callback |
| interfaces/gui_qt/shell/capture_exclusion.py | exclude_hwnd_from_capture() | Yes | Logs warning when SetWindowDisplayAffinity fails |
| interfaces/gui_qt/shell/capture_exclusion.py | exclude_hwnd_from_capture() | Yes | Logs debug when failing to exclude hwnd from capture |
| brain/reasoning/perspective_engine.py | PerspectiveEngine._load_keywords() | Yes | Logs when perspective keywords file not found |
| brain/reasoning/core.py | AllyCore.run_turn() | Yes | Logs screen header with name and confidence |
| brain/reasoning/core.py | AllyCore.run_turn() | Yes | Logs Scribe extracting with mode |
| brain/reasoning/core.py | AllyCore.run_turn() | Yes | Logs confirmed facts (OCR, bypassed the Scribe) |
| brain/reasoning/core.py | AllyCore.run_turn() | Yes | Logs screen elements |
| brain/reasoning/core.py | AllyCore.run_turn() | Yes | Logs entity registry (accumulated across the run) |
| brain/reasoning/core.py | AllyCore.run_turn() | Yes | Logs genre information |
| brain/reasoning/core.py | AllyCore.run_turn() | Yes | Logs Ally (blind to the image) section header |
| brain/reasoning/core.py | AllyCore.run_turn() | Yes | Logs analysis output |
| brain/reasoning/core.py | AllyCore.run_turn() | Yes | Logs actions from ally output |
| brain/reasoning/core.py | AllyCore.run_turn() | Yes | Logs entity registry (accumulated across the run) - second occurrence |
| brain/reasoning/core.py | AllyCore.run_turn() | Yes | Logs skip Scribe/Ally reason |
| brain/reasoning/core.py | AllyCore.run_turn() | Yes | Logs run ended (boundary resolved) |
| brain/reasoning/core.py | AllyCore.run_loop() | Yes | Logs when no collector configured |
| brain/reasoning/core.py | AllyCore.run_loop() | Yes | Logs starting turn loop |
| brain/reasoning/core.py | AllyCore.run_loop() | Yes | Logs run concluded and starting new run session |
| brain/reasoning/core.py | AllyCore.run_loop() | Yes | Logs stopping loop on KeyboardInterrupt |
| tooling/tools/update_docs.py | update_readme() | Yes | Logs when target directory does not exist |
| tooling/tools/update_docs.py | update_readme() | Yes | Logs successful update with count |
| tooling/tools/update_docs.py | install_git_hook() | Yes | Logs when no .git directory found |
| tooling/tools/update_docs.py | install_git_hook() | Yes | Logs installed git pre-commit hook path |
| infrastructure/logger/logger.py | log() function | N/A | This is the logger function itself - module level |
| tooling/tools/inspect_coords.py | save_to_disk() | Yes | Logs layout changes successfully saved |
| tooling/tools/inspect_coords.py | show_ocr_preview() | Yes | Logs OCR result |
| tooling/tools/inspect_coords.py | mouse_callback() | Yes | Logs action canceled |
| tooling/tools/inspect_coords.py | mouse_callback() | Yes | Logs box deselected |
| tooling/tools/inspect_coords.py | mouse_callback() | Yes | Logs selected box |
| tooling/tools/inspect_coords.py | mouse_callback() | Yes | Logs updated box dimensions/position |
| tooling/tools/inspect_coords.py | seed_from_scribe() | Yes | Logs calling Scribe to seed draft boxes |
| tooling/tools/inspect_coords.py | seed_from_scribe() | Yes | Logs added draft box(es) from Scribe |
| tooling/tools/inspect_coords.py | main() | Yes | Logs layout editor active |
| tooling/tools/inspect_coords.py | main() | Yes | Logs lost captured frame -- stopping |
| tooling/tools/inspect_coords.py | main() | Yes | Logs deleted box |
| tooling/tools/inspect_coords.py | main() | Yes | Logs requires_hover set to value |
| tooling/tools/inspect_coords.py | main() | Yes | Logs ignore_motion set to value |
| tooling/tools/inspect_coords.py | main() | Yes | Logs view refreshed |
| tooling/tools/inspect_coords.py | main() | Yes | Logs view refreshed (duplicate) |
| tooling/tools/inspect_coords.py | main() | Yes | Logs anchor set to value |
| infrastructure/llm/model_lister.py | get_available_models() | Yes | Logs failed to fetch models dynamically |
| infrastructure/llm/model_lister.py | get_available_models() | Yes | Logs failed to load fallback static config |
| infrastructure/llm/gemini_provider.py | retry_with_gemini_backoff wrapper | Yes | Logs Gemini API error (max retries exceeded) |
| infrastructure/llm/gemini_provider.py | retry_with_gemini_backoff wrapper | Yes | Logs Gemini API error with retry attempt |
| infrastructure/llm/gemini_provider.py | GeminiProvider.generate_structured() | Yes | Logs completed first LLM generation |
| infrastructure/llm/gemini_provider.py | GeminiProvider.generate_structured_stream() | No | Logs failed to parse final JSON buffer via partial_json_parser |
| infrastructure/llm/gemini_provider.py | GeminiProvider.generate_structured_stream_field() | Yes | Logs failed to parse final JSON buffer via partial_json_parser |
| infrastructure/llm/gemini_provider.py | GeminiProvider.generate_structured_stream_field() | Yes | Logs Gemini streaming error (max retries exceeded) |
| infrastructure/llm/gemini_provider.py | GeminiProvider.generate_structured_stream_field() | Yes | Logs Gemini streaming error with retry attempt |
| brain/perception/scribe.py | Scribe.extract() | Yes | Logs completed Scribe extraction |
| brain/perception/screen_category_store.py | ScreenCategoryStore._ensure_seeded() | Yes | Logs no seed file at path |
| brain/perception/screen_category_store.py | ScreenCategoryStore._ensure_seeded() | Yes | Logs CLIP unavailable -- cannot embed seed categories |
| brain/perception/screen_category_store.py | ScreenCategoryStore._ensure_seeded() | Yes | Logs seeded off_game categories |
| brain/perception/screen_bootstrapper.py | ScreenBootstrapper.__init__() | Yes | Logs initialized screen collector bootstrapper |
| brain/perception/screen_bootstrapper.py | ScreenBootstrapper.bootstrap() | Yes | Logs drafted screen with elements and validation count |
| brain/perception/layout.py | LayoutManager.load_layouts() | Yes | Logs warning when filepath not found |
| brain/perception/layout.py | LayoutManager.load_layouts() | Yes | Logs loaded UI elements from filepath |
| brain/perception/layout.py | LayoutManager.load_layouts() | Yes | Logs error parsing filepath |
| ingestion/collectors/window_manager.py | ClientRect.__init__() | Yes | Logs initialized window manager |
| ingestion/collectors/window_manager.py | ClientRect._get_window_handle() | Yes | Logs window not found |
| brain/perception/geometry.py | normalized_box_to_pixels() | Yes | Logs warning for invalid box_2d |
| ingestion/collectors/screen_collector.py | ScreenCollector.capture() | Yes | Logs completed first screen capture |
| ingestion/collectors/screen_collector.py | ScreenCollector.capture_bgr() | Yes | Logs window not found or minimized |
| brain/perception/change_detector.py | ChangeDetector.has_changed() | Yes | Logs scikit-image not installed -- falling back |
| brain/perception/change_detector.py | ChangeDetector.has_changed() | Yes | Logs SSIM calculation failed due to memory/allocation error |
| brain/perception/change_detector.py | ChangeDetector.has_changed() | Yes | Logs cooldown active |
| brain/perception/change_detector.py | ChangeDetector.has_changed() | Yes | Logs transition started |
| brain/perception/change_detector.py | ChangeDetector.has_changed() | Yes | Logs screen settled |
| tooling/tools/display.py | show_image() | Yes | Logs captured frame is empty (two occurrences) |
| brain/memory/db.py | MemoryDB._init_db() | Yes | Logs entities indexes |
| brain/memory/db.py | MemoryDB.upsert_entities() | Yes | Logs upsert_entities with parameters |
| brain/memory/db.py | MemoryDB.upsert_entities() | Yes | Logs upserting entity with id and name |
| main.py | main() | N/A | Logs summary (lambda function) |
| main.py | main() | N/A | Logs chat message (lambda function) |
| main.py | main() | N/A | Logs connection status (lambda function) |
| tests/test_logger_pubsub.py | test_logger_pubsub() | N/A | Test file - logs hello pubsub test |
| tests/test_logger_pubsub.py | test_logger_pubsub() | N/A | Test file - logs should not be received |
| tests/test_logger_pubsub.py | test_logger_pubsub() | N/A | Test file - logs testing exception safety |