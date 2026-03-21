# tyche/utils/logging.py
import json, sys, time

class StructuredLogger:
    def __init__(self, service_name: str):
        self.service_name = service_name

    def _emit(self, level: str, message: str, **kwargs):
        print(json.dumps({"timestamp_ns": time.time_ns(), "service": self.service_name,
                           "level": level, "message": message, **kwargs}),
              file=sys.stderr, flush=True)

    def info(self, msg, **kw): self._emit("INFO", msg, **kw)
    def warn(self, msg, **kw): self._emit("WARN", msg, **kw)
    def error(self, msg, **kw): self._emit("ERROR", msg, **kw)
    def debug(self, msg, **kw): self._emit("DEBUG", msg, **kw)
