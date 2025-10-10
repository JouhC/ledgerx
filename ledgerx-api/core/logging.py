import logging
import sys

def setup_logging(level: str = "INFO") -> None:
    """Set up global logging format and handlers."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Reduce noise from external libraries (optional)
    logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)
    logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
