// 실제 요구사항 카드 API 호출 (contracts/ROOM_FEATURES_API.md §5).
// D23 자리 표시는 status가, D27 직접 편집은 PUT fields가, D24 사실 확인은 fact와 pending_owner이 담당한다.
export type CardFieldStatus = 'filled' | 'assumed' | 'placeholder' | 'pending_owner';

export interface CardField {
  key: string;
  label: string;
  value: string;
  status: CardFieldStatus;
  fact: boolean;
  placeholder: boolean;
}

export interface CardPhoto {
  id: string;
  url: string;
  caption?: string | null;
}

/** 공지 띠·팝업 (D56) + 사진 (NOTICE_PHOTO_CONTRACT). 글·사진이 둘 다 비면 공지 없음. */
export interface CardNotice {
  text: string;
  popup: boolean;
  photos?: string[];
}

export interface RoomCard {
  title: string;
  industry: string | null;
  fields: CardField[];
  photos: CardPhoto[];
  choice: string | null;
  notice?: CardNotice;
  published: string | null;
  site_url: string | null;
  can_edit: boolean;
  layout?: Record<string, { order?: string[]; hidden?: string[]; added?: string[] }>;
  /** 무료 디자인 남은 횟수 (USAGE_QUOTA_CONTRACT §2-6). 예전 서버는 없다 */
  quota?: CardQuota | null;
  /** 초대·기념(청첩장)만: 양가 연락처·계좌 (넣은 값 또는 시안 기본 묶음) */
  event?: CardEvent;
  /** 선생님·담당자 (BUILDER_FIX_1003_CONTRACT S2, 서버 S1). 없으면 대화에서 받은 값·예시 */
  staff?: StaffMember[];
  /** 주변 안내 (10/4). 오시는 길 위쪽 "OO역 · 도보 3분" 줄 */
  around?: AroundEdit;
}

/** 주변 안내 한 줄: 장소 + 어떻게(도보·차로 = 분, 거리 = km/m, 직접 = 글 그대로) */
export interface AroundItem {
  name: string;
  how: 'walk' | 'car' | 'distance' | 'text';
  value: string;
}

/** title = 크게 보일 것: place(장소 이름) / distance(거리·시간) */
export interface AroundEdit {
  title: 'place' | 'distance';
  items: AroundItem[];
}

/** 선생님·담당자 1명 (BUILDER_FIX_1003_CONTRACT S2). specialties는 최대 4개 */
export interface StaffMember {
  name: string;
  role: string;
  subject: string;
  tagline: string;
  bio: string;
  specialties: string[];
  /** 서버가 주는 지금 사진 주소(staff:이름 태그 중 최근 장). 없으면 "" */
  photo?: string;
  /** 저장할 때만: 고치기 전 이름. 이름이 바뀌면 서버가 사진을 새 이름으로 옮긴다 */
  prev_name?: string;
}

export interface EventPerson {
  role: string;
  name: string;
  phone?: string;
}

export interface EventAccount {
  role: string;
  holder: string;
  bank: string;
  number: string;
}

export interface CardEvent {
  family: { side: string; people: EventPerson[] }[];
  gift: { side: string; accounts: EventAccount[] }[];
  /** 사장님이 넣은 값인가 (아니면 시안 기본·예시) */
  saved: { family: boolean; gift: boolean };
}

export interface CardQuota {
  design: { left: number; total: number };
  restyle: { left: number; total: number };
  /** 다시 채워지는 날, 예: "11월 1일" */
  resets: string;
}

/** 미리보기 구역 1개 (EDIT_WAVE2_CONTRACT §2.1). 숨긴 것까지 순서대로 온다. */
export interface PreviewSection {
  id: string;
  label: string;
  bind: string;
  locked: boolean;
  hidden: boolean;
  /** 지금 모양·기본 모양 (COMPONENT_ENGINE_PLAN §6). 예전 서버는 없다 */
  variant?: string;
  base_variant?: string;
  /** 같은 데이터로 바꿔 쓸 수 있는 모양들. 한 개 이하면 모양 바꾸기를 보이지 않는다 */
  shapes?: PreviewShape[];
}

/** 구역 모양 하나 (templates/components.json). */
export interface PreviewShape {
  variant: string;
  name: string;
  desc: string;
  new: boolean;
}

/** 편집 미리보기의 토큰 CSS·<body> 스타일 축 속성 (agt-theme로 바꿔 끼운다). */
export interface PreviewTheme {
  css: string;
  motion: string;
  attrs: Record<string, string>;
  /** 관리하는 속성 이름 전부(없는 것은 지운다) */
  axes: string[];
}

/** 구역 조각: id(구역 id)·hash. html은 저장 전 미리 그리기에서 바뀐 것만 온다. */
export interface PreviewPart {
  id: string;
  hash: string;
  html?: string;
}

/** 스타일 축 하나: 기본값과 {값: 이름}. */
export interface StyleAxis {
  default: string;
  values: Record<string, string>;
}

/** 이 안에 더할 수 있는 구역 (EDIT_WAVE2_CONTRACT §2.1). */
export interface PreviewAddable {
  id: string;
  label: string;
  bind: string;
}

/** GET preview 응답 (EDIT_WAVE2_CONTRACT §2.1). */
export interface CardPreview {
  variant: string;
  html: string;
  sections: PreviewSection[];
  addable: PreviewAddable[];
  /** 이 안의 지금 구역 편집 (없으면 빈 객체). 다음 저장이 더한 구역을 잃지 않게 여기서 시작한다. */
  layout: { order?: string[]; hidden?: string[]; added?: string[] };
  /** 항목의 지금 가격·설명·그룹·사진 */
  items: PreviewItem[];
  /** 지금 보이는 그룹 순서 (GROUP_CARDS_CONTRACT §2-6, 빈 그룹 포함). 예전 서버는 없다 */
  groups?: string[];
  /** 실시간 미리보기 (COMPONENT_ENGINE_PLAN §5). 예전 서버는 없다 → 늘 새로 불러온다 */
  shell?: string;
  order?: string[];
  theme?: PreviewTheme;
  parts?: PreviewPart[];
  /** 이 안에서 고른 스타일 축 {surface: 'outline'}(기본값은 빠짐)과 고를 수 있는 축 */
  style?: Record<string, string>;
  styles?: Record<string, StyleAxis>;
}

export interface PreviewItem {
  name: string;
  price: string;
  note: string;
  /** 지금 보이는 그룹 (그룹 카드 §2-6) */
  group?: string;
  /** own = 내 사진 있음, auto = 예시 사진, none = 사진 없음 */
  photo?: 'own' | 'auto' | 'none';
}

/** 항목 고치기 1줄 (EDIT_WAVE2_CONTRACT §2.2). */
export interface CardItemEdit {
  name: string;
  rename?: string;
  price?: string;
  note?: string;
  remove?: boolean;
  add?: boolean;
  /** 그룹 이름 (그룹 카드 §2-1) */
  group?: string;
  /** none = 사진 없음, auto = 기본(내 사진 → 예시 사진) */
  photo?: 'auto' | 'none';
}

/** 그룹 목록 통째로 (그룹 카드 §2-2). rename = 옛 이름 → 새 이름 */
export interface CardGroupsEdit {
  order: string[];
  rename?: Record<string, string>;
}

/** 구역 순서·숨기기·추가 (EDIT_WAVE2_CONTRACT §2.2). */
export interface CardLayoutEdit {
  variant: string;
  order?: string[];
  hidden?: string[];
  added?: string[];
  reset?: boolean;
  /** 구역별 모양 {구역 id: 변형}. 빼면 지금 값 그대로, {}면 모두 기본 모양으로 */
  variants?: Record<string, string>;
}

/** 스타일 축 고르기 (안별). 기본값이거나 빼면 그 축은 기본 모양. */
export interface CardStyleEdit {
  variant: string;
  surface?: string;
  heading?: string;
}

/** PUT /card에 fields·notice 말고 더 보낼 것. choice는 고른 안 바꾸기(빌더 "모양 바꾸기"). */
export interface CardSaveExtra {
  style?: CardStyleEdit;
  event?: Partial<Pick<CardEvent, 'family' | 'gift'>>;
  items?: CardItemEdit[];
  groups?: CardGroupsEdit;
  layout?: CardLayoutEdit;
  choice?: string;
  staff?: StaffMember[];
  around?: AroundEdit;
}

export const MEMBER_KEY = 'agt001_member_id';

/** 이 기기의 방 참여자 확인 값. 못 읽으면 null. */
export function readMemberId(): string | null {
  try {
    return localStorage.getItem(MEMBER_KEY);
  } catch {
    return null;
  }
}

/** 주소창 ?room=<id>을 읽는다. 없거나 비면 null. */
export function readRoomId(search?: string): string | null {
  try {
    const raw = search ?? (typeof location !== 'undefined' ? location.search : '');
    const value = new URLSearchParams(raw).get('room');
    if (!value || value.trim() === '') return null;
    return value;
  } catch {
    return null;
  }
}

/** 상태 배지 문구. filled는 배지를 붙이지 않는다. */
export function statusLabel(status: CardFieldStatus): string | null {
  if (status === 'placeholder') return '입력 필요';
  if (status === 'assumed') return '가정';
  if (status === 'pending_owner') return '확인 대기';
  return null;
}

function memberHeaders(memberId: string | null): Record<string, string> {
  const headers: Record<string, string> = {};
  if (memberId) headers['X-Member-Id'] = memberId;
  return headers;
}

/** 실제 카드를 불러온다. 실패하면 예외를 던져 목업 화면으로 돌린다. */
export async function fetchCard(roomId: string, memberId: string | null): Promise<RoomCard> {
  const res = await fetch(`/api/rooms/${encodeURIComponent(roomId)}/card`, {
    credentials: 'same-origin',
    headers: memberHeaders(memberId),
  });
  if (!res.ok) throw new Error(`카드를 불러오지 못했습니다 (${res.status})`);
  const data = (await res.json()) as RoomCard;
  if (!data || !Array.isArray(data.fields)) throw new Error('카드 모양이 맞지 않아요.');
  return data;
}

/** 바뀐 칸만 저장한다. 빈 문자열은 자리 표시로 되돌린다(서버 계약 §5). */
export async function saveCard(
  roomId: string,
  memberId: string | null,
  fields: Record<string, string>,
  notice?: CardNotice,
  extra?: CardSaveExtra,
): Promise<RoomCard> {
  const body: Record<string, unknown> = { fields };
  if (notice) body.notice = notice;
  if (extra?.items) body.items = extra.items;
  if (extra?.groups) body.groups = extra.groups;
  if (extra?.layout) body.layout = extra.layout;
  if (extra?.choice) body.choice = extra.choice;
  if (extra?.event) body.event = extra.event;
  if (extra?.staff) body.staff = extra.staff;
  if (extra?.around) body.around = extra.around;
  if (extra?.style) body.style = extra.style;
  const res = await fetch(`/api/rooms/${encodeURIComponent(roomId)}/card`, {
    method: 'PUT',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...memberHeaders(memberId) },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    // 400이면 서버가 틀린 곳을 한 줄로 알려 준다(예: "김민준 전화번호: 전화번호 자리수가 맞지 않아요")
    const detail = res.status === 400 ? await res.json().then((d) => d?.detail).catch(() => '') : '';
    throw new Error(typeof detail === 'string' && detail ? detail : `저장하지 못했습니다 (${res.status})`);
  }
  const data = (await res.json()) as RoomCard;
  if (!data || !Array.isArray(data.fields)) throw new Error('카드 모양이 맞지 않아요.');
  return data;
}

/** 미리보기를 불러온다 (EDIT_WAVE2_CONTRACT §2.1). 실패하면 status를 단 예외를 던진다. */
export async function getPreview(
  roomId: string,
  memberId: string | null,
  variant: string,
): Promise<CardPreview> {
  const res = await fetch(
    `/api/rooms/${encodeURIComponent(roomId)}/card/preview?variant=${encodeURIComponent(variant)}`,
    { credentials: 'same-origin', headers: memberHeaders(memberId) },
  );
  if (!res.ok) {
    const err = new Error(`미리보기를 불러오지 못했습니다 (${res.status})`) as Error & { status: number };
    err.status = res.status;
    throw err;
  }
  const data = (await res.json()) as CardPreview;
  if (!data || typeof data.html !== 'string' || !Array.isArray(data.sections)) {
    throw new Error('미리보기 모양이 맞지 않아요.');
  }
  return data;
}

/** 저장 전 미리 그리기 요청 (COMPONENT_ENGINE_PLAN §5). have = 미리보기에 이미 있는 구역 해시. */
export interface DraftRequest {
  variant: string;
  fields?: Record<string, string>;
  layout?: CardLayoutEdit;
  style?: CardStyleEdit;
  have: Record<string, string>;
  shell?: string;
}

export interface DraftResponse {
  variant: string;
  shell: string;
  order: string[];
  theme: PreviewTheme;
  parts: PreviewPart[];
  /** 뼈대가 달라졌을 때만: 새로 불러올 완전한 문서 */
  html?: string;
}

/** 고치는 중인 값으로 그린 미리보기의 바뀐 구역만 받는다. 카드에는 쓰지 않는다. */
export async function draftPreview(roomId: string, memberId: string | null, req: DraftRequest): Promise<DraftResponse> {
  const res = await fetch(`/api/rooms/${encodeURIComponent(roomId)}/card/preview/draft`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...memberHeaders(memberId) },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error(`미리보기를 그리지 못했어요 (${res.status})`);
  const data = (await res.json()) as DraftResponse;
  if (!data || !Array.isArray(data.parts) || typeof data.shell !== 'string') throw new Error('미리보기 모양이 맞지 않아요.');
  return data;
}

/** 빌더 시작 응답 (BUILDER_CONTRACT §2.1). member_id는 방장 신분이다. */
export interface BuilderStart {
  room_id: string;
  member_id: string;
  builder_url: string;
}

/** 템플릿으로 빌더 방을 연다. 실패하면 예외를 던진다. */
export async function startBuilder(template: string): Promise<BuilderStart> {
  const res = await fetch('/api/start', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ template }),
  });
  if (!res.ok) throw new Error(`시작하지 못했습니다 (${res.status})`);
  const data = (await res.json()) as BuilderStart;
  if (!data || typeof data.room_id !== 'string' || typeof data.member_id !== 'string' || typeof data.builder_url !== 'string') {
    throw new Error('시작 모양이 맞지 않아요.');
  }
  return data;
}

/** 기능 칩 1개 (BUILDER_CONTRACT §2.2). hero·inquiry는 목록에 없다(항상 켜짐). */
export interface FeatureChip {
  key: string;
  label: string;
  kind: 'section' | 'shop';
  on: boolean;
  locked?: boolean;
  needs_text?: boolean;
  after_publish?: boolean;
}

/** GET features 응답 (BUILDER_CONTRACT §2.2). */
export interface FeatureList {
  variant: string;
  features: FeatureChip[];
}

/** 기능 칩 목록을 불러온다. 실패하면 예외를 던진다. */
export async function getFeatures(roomId: string, memberId: string | null): Promise<FeatureList> {
  const res = await fetch(`/api/rooms/${encodeURIComponent(roomId)}/features`, {
    credentials: 'same-origin',
    headers: memberHeaders(memberId),
  });
  if (!res.ok) throw new Error(`기능을 불러오지 못했습니다 (${res.status})`);
  const data = (await res.json()) as FeatureList;
  if (!data || !Array.isArray(data.features)) throw new Error('기능 모양이 맞지 않아요.');
  return data;
}

/** PUT features 응답 (BUILDER_CONTRACT §2.3). focus는 새로 보인 구역 id(끄면 null). */
export interface FeatureUpdate {
  features: FeatureChip[];
  focus: string | null;
}

/** 기능 칩을 켜고 끈다. 공지는 text(1~200자)와 함께 켠다. */
export async function putFeature(
  roomId: string,
  memberId: string | null,
  key: string,
  on: boolean,
  text?: string,
  photos?: string[],
): Promise<FeatureUpdate> {
  const body: Record<string, unknown> = { key, on };
  if (text !== undefined) body.text = text;
  if (photos && photos.length) body.photos = photos;
  const res = await fetch(`/api/rooms/${encodeURIComponent(roomId)}/features`, {
    method: 'PUT',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...memberHeaders(memberId) },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = new Error(`바꾸지 못했습니다 (${res.status})`) as Error & { status: number };
    err.status = res.status;
    throw err;
  }
  const data = (await res.json()) as FeatureUpdate;
  if (!data || !Array.isArray(data.features)) throw new Error('기능 모양이 맞지 않아요.');
  return data;
}

/** 공개 결과 (BUILDER_CONTRACT §2.5). ok면 site_url, 아니면 need별 안내. */
export interface PublishResult {
  ok?: boolean;
  site_url?: string;
  need?: 'login' | 'confirm' | 'blocked';
  message?: string;
  login_urls?: string[];
}

/** 빌더에서 공개한다. force는 빈칸 확인 뒤 "그대로 공개"가 쓴다. */
export async function publishRoom(
  roomId: string,
  memberId: string | null,
  force: boolean,
): Promise<PublishResult> {
  const res = await fetch(`/api/rooms/${encodeURIComponent(roomId)}/publish`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...memberHeaders(memberId) },
    body: JSON.stringify({ force }),
  });
  if (!res.ok) throw new Error(`공개하지 못했습니다 (${res.status})`);
  const data = (await res.json()) as PublishResult;
  if (!data || (data.ok !== true && typeof data.need !== 'string')) throw new Error('공개 모양이 맞지 않아요.');
  return data;
}

/** 말로 고치기 답 (SAY_CONTRACT §6). focus는 바뀐 구역 id(없으면 null). */
export interface SayResponse {
  reply: string;
  focus: string | null;
  features: FeatureChip[];
  undo: boolean;
  rejected: string[];
  source: 'rule' | 'llm' | 'none';
}

/** 빌더에서 말로 고친다. text는 1~300자. 실패하면 예외를 던진다. */
export async function say(roomId: string, memberId: string | null, text: string): Promise<SayResponse> {
  const res = await fetch(`/api/rooms/${encodeURIComponent(roomId)}/say`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...memberHeaders(memberId) },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error(`말을 전하지 못했습니다 (${res.status})`);
  const data = (await res.json()) as SayResponse;
  if (!data || typeof data.reply !== 'string' || !Array.isArray(data.features)) {
    throw new Error('말하기 모양이 맞지 않아요.');
  }
  return data;
}

/** 되돌리기 답 (SAY_CONTRACT §6). */
export interface UndoResponse {
  reply: string;
  features: FeatureChip[];
  undo: false;
}

/** 말로 고친 것을 한 단계 되돌린다. 실패하면 예외를 던진다. */
export async function undoSay(roomId: string, memberId: string | null): Promise<UndoResponse> {
  const res = await fetch(`/api/rooms/${encodeURIComponent(roomId)}/undo`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { ...memberHeaders(memberId) },
  });
  if (!res.ok) throw new Error(`되돌리지 못했습니다 (${res.status})`);
  const data = (await res.json()) as UndoResponse;
  if (!data || typeof data.reply !== 'string' || !Array.isArray(data.features)) {
    throw new Error('되돌리기 모양이 맞지 않아요.');
  }
  return data;
}

/** 사진을 올린다. 채팅방과 같은 호출(POST /room/{id}/photos, FormData file+tag). */
export async function uploadPhoto(
  roomId: string,
  memberId: string | null,
  file: File,
  tag?: string,
): Promise<{ id: string; url: string }> {
  const form = new FormData();
  form.append('file', file);
  if (tag) form.append('tag', tag);
  const res = await fetch(`/room/${encodeURIComponent(roomId)}/photos`, {
    method: 'POST',
    headers: memberHeaders(memberId),
    body: form,
  });
  if (!res.ok) throw new Error(`사진을 올리지 못했습니다 (${res.status})`);
  const data = (await res.json().catch(() => ({}))) as { id?: unknown; url?: unknown };
  return { id: String(data.id ?? ''), url: String(data.url ?? '') };
}

/** 주소 후보 1개 (MAP_CONTRACT §1). x는 경도, y는 위도. */
export interface GeoCandidate {
  road: string;
  jibun: string;
  x: number;
  y: number;
}

/** 고른 도로명으로 좌표 후보를 찾는다. 주소 말만 보낸다(이름·전화 금지). */
export async function geoSearch(
  roomId: string,
  memberId: string | null,
  query: string,
): Promise<GeoCandidate[]> {
  const res = await fetch(
    `/api/rooms/${encodeURIComponent(roomId)}/geo/search?q=${encodeURIComponent(query)}`,
    { credentials: 'same-origin', headers: memberHeaders(memberId) },
  );
  if (!res.ok) throw new Error(`주소를 찾지 못했습니다 (${res.status})`);
  const data = (await res.json()) as { candidates?: unknown };
  if (!data || !Array.isArray(data.candidates)) throw new Error('주소 모양이 맞지 않아요.');
  return data.candidates as GeoCandidate[];
}

/** 주소 저장 본문 (MAP_CONTRACT §1). */
export interface GeoSaveBody {
  road: string;
  jibun?: string;
  detail?: string;
  x?: number;
  y?: number;
  src: string;
}

/** 고른 주소를 저장한다. 답은 PUT /card와 같은 카드다. */
export async function saveGeo(
  roomId: string,
  memberId: string | null,
  body: GeoSaveBody,
): Promise<RoomCard> {
  const res = await fetch(`/api/rooms/${encodeURIComponent(roomId)}/geo`, {
    method: 'PUT',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...memberHeaders(memberId) },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`저장하지 못했습니다 (${res.status})`);
  const data = (await res.json()) as RoomCard;
  if (!data || !Array.isArray(data.fields)) throw new Error('카드 모양이 맞지 않아요.');
  return data;
}

/** 고칠 곳 목록 1개 (FIX_TAGS_CONTRACT §2). 모양 검사는 여기서만 한다. */
export async function getFixTargets(
  roomId: string,
  memberId: string | null,
): Promise<import('../builder/fixTags').FixTarget[]> {
  const res = await fetch(`/api/rooms/${encodeURIComponent(roomId)}/fix-targets`, {
    credentials: 'same-origin',
    headers: memberHeaders(memberId),
  });
  if (!res.ok) throw new Error(`고칠 곳을 불러오지 못했습니다 (${res.status})`);
  const data = (await res.json()) as { targets?: unknown };
  if (!data || !Array.isArray(data.targets)) throw new Error('고칠 곳 모양이 맞지 않아요.');
  for (const t of data.targets) {
    const v = t as { key?: unknown; label?: unknown; current?: unknown; parts?: unknown };
    if (typeof v.key !== 'string' || typeof v.label !== 'string') throw new Error('고칠 곳 모양이 맞지 않아요.');
    if (typeof v.current !== 'string' || !Array.isArray(v.parts)) throw new Error('고칠 곳 모양이 맞지 않아요.');
  }
  return data.targets as import('../builder/fixTags').FixTarget[];
}

/** 청첩장 방명록 (방장만, 최신순). */
export interface GuestbookEntry {
  id: number;
  name: string;
  message: string;
  ts: string;
}

export async function listGuestbook(roomId: string, memberId: string | null): Promise<GuestbookEntry[]> {
  const res = await fetch(`/api/rooms/${encodeURIComponent(roomId)}/guestbook`, {
    credentials: 'same-origin',
    headers: memberHeaders(memberId),
  });
  if (!res.ok) throw new Error(`방명록을 불러오지 못했어요 (${res.status})`);
  const data = (await res.json()) as { entries?: GuestbookEntry[] };
  return Array.isArray(data.entries) ? data.entries : [];
}

export async function deleteGuestbook(roomId: string, memberId: string | null, id: number): Promise<void> {
  const res = await fetch(`/api/rooms/${encodeURIComponent(roomId)}/guestbook/${id}`, {
    method: 'DELETE',
    credentials: 'same-origin',
    headers: memberHeaders(memberId),
  });
  if (!res.ok && res.status !== 404) throw new Error(`지우지 못했어요 (${res.status})`);
}

/** 청첩장 참석 여부 집계 (방장만). */
export interface RsvpEntry {
  id: number;
  name: string;
  side: string;
  attend: boolean;
  count: number;
  meal: boolean;
  note: string;
  contact: string;
  ts: string;
}

export interface RsvpSummary {
  entries: RsvpEntry[];
  total: { replies?: number; people?: number; declined?: number; meal?: number };
  sides: Record<string, number>;
}

export async function getRsvp(roomId: string, memberId: string | null): Promise<RsvpSummary> {
  const res = await fetch(`/api/rooms/${encodeURIComponent(roomId)}/rsvp`, {
    credentials: 'same-origin',
    headers: memberHeaders(memberId),
  });
  if (!res.ok) throw new Error(`참석 여부를 불러오지 못했어요 (${res.status})`);
  return (await res.json()) as RsvpSummary;
}
