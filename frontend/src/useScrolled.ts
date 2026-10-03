import { useEffect, useState } from 'react';

/** 페이지가 조금이라도 내려갔는가. 위 띠를 투명 → 진한 바탕으로 바꿀 때 쓴다(랜딩·내 프로젝트). */
export function useScrolled(offset = 8): boolean {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > offset);
    on();
    window.addEventListener('scroll', on, { passive: true });
    return () => window.removeEventListener('scroll', on);
  }, [offset]);
  return scrolled;
}
