"""M0 引导脚本：把 Python 自带 pip/setuptools wheel 直接解压进 venv（绕开 ensurepip 的临时目录）。"""
import glob
import zipfile

SRC = r'D:\dsh-workspace\.tools\python\cpython-3.12.13-windows-x86_64-none\Lib\ensurepip\_bundled'
DEST = r'D:\dsh-workspace\minecraft-launcher\.venv\Lib\site-packages'

for whl in sorted(glob.glob(SRC + '\\*.whl')):
    print('extracting', whl)
    with zipfile.ZipFile(whl) as z:
        z.extractall(DEST)
print('bootstrap done')
