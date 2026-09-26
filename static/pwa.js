// 서비스 워커 등록(홈 화면 설치용). 지원하지 않는 브라우저에서는 아무 일도 하지 않는다.
if ('serviceWorker' in navigator && location.protocol === 'https:') {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  });
}
// 설치 가능할 때 화면(랜딩의 "앱 설치" 버튼)이 쓸 수 있게 이벤트를 보관한다.
window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  window.__agtInstall = e;
  window.dispatchEvent(new Event('agt-install-ready'));
});
window.addEventListener('appinstalled', () => {
  window.__agtInstall = null;
  window.dispatchEvent(new Event('agt-install-ready'));
});
