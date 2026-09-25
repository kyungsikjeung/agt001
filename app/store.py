"""세션·방 저장소.

0-1 단계: 인메모리 dict가 원본이고 JSON 파일은 재시작 복구용 백업이다.
0-2 단계에서 PostgreSQL 구현으로 교체한다. 호출부는 이 모듈의 인터페이스만 쓴다.
"""
import json
import logging
import threading
from typing import Callable, Optional

from app.config import settings

log = logging.getLogger(__name__)


class JsonStore:
    def __init__(self, filename: str, on_load: Optional[Callable[[dict], None]] = None):
        self.filename = filename
        self.on_load = on_load
        self.data: dict = {}
        # 요청 스레드와 코드생성 백그라운드 스레드가 동시에 접근한다.
        self.lock = threading.Lock()

    @property
    def path(self):
        return settings.generated_dir / self.filename

    def get(self, key, default=None):
        with self.lock:
            return self.data.get(key, default)

    def setdefault(self, key, value):
        with self.lock:
            return self.data.setdefault(key, value)

    def set(self, key, value):
        with self.lock:
            self.data[key] = value

    def clear(self):
        with self.lock:
            self.data.clear()

    def save(self) -> None:
        """원자적으로(tmp+rename) 저장한다. 실패해도 요청 처리는 계속한다."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.path.with_suffix(".json.tmp")
            with self.lock:
                payload = json.dumps(self.data, ensure_ascii=False)
            tmp_path.write_text(payload, encoding="utf-8")
            tmp_path.replace(self.path)
        except Exception:
            log.exception("%s 저장 실패 (계속 진행)", self.filename)

    def load(self) -> None:
        if not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            log.exception("%s 복구 실패 (빈 상태로 시작)", self.filename)
            return
        if self.on_load:
            for item in data.values():
                self.on_load(item)
        with self.lock:
            self.data.update(data)
        log.info("%s: %d개 복구", self.filename, len(data))


def _recover_session(session: dict) -> None:
    # 코드생성 스레드는 재시작과 함께 사라지므로, 사용자가 '진행'으로 재시도할 수 있게 되돌린다.
    if session.get("state") == "GENERATING":
        session["state"] = "QUOTED"
        session["codegen"] = None


def _recover_room(room: dict) -> None:
    room["ai_status"] = "IDLE"


sessions = JsonStore("sessions.json", on_load=_recover_session)
rooms = JsonStore("rooms.json", on_load=_recover_room)
