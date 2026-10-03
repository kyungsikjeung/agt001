// 한마디 까치 표정 (빈 화면·불러오는 중·오류). 그림은 꾸밈이라 alt를 비우고 글은 그대로 읽힌다.
import type { ReactNode } from 'react';

const SRC = { hi: '/icons/kkachi.svg', wait: '/icons/kkachi-wait.svg', oops: '/icons/kkachi-oops.svg' } as const;

export default function Mascot({
  mood,
  role,
  className = '',
  children,
}: {
  mood: keyof typeof SRC;
  role?: 'status' | 'alert';
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={`mascot mascot--${mood} ${className}`.trim()}>
      <img className="mascot__img" src={SRC[mood]} alt="" width={72} height={72} />
      <div className="mascot__body" role={role}>
        {children}
      </div>
    </div>
  );
}
