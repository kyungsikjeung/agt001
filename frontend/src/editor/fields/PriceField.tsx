// 가격 칸 (공용 단위 칸 위에 만든 메뉴·객실 가격). 숫자만 누르면 "4,500원"으로, "시가·가격 문의"는 직접 쓰기.
// 저장 모양은 예전과 같은 글("4,500원")이라 서버·공개 사이트는 그대로다. 금액이 숫자 모양으로 모이므로
// 나중에 결제를 붙일 때 이 값을 결제 금액으로 쓴다(직접 쓰기 값은 결제 대상에서 빼면 된다).
import { useState } from 'react';
import UnitValueField, { PRICE_UNITS, parsePrice } from './UnitValueField';

export function wonText(value: string): string {
  return value ? `${Number(value).toLocaleString('ko-KR')}원` : '';
}

export default function PriceField({ price, disabled, onChange }: { price: string; disabled?: boolean; onChange: (price: string) => void }) {
  const [unit, setUnit] = useState(() => parsePrice(price).unit);
  const parsed = parsePrice(price);
  const value = unit === 'won' ? (parsed.unit === 'won' ? parsed.value : '') : price;
  return (
    <UnitValueField
      label="가격"
      units={PRICE_UNITS}
      unit={unit}
      value={value}
      disabled={disabled}
      onChange={(u, v) => {
        if (u !== unit) {
          setUnit(u);
          // 금액 → 직접 쓰기로 바꾸면 보이던 글("4,500원")을 그대로 두고 고치게 한다
          onChange(u === 'text' ? price : parsePrice(price).unit === 'won' ? price : '');
          return;
        }
        onChange(u === 'won' ? wonText(v) : v);
      }}
    />
  );
}
