# kindle_korean_font_fix

킨들에서 한국 도서를 다루기 위한 Calibre 플러그인 두 개.

## 1. Korean Font Fallback Fixer

EPUB CSS가 라틴 전용 폰트를 지정하면 킨들이 한글을 내장 bitmap 폰트로 폴백하는 문제 해결.

### 구조

- `FileTypePlugin` + `on_preprocess=True` → EPUB → KFX 변환 직전 가로채기
- 모든 CSS 파일에 `@font-face { font-family: "KoreanFallback"; src: local("<폰트명>"); unicode-range: <한글> }` 주입
- 기존 `font-family` 선언 전체에 `"KoreanFallback"` 추가 (generic family 직전)
- font-family가 아예 없으면 `body, p, div, h1-h6, li, blockquote, td, th, span`에 폴백 규칙 추가
- 보너스: EPUB3 `<nav epub:type="page-list">`와 NCX `<pageList>` 제거 (KFX 페이지 추정이 EPUB 데이터에 의해 무시되는 문제 해결)
- 폰트 이름은 `site_customization`에서 입력받음

킨들 사용 조건: **Aa → Publisher Font ON**

## 2. Fetch Page Count

선택 도서의 페이지수를 알라딘 / Google Books에서 가져와 커스텀 컬럼에 저장.

### 구조

- 단일 zip에 `InterfaceActionBase` + `InterfaceAction` 함께 (`actual_plugin='calibre_plugins.fetch_page_count:FetchPageCountAction'`)
- 설정은 `JSONConfig('plugins/fetch_page_count')` → TTB 키 + 컬럼명. 변경 후 재시작 불필요
- 툴바 액션의 첫 클릭 시 메뉴(`페이지수 가져오기` + `설정...`)를 build & attach
- 책 선택은 `library_view.selectionModel().selectedRows()` → `model.id(row.row())` (book_id 반환). **`currentIndex()` 폴백은 쓰지 않음** — 의도하지 않은 책을 가져옴

### Calibre API 함정

- **`db.get_metadata(idx)` 디폴트가 `index_is_id=False`** — 인자를 row index로 해석. book_id 가져왔다고 그대로 넘기면 다른 책 metadata가 반환됨. → `db.new_api.get_metadata(book_id)` 사용
- `db.set_custom(book_id, val, ...)`는 book_id 그대로 받음 (디폴트 OK)
- 커스텀 컬럼 메타데이터 키는 `#pages` (# 포함). `set_custom`의 `label` 인자는 `pages` (# 없이)
- 컬럼 타입(text/int 등)에 맞춰 값 변환 필요 — text 컬럼에 int 넘기면 `'int' object has no attribute 'decode'`
- `library_view.refresh_grid()` (Calibre 9.8) — `refresh_ids()`는 없음

### 페이지 조회 전략

한글 도서 → 알라딘 우선 / 영문 → Google 우선. `_has_hangul()`로 판정.

알라딘:
1. `ItemLookUp` by ISBN13 → eBook이면 `subInfo.paperBookList`의 종이책 ISBN/ItemId로 재조회 (eBook에는 `itemPage` 없음)
2. `ItemSearch` by Title (상위 3개 ItemId) → 각각 `ItemLookUp`으로 페이지수 (ItemSearch 자체는 `subInfo`가 비어있음)
3. 스크래핑 (현재 알라딘 페이지 구조 변경으로 거의 안 됨)

Google Books:
- `q=isbn:...` 또는 `q=intitle:"..." inauthor:"..."` 검색, `pageCount` 있는 첫 결과 반환
- **무인증 IP 쿼터가 작음** — 429 한 번 받으면 세션 내 더 호출 안 함

### 사용자 미발견 결과

책당 한 줄: `· 제목 — 사유` (사유 예: `Google 쿼터 초과`, `알라딘/Google 모두 결과 없음`, `ISBN/제목 없음`)

## 파일 구조

```
korean_font_fixer/__init__.py
korean_font_fixer.zip
fetch_page_count/__init__.py
fetch_page_count/plugin-import-name-fetch_page_count.txt    # 필수: 빈 파일
fetch_page_count.zip
```

`plugin-import-name-*.txt` 없으면 Calibre가 `calibre_plugins.fetch_page_count` 네임스페이스를 등록 안 함 → 액션이 툴바에 안 뜸.

## 빌드 & 설치

```bash
zip -j korean_font_fixer.zip korean_font_fixer/__init__.py
zip -j fetch_page_count.zip fetch_page_count/__init__.py fetch_page_count/plugin-import-name-fetch_page_count.txt

/Applications/calibre.app/Contents/MacOS/calibre-customize -a fetch_page_count.zip
```

zip을 `~/Library/Preferences/calibre/plugins/`에 직접 복사하는 건 안 됨 — Calibre가 별도로 등록해야 함. `calibre-customize -a`로 설치.

## 제한사항

- 킨들 KFX 렌더러의 `local()` CSS 함수 지원 여부 불확실 → 안 되면 폰트 직접 임베드 필요
- 알라딘 상품 페이지 HTML이 JS 로딩으로 변경됨 → `_al_scrape`, `_al_search`는 사실상 무력. TTB API 사용 필수
- Google Books 무인증 쿼터 한계 — API 키 발급(Books API 활성화) 시 일일 1000건 무료
