# Korean Font Fallback Fixer — 개선 계획

## 배경: 왜 시스템 폰트 교체는 불가능한가

조사 결과 (MobileRead 포럼, Epubor 등) 확정:

- `/opt/amazon/ebook/fonts/` 는 stock 펌웨어에서 쓰기 차단
- Amazon 샌드박스가 `fc-cache` 실행도 막음
- 알려진 교체 방법 모두 jailbreak (USBNetwork + SSH + root) 필요
- 구형 Kindle 의 `reader.pref` 에 `ALLOW_USER_FONT=true` 트릭은 `/fonts/` 폴더 활성화일 뿐 시스템 폰트 교체 아님

→ 활용 가능한 채널은 두 개뿐:
1. **사용자 업로드 폰트**: 킨들 `/fonts/` 폴더 (Personal Fonts)
2. **임베드 폰트**: 책 파일 내부 `OEBPS/Fonts/` + `@font-face url(...)`

## 케이스 정리

실제 책들에서 만난 패턴들. 신규 기능 설계 시 이 함정들 회피.

### Case 1 — 비-임베드 한글 폰트 참조 *(처리됨)*
**예**: 모비딕 (`font-family:"나눔명조"`, `"나눔고딕 ExtraBold"`)
- CSS 는 한글 폰트를 참조하지만 `@font-face` 없고 EPUB 에 파일도 없음
- 킨들에 사용자 업로드한 폰트의 name table 에 일치하는 이름 없으면 bitmap 으로 폴백
- **해결**: 사용자가 설정한 fallback 폰트 이름으로 CSS 참조 통째 교체

### Case 2 — 임베드 폰트의 alias 와 파일 내부 이름 불일치 *(처리됨, 단 조심)*
**예**: Karen Hao (`@font-face { font-family:"MjL"; src:url(KoPubWBL.ttf) }`)
- 폰트 파일은 EPUB 에 있음, alias 는 짧은 코드
- 파일 내부 이름은 "KoPubWorldBatang Light"
- KFX 가 alias 무시하고 내부 이름으로 매칭하는 케이스 존재
- **해결**: 폰트 파일의 name table 읽어서 CSS 참조를 실제 내부 이름으로 교체
- ⚠ KFX 가 alias 를 인정하는 케이스도 있음 — rewrite 가 항상 안전하지 않을 수 있음 (자동 감지 불가)

### Case 3 — Alias 가 폰트의 다른 언어 이름 *(거짓 mismatch, 처리됨)*
**예**: UnDotum.ttf — name table 에 "UnDotum" (영문) + "은 돋움" (한글)
- CSS `@font-face { font-family:"은 돋움" }`, 파일 family name 은 "UnDotum"
- **단순 비교 시 mismatch 로 잘못 분류** → 진단 노이즈
- **해결**: name table 의 모든 언어 변형 수집해서 alias 가 그 중 하나라도 일치하면 mismatch 아님

### Case 4 — CSS 에 정의됐으나 HTML 에서 미사용 *(거짓 누락, 처리됨)*
**예**: Steinbeck 분노의 포도 — `.iG{font-family:AppleGothic}` 정의만 있고 HTML 에서 `class="iG"` 안 씀
- 누락 폰트로 잡혀도 실제 렌더링에 영향 없음
- **해결**: HTML 의 `class="..."` 수집 → 셀렉터의 클래스가 실제 사용되는지 체크 → 미사용은 별도 카테고리

### Case 5 — Latin/시스템 폰트 *(별도 분류, 처리됨)*
**예**: AppleGothic, Times New Roman, Tahoma, Old English Text MT
- 킨들에 없어도 자체 처리 (Latin 기본 폰트로 폴백)
- 한글 폰트 누락과 같은 톤으로 경고하면 노이즈
- **해결**: 시스템 폰트 목록 + 한글 키워드 검사로 분류 → 한글 누락만 강조

### Case 6 — KFX 가 alias 를 인정하는 케이스 *(처리 검토 중)*
**예**: 어떤 책의 `tmp`, `\ace0\b515`, `sun`, `han` 같은 짧은 alias
- alias 와 파일 내부 이름이 완전히 다른데도 KFX 가 정상 매칭
- 책마다 다르고 KFX 펌웨어/변환기 버전에 따라 다를 가능성
- **현재 처리**: rewrite 는 항상 적용 (safe no-op 가정), 진단은 정보성으로만 표시
- **위험**: 만약 KFX 가 alias-only 매칭하는 케이스라면 rewrite 가 깨뜨릴 수 있음
- **자동 감지 불가**: 변환 결과는 binary KFX, 렌더링은 킨들에서만

### Case 7 — 한글도 기본 폴백이 깨끗한 경우 *(불확실)*
**예**: 분노의 포도 — AppleGothic 으로 한글 텍스트 스타일됐으나 킨들에서 bitmap 안 보임
- 우리가 가정한 "킨들 기본 한글 = ugly bitmap" 이 항상 맞지 않음
- 펌웨어 버전, Aa 설정, 책의 한글 분량에 따라 다를 수 있음

## 구현 완료

| 기능 | 위치 | 비고 |
|------|------|------|
| NCX `<pageList>` / EPUB3 nav page-list 제거 | Korean Font Fixer | KFX 페이지 추정 보호 |
| 비-임베드 폰트 → 사용자 fallback 으로 교체 | Korean Font Fixer | Case 1 |
| @font-face alias → 파일 내부 이름으로 자동 교체 | Korean Font Fixer | Case 2 (단 Case 6 위험 있음) |
| EPUB 진단 (책별) | EPUB Diagnostics | 임베드/누락/미사용/페이지데이터 표시 |
| 라이브러리 전체 스캔 | EPUB Diagnostics | 한글 누락 / 페이지데이터 / alias 불일치 책 목록 |
| Alias mismatch 다국어 필터 | 양쪽 플러그인 | Case 3 |
| 시스템/Latin 폰트 분리 | EPUB Diagnostics | Case 5 |
| 미사용 CSS 클래스 필터 | EPUB Diagnostics | Case 4 |

## 향후 계획

### A. 사용자 폰트 폴더 자동 매핑

**문제**: 책마다 다른 한글 폰트 참조 (`나눔명조`, `KoPub돋움` 등). 사용자가 매번 매핑 입력하긴 번거로움.

**아이디어**: 사용자가 로컬 폰트 폴더 한 번 지정 → 그 폴더의 모든 폰트 파일 name table 읽어서 사용 가능한 이름 set 구축 → 변환 시 자동 활용.

**동작**:
```
설정: "내 폰트 폴더 = ~/kindle_fonts/"
폴더 내용: NanumMyeongjo.otf, NanumGothic.otf, KoPubDotum.otf, ...
각 파일의 name table 에서 모든 이름 수집 →
{"NanumMyeongjo", "나눔명조", "NanumGothic", "나눔고딕", "KoPub Dotum", "코펍돋움", ...}

변환 시:
- CSS `font-family:"나눔명조"` → 이름 set 에 있음 → 그대로 둠 (킨들이 매칭함)
- CSS `font-family:"나눔고딕 ExtraBold"` → set 에 없음 → 기본 fallback 으로 교체
```

**장점**: 한 번 폴더 설정 → 모든 책에 자동 적용. 수동 매핑 거의 불필요.

**구현 메모**:
- 폴더 변경 감지 (mtime 캐싱)
- 사용자가 폴더 = 킨들 `/fonts/` 의 미러로 관리한다고 가정
- EPUB Diagnostics 의 라이브러리 스캔에서 "이 폰트 폴더로 커버되는지" 자동 표시 가능

### B. 수동 매핑 (예외 케이스용)

자동 매핑으로 해결 안 되는 케이스 보강:
- 사용자 폰트 폴더에 없지만 책에서 참조하는 폰트
- 폴더에 있어도 이름이 안 맞아 매칭 안 되는 경우

**설정 UI**:
```
폰트 매핑 (한 줄당 원본=대체):
나눔명조=MyKoreanFont
KoPub돋움=NanumGothic
```

자동 매핑보다 우선순위 높음. 폴더 매칭 실패 시에도 적용.

### C. 자동 임베드

**문제**: 사용자가 폰트를 킨들 `/fonts/` 에 업로드해야 매핑 동작. 킨들 연결/관리 귀찮음.

**아이디어**: 사용자 폰트 폴더의 폰트 파일을 변환 시 EPUB 에 자동 임베드.

**동작**:
- 자동 매핑에서 매칭 실패한 폰트 참조 발견
- 사용자 폴더에서 해당 폰트 파일 찾음 (이름 매칭)
- 파일을 EPUB `OEBPS/Fonts/` 에 복사
- `@font-face { font-family:"이름"; src:url(...) }` 주입
- OPF manifest 갱신

**비용**: 책 크기 + 1~3MB per font

**의존성**: 폰트 name table 읽기 (이미 `fontTools` 사용)

### D. Alias rewrite 옵션화 (Case 6 안전장치)

현재 alias rewrite 는 항상 적용. KFX 가 alias 인정하는 책에서 깨뜨릴 위험.

**옵션 추가**:
```
☐ @font-face alias 자동 교체 (KFX 호환성)
   - 켜면: 임베드 폰트의 alias 와 파일 내부 이름 다를 때 CSS 참조 교체
   - 끄면: alias 그대로 (KFX 가 alias 인정하면 동작)
```

기본값은 ON (Karen Hao 같은 케이스가 빈도 높을 듯) 이지만 사용자가 문제 시 OFF.

### E. EPUB Diagnostics 확장

- "라이브러리 폰트 요약" 메뉴 (모든 책에서 참조되는 unique 폰트 + 어느 책에 쓰이는지)
- 자동 매핑 폴더와 비교 → 커버 / 미커버 표시
- 매핑 후보 추천 (누락 폰트 → 비슷한 이름의 폴더 폰트)
- 누락 폰트 클릭 → Korean Font Fixer 의 수동 매핑 입력란에 자동 추가

## 구현 순서 (제안)

| 단계 | 기능 | 효과 |
|------|------|------|
| 1 | A. 자동 매핑 (폰트 폴더 기반) | 사용자 입력 최소화, 가장 큰 효용 |
| 2 | D. Alias rewrite 옵션화 | Case 6 안전망 |
| 3 | E. Diagnostics 폴더 매칭 표시 | A 의 결과를 시각화 |
| 4 | B. 수동 매핑 | A 의 예외 처리 |
| 5 | C. 자동 임베드 | 가장 강력하나 복잡, 후순위 |

## 미해결 / 추가 검토

- KFX 변환기가 새로 주입한 `@font-face url()` 을 어떻게 처리하는지 실측 필요
- 폰트 라이선스: 자동 임베드 시 재배포 — 사용자 책임 명시
- 폰트 서브셋팅은 Calibre 가 변환 시 처리 — 우리는 풀셋 임베드 후 위임
- Case 6 (KFX 가 alias 인정/무시 케이스 구분) 추가 연구 — KoReader 소스 코드, KFX 명세 등 참고
- Case 7 (킨들 한글 기본 폴백의 실제 모습) — 펌웨어별 차이 조사
