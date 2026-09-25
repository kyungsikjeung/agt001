"""tests/engine 전용 conftest. DB 없이 엔진 단위 검증만 돌린다.

앱 import 전에 테스트용 환경변수를 고정한다 (.env를 읽지 않고 동작해야 함).
실제 NVIDIA/NIM 호출 금지: 모든 테스트는 llm.chat_json을 가짜로 바꾼다.
"""
import os

os.environ.setdefault("NIM_API_KEY", "test")
os.environ["PRECOMPUTE_EMBEDDINGS"] = "false"
os.environ["RUN_MIGRATIONS_ON_STARTUP"] = "false"
