"""Windows için .exe derler (PyInstaller).

Kullanım (proje kök klasöründe, sanal ortam açıkken):
    pip install pyinstaller waitress
    python build_exe.py            # önerilen: klasör modu (hızlı açılır)
    python build_exe.py --konsol   # hata ayıklama: siyah konsol penceresi de açılır

Sonuç: dist\\TarladanSofraya\\TarladanSofraya.exe  (yanındaki _internal klasörüyle birlikte)
"""
import os
import shutil
import sys

import PyInstaller.__main__

ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_COPY = os.path.join(ROOT, "build", "static_paket")


def copy_static():
    """app/static'i kullanıcı yüklemeleri OLMADAN kopyalar (kendi test görselleriniz pakete girmesin)."""
    if os.path.exists(STATIC_COPY):
        shutil.rmtree(STATIC_COPY)
    shutil.copytree(os.path.join(ROOT, "app", "static"), STATIC_COPY,
                    ignore=shutil.ignore_patterns("uploads"))
    return STATIC_COPY


def main():
    os.chdir(ROOT)
    sep = os.pathsep  # Windows'ta ";"
    args = [
        "masaustu.py",
        "--name=TarladanSofraya",
        "--noconfirm",
        "--clean",
        f"--add-data=app{os.sep}templates{sep}app/templates",
        f"--add-data={copy_static()}{sep}app/static",
        "--collect-submodules=app",       # rotalar create_app içinde içe aktarıldığı için hepsini topla
        "--collect-submodules=scripts",
        "--hidden-import=email_validator",
        "--hidden-import=waitress",
    ]
    args.append("--console" if "--konsol" in sys.argv else "--windowed")
    if os.path.exists("icon.ico"):
        args.append("--icon=icon.ico")
    # .env, instance/ (veri tabanı), migrations/ ve testler pakete EKLENMEZ.
    PyInstaller.__main__.run(args)
    print("\nBitti: dist\\TarladanSofraya\\TarladanSofraya.exe")


if __name__ == "__main__":
    main()
