@echo off
REM DropRAG Windows 构建脚本
REM
REM 用法: build_windows.bat
REM 前提: Python 3.10+ 已安装，pip 可用

echo === DropRAG Windows Build ===

REM 安装 PyInstaller
pip install --quiet pyinstaller

REM 安装核心依赖（不含 torch/sklearn 等大体积包）
pip install --quiet ^
    fastapi>=0.100.0 ^
    uvicorn[standard]>=0.24.0 ^
    pydantic>=2.0.0 ^
    pydantic-settings>=2.0.0 ^
    sqlite-vec>=0.1.6 ^
    numpy>=1.24.0 ^
    watchdog>=3.0.0 ^
    pyyaml>=6.0 ^
    chardet>=5.0.0

REM 构建
pyinstaller droprag.spec --clean --noconfirm

REM 打包
cd dist
python -c "import zipfile,os;src='droprag';out='droprag-0.1.0-windows-amd64.zip';zf=zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=6);[zf.write(os.path.join(r,f),os.path.relpath(os.path.join(r,f),'.')) for r,d,fs in os.walk(src) for f in fs];zf.close();print(f'Built: {out} ({os.path.getsize(out)/1024/1024:.1f} MB)')"

echo === Done ===
pause
