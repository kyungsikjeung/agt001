// 서비스 워커 등록(홈 화면 설치용). 지원하지 않는 브라우저에서는 아무 일도 하지 않는다.
if ('serviceWorker' in navigator && location.protocol === 'https:') {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  });
}
