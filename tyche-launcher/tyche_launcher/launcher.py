"""Launcher - process lifecycle management."""

import subprocess
import time
import logging
import threading
import os
from typing import Dict, Optional

from .config import LauncherConfig, ModuleConfig
from .monitor import ProcessMonitor


class Launcher:
    """Manages module processes lifecycle.

    Reads configuration, starts modules as subprocesses,
    monitors their health, and applies restart policies.
    """

    def __init__(self, config: LauncherConfig):
        self.config = config
        self._monitors: Dict[str, ProcessMonitor] = {}
        self._module_configs: Dict[str, ModuleConfig] = {}
        self._processes: Dict[str, Optional[subprocess.Popen]] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._logger = logging.getLogger("tyche.launcher")

        # Create monitors for each module
        for mod_config in config.modules:
            self._monitors[mod_config.name] = ProcessMonitor(
                name=mod_config.name,
                restart_policy=mod_config.restart_policy,
                max_restarts=mod_config.max_restarts,
                restart_window_seconds=mod_config.restart_window_seconds,
                cpu_core=mod_config.cpu_core,
            )
            self._module_configs[mod_config.name] = mod_config
            self._processes[mod_config.name] = None

    def start(self) -> None:
        """Start all configured modules."""
        self._running = True

        # Start all modules
        for mod_config in self.config.modules:
            self._start_module(mod_config)

        # Start polling thread
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._logger.info("Launcher started")

    def stop(self) -> None:
        """Stop all running modules."""
        self._running = False

        for name, process in self._processes.items():
            if process:
                self._stop_module(name, process)

        if self._thread:
            self._thread.join(timeout=5.0)

        self._logger.info("Launcher stopped")

    def _run(self) -> None:
        """Main run loop - poll and restart as needed."""
        while self._running:
            # Check each process
            for name, process in self._processes.items():
                if process:
                    poll_result = process.poll()
                    if poll_result is not None:
                        # Process exited
                        monitor = self._monitors[name]
                        monitor.record_exit(poll_result)
                        self._processes[name] = None

                        if monitor.should_restart():
                            self._start_module(self._module_configs[name])

            time.sleep(self.config.poll_interval_ms / 1000.0)

    def _start_module(self, mod_config: ModuleConfig) -> None:
        """Start a single module as subprocess."""
        monitor = self._monitors[mod_config.name]

        # Only skip if we've already started and shouldn't restart
        if monitor.start_count > 0 and not monitor.should_restart():
            self._logger.info(f"Skipping restart for {mod_config.name} (policy or circuit breaker)")
            return

        env = os.environ.copy()
        env.update(mod_config.environment)

        try:
            process = subprocess.Popen(
                mod_config.command,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self._processes[mod_config.name] = process
            monitor.record_start(process.pid)
            self._logger.info(f"Started {mod_config.name} (pid={process.pid})")
        except Exception as e:
            self._logger.error(f"Failed to start {mod_config.name}: {e}")

    def _stop_module(self, name: str, process: subprocess.Popen) -> None:
        """Stop a single module process."""
        try:
            process.terminate()
            process.wait(timeout=5)
            self._logger.info(f"Stopped {name}")
        except subprocess.TimeoutExpired:
            process.kill()
            self._logger.warning(f"Force killed {name}")
        except Exception as e:
            self._logger.error(f"Error stopping {name}: {e}")

    def poll(self) -> None:
        """Poll all processes and handle restarts."""
        # This is called by the run loop, but can also be called manually
        pass

    def get_status(self) -> Dict[str, dict]:
        """Get status of all monitored modules."""
        return {
            name: monitor.get_status()
            for name, monitor in self._monitors.items()
        }

    def run(self) -> None:
        """Start and run until interrupted."""
        self.start()
        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()
