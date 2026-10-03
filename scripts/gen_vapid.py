"""휴대폰 알림(웹 푸시) VAPID 키 만들기 (OWNER_NOTIFY_PLAN N2).

비밀 키 한 줄과 공개 키를 출력한다. 비밀 키는 서버 .env의 VAPID_PRIVATE_KEY에 넣거나
관리자 화면 > 키 관리 > "휴대폰 알림(웹 푸시) VAPID 비밀 키"에 넣는다(값은 이 저장소에 커밋하지 않는다).
공개 키는 서버가 비밀 키에서 계산해 브라우저에 주므로 따로 넣을 곳은 없다(확인용).

키를 바꾸면 이미 켠 기기는 모두 다시 "휴대폰 알림 켜기"를 눌러야 한다. 한 번 만들면 계속 쓴다.

사용법: .venv/bin/python scripts/gen_vapid.py
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


if __name__ == "__main__":  # 서버 설정(.env) 없이 돈다. 형식은 app/services/push.py와 같다
    key = ec.generate_private_key(ec.SECP256R1())
    private = _b64e(key.private_numbers().private_value.to_bytes(32, "big"))
    public = _b64e(key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
    print(f"VAPID_PRIVATE_KEY={private}")
    print(f"# 공개 키(확인용): {public}")
    print("# VAPID_SUBJECT=mailto:운영자메일  (애플 푸시에 필요. 비우면 PUBLIC_BASE_URL을 쓴다)")
