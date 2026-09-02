import glob

files = [
    'brain/reasoning/core.py',
    'brain/reasoning/ally_agent.py',
    'tooling/goodies/geneology.py',
    'brain/perception/scribe.py',
    'brain/perception/screen_classifier.py',
    'brain/perception/screen_category_store.py',
    'brain/perception/screen_bootstrapper.py',
    'brain/perception/clip_classifier.py',
    'brain/perception/change_detector.py',
    'tests/test_ally.py',
    'brain/memory/personality.py',
    'brain/memory/narrative.py',
    'interfaces/gui/settings_window.py',
    'tests/debuggers/debug_raw_thinking_stream_shape.py',
    'interfaces/gui_qt/prod/voice_input_controller.py',
    'interfaces/gui_qt/prod/settings_dialog.py',
    'ingestion/collectors/screen_collector.py',
    'infrastructure/tts/audio_player.py',
    'infrastructure/stt/recognizer.py',
    'infrastructure/stt/assembler.py'
]

for path in files:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        if 'cabinet.configs.config_manager' in content:
            new_content = content.replace('storage.configs.config_manager', 'cabinet.configs.config_manager')
            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f'Successfully updated: {path}')
    except Exception as e:
        print(f'Error updating {path}: {e}')
print('Done!')
