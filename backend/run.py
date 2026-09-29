"""
SynthGen AI — Server entry point.

Usage:
    cd backend
    python -m uvicorn app.main:app --reload --port 8000

Or:
    python run.py
"""
import uvicorn
from app.core.config import get_config


def main():
    config = get_config()
    uvicorn.run(
        "app.main:app",
        host=config.server.host,
        port=config.server.port,
        reload=config.server.debug,
        log_level="info",
    )


if __name__ == "__main__":
    main()
