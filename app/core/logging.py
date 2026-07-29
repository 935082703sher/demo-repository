"""Safe application logging configuration."""

import logging


def configure_logging(level: str) -> None:
    """Configure consistent logs without citizen message content."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s level=%(levelname)s logger=%(name)s %(message)s",
        force=True,
    )
