# 🗺️ YouTube → Master Excel CLI Tool 구현 로드맵

*설계 문서 (Final) 기반 Phase별 구현 계획*

---

## 전제 조건

- **런타임**: Python 3.12+ / uv 패키지 매니저
- **핵심 의존성**: `yt-dlp`, `openpyxl`, `openai`, `rich`, `pyyaml`
- **설계 문서**: `docs/youtube_master_excel_cli_design_final.md`
- **각 Phase 종료 조건**: 해당 Phase의 모든 체크리스트 항목이 완료되고, 수동 테스트를 통과해야 다음 Phase로 진행

---

## Phase 0: 프로젝트 스캐폴딩

> 코드를 작성하기 전에 프로젝트 구조와 개발 환경을 확립한다.

### 작업 내용

- uv 프로젝트 초기화 (`pyproject.toml`)
- 디렉토리 구조 생성
- 의존성 정의 및 설치
- config.yaml 기본 템플릿 생성
- CLI 엔트리포인트 설정 (`yt-excel` 커맨드)

### 디렉토리 구조

```
yt-excel/
├── pyproject.toml
├── config.yaml
├── CLAUDE.md
├── README.md
├── docs/
│   ├── youtube_master_excel_cli_design_final.md
│   └── Roadmap.md
├── src/
│   └── yt_excel/
│       ├── __init__.py
│       ├── cli.py              # CLI 엔트리포인트
│       ├── config.py           # config.yaml 로딩
│       ├── environment.py      # API 키 검증
│       ├── youtube.py          # URL 파싱, 메타데이터, 자막 다운로드
│       ├── vtt.py              # VTT 파싱, 마크업 strip, 세그먼트 처리
│       ├── translator.py       # Translation Engine
│       ├── excel.py            # Excel 읽기/쓰기, 스타일, 초기화
│       └── retry.py            # 공통 retry 유틸리티
└── tests/
    ├── __init__.py
    ├── fixtures/
    ├── test_youtube.py
    ├── test_vtt.py
    ├── test_translator.py
    └── test_excel.py
```

### 완료 조건

- [ ] `uv run yt-excel --help` 가 도움말을 출력한다
- [ ] `uv run yt-excel --version` 이 버전 정보를 출력한다
- [ ] config.yaml을 로딩하여 기본값을 반환한다

### 참조 설계 섹션

- 14️⃣ Config 파일 설계
- 13.6 CLI 인터페이스 요약

---

## Phase 1: 환경 검증 + URL 파싱

> 파이프라인의 시작점. 외부 의존성 없이 입력 검증만 수행한다.

### 작업 내용

- `OPENAI_API_KEY` 환경 변수 검증 로직 (`environment.py`)
- YouTube URL 파싱 및 video_id 추출 (`youtube.py`)
- CLI 옵션 파싱 (`--master`, `--model`, `--verbose`, `--quiet`, `--dry-run`)
- `--dry-run` 모드에서 API 키 검증 건너뛰기

### 완료 조건

- [ ] API 키 미설정 시 설정 안내 메시지와 함께 종료
- [ ] API 키가 빈 문자열인 경우도 감지
- [ ] 유효한 YouTube URL에서 video_id 11자를 정확히 추출
- [ ] 잘못된 URL 입력 시 에러 메시지와 함께 종료
- [ ] `--dry-run` 모드에서 API 키 없이도 진행 가능
- [ ] CLI 옵션이 config.yaml 기본값을 올바르게 오버라이드

### 참조 설계 섹션

- 4️⃣ API 키 관리
- 3️⃣ 전체 아키텍처 (처음 3단계)

---

## Phase 2: 자막 다운로드 파이프라인

> YouTube에서 수동 영어 자막을 다운로드하는 전체 흐름을 구현한다.

### 작업 내용

- 영상 메타데이터 조회: 제목, 채널명, 영상 길이 (`youtube.py`)
- 자막 목록 조회 및 영어 언어 코드 매칭 (`en` 우선, `en-*` fallback)
- 자막 유형 분류 (manual / auto / none) 및 분기 처리
- 수동 자막 VTT 파일 다운로드
- 네트워크 단계 retry 로직 적용 (Exponential Backoff + Jitter)

### 완료 조건

- [ ] 수동 영어 자막이 있는 영상에서 VTT 파일을 정상 다운로드
- [ ] `en-US`, `en-GB` 등 영어 변종 코드를 올바르게 인식
- [ ] 자동 생성 자막만 있는 영상에서 경고 메시지 후 종료
- [ ] 자막이 없는 영상에서 에러 메시지 후 종료
- [ ] 수동 + 자동 공존 시 수동만 선택
- [ ] 네트워크 실패 시 3회 재시도 후 종료
- [ ] `--dry-run` 모드에서 자막 가용성 확인까지만 수행

### 참조 설계 섹션

- 5️⃣ 자막 다운로드 정책
- 7️⃣ 전체 파이프라인 Retry 정책 (네트워크 단계)

---

## Phase 3: VTT 파싱 + 세그먼트 처리

> 다운로드된 VTT를 파싱하고 학습에 적합한 세그먼트로 정제한다.

### 작업 내용

- VTT 파일 파싱: timestamp 추출, 텍스트 추출 (`vtt.py`)
- HTML/WebVTT 마크업 strip (태그 제거, 엔티티 디코딩)
- 다중 라인 → 단일 라인 변환 (Segment Normalizer)
- 비언어 텍스트 제거 (`[Music]`, `[Applause]`, `♪ ♪` 등)
- 짧은 세그먼트 필터링 (duration < 0.5초 또는 text < 2자)
- 필터링 후 0개 세그먼트 에러 처리
- Timestamp 누락 세그먼트 감지 및 즉시 종료

### 완료 조건

- [ ] VTT에서 start/end timestamp와 텍스트를 정확히 추출
- [ ] `<c>`, `<v>`, `<b>`, `<i>`, `<font>` 등 모든 태그가 제거되고 텍스트는 보존
- [ ] `&amp;`, `&lt;`, `&#39;` 등 HTML 엔티티가 올바르게 디코딩
- [ ] VTT 위치 지시자 (`align:start`, `position:10%` 등)가 제거
- [ ] 여러 줄 텍스트가 단일 공백으로 합쳐짐
- [ ] `[Music]`, `(Laughs)`, `♪ ♪` 등 비언어 텍스트가 제거
- [ ] 비언어 제거 후 빈 세그먼트가 삭제
- [ ] 0.5초 미만 또는 2자 미만 세그먼트가 필터링
- [ ] `--dry-run` 모드에서 필터링 결과 미리보기 표시
- [ ] Timestamp가 `HH:MM:SS.mmm` 형식으로 정규화

### 참조 설계 섹션

- 6️⃣ VTT 파싱 및 세그먼트 처리 (전체)

---

## Phase 4: Translation Engine

> OpenAI API를 사용한 Sliding Window 배치 번역을 구현한다.

### 작업 내용

- OpenAI API 클라이언트 설정 (`translator.py`)
- Sliding Window 배치 구성 (batch_size=10, context_before/after=3)
- 시스템 프롬프트 작성 (`[CONTEXT]` / `[TRANSLATE]` 구분)
- `response_format: { type: "json_object" }` 적용
- 응답 파싱: JSON 모드 + 마크다운 코드 블록 fallback strip
- 응답 검증: 배열 길이 일치/초과/부족 처리
- 배치별 retry (3회, Exponential Backoff + Retry-After)
- Rate Limit 대응 (요청 간 200ms 간격, 429 처리)
- 실패 배치는 Korean 비워두고 계속 진행
- Progress bar (`rich` 라이브러리)

### 완료 조건

- [ ] 10개 세그먼트를 1배치로 번역 요청/응답 성공
- [ ] 앞뒤 3개 컨텍스트 세그먼트가 올바르게 포함되되 번역되지 않음
- [ ] 영상 시작/끝 edge case에서 context 수가 자동 조정
- [ ] 총 세그먼트 ≤ 10인 경우 단일 배치로 처리
- [ ] JSON 응답이 정확히 N개 항목을 포함
- [ ] 배열 길이 초과 시 앞 N개만 사용 + 경고 로그
- [ ] 배열 길이 부족 시 재시도
- [ ] 3회 실패 배치의 세그먼트가 Korean 빈 상태로 저장
- [ ] 429 응답 시 Retry-After 헤더 기반 대기
- [ ] Progress bar가 세그먼트 단위로 진행률 표시
- [ ] `--dry-run` 모드에서 번역 API를 호출하지 않고 예상 비용 표시

### 참조 설계 섹션

- 7️⃣ Translation Engine (전체)

---

## Phase 5: Excel Writer + Master.xlsx 관리

> 번역 결과를 Excel에 저장하고, Master 파일의 생명주기를 관리한다.

### 작업 내용

- Master.xlsx 초기화 로직 (`excel.py`)
  - 파일 미존재 시 신규 생성 (_metadata + _study_log 헤더 포함)
  - 기존 파일 무결성 검증 (누락 시트 복구, 기존 데이터 보호)
- 파일 잠금 사전 검증 (best-effort)
- 중복 체크 (_metadata에서 video_id 조회)
- 데이터 시트 생성
  - Sheet Naming (특수문자 치환, 31자 truncation, 중복 접미사)
  - Column 기입 (Index, Start, End, English, Korean)
- _metadata 행 추가 (13개 필드)
- _study_log 행 추가 (CLI 자동 5개 필드 + 사용자 기본값 3개 필드)
- 스타일 정책 적용
  - 폰트 auto-detect (Noto Sans KR → Malgun Gothic fallback)
  - 헤더 스타일 (#F2F2F2, Bold, 하단 테두리)
  - 데이터 영역 (Wrap Text, Top 정렬, 연한 수평 테두리)
  - 컬럼 너비/정렬
  - Freeze Top Row, Auto Filter, Sheet Tab Color
  - Conditional Formatting (번역 실패 행, Not Started 상태)
- Timestamp 텍스트 형식 저장

### 완료 조건

- [ ] 최초 실행 시 Master.xlsx가 _metadata + _study_log 포함으로 생성
- [ ] 기존 파일에서 _study_log만 누락 시 _study_log만 복구, 기존 데이터 보존
- [ ] _metadata 누락 시 경고 메시지 출력 후 재생성
- [ ] 파일이 Excel에서 열려 있을 때 사전 검증에서 즉시 종료
- [ ] 이미 처리된 video_id에 대해 중복 안내 후 종료
- [ ] 시트 이름이 31자 이내, 금지 문자 치환, 중복 접미사 처리
- [ ] 데이터 시트의 5개 컬럼이 올바른 값으로 기입
- [ ] Timestamp가 텍스트 형식으로 저장 (시간 서식 변환 없음)
- [ ] _metadata에 13개 필드가 올바르게 기록
- [ ] _study_log에 Status="Not Started", Review Count=0으로 초기화
- [ ] 폰트가 시스템에 따라 올바르게 선택 (Noto Sans KR 또는 Malgun Gothic)
- [ ] 헤더 배경 #F2F2F2, 글자 #333333, Bold 적용
- [ ] 번역 실패 행이 #FFF2F2 배경으로 표시
- [ ] _study_log에서 Not Started 행이 #FFF8E1 배경으로 표시
- [ ] Freeze Top Row가 모든 시트에 적용
- [ ] _metadata, _study_log에 Auto Filter 적용
- [ ] Sheet Tab Color 적용 (회색, 파랑)
- [ ] Excel 파일이 Microsoft Excel과 LibreOffice에서 정상 열림

### 참조 설계 섹션

- 8️⃣ Master.xlsx 구조
- 9️⃣ Metadata Sheet 설계
- 🔟 학습 로그 시트 설계
- 1️⃣1️⃣ Excel 스타일 정책

---

## Phase 6: 파이프라인 통합 + CLI UX

> 모든 모듈을 하나의 파이프라인으로 연결하고 CLI UX를 완성한다.

### 작업 내용

- 전체 파이프라인 연결 (cli.py에서 각 모듈 순차 호출)
- 단계별 CLI 출력 (이모지 접두사, 색상, 들여쓰기)
- 에러 표시 규칙 적용 (INFO/WARNING/ERROR/SUCCESS)
- Summary 출력 (세그먼트 수, 번역 성공/실패, 비용, 시간)
- `--verbose` 모드: 각 세그먼트 상세, API 응답 시간, 제거 태그 목록
- `--quiet` 모드: 오류와 최종 결과만
- `--dry-run` 모드: 번역/저장 없이 분석 결과만 표시
- 전체 실행 시간 측정

### 완료 조건

- [ ] URL 입력부터 Summary 출력까지 전체 파이프라인이 정상 동작
- [ ] 설계 문서 13.1의 CLI 출력 예시와 동일한 형태로 표시
- [ ] `--verbose` 모드에서 상세 정보 추가 출력
- [ ] `--quiet` 모드에서 최소 출력
- [ ] `--dry-run` 모드에서 API 호출 없이 분석 결과 표시
- [ ] 각 단계에서 에러 발생 시 적절한 수준(INFO/WARNING/ERROR)으로 표시
- [ ] 파이프라인 중간 실패 시 이미 완료된 작업 내역이 손실되지 않음
- [ ] Summary에 비용 추정치와 총 소요 시간이 표시

### 참조 설계 섹션

- 1️⃣3️⃣ CLI UX 설계 (전체)
- 3️⃣ 전체 아키텍처

---

## Phase 7: 엣지 케이스 + 안정화

> 실제 사용에서 발생할 수 있는 예외 상황을 처리하고 안정성을 높인다.

### 작업 내용

- 다양한 YouTube 영상으로 E2E 테스트
  - TED-Ed (기본 대상)
  - TED Talk (장시간, 다량 세그먼트)
  - 자막 없는 영상
  - 자동 생성 자막만 있는 영상
  - `en-US`, `en-GB` 자막 영상
- VTT edge case 테스트
  - `<c>` word-level timing이 포함된 VTT
  - `<v>` 화자 태그가 포함된 VTT
  - 비언어 텍스트와 일반 텍스트가 혼합된 세그먼트
  - 매우 긴 세그먼트 (100단어 이상)
  - 전체가 비언어인 세그먼트
- Excel edge case 테스트
  - 시트 이름 31자 초과 제목
  - 특수문자가 가득한 제목 (`What is 1/0? [Part 2]: A *New* Theory`)
  - 동일 제목 영상 2개 연속 처리
  - 100+ 시트가 있는 Master.xlsx
- 번역 실패 시나리오 테스트
  - API timeout
  - 잘못된 API 키
  - Rate limit (429)
  - JSON 파싱 실패
  - 배열 길이 불일치
- 파일 시스템 테스트
  - Master.xlsx가 읽기 전용
  - Master.xlsx가 Excel에서 열려 있는 상태
  - 디스크 경로에 한글/공백 포함
- 발견된 버그 수정 및 안정화

### 완료 조건

- [ ] 위의 모든 테스트 시나리오에서 프로그램이 crash 없이 적절한 메시지를 출력
- [ ] 번역 부분 실패 시 성공한 세그먼트는 정상 저장, 실패 세그먼트는 빈 상태로 저장
- [ ] 동일 영상 재실행 시 중복 안내 후 정상 종료
- [ ] 다양한 영어 변종 코드에서 자막 인식 성공

### 참조 설계 섹션

- 1️⃣2️⃣ 오류 처리 종합
- 설계 문서 전체 (edge case 산재)

---

## Phase별 의존 관계

```
Phase 0 ─→ Phase 1 ─→ Phase 2 ─→ Phase 3 ─┐
                                             ├─→ Phase 6 ─→ Phase 7
                       Phase 4 (번역) ───────┘        ↑
                       Phase 5 (Excel) ───────────────┘
```

- Phase 0~3은 순차적으로 진행 (각 단계가 이전 단계의 출력을 사용)
- Phase 4 (번역)는 Phase 3 완료 후 시작 가능
- Phase 5 (Excel)는 Phase 1 완료 후 독립적으로 병행 가능 (자막 없이 Excel 구조만 구현)
- Phase 6은 Phase 3, 4, 5가 모두 완료된 후 통합
- Phase 7은 Phase 6 완료 후 안정화

---

## 우선순위 요약

| Phase | 핵심 산출물 | 예상 규모 |
|-------|-----------|-----------|
| 0 | 프로젝트 골격, CLI 엔트리포인트 | 소 |
| 1 | 환경 검증, URL 파싱 | 소 |
| 2 | 자막 다운로드 파이프라인 | 중 |
| 3 | VTT 파싱, 세그먼트 정제 | 중 |
| 4 | Sliding Window 번역 엔진 | 대 |
| 5 | Excel 쓰기, 스타일, 초기화 | 대 |
| 6 | 파이프라인 통합, CLI UX | 중 |
| 7 | E2E 테스트, 안정화 | 중 |