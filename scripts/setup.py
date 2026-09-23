#!/usr/bin/env python3
"""Install the local MVP dependencies without global Python packages."""

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
BACKEND = ROOT / "backend"
VENV = BACKEND / ".venv"
PYTHON = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def prerequisites() -> str:
    if sys.version_info < (3, 11):
        raise RuntimeError("Нужен Python 3.11 или новее; проект проверен на Python 3.13.9.")
    node = shutil.which("node")
    npm = shutil.which("npm")
    if not node or not npm:
        raise RuntimeError("Установите Node.js и npm и добавьте их в PATH. Нужен Node.js >= 22.13.0.")
    version = subprocess.check_output([node, "--version"], text=True).strip()
    match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", version)
    if not match or tuple(map(int, match.groups())) < (22, 13, 0):
        raise RuntimeError(f"Нужен Node.js >= 22.13.0, найден {version}.")
    for path in (BACKEND / "requirements.txt", FRONTEND / "package-lock.json"):
        if not path.is_file():
            raise RuntimeError(f"Нет файла зависимостей: {path}")
    print(f"Python {sys.version.split()[0]}; Node.js {version}; npm: {npm}", flush=True)
    return npm


def main() -> int:
    parser = argparse.ArgumentParser(description="Установка backend/.venv и зависимостей frontend по lock-файлу.")
    parser.add_argument("--check", action="store_true", help="Проверить инструменты и файлы зависимостей без установки.")
    args = parser.parse_args()
    try:
        npm = prerequisites()
        if args.check:
            print("Предварительная проверка пройдена. Зависимости не изменены.")
            return 0
        if not PYTHON.is_file():
            print(f"Создаём виртуальное окружение: {VENV}", flush=True)
            venv.EnvBuilder(with_pip=True).create(VENV)
        virtual_version = subprocess.check_output(
            [str(PYTHON), "-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))"], text=True,
        ).strip()
        if tuple(map(int, virtual_version.split("."))) < (3, 11, 0):
            raise RuntimeError(f"В backend/.venv используется Python {virtual_version}. Пересоздайте это окружение с Python 3.11+.")
        print("Устанавливаем зафиксированные Python-зависимости…", flush=True)
        subprocess.run([str(PYTHON), "-m", "pip", "install", "-r", str(BACKEND / "requirements.txt")], cwd=ROOT, check=True)
        subprocess.run([str(PYTHON), "-m", "pip", "check"], cwd=ROOT, check=True)
        print("Устанавливаем frontend через npm ci…", flush=True)
        environment = os.environ.copy()
        if not any(name in environment for name in (
            "SHARP_IGNORE_GLOBAL_LIBVIPS", "SHARP_FORCE_GLOBAL_LIBVIPS",
            "npm_config_build_from_source", "NPM_CONFIG_BUILD_FROM_SOURCE",
        )):
            environment["SHARP_IGNORE_GLOBAL_LIBVIPS"] = "1"
        subprocess.run(
            [npm, "ci", "--include=dev", "--include=optional", "--no-audit", "--no-fund"],
            cwd=FRONTEND, env=environment, check=True,
        )
        print("Готово. Запуск: python3 scripts/dev.py", flush=True)
        return 0
    except KeyboardInterrupt:
        print("\nУстановка прервана. Её можно запустить повторно.", file=sys.stderr)
        return 130
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(f"Ошибка установки: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
