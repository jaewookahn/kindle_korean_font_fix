# Kindle Korean Font Fallback Fixer

킨들에서 EPUB을 읽을 때 한글이 기본 폰트(bitmap 계열)로 표시되는 문제를 해결하는 Calibre 플러그인.

## 문제

EPUB CSS가 라틴 전용 폰트를 지정하면, 킨들은 한글 렌더링 시 내장 기본 한국어 폰트로 폴백한다. Aa 메뉴에서 사용자 폰트를 선택해도 이 폴백 체인은 변경되지 않는다.

탈옥 없이 시스템 폰트를 교체하는 방법은 없으며, 이 플러그인은 EPUB → KFX 변환 시 CSS를 수정해 킨들의 `fonts/` 폴더에 업로드한 폰트를 한글 폴백으로 지정한다.

## 동작 방식

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

## 설치

### 1. 킨들에 한국어 폰트 업로드

킨들을 USB로 연결 → `fonts/` 폴더에 TTF/OTF 파일 복사.  
추천 폰트: [Noto Sans CJK KR](https://fonts.google.com/noto/specimen/Noto+Sans+KR), [나눔고딕](https://hangeul.naver.com/font)

### 2. Calibre 플러그인 설치

1. `korean_font_fixer.zip` 다운로드
2. Calibre → **Preferences > Plugins > Load plugin from file** → zip 선택
3. 플러그인 목록에서 **Korean Font Fallback Fixer** 더블클릭 → **Customize plugin**
4. 업로드한 폰트의 **family name** 입력

   | 폰트 파일 | Family name |
   |-----------|-------------|
   | NanumGothic.ttf | `NanumGothic` |
   | NotoSansKR-Regular.otf | `Noto Sans KR` |
   | KoPubDotum.ttf | `KoPub Dotum` |

   > macOS에서 family name 확인: 폰트 파일 선택 후 Space → 미리보기 상단 이름

### 3. 변환 및 읽기

- Calibre에서 평소처럼 EPUB → KFX 변환 (플러그인이 자동으로 CSS 수정)
- 킨들에서 책 열기 → **Aa → Publisher Font: ON**

## 빌드

```bash
zip -j korean_font_fixer.zip korean_font_fixer/__init__.py
```

## 제한사항

- 킨들 KFX 렌더러의 `local()` CSS 함수 지원이 공식 확인되지 않음 — 동작하지 않으면 폰트를 EPUB에 직접 임베드하는 방식 검토 필요
- KFX 포맷은 Calibre를 통한 폰트 임베딩이 불안정 (AZW3가 더 안정적)
- 탈옥 후 시스템 폰트(`/opt/amazon/ebook/fonts/`)를 교체하는 방법이 가장 근본적인 해결책

## 라이선스

MIT
