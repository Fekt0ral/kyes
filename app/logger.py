import logging
from config import settings
import sys

def setup_logging() -> None:
    level = settings.log_level.upper()
    logging.basicConfig(
        level=level,
        format=settings.log_format,
        handlers=[logging.StreamHandler(sys.stdout)],
    )

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)