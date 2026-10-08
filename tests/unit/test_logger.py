import logging

from src.utils.logger import get_logger


def test_logger_defaults_to_warning_and_respects_env(monkeypatch):
    logger_name = 'stock_screener.test_logger'
    logger = logging.getLogger(logger_name)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    logger.setLevel(logging.NOTSET)

    monkeypatch.delenv('SCREENER_LOG_LEVEL', raising=False)
    configured = get_logger(logger_name)
    assert configured.level == logging.WARNING

    monkeypatch.setenv('SCREENER_LOG_LEVEL', 'INFO')
    logger = logging.getLogger(logger_name)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    logger.setLevel(logging.NOTSET)
    configured = get_logger(logger_name)
    assert configured.level == logging.INFO
