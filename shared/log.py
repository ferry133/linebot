"""Logging setup with Asia/Taipei (UTC+8) timestamps."""

import logging
from datetime import datetime, timezone, timedelta

_TAIPEI = timezone(timedelta(hours=8))


class _TaipeiFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=_TAIPEI)
        return dt.strftime(datefmt or "%H:%M:%S")


def setup(level=logging.INFO):
    handler = logging.StreamHandler()
    handler.setFormatter(_TaipeiFormatter("%(asctime)s %(message)s", datefmt="%H:%M:%S"))
    logging.root.handlers = []
    logging.root.addHandler(handler)
    logging.root.setLevel(level)
