"""음성 → 글자 (NVIDIA 호스팅 Parakeet 1.1B RNNT 다국어). docs/product/VOICE_INPUT_PLAN.md 부록.

휴대폰 녹음(webm/opus, iOS는 mp4/aac)을 ffmpeg로 16kHz 모노 WAV로 바꾼 뒤 전사한다.
녹음은 메모리와 임시 파일에서만 다루고 끝나면 지운다(저장하지 않음). 글자는 입력창에 넣기만 하고,
보내기 전에 사장님이 고친다(자동 전송 없음 — 화면 쪽 static/voice.js).
"""
import logging
import re
import subprocess
import tempfile
from pathlib import Path

from app.config import settings

log = logging.getLogger(__name__)

MAX_BYTES = 5 * 1024 * 1024
MAX_SECONDS = 60
ALLOWED_TYPES = ("audio/webm", "audio/ogg", "audio/mp4", "audio/wav", "audio/x-wav", "audio/mpeg", "audio/aac")


class SttUnavailable(Exception):
    pass


class BadAudio(Exception):
    pass


def to_wav16k(data: bytes) -> bytes:
    """어떤 형식이든 16kHz 모노 16비트 WAV로. 60초에서 자른다."""
    with tempfile.TemporaryDirectory() as d:
        src, dst = Path(d) / "in", Path(d) / "out.wav"
        src.write_bytes(data)
        try:
            subprocess.run(
                ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(src), "-t", str(MAX_SECONDS),
                 "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", str(dst)],
                check=True, timeout=20, capture_output=True,
            )
        except FileNotFoundError as e:
            raise SttUnavailable("ffmpeg 없음") from e
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            raise BadAudio("오디오 변환 실패") from e
        return dst.read_bytes()


def _recognize(wav: bytes) -> str:
    key = settings.nvidia_api_key or settings.nim_api_key
    if not settings.stt_enabled or not key:
        raise SttUnavailable("음성 인식 꺼짐")
    import riva.client  # grpc를 쓰는 무거운 모듈이라 실제로 부를 때만 가져온다

    auth = riva.client.Auth(uri=settings.stt_server, use_ssl=True, metadata_args=[
        ["function-id", settings.stt_function_id], ["authorization", f"Bearer {key}"]])
    config = riva.client.RecognitionConfig(
        encoding=riva.client.AudioEncoding.LINEAR_PCM, sample_rate_hertz=16000, language_code="ko-KR",
        max_alternatives=1, enable_automatic_punctuation=True, audio_channel_count=1)
    try:
        resp = riva.client.ASRService(auth).offline_recognize(wav, config)
    except Exception as e:
        log.warning("음성 인식 호출 실패: %s", type(e).__name__)
        raise SttUnavailable("음성 인식 호출 실패") from e
    return " ".join(r.alternatives[0].transcript for r in resp.results if r.alternatives).strip()


_KO_DIGITS = {"공": "0", "영": "0", "빵": "0", "일": "1", "이": "2", "삼": "3", "사": "4",
              "오": "5", "육": "6", "륙": "6", "칠": "7", "팔": "8", "구": "9"}
# 한글로 읽은 숫자가 7자 이상 이어지면(전화번호) 숫자로 바꾼다. 짧은 말("이 사진")은 건드리지 않는다.
_KO_DIGIT_RUN = re.compile(r"(?:[공영빵일이삼사오육륙칠팔구][\s-]*){7,}[공영빵일이삼사오육륙칠팔구]?")


def normalize_digits(text: str) -> str:
    def conv(m):
        chars = [c for c in m.group(0) if c in _KO_DIGITS]
        digits = "".join(_KO_DIGITS[c] for c in chars)
        if len(digits) == 11 and digits.startswith("01"):
            return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
        return digits
    return _KO_DIGIT_RUN.sub(conv, text)


def transcribe(data: bytes) -> str:
    if len(data) > MAX_BYTES:
        raise BadAudio("너무 큼")
    return normalize_digits(_recognize(to_wav16k(data)))
