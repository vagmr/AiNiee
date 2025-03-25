# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['AiNiee.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['pyinstaller', 'openai', 'cohere==5.10.0', 'anthropic', 'tiktoken', 'numpy', 'openpyxl', 'PyQt5', 'PyQt-Fluent-Widgets[full]', 'opencc', 'google-generativeai', 'ebooklib', 'beautifulsoup4', 'pandas', 'chardet', 'PyYAML', '', 'rich', 'tqdm', 'jaconv', 'python-rapidjson'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AiNiee',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['Resource\\Avatar.png'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AiNiee',
)
