from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


DEFAULT_CORS_ORIGINS = (
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
)


@dataclass(frozen=True)
class ServiceSettings:
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: tuple[str, ...] = DEFAULT_CORS_ORIGINS

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> ServiceSettings:
        values = os.environ if environ is None else environ
        host = values.get("SOLVER_HOST", "127.0.0.1").strip() or "127.0.0.1"
        raw_port = values.get("SOLVER_PORT", "8000")
        try:
            port = int(raw_port)
        except ValueError as error:
            raise ValueError("SOLVER_PORT must be an integer between 1 and 65535.") from error
        if not 1 <= port <= 65535:
            raise ValueError("SOLVER_PORT must be an integer between 1 and 65535.")

        raw_origins = values.get("SOLVER_CORS_ORIGINS")
        if raw_origins is None:
            cors_origins = DEFAULT_CORS_ORIGINS
        else:
            cors_origins = tuple(origin.strip().rstrip("/") for origin in raw_origins.split(",") if origin.strip())
        return cls(host=host, port=port, cors_origins=cors_origins)
