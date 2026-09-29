# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['installer_wizard.py'],
    pathex=[],
    binaries=[],
    datas=[('C:/Users/AGY-VCO/helios_space_weather/dist/payload.zip', '.'), ('C:/Users/AGY-VCO/helios_space_weather/assets/helios.ico', 'assets')],
    hiddenimports=[],
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
    a.binaries,
    a.datas,
    [],
    name='HELIOS-L1-Setup',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['C:/Users/AGY-VCO/helios_space_weather/assets/helios.ico'],
)
