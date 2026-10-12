"""The last few hundred log lines, kept in memory for the Settings page.

The service runs unprivileged and can't read its own journal, so the page reads
this instead of journalctl.
"""
import logging
from collections import deque

LINES = deque(maxlen=400)


class _Handler(logging.Handler):
    def emit(self, record):
        try:
            msg = record.getMessage()
            if record.exc_info:
                msg += "\n" + logging.Formatter().formatException(record.exc_info)
            LINES.append({"t": round(record.created, 3), "level": record.levelname,
                          "name": record.name, "msg": msg[:4000]})
        except Exception:  # logging must never raise
            pass


def install(level=logging.INFO):
    h = _Handler(level)
    logging.getLogger().addHandler(h)
    return h


def lines(since=0.0):
    return [x for x in list(LINES) if x["t"] > since]
