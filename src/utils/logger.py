from __future__ import annotations

import logging
import os
import threading

_LOCK = threading.Lock()


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    level_name = os.getenv('SCREENER_LOG_LEVEL', 'WARNING').upper()
    level = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL,
    }.get(level_name, logging.WARNING)

    with _LOCK:
        logger.setLevel(level)
        if logger.handlers:
            return logger
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter('%(asctime)s | %(levelname)s | %(name)s | %(message)s')
        )
        logger.addHandler(handler)
        logger.propagate = False
    return logger
