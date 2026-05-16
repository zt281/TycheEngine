"""一键启动 TycheEngine + StaticData + 运行 query_ag_example.

自动清理残留 Python 进程，按序启动，查询完成后退出。
"""

import logging
import os
import signal
import subprocess
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

PYTHON = sys.executable
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def kill_stale_processes():
    """杀掉占用引擎端口的残留 Python 进程."""
    import re

    ports = {"5555", "5556", "5559", "5560", "5564"}
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, timeout=5,
        )
        pids_to_kill = set()
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 5:
                local_addr = parts[1]
                state = parts[3] if len(parts) > 3 else ""
                pid = parts[4]
                for port in ports:
                    if f":{port}" in local_addr and state in ("LISTENING", "ESTABLISHED"):
                        try:
                            pids_to_kill.add(int(pid))
                        except ValueError:
                            pass
        for pid in pids_to_kill:
            if pid != os.getpid():
                logger.info("Killing stale process PID %d", pid)
                subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                               capture_output=True, timeout=5)
        if pids_to_kill:
            time.sleep(2)  # 等待端口释放
    except Exception as e:
        logger.warning("Failed to check/kill stale processes: %s", e)


def wait_for_port(port: int, timeout: float = 10.0) -> bool:
    """等待端口被监听."""
    import socket
    start = time.time()
    while time.time() - start < timeout:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            s.connect(("127.0.0.1", port))
            s.close()
            return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.2)
    return False


def main():
    # 1. 清理残留进程
    logger.info("Step 1: Cleaning stale processes...")
    kill_stale_processes()

    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.join(PROJECT_ROOT, "src")

    procs = []

    try:
        # 2. 启动引擎
        logger.info("Step 2: Starting TycheEngine...")
        engine = subprocess.Popen(
            [PYTHON, "main.py"],
            cwd=PROJECT_ROOT, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        procs.append(engine)

        if not wait_for_port(5555):
            logger.error("Engine failed to start on port 5555")
            return
        logger.info("Engine is ready on port 5555")

        # 3. 启动 static_data 模块
        logger.info("Step 3: Starting static_data module...")
        static_data = subprocess.Popen(
            [PYTHON, "-m", "src.modules.static_data"],
            cwd=PROJECT_ROOT, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        procs.append(static_data)
        time.sleep(2)  # 等待模块注册

        # 4. 运行 query_ag_example
        logger.info("Step 4: Running query_ag_example...")
        result = subprocess.run(
            [PYTHON, "examples/query_ag_example.py"],
            cwd=PROJECT_ROOT,
            capture_output=True, text=True, timeout=60,
        )
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        logger.info("query_ag_example exited with code %d", result.returncode)

    except subprocess.TimeoutExpired:
        logger.error("query_ag_example timed out!")
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        # 5. 清理
        logger.info("Cleaning up...")
        for p in procs:
            p.terminate()
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                p.kill()
        logger.info("Done.")


if __name__ == "__main__":
    main()
