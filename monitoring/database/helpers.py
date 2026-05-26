import re
import traceback

_PARAM_RE = re.compile(
    r"'[^']*'"  # single-quoted strings
    r'|"[^"]*"'  # double-quoted strings
    r"|\b\d+\b"  # bare integers
    r"|\$\d+"  # $1 $2 … positional params (postgres)
    r"|\?",  # ? params (sqlite / mysql)
    re.IGNORECASE,
)
_WS_RE = re.compile(r"\s+")


def normalize_sql(sql: str) -> str:
    sql = _PARAM_RE.sub("?", sql)
    sql = _WS_RE.sub(" ", sql).strip().upper()
    return sql


_SKIP_MODULES = {
    "sqlalchemy",
    "sqlmodel",
    "starlette",
    "fastapi",
    "anyio",
    "asyncio",
    "uvicorn",
    "asyncpg",
    "psycopg",
    "pymysql",
    "sqlite3",
    "concurrent",
    "threading",
    "importlib",
}


def capture_stack(depth: int = 20) -> list[str]:
    frames = []

    for frame_info in traceback.extract_stack()[:-2]:  # drop capture_stack itself
        module = frame_info.filename
        if any(skip in module for skip in _SKIP_MODULES):
            continue

        frames.append(
            f"    {frame_info.filename}:{frame_info.lineno} in {frame_info.name}\n" f"      {frame_info.line}"
        )

        if len(frames) >= depth:
            break

    return frames
