import json
from datetime import datetime
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "router_log.jsonl"


def write_log(record: dict[str, Any]) -> None:
    """βRouterの実行記録をJSONL形式で保存する。"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    log_record = {
        "timestamp": datetime.now().astimezone().isoformat(
            timespec="seconds"
        ),
        **record,
    }

    with LOG_FILE.open("a", encoding="utf-8") as file:
        file.write(
            json.dumps(
                log_record,
                ensure_ascii=False,
            )
            + "\n"
        )
