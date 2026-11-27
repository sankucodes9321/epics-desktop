"""Process-level hardening and structured application diagnostics."""
import atexit
from datetime import datetime, timezone
import gc
import json
import logging
import resource


class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({"timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                           "level": record.levelname, "message": record.getMessage(),
                           **getattr(record, "metrics", {})})


def startup(verbose=False):
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    atexit.register(gc.collect)
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(handlers=[handler], level=logging.INFO, force=True)
    logging.getLogger("privacy").setLevel(logging.DEBUG if verbose else logging.INFO)
