# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for Bulletin Generator desktop app.
#
# Before building:
#   1. Copy desktop_config.py.example to desktop_config.py and fill in credentials
#   2. Install PyInstaller:  pip install pyinstaller
#   3. Build:                pyinstaller bulletin-generator.spec
#
# The .app bundle will be in dist/Bulletin Generator.app

block_cipher = None

a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('worship-booklet.html', '.'),
        ('song-database.json',   '.'),
        ('data',                 'data'),
        ('desktop_config.py',    '.'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BulletinGenerator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='BulletinGenerator',
)

app = BUNDLE(
    coll,
    name='Bulletin Generator.app',
    icon=None,
    bundle_identifier='com.bulletingenerator.app',
    info_plist={
        'CFBundleName':             'Bulletin Generator',
        'CFBundleDisplayName':      'Bulletin Generator',
        'CFBundleVersion':          '1.0.4',
        'CFBundleShortVersionString': '1.0.4',
        'NSHighResolutionCapable':  True,
        'LSBackgroundOnly':         False,
        'NSHumanReadableCopyright': 'Bulletin Generator',
    },
)
