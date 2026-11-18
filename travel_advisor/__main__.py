"""``python -m travel_advisor`` 的入口。"""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.getenv("TRAVEL_ADVISOR_HOST", "127.0.0.1")
    port = int(os.getenv("TRAVEL_ADVISOR_PORT", "8010"))
    uvicorn.run("travel_advisor.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
