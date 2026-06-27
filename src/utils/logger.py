from __future__ import annotations

import logging
import threading

_LOCK = threading.Lock()


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    with _LOCK:
        if logger.handlers:
            return logger
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter('%(asctime)s | %(levelname)s | %(name)s | %(message)s')
        )
        logger.addHandler(handler)
        logger.propagate = False
    return logger
