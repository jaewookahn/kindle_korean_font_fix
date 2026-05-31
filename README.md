# Kindle Korean Tools — Calibre 플러그인 모음

킨들에서 한국 도서를 더 잘 다루기 위한 두 개의 Calibre 플러그인.

| 플러그인 | 용도 |
|----------|------|
| **Korean Font Fallback Fixer** | EPUB → KFX 변환 시 CSS에 한국어 폰트 폴백 주입 |
| **Fetch Page Count** | 알라딘 / Google Books에서 페이지수를 가져와 커스텀 컬럼에 저장 |

---

## 1. Korean Font Fallback Fixer

킨들에서 EPUB을 읽을 때 한글이 기본 폰트(bitmap 계열)로 표시되는 문제를 해결.

### 문제

EPUB CSS가 라틴 전용 폰트를 지정하면, 킨들은 한글 렌더링 시 내장 기본 한국어 폰트로 폴백한다. Aa 메뉴에서 사용자 폰트를 선택해도 이 폴백 체인은 변경되지 않는다.

탈옥 없이 시스템 폰트를 교체하는 방법은 없으며, 이 플러그인은 EPUB → KFX 변환 시 CSS를 수정해 킨들의 `fonts/` 폴더에 업로드한 폰트를 한글 폴백으로 지정한다.

### 동작 방식

Calibre가 EPUB을 KFX로 변환하기 직전, 플러그인이 EPUB 내 모든 CSS 파일에 주입:

```css
/* 주입 예시 */
@font-face {
    font-family: "KoreanFallback";
    src: local("NanumGothic");       /* 킨들 fonts/ 폴더의 폰트 */
    unicode-range: U+AC00-U+D7A3, ...; /* 한글 코드포인트만 */
}

/* 기존 선언에 KoreanFallback 추가 */
body { font-family: "SomeLatinFont", "KoreanFallback", serif; }
```

- 라틴 문자 → 기존 폰트 그대로
- 한글 → 기존 폰트에 한글 글리프 없음 → KoreanFallback → 킨들이 `fonts/` 폴더에서 로드

EPUB3 nav의 `<nav epub:type="page-list">`와 NCX의 `<pageList>`도 함께 제거 — KFX 페이지 추정이 EPUB 페이지 데이터에 의해 무시되는 문제 해결.

### 설치

1. 킨들 USB 연결 → `fonts/` 폴더에 TTF/OTF 복사  
   추천: [Noto Sans KR](https://fonts.google.com/noto/specimen/Noto+Sans+KR), [나눔고딕](https://hangeul.naver.com/font)
2. Calibre → **Preferences > Plugins > Load plugin from file** → `korean_font_fixer.zip`
3. **Korean Font Fallback Fixer** 더블클릭 → **Customize plugin** → 폰트 family name 입력

   | 폰트 파일 | Family name |
   |-----------|-------------|
   | NanumGothic.ttf | `NanumGothic` |
   | NotoSansKR-Regular.otf | `Noto Sans KR` |
   | KoPubDotum.ttf | `KoPub Dotum` |

   > macOS에서 family name 확인: 폰트 파일 Space → 미리보기 상단 이름

4. 평소처럼 EPUB → KFX 변환 → 킨들에서 **Aa → Publisher Font: ON**

---

## 2. Fetch Page Count

선택한 도서의 페이지수를 알라딘과 Google Books에서 자동으로 가져와 사용자 정의 컬럼에 저장.

### 동작 방식

- **한글 도서**: 알라딘 우선 (ISBN API → 제목 API → 스크래핑) → Google Books 폴백
- **영문/기타**: Google Books 우선 → 알라딘 폴백
- **eBook ISBN**: 알라딘이 종이책으로 자동 리다이렉트 (`paperBookList`에서 종이책 ISBN/ItemId 추출 후 재조회) — eBook은 `itemPage`가 없음
- **Google 429 (쿼터 초과)**: 한 번 감지하면 그 세션에서는 더 호출하지 않음
- 현재 정렬 상태 무시하고 그리드에서 실제 선택된 책의 ID를 정확히 인식

### 설치

1. Calibre → **Preferences > Plugins > Load plugin from file** → `fetch_page_count.zip`
2. 사용자 정의 컬럼 추가 (예: `pages`, 텍스트 또는 정수 타입)
3. 툴바의 **페이지수 가져오기** 버튼 옆 드롭다운 → **설정...** → 알라딘 TTB 키 / 컬럼 이름 입력
4. TTB 키 발급: https://blog.aladin.co.kr/openapi (한글책 정확도 크게 향상)

### 사용

라이브러리에서 책 선택 → 툴바 **페이지수 가져오기** 클릭 → 결과 다이얼로그가 업데이트 / 미발견 권수 표시.

미발견된 책은 사유와 함께 표시 (`Google 쿼터 초과`, `알라딘/Google 모두 결과 없음` 등).

---

## 빌드

```bash
zip -j korean_font_fixer.zip korean_font_fixer/__init__.py
zip -j fetch_page_count.zip fetch_page_count/__init__.py fetch_page_count/plugin-import-name-fetch_page_count.txt
```

`plugin-import-name-*.txt` 빈 파일은 Calibre가 `calibre_plugins.<name>` 모듈 네임을 등록하는 데 필요. flat zip 구조 필수.

## 제한사항

- 킨들 KFX 렌더러의 `local()` CSS 함수 지원이 공식 확인되지 않음
- KFX 포맷은 Calibre를 통한 폰트 임베딩이 불안정 (AZW3가 더 안정적)
- 탈옥 후 시스템 폰트(`/opt/amazon/ebook/fonts/`)를 교체하는 방법이 가장 근본적인 해결책
- Google Books 무인증 호출은 IP 단위 일일 쿼터가 작음 — API 키 발급 권장

## 라이선스

MIT
