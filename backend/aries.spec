# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — 输出 dist/aries.exe，发布时复制为 frontend/resources/aries_backend.exe
# 外部资源（与 exe 同级，由 build_backend.ps1 复制）：
#   bin/rg.exe
#   cli/dist + cli/node_modules

from pathlib import Path

_backend = Path(SPECPATH)

_binaries = []
if (_backend / 'bin' / 'rg.exe').is_file():
    _binaries.append((str(_backend / 'bin' / 'rg.exe'), 'bin'))

_datas = [
    ('api', 'api'),
    ('db', 'db'),
    ('engine', 'engine'),
    ('models', 'models'),
    ('services', 'services'),
    ('utils', 'utils'),
    ('plugins', 'plugins'),
    ('tools', 'tools'),
    ('prompt', 'prompt'),
    ('memory', 'memory'),
    ('aries_mcp', 'aries_mcp'),
]
if (_backend / 'VERSION').is_file():
    _datas.append(('VERSION', '.'))

a = Analysis(
    ['main.py'],
    pathex=[str(_backend)],
    binaries=_binaries,
    datas=_datas,
    hiddenimports=[
        'uvicorn',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.loops.auto',
        'httpx',
        'websockets',
        'sqlalchemy',
        'openai',
        'python_multipart',
        'aiofiles',
        'qrcode',
        'PIL',
        'dotenv',
        'lark_oapi',
        'mcp',
        'pypdf',
        'pydantic',
        'pydantic_settings',
        'passlib',
        'bcrypt',
        'cryptography',
        'pyflakes',
        'psutil',
        'send2trash',
        'engine',
        'engine.skills_manager',
        'engine.plugin_manager',
        'engine.subagent_runtime',
        'utils.app_paths',
    ],
    hookspath=[],
    hooksconfig={},
    excludes=[
        'pandas',
        'openpyxl',
        'moviepy',
        'matplotlib',
        'scipy',
        'sklearn',
        'tensorflow',
        'torch',
        'seaborn',
        'plotly',
        'bokeh',
        'dash',
        'flask',
        'django',
        'notebook',
        'ipython',
        'jupyter',
        'streamlit',
        'boto3',
        'botocore',
        's3transfer',
        'paramiko',
        'docker',
        'kubernetes',
        'tkinter',
        'unittest',
        'pytest',
        'PyQt5',
        'PyQt6',
        'PySide2',
        'PySide6',
        'wx',
        'win32com',
        'win32api',
        'win32gui',
        'win32con',
        'pythoncom',
        'pywintypes',
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='aries',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
