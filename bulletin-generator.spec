# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for Bulletin Generator desktop app.
#
# Before building:
#   1. Copy desktop_config.py.example to desktop_config.py and fill in the
#      app-owned OAuth credentials that should ship with the desktop build
#   2. Install PyInstaller:  pip install pyinstaller
#   3. Build:                pyinstaller bulletin-generator.spec
#
# The .app bundle will be in dist/Bulletin Generator.app

import shutil
import subprocess
import tempfile
from pathlib import Path

block_cipher = None

ROOT_DIR = Path(__file__).resolve().parent
SVG_ICON_PATH = ROOT_DIR / 'bulletin Generator icon.svg'
FALLBACK_ICON_PATH = ROOT_DIR / 'Bulletin Generator.icns'


def _build_icns_from_svg(svg_path):
    """
    Convert the checked-in SVG icon into an .icns file for the macOS app bundle.
    Falls back to the committed .icns file if conversion tools are unavailable.
    """
    qlmanage = shutil.which('qlmanage')
    sips = shutil.which('sips')
    iconutil = shutil.which('iconutil')
    if not (qlmanage and sips and iconutil):
        raise RuntimeError('Missing one or more macOS icon tools: qlmanage, sips, iconutil')

    out_icns = ROOT_DIR / 'build' / 'Bulletin Generator.generated.icns'
    out_icns.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        iconset_dir = tmpdir_path / 'BulletinGenerator.iconset'
        iconset_dir.mkdir()

        subprocess.run(
            [qlmanage, '-t', '-s', '1024', '-o', str(tmpdir_path), str(svg_path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        preview_png = tmpdir_path / f'{svg_path.name}.png'
        if not preview_png.exists():
            raise RuntimeError(f'Quick Look did not produce a preview for {svg_path.name}')

        sizes = [16, 32, 128, 256, 512]
        for size in sizes:
            subprocess.run(
                [sips, '-z', str(size), str(size), str(preview_png), '--out',
                 str(iconset_dir / f'icon_{size}x{size}.png')],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            subprocess.run(
                [sips, '-z', str(size * 2), str(size * 2), str(preview_png), '--out',
                 str(iconset_dir / f'icon_{size}x{size}@2x.png')],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        subprocess.run(
            [iconutil, '-c', 'icns', str(iconset_dir), '-o', str(out_icns)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    return str(out_icns)


def resolve_bundle_icon():
    if SVG_ICON_PATH.exists():
        try:
            generated_path = _build_icns_from_svg(SVG_ICON_PATH)
            print(f'Using generated app icon from {SVG_ICON_PATH.name}')
            return generated_path
        except Exception as exc:
            print(f'Warning: could not generate .icns from {SVG_ICON_PATH.name}: {exc}')

    print(f'Using fallback app icon {FALLBACK_ICON_PATH.name}')
    return str(FALLBACK_ICON_PATH)


BUNDLE_ICON_PATH = resolve_bundle_icon()

a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('index.html',                         '.'),
        ('src',                                'src'),
        ('data/projects.example.json',        'data'),
        ('data/announcements.example.json',   'data'),
        ('data/settings.example.json',        'data'),
        ('desktop_config.py',                 '.'),
        ('menubar-icon.png',                  '.'),
    ],
    hiddenimports=['encodings.idna', 'rumps'],
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
    icon=BUNDLE_ICON_PATH,
    bundle_identifier='com.bulletingenerator.app',
    info_plist={
        'CFBundleName':             'Bulletin Generator',
        'CFBundleDisplayName':      'Bulletin Generator',
        'CFBundleVersion':          '1.08',
        'CFBundleShortVersionString': '1.08',
        'NSHighResolutionCapable':  True,
        'LSUIElement':              True,   # menu bar only — no dock icon
        'NSHumanReadableCopyright': 'Bulletin Generator',
    },
)
