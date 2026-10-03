# 화면 백업 (2026-10-03)

실시간 대화·미리보기 화면(`static/live.html`)을 만들기 전의 화면을 그대로 둔 것이다. 고치지 않는다.

| 파일 | 원본 | 주소 |
|---|---|---|
| room.html | static/room.html (채팅방) | `/backup/2026-10-03/room.html?room=<id>` |
| voice.js | static/voice.js (마이크·무전기·손 안 쓰는 모드·읽어주기) | room.html이 이 사본을 쓴다 |
| callbot.js | static/callbot.js (전화로 답하기) | room.html이 이 사본을 쓴다 |
| chat.html·index.html | 같은 이름 | `/backup/2026-10-03/chat.html` |

코드 기준점: 커밋 `e00ad37`. 되돌릴 때는 이 파일들을 static/로 다시 복사한다.
