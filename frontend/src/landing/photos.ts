// 랜딩 예시 사진 (Gemini 생성, scripts/gen_landing_examples.py). D51: 실사 느낌이라 화면에 "예시 이미지"를 붙인다.
const files = import.meta.glob<string>('./img/*.webp', { eager: true, import: 'default' });

// './img/cafe.webp' → 'cafe'
export const PHOTOS: Record<string, string> = Object.fromEntries(
  Object.entries(files).map(([path, url]) => [path.slice('./img/'.length, -'.webp'.length), url]),
);

// 아래쪽을 어둡게 깔아 흰 글자(가게 이름)가 읽히게 한다.
export const photoBg = (url: string) =>
  `linear-gradient(180deg, rgba(0,0,0,0) 30%, rgba(0,0,0,0.62)), url(${url}) center / cover`;
