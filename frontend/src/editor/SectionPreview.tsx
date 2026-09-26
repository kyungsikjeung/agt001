// 명세를 섹션 부품으로 그린 미리보기 (SPEC §2 클래스 규칙 s-<type>--<variant>).
// 편집 모드에서는 편집 가능한 글자가 버튼이 된다.
import type { DesignSection, DesignSpec, PlaceholderSlot } from './types';
import { isLocked } from './specReducer';

export interface EditTarget {
  sectionId: string;
  key: string;
  itemIndex?: number;
  itemField?: string;
  label: string;
  value: string;
  multiline?: boolean;
}

interface PreviewProps {
  spec: DesignSpec;
  mode: 'preview' | 'edit';
  placeholders: PlaceholderSlot[];
  onEdit: (t: EditTarget) => void;
}

function slotId(sectionId: string, key: string, itemIndex?: number): string {
  return itemIndex === undefined
    ? `slot-${sectionId}-${key}`
    : `slot-${sectionId}-${key}-${itemIndex}`;
}

function placeholderFor(
  placeholders: PlaceholderSlot[],
  sectionId: string,
  key: string,
  itemIndex?: number,
): PlaceholderSlot | undefined {
  return placeholders.find(
    (p) => p.sectionId === sectionId && p.key === key && (p.itemIndex ?? undefined) === itemIndex,
  );
}

function str(v: unknown): string {
  return typeof v === 'string' ? v : '';
}

interface FieldProps {
  id?: string;
  text: string;
  placeholder: string;
  locked: boolean;
  mode: 'preview' | 'edit';
  label: string;
  onEdit?: () => void;
  heading?: 'h1' | 'h2' | 'none';
}

function Field({ id, text, placeholder, locked, mode, label, onEdit, heading }: FieldProps) {
  const blank = text.trim() === '';
  const lockMark = locked ? (
    <span className="ed-lock" role="img" aria-label="직접 정하신 값(잠금)">
      🔒
    </span>
  ) : null;
  if (mode === 'preview' || !onEdit) {
    const cls = blank ? 'ed-field--slot' : undefined;
    const shown = blank ? placeholder : text;
    const inner = (
      <span className={cls} aria-label={blank ? `${label}: 아직 입력되지 않음` : undefined}>
        {shown}
        {lockMark}
      </span>
    );
    if (heading === 'h1') return <h1 className="s-title" id={id}>{inner}</h1>;
    if (heading === 'h2') return <h2 id={id}>{inner}</h2>;
    return <span id={id}>{inner}</span>;
  }
  return (
    <button
      type="button"
      id={id}
      className={blank ? 'ed-field ed-field--slot' : 'ed-field'}
      aria-label={`${label} 고치기${locked ? ' (직접 정하신 값)' : ''}${blank ? ': 아직 입력되지 않음' : ''}`}
      onClick={onEdit}
    >
      {blank ? placeholder : text}
      {lockMark}
    </button>
  );
}

function SectionShell({ section, children }: { section: DesignSection; children: React.ReactNode }) {
  return (
    <section className={`s-${section.type} s-${section.type}--${section.variant}`} aria-label={section.id}>
      {children}
    </section>
  );
}

export default function SectionPreview({ spec, mode, placeholders, onEdit }: PreviewProps) {
  const edit = (
    sectionId: string,
    key: string,
    label: string,
    value: string,
    extra?: { itemIndex?: number; itemField?: string; multiline?: boolean },
  ) => () =>
    onEdit({ sectionId, key, label, value, itemIndex: extra?.itemIndex, itemField: extra?.itemField, multiline: extra?.multiline });

  return (
    <>
      {spec.sections.map((section) => {
        const c = section.content as Record<string, unknown>;
        const locked = (key: string) => isLocked(spec, section.id, key);
        if (section.type === 'hero') {
          return (
            <SectionShell key={section.id} section={section}>
              <div className="s-media" aria-hidden="true" />
              <div className="s-hero__body">
                <p className="s-kicker">예시</p>
                <Field
                  heading="h1"
                  label="가게 이름"
                  text={str(c['title'])}
                  placeholder="[가게 이름 입력]"
                  locked={locked('title')}
                  mode={mode}
                  onEdit={edit(section.id, 'title', '가게 이름', str(c['title']))}
                />
                <p className="s-lead">
                  <Field
                    label="소개 한 줄"
                    text={str(c['subtitle'])}
                    placeholder="[소개 한 줄 입력]"
                    locked={locked('subtitle')}
                    mode={mode}
                    onEdit={edit(section.id, 'subtitle', '소개 한 줄', str(c['subtitle']), { multiline: true })}
                  />
                </p>
              </div>
            </SectionShell>
          );
        }
        if (section.type === 'intro') {
          if (str(c['body']).trim() === '' && mode === 'preview') return null;
          return (
            <SectionShell key={section.id} section={section}>
              <h2>소개</h2>
              <p>
                <Field
                  label="소개 글"
                  text={str(c['body'])}
                  placeholder="[소개 글 입력]"
                  locked={locked('body')}
                  mode={mode}
                  onEdit={edit(section.id, 'body', '소개 글', str(c['body']), { multiline: true })}
                />
              </p>
              {str(c['owner_name']).trim() !== '' || mode === 'edit' ? (
                <p>
                  사장님:{' '}
                  <Field
                    label="사장님 이름"
                    text={str(c['owner_name'])}
                    placeholder="[사장님 이름 입력]"
                    locked={locked('owner_name')}
                    mode={mode}
                    onEdit={edit(section.id, 'owner_name', '사장님 이름', str(c['owner_name']))}
                  />
                </p>
              ) : null}
            </SectionShell>
          );
        }
        if (section.type === 'offerings') {
          const items = (Array.isArray(c['items']) ? c['items'] : []) as Array<Record<string, unknown>>;
          return (
            <SectionShell key={section.id} section={section}>
              <h2>{str(c['label']) === '' ? '메뉴' : str(c['label'])}</h2>
              {items.length === 0 ? (
                <p>
                  <Field
                    id={slotId(section.id, 'items')}
                    label="상품·메뉴"
                    text=""
                    placeholder="[메뉴 입력]"
                    locked={locked('items')}
                    mode={mode}
                  />
                </p>
              ) : (
                <ul>
                  {items.map((item, i) => {
                    const slot = placeholderFor(placeholders, section.id, 'items', i);
                    return (
                      <li key={i} id={slot ? slotId(section.id, 'items', i) : undefined}>
                        <strong>
                          <Field
                            label={`${str(item['name']) === '' ? `항목 ${i + 1}` : str(item['name'])} 이름`}
                            text={str(item['name'])}
                            placeholder="[이름 입력]"
                            locked={locked('items')}
                            mode={mode}
                            onEdit={edit(section.id, 'items', '이름', str(item['name']), { itemIndex: i, itemField: 'name' })}
                          />
                        </strong>
                        {str(item['desc']) !== '' || mode === 'edit' ? (
                          <div>
                            <Field
                              label="설명"
                              text={str(item['desc'])}
                              placeholder="[설명 입력]"
                              locked={locked('items')}
                              mode={mode}
                              onEdit={edit(section.id, 'items', '설명', str(item['desc']), {
                                itemIndex: i,
                                itemField: 'desc',
                                multiline: true,
                              })}
                            />
                          </div>
                        ) : null}
                        <div>
                          <Field
                            label={`${str(item['name']) === '' ? `항목 ${i + 1}` : str(item['name'])} 가격`}
                            text={str(item['price'])}
                            placeholder="[가격 입력]"
                            locked={locked('items')}
                            mode={mode}
                            onEdit={edit(section.id, 'items', '가격', str(item['price']), { itemIndex: i, itemField: 'price' })}
                          />
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </SectionShell>
          );
        }
        if (section.type === 'gallery') {
          const items = (Array.isArray(c['items']) ? c['items'] : []) as Array<Record<string, unknown>>;
          if (items.length === 0) return null;
          return (
            <SectionShell key={section.id} section={section}>
              <h2>사진첩</h2>
              <ul>
                {items.map((item, i) => (
                  <li key={i}>{str(item['alt']) === '' ? `사진 ${i + 1}` : str(item['alt'])}</li>
                ))}
              </ul>
            </SectionShell>
          );
        }
        if (section.type === 'around') {
          const slot = placeholderFor(placeholders, section.id, 'address');
          return (
            <SectionShell key={section.id} section={section}>
              <h2>오시는 길</h2>
              <address>
                <Field
                  id={slot ? slotId(section.id, 'address') : undefined}
                  label="주소"
                  text={str(c['address'])}
                  placeholder="[주소 입력]"
                  locked={locked('address')}
                  mode={mode}
                  onEdit={edit(section.id, 'address', '주소', str(c['address']))}
                />
              </address>
            </SectionShell>
          );
        }
        if (section.type === 'contact') {
          const phoneSlot = placeholderFor(placeholders, section.id, 'phone');
          const hoursSlot = placeholderFor(placeholders, section.id, 'hours');
          const addrSlot = placeholderFor(placeholders, section.id, 'address');
          const phone = str(c['phone']);
          const channel = str(c['channel_url']);
          const showChannel = mode === 'edit' || channel.trim() !== '';
          return (
            <SectionShell key={section.id} section={section}>
              <h2>영업시간·연락</h2>
              {showChannel ? (
                mode === 'edit' ? (
                  <p>
                    <Field
                      label="카카오톡 채널 주소"
                      text={channel}
                      placeholder="[채널 주소 입력]"
                      locked={locked('channel_url')}
                      mode={mode}
                      onEdit={edit(section.id, 'channel_url', '카카오톡 채널 주소', channel)}
                    />
                  </p>
                ) : (
                  <p>
                    <a href={channel} target="_blank" rel="noopener noreferrer" aria-label="카카오톡 채널로 문의하기">
                      카카오톡으로 문의하기
                    </a>
                  </p>
                )
              ) : (
                <p className="ed-fact-note">채널이 없으면 전화·문자로 바로 받을 수 있어요</p>
              )}
              <dl>
                <dt>전화</dt>
                <dd id={phoneSlot ? slotId(section.id, 'phone') : undefined}>
                  {mode === 'edit' ? (
                    <Field
                      label="전화번호"
                      text={phone}
                      placeholder="[전화번호 입력]"
                      locked={locked('phone')}
                      mode={mode}
                      onEdit={edit(section.id, 'phone', '전화번호', phone)}
                    />
                  ) : phone.trim() === '' ? (
                    <span className="ed-field--slot" aria-label="전화번호: 아직 입력되지 않음">
                      [전화번호 입력]
                    </span>
                  ) : (
                    <a href={`tel:${phone.replace(/[^0-9+]/g, '')}`} aria-label="가게에 전화하기">
                      {phone}
                      {locked('phone') ? (
                        <span className="ed-lock" role="img" aria-label="직접 정하신 값(잠금)">
                          🔒
                        </span>
                      ) : null}
                    </a>
                  )}
                </dd>
                <dt>영업시간</dt>
                <dd id={hoursSlot ? slotId(section.id, 'hours') : undefined}>
                  <Field
                    label="영업시간"
                    text={str(c['hours'])}
                    placeholder="[영업시간 입력]"
                    locked={locked('hours')}
                    mode={mode}
                    onEdit={edit(section.id, 'hours', '영업시간', str(c['hours']))}
                  />
                </dd>
                {(str(c['address']).trim() !== '' || mode === 'edit') && (
                  <>
                    <dt>주소</dt>
                    <dd id={addrSlot ? slotId(section.id, 'address') : undefined}>
                      <Field
                        label="주소"
                        text={str(c['address'])}
                        placeholder="[주소 입력]"
                        locked={locked('address')}
                        mode={mode}
                        onEdit={edit(section.id, 'address', '주소', str(c['address']))}
                      />
                    </dd>
                  </>
                )}
              </dl>
              <p className="ed-fact-note">공유방의 사실 변경(전화·주소·가격·영업시간)은 방장 확인이 필요해요. (목업 문구)</p>
            </SectionShell>
          );
        }
        if (section.type === 'cta') {
          const phone = str(c['phone']);
          const channel = str(c['channel_url']);
          const slot = placeholderFor(placeholders, section.id, 'phone');
          return (
            <SectionShell key={section.id} section={section}>
              <h2>예약·문의</h2>
              {mode === 'edit' ? (
                <p>
                  <Field
                    label="카카오톡 채널 주소"
                    text={channel}
                    placeholder="[채널 주소 입력]"
                    locked={locked('channel_url')}
                    mode={mode}
                    onEdit={edit(section.id, 'channel_url', '카카오톡 채널 주소', channel)}
                  />
                </p>
              ) : channel.trim() !== '' ? (
                <p>
                  <a href={channel} target="_blank" rel="noopener noreferrer" aria-label="카카오톡 채널로 문의하기">
                    카카오톡으로 문의하기
                  </a>
                </p>
              ) : null}
              <div id={slot ? slotId(section.id, 'phone') : undefined}>
                {mode === 'edit' || phone.trim() === '' ? (
                  <Field
                    label="예약 전화번호"
                    text={phone}
                    placeholder="[전화번호 입력]"
                    locked={locked('phone')}
                    mode={mode}
                    onEdit={edit(section.id, 'phone', '예약 전화번호', phone)}
                  />
                ) : (
                  <p>
                    <a href={`tel:${phone.replace(/[^0-9+]/g, '')}`} aria-label="가게에 전화하기">전화하기</a>{' '}
                    <a href={`sms:${phone.replace(/[^0-9+]/g, '')}`} aria-label="가게에 문자로 문의하기">문자로 문의</a>
                  </p>
                )}
              </div>
            </SectionShell>
          );
        }
        // reviews
        const items = (Array.isArray(c['items']) ? c['items'] : []) as Array<Record<string, unknown>>;
        return (
          <SectionShell key={section.id} section={section}>
            <h2>후기</h2>
            {items.length === 0 ? (
              <p>후기가 모이면 여기에 표시됩니다. (예시 — 가짜 후기를 넣지 않습니다)</p>
            ) : (
              <ul>
                {items.map((item, i) => (
                  <li key={i}>
                    {str(item['quote'])} — {str(item['author'])}
                  </li>
                ))}
              </ul>
            )}
          </SectionShell>
        );
      })}
    </>
  );
}
