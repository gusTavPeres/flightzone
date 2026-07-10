"""Logging simples para o terminal."""
import logging
import sys

_configured = False


def setup_logger(name: str) -> logging.Logger:
    global _configured
    if not _configured:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
            stream=sys.stdout,
        )
        _configured = True
    return logging.getLogger(name)
