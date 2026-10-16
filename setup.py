import os
import subprocess
import sys
from pathlib import Path

def main():
    if sys.version_info < (3, 10):
        raise RuntimeError('Please install Python 3.10 or later from https://www.python.org/downloads/')
    import tkinter
    base=Path(__file__).resolve().parent
    env=base/'.venv'
    subprocess.run([sys.executable,'-m','venv',str(env)],check=True)
    executable=env/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    subprocess.run([str(executable),'-m','pip','install','-r',str(base/'requirements.txt')],check=True)
    subprocess.run([str(executable),'-c','import tkinter; import pypdf; import tkinterdnd2; print("Ready / 安装完成")'],check=True)

if __name__=='__main__':
    try: main()
    except Exception as e:
        print('Setup failed / 安装失败:',e)
        print('Use the official Python installer (including Tcl/Tk). Check your network and try again.')
        sys.exit(1)
