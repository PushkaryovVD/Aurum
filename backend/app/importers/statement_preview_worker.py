"""Resource-limited worker for parsing untrusted statement documents."""
import json
from pathlib import Path
import resource
import sys

WORKER_MEMORY_LIMIT_BYTES = 1536 * 1024 * 1024
WORKER_CPU_LIMIT_SECONDS = 120


def _write_error(detail: str) -> int:
    sys.stdout.write(json.dumps({"error": detail}))
    return 0


def main() -> int:
    resource.setrlimit(
        resource.RLIMIT_AS,
        (WORKER_MEMORY_LIMIT_BYTES, WORKER_MEMORY_LIMIT_BYTES),
    )
    resource.setrlimit(
        resource.RLIMIT_CPU,
        (WORKER_CPU_LIMIT_SECONDS, WORKER_CPU_LIMIT_SECONDS),
    )
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

    # Import parsers only after limits are active. Native PDF/XLSX libraries
    # therefore never execute against an untrusted upload in the API process.
    from fastapi import HTTPException

    from app.importers import resolve_importers

    file_name = sys.argv[1] if len(sys.argv) > 1 else "statement"
    content = sys.stdin.buffer.read()
    importers = resolve_importers(file_name)
    if not importers:
        return _write_error("Unsupported statement file type")

    errors: list[str] = []
    for importer in importers:
        try:
            preview = importer.parse(file_name, content)
            sys.stdout.write('{"preview":')
            sys.stdout.write(preview.model_dump_json())
            sys.stdout.write("}")
            return 0
        except HTTPException as exc:
            if exc.status_code != 422:
                return _write_error("Statement parsing failed")
            errors.append(str(exc.detail))
        except Exception:
            return _write_error("Statement parsing failed")

    return _write_error("Statement format was not recognized: " + "; ".join(errors))


if __name__ == "__main__":
    raise SystemExit(main())
