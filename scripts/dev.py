#!/usr/bin/env python3
"""Supervise only the two local processes started by this script (macOS/Linux)."""

import argparse
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "backend" / ".venv" / "bin" / "python"
FRONTEND = ROOT / "frontend"
PORTS = (8000, 5173)


class StopRequested(Exception):
    def __init__(self, signum: int):
        self.signum = signum


def check_environment(*, production: bool = False) -> str:
    if os.name != "posix":
        raise RuntimeError("Общий запуск поддерживает macOS/Linux. Для другой системы запустите два сервиса отдельно по README.")
    if not PYTHON.is_file():
        raise RuntimeError("Нет backend/.venv. Сначала выполните: python3 scripts/setup.py")
    subprocess.run([str(PYTHON), "-c", "import fastapi, uvicorn, pydantic"], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    npm = shutil.which("npm")
    if not npm or not shutil.which("node") or not (FRONTEND / "node_modules" / "next" / "package.json").is_file():
        raise RuntimeError("Не найдены Node.js/npm или зависимости frontend. Выполните: python3 scripts/setup.py")
    if production and not (FRONTEND / ".next" / "BUILD_ID").is_file():
        raise RuntimeError("Нет production-сборки. Выполните: npm --prefix frontend run build")
    busy = []
    for port in PORTS:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                # Match server bind behaviour: recently closed connections in
                # TIME_WAIT must not look like an active listening server.
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                probe.bind(("127.0.0.1", port))
        except OSError as error:
            busy.append(f"127.0.0.1:{port}: {error}")
    if busy:
        raise RuntimeError("Порты недоступны; существующие процессы не тронуты:\n" + "\n".join(busy))
    return npm


def stop_processes(processes: list[tuple[str, subprocess.Popen]]) -> None:
    """Stop our sessions, including grandchildren left behind by npm."""
    for _, process in processes:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            if process.poll() is None:
                process.terminate()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if all(process.poll() is not None for _, process in processes):
            break
        time.sleep(0.1)
    for _, process in processes:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            if process.poll() is None:
                process.kill()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass


def supervise(commands: list[tuple[str, list[str], Path]], environment: dict[str, str]) -> int:
    processes: list[tuple[str, subprocess.Popen]] = []
    old_handlers = {}
    stop_signal = None

    def request_stop(signum: int, frame) -> None:
        nonlocal stop_signal
        stop_signal = signum

    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            old_handlers[signum] = signal.signal(signum, request_stop)
        for name, command, directory in commands:
            if stop_signal is not None:
                raise StopRequested(stop_signal)
            process = subprocess.Popen(command, cwd=directory, env=environment, start_new_session=True)
            processes.append((name, process))
            print(f"Запущен {name} (PID {process.pid}).", flush=True)
        print("\nИнтерфейс: http://127.0.0.1:5173 · API: http://127.0.0.1:8000/docs", flush=True)
        print("Дождитесь сообщения Ready от Next.js. Ctrl-C остановит оба сервиса.\n", flush=True)
        while True:
            if stop_signal is not None:
                raise StopRequested(stop_signal)
            for name, process in processes:
                result = process.poll()
                if result is not None:
                    print(f"{name} завершился (код {result}); останавливаем остальные сервисы.", file=sys.stderr)
                    return result if result > 0 else 1
            time.sleep(0.2)
    except StopRequested as error:
        print("\nОстанавливаем локальные сервисы…", flush=True)
        return 130 if error.signum == signal.SIGINT else 128 + error.signum
    except OSError as error:
        print(f"Не удалось запустить сервис: {error}", file=sys.stderr)
        return 1
    finally:
        for signum in old_handlers:
            signal.signal(signum, signal.SIG_IGN)
        stop_processes(processes)
        for signum, handler in old_handlers.items():
            signal.signal(signum, handler)


def main() -> int:
    parser = argparse.ArgumentParser(description="Совместный локальный запуск FastAPI и Next.js с остановкой дочерних процессов.")
    parser.add_argument("--check", action="store_true", help="Проверить зависимости и доступность портов, не запускать серверы.")
    parser.add_argument("--production", action="store_true", help="Запустить готовую Next.js-сборку через npm start после npm run build.")
    args = parser.parse_args()
    try:
        npm = check_environment(production=args.production)
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(f"Запуск отменён: {error}", file=sys.stderr)
        return 1
    if args.check:
        print("Зависимости доступны; порты 8000 и 5173 свободны. Серверы не запускались.")
        return 0
    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"
    environment["BACKEND_URL"] = "http://127.0.0.1:8000"
    commands = [
        ("FastAPI", [str(PYTHON), "-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "127.0.0.1", "--port", "8000"], ROOT),
        ("Next.js", [npm, "run", "start" if args.production else "dev"], FRONTEND),
    ]
    return supervise(commands, environment)


if __name__ == "__main__":
    raise SystemExit(main())
