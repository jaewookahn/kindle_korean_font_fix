# kindle_korean_font_fix

킨들에서 EPUB의 한글 폰트 폴백 문제를 해결하는 Calibre 플러그인.

## 문제

EPUB CSS가 라틴 전용 폰트(한글 글리프 없음)를 지정하면, 킨들은 한글 렌더링 시
내장 기본 한국어 폰트(보기 흉한 bitmap 계열)로 폴백한다.
Aa 메뉴에서 사용자 폰트를 선택해도 폴백 체인이 변경되지 않아 해결되지 않는다.

## 해결 방식

Calibre의 `FileTypePlugin` (`on_preprocess=True`)을 사용해 EPUB → KFX 변환 직전
EPUB의 모든 CSS 파일에 아래 두 가지를 주입한다:

1. `@font-face` 선언 — 킨들 `fonts/` 폴더에 업로드된 폰트를 `local()`로 참조,
   `unicode-range`로 한글 코드포인트만 커버
2. 기존 `font-family` 선언 전체에 `"KoreanFallback"` 추가 (generic family 직전 삽입)
   CSS에 font-family가 아예 없으면 주요 요소(`body, p, div, h1-h6, li, ...`)에 규칙 추가

킨들에서는 **Aa → Publisher Font ON** 상태로 읽어야 주입된 폰트가 적용된다.

## 파일 구조

```
korean_font_fixer/
  __init__.py          # 플러그인 본체
korean_font_fixer.zip  # Calibre에 직접 설치 가능한 패키지
```

## 빌드 (zip 재생성)

```bash
zip -j korean_font_fixer.zip korean_font_fixer/__init__.py
```

## 설치

1. Calibre → Preferences > Plugins > Load plugin from file → `korean_font_fixer.zip`
2. 플러그인 목록에서 **Korean Font Fallback Fixer** 더블클릭 → Customize plugin
3. 킨들 `fonts/` 폴더에 올려둔 폰트의 family name 입력 (예: `NanumGothic`)
   - macOS: 폰트 파일 Space → 미리보기 상단 이름 확인
   - 또는 Font Book 앱에서 확인

## 제한사항

- `local()` CSS 함수의 킨들 KFX 렌더러 지원 여부가 불확실 — 테스트 필요
  → 안 되면 폰트를 EPUB에 직접 임베드하는 방식으로 확장 필요
- KFX 포맷은 Calibre를 통한 폰트 임베딩이 불안정 (AZW3가 더 안정적)
- 킨들 펌웨어 업데이트 등으로 인한 `local()` 동작 변화 가능성 있음
