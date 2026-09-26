"""글자 → 음성 (NVIDIA 호스팅 Magpie TTS 다국어). docs/product/VOICE_INPUT_PLAN.md 부록.

AI 답장을 읽어주는 선택 버튼용이다. 자동 재생하지 않는다(화면 쪽 static/voice.js).
Riva가 내놓는 날것 PCM(16비트 모노)에 WAV 머리말을 붙여서 돌려준다.
인증 방식은 인식(stt.py)과 같다: Riva gRPC grpc.nvcf.nvidia.com:443,
metadata function-id + authorization Bearer. 키도 인식과 같은 키를 쓴다.
"""
import logging
import struct

from app.config import settings
from app.services import keystore

log = logging.getLogger(__name__)

# Riva 합성 요청 형식. 인식과 같은 서버를 쓴다.
TTS_SERVER = "grpc.nvcf.nvidia.com:443"
SAMPLE_RATE = 22050
MAX_CHARS = 300


class TtsUnavailable(Exception):
    pass


class TtsUpstream(Exception):
    pass


def to_wav(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    """날것 PCM(16비트 모노)에 44바이트 WAV 머리말을 붙인다."""
    head = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(pcm), b"WAVE",
        b"fmt ", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16,
        b"data", len(pcm),
    )
    return head + pcm


def _synthesize_pcm(text: str) -> bytes:
    key = settings.nvidia_api_key or keystore.get("nim_api_key")
    if not settings.tts_enabled or not key:
        raise TtsUnavailable("음성 합성 꺼짐")
    import riva.client  # grpc를 쓰는 무거운 모듈이라 실제로 부를 때만 가져온다

    auth = riva.client.Auth(uri=TTS_SERVER, use_ssl=True, metadata_args=[
        ["function-id", settings.tts_function_id], ["authorization", f"Bearer {key}"]])
    svc = riva.client.SpeechSynthesisService(auth)
    try:
        future = svc.synthesize(
            text,
            voice_name=settings.tts_voice,
            language_code="ko-KR",
            encoding=riva.client.AudioEncoding.LINEAR_PCM,
            sample_rate_hz=SAMPLE_RATE,
            future=True,
        )
        resp = future.result(timeout=settings.tts_timeout_sec)
    except Exception as e:
        log.warning("음성 합성 호출 실패: %s", type(e).__name__)
        raise TtsUpstream("음성 합성 호출 실패") from e
    pcm = bytes(getattr(resp, "audio", b"") or b"")
    if not pcm:
        raise TtsUpstream("빈 오디오")
    return pcm


def synthesize(text: str) -> bytes:
    """깨끗한 글자(1~300자)를 WAV 바이트로 바꾼다. 길이는 API 층에서 자른다."""
    return to_wav(_synthesize_pcm(text))
