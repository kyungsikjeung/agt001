// WP P-10a 사장님용 직접 편집 프로토타입 — 디자인 명세 타입.
// 근거: docs/product/SECTION_LIBRARY_SPEC.md §0(명세 골격)·§1(tokens)·§2(섹션 8종)·§5(patch 연산·locked).

export type PaletteId =
  | 'forest'
  | 'coffee'
  | 'brick'
  | 'charcoal-gold'
  | 'moss'
  | 'navy';

export type FontPairId =
  | 'serif-warm'
  | 'sans-clean'
  | 'serif-elegant'
  | 'round-soft'
  | 'gothic-strong'
  | 'pop-point';

export type DensityId = 'compact' | 'comfortable' | 'roomy';
export type RadiusId = 'sharp' | 'soft' | 'round';
export type ImageStyleId = 'full-bleed' | 'card' | 'circle-mini';

export interface DesignTokens {
  palette: PaletteId;
  font_pair: FontPairId;
  density: DensityId;
  radius: RadiusId;
  image_style: ImageStyleId;
}

export type SectionType =
  | 'hero'
  | 'intro'
  | 'offerings'
  | 'gallery'
  | 'around'
  | 'contact'
  | 'reviews'
  | 'cta';

export type SectionVariant =
  | 'photo-overlay'
  | 'photo-side'
  | 'text-only'
  | 'short'
  | 'owner'
  | 'stats'
  | 'photo-grid'
  | 'list-price'
  | 'tabs'
  | 'grid'
  | 'swipe'
  | 'map-list'
  | 'transit'
  | 'call-first'
  | 'booking-first'
  | 'chat-first'
  | 'slot-only'
  | 'list'
  | 'call-sms'
  | 'external';

/** 섹션 type별 허용 variant (SPEC §2). */
export const VARIANTS_BY_TYPE: Record<SectionType, SectionVariant[]> = {
  hero: ['photo-overlay', 'photo-side', 'text-only'],
  intro: ['short', 'owner', 'stats'],
  offerings: ['photo-grid', 'list-price', 'tabs'],
  gallery: ['grid', 'swipe'],
  around: ['map-list', 'transit'],
  contact: ['call-first', 'booking-first', 'chat-first'],
  reviews: ['slot-only', 'list'],
  cta: ['call-sms', 'external'],
};

export interface HeroContent {
  title?: string;
  subtitle?: string;
  image?: string;
  cta?: { label?: string; href?: string };
}

export interface IntroContent {
  body?: string;
  owner_name?: string;
  stats?: Array<{ value?: string; label?: string }>;
}

export interface OfferingsItem {
  name?: string;
  desc?: string;
  price?: string;
  image?: string;
}

export interface OfferingsContent {
  label?: string;
  items?: OfferingsItem[];
}

export interface GalleryContent {
  items?: Array<{ src?: string; alt?: string }>;
}

export interface AroundContent {
  address?: string;
  map_url?: string;
  items?: Array<{ name?: string; note?: string }>;
}

export interface ContactContent {
  phone?: string;
  hours?: string;
  address?: string;
  channel_url?: string;
  booking_url?: string;
}

export interface ReviewsContent {
  items?: Array<{ quote?: string; author?: string; source?: string }>;
}

export interface CtaContent {
  phone?: string;
  booking_url?: string;
  channel_url?: string;
}

export type SectionContent =
  | HeroContent
  | IntroContent
  | OfferingsContent
  | GalleryContent
  | AroundContent
  | ContactContent
  | ReviewsContent
  | CtaContent;

export interface DesignSection {
  id: string;
  type: SectionType;
  variant: SectionVariant;
  content: Record<string, unknown>;
}

export interface DesignSpec {
  version: number;
  based_on_prd_version: number;
  shopName: string;
  tokens: DesignTokens;
  sections: DesignSection[];
  /** "<section-id>.<content-key>" 형태 (SPEC §5.2). */
  locked: string[];
}

/** 자리 표시(공개 전 필수, D23) 1칸. */
export interface PlaceholderSlot {
  sectionId: string;
  key: string;
  /** item 내부 필드일 때(예: offerings 가격) */
  itemIndex?: number;
  label: string;
  /** 화면에 보여줄 자리 표시 문구 */
  placeholder: string;
}

/** 편집기에서 허용하는 유일한 연산 (D27: 내용만 직접). */
export interface SetContentOp {
  op: 'set_content';
  section: string;
  key: string;
  value: unknown;
}
