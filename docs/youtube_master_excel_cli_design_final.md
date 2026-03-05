# 📘 YouTube → Master Excel CLI Tool 설계 문서 (Final)

*(uv + Python 기반 / Listening·Speaking 최적화)*

---

# 변경 이력

| 버전 | 변경 내용 |
|------|-----------|
| v3 | 초기 설계 확정 |
| v4 | 자막 판별 로직, 번역 엔진 구체화, 컨텍스트 번역, Sheet Naming 규칙, Metadata 설계, 마크업 정책, Retry 정책, UX 설계 추가 |
| v4.1 | Sheet 이름에서 VideoID 제거 — 제목만 사용, 31자 전체를 Title에 할당 |
| v4.2 | Excel 스타일 정책 추가 (폰트 auto-detect, 연한 헤더, Conditional Formatting), _study_log 시트 추가 |
| v4.3 | Master.xlsx 초기화 및 무결성 검증 로직 추가 (파일 미존재 시 생성, 시트 누락 시 복구) |
| Final | v3 + v4 계열 통합, API 키 관리 정책 추가, 외부 피드백 반영 (언어 코드 유연성, 파일 잠금 사전 검증, JSON 응답 안정성) |

---

# 1️⃣ 시스템 목적

YouTube URL을 입력받아:

1. 수동 업로드된 English 자막만 사용
2. 원본 timestamp 100% 유지
3. VTT 세그먼트 그대로 유지 (병합/분리 금지)
4. 비언어 텍스트 제거
5. 아주 짧은 세그먼트 필터링
6. English 기준 1:1 Korean 번역 생성
7. Master.xlsx에 새로운 Sheet 생성
8. 이미 처리된 영상이면 재실행 금지

---

# 2️⃣ 핵심 설계 원칙

1. English = Source of Truth
2. Timestamp는 원본에서만 온다
3. 자동 생성 자막(auto-caption)은 사용하지 않는다
4. 데이터 무결성이 학습 편의성보다 우선한다
5. LLM은 번역 엔진 역할만 수행한다
6. Master Excel은 Immutable Data Layer다

---

# 3️⃣ 전체 아키텍처

```
CLI (입력 파싱 + 옵션 처리)
  ↓
Environment Validator (API 키 확인)
  ↓
URL Parser (video_id 추출)
  ↓
Video Metadata Fetcher ←── retry 3회
  ↓
Master.xlsx Initializer (파일 존재 확인 → 신규 생성 또는 무결성 검증)
  ↓
File Lock Check (쓰기 권한 사전 검증, best-effort)
  ↓
Duplicate Check (_metadata sheet 조회)
  ↓
Caption Lister ←── retry 3회
  ↓
Caption Type Validator (manual/auto/none 분류)
  ↓
Caption Downloader (manual en only) ←── retry 3회
  ↓
VTT Parser
  ↓
Markup Stripper (HTML/WebVTT 태그 제거)
  ↓
Segment Normalizer (다중 라인 → 단일 라인)
  ↓
Segment Filter (비언어 제거 + 짧은 구간 제거)
  ↓
Translation Engine (Sliding Window 배치) ←── 배치별 retry 3회
  ↓
Excel Writer ←── retry 2회
  ↓
Metadata Writer ←── retry 2회
  ↓
Study Log Writer ←── retry 2회
  ↓
Summary 출력
```

---

# 4️⃣ API 키 관리

## 4.1 관리 방식

환경 변수 `OPENAI_API_KEY`로 관리한다. config.yaml에 API 키를 저장하지 않는다.

프로젝트 루트의 `.env` 파일을 지원하여 매 세션마다 환경 변수를 설정하는 번거로움을 줄인다.
`python-dotenv` 패키지를 사용하여 `.env` 파일에서 환경 변수를 로딩한다.

### 로딩 우선순위

```
1. 시스템 환경 변수 (이미 설정되어 있으면 최우선)
2. .env 파일 (시스템 환경 변수에 없을 때 fallback)
3. 둘 다 없으면 → 에러 메시지 출력 후 종료
```

`python-dotenv`의 `override=False` 옵션을 사용하여 시스템 환경 변수가 .env보다 우선하도록 한다.

### .env 파일 관리

```
# .env.example (커밋 대상 — 필요한 변수 안내용)
OPENAI_API_KEY=your-api-key-here
```

```
# .env (gitignore 대상 — 실제 키 보관)
OPENAI_API_KEY=sk-실제키값
```

- `.env`는 `.gitignore`에 포함하여 절대 커밋하지 않는다
- `.env.example`은 커밋하여 어떤 환경 변수가 필요한지 안내한다

## 4.2 검증 흐름

```
CLI 시작
→ .env 파일 로딩 (python-dotenv, override=False)
→ 환경 변수 OPENAI_API_KEY 존재 확인
→ 없음:
    ❌ ERROR: OPENAI_API_KEY is not set.

    Set it with one of:
      1. Create a .env file:  echo OPENAI_API_KEY=sk-... > .env
      2. Export directly:      export OPENAI_API_KEY="sk-..."  (Linux/macOS)
                               $env:OPENAI_API_KEY="sk-..."    (PowerShell)

    Aborting.
→ 있음: 빈 문자열 확인
    → 빈 문자열:
        ❌ ERROR: OPENAI_API_KEY is set but empty.
        Aborting.
    → 값 존재: 정상 진행
```

## 4.3 검증 시점

- CLI 시작 직후, URL 파싱 전에 수행
- `--dry-run` 모드에서는 검증을 건너뛴다 (API를 호출하지 않으므로)
- API 키 형식 검증(sk- 접두사 등)은 하지 않는다 — OpenAI 측 형식 변경에 의존하지 않기 위함

## 4.4 보안 원칙

- API 키는 config.yaml에 절대 저장하지 않는다
- `.env` 파일은 `.gitignore`에 포함하여 절대 커밋하지 않는다
- CLI 로그(verbose 모드 포함)에 API 키를 출력하지 않는다
- 에러 메시지에 API 키 값을 포함하지 않는다

---

# 5️⃣ 자막 다운로드 정책

## 5.1 자동 생성 자막 판별

`yt-dlp --list-subs <URL>` 출력에서 자막 유형을 분류한다.

- **수동 자막**: `subtitles` 필드에 영어 코드 존재
- **자동 생성 자막**: `automatic_captions` 필드에 영어 코드 존재

### 영어 언어 코드 매칭

YouTube 크리에이터에 따라 `en`, `en-US`, `en-GB`, `en-CA` 등 다양한 영어 코드로 자막을 업로드한다.
`en`으로 시작하는(`startswith('en')`) 모든 코드를 영어로 인식한다.
ISO 639-1에서 `en`으로 시작하는 비영어 언어는 없으므로 안전하다.

**여러 영어 변종이 동시에 존재할 때 우선순위:**

```
1. 'en' 정확 일치 → 최우선 선택
2. 'en' 정확 일치 없으면 → 'en-*' 중 첫 번째 선택
```

## 5.2 분기 처리

```
subtitles에 영어 코드 있음 → 수동 자막 다운로드 → 정상 진행
subtitles에 영어 코드 없음 + automatic_captions에 영어 코드 있음 → 자동 자막 감지 → 사용자 안내 후 종료
subtitles에 영어 코드 없음 + automatic_captions에 영어 코드 없음 → 자막 자체가 없음 → 사용자 안내 후 종료
```

## 5.3 사용자 안내 메시지

**자동 생성 자막만 있는 경우:**

```
⚠ WARNING: This video only has auto-generated English captions.
Auto-generated captions are excluded by policy due to low accuracy.

Possible actions:
  1. Choose a different video with manual captions
  2. Manually upload captions to the video and retry

Aborting extraction.
```

**자막이 아예 없는 경우:**

```
❌ ERROR: No English captions found for this video.
Neither manual nor auto-generated English captions are available.

Aborting extraction.
```

## 5.4 수동 자막 + 자동 자막 공존 시

수동 자막만 사용한다. 자동 자막은 완전히 무시한다. 별도 안내 없이 정상 진행한다.

---

# 6️⃣ VTT 파싱 및 세그먼트 처리

## 6.1 Segment Normalizer

- VTT 세그먼트 그대로 유지
- 병합 금지
- 분리 금지
- timestamp 변경 금지
- 여러 줄 텍스트는 공백으로 합쳐 단일 라인으로 변환

## 6.2 HTML/WebVTT 마크업 Strip

### 제거 대상

**WebVTT 전용 태그:**

| 태그 | 설명 | 예시 |
|------|------|------|
| `<c>` | word-level timing | `<c.colorE5E5E5>word</c>` |
| `<v>` | 화자 식별 | `<v Speaker>text</v>` |
| `<lang>` | 언어 지정 | `<lang en>text</lang>` |
| `<ruby>`, `<rt>` | 루비 텍스트 | CJK 발음 표기 |

**HTML 인라인 태그:**

| 태그 | 설명 |
|------|------|
| `<b>`, `</b>` | 굵게 |
| `<i>`, `</i>` | 기울임 |
| `<u>`, `</u>` | 밑줄 |
| `<font>`, `</font>` | 폰트 스타일 |

**VTT 위치/스타일 지시자:**

| 패턴 | 설명 |
|------|------|
| `align:start` | 정렬 |
| `position:10%` | 위치 |
| `size:80%` | 크기 |
| `line:0` | 라인 위치 |

### 처리 순서

```
1. VTT cue 설정 라인 제거 (align, position 등)
2. HTML/WebVTT 태그 제거 (정규식: <[^>]+>)
3. HTML 엔티티 디코딩 (&amp; → &, &lt; → <, &#39; → ' 등)
4. 비언어 텍스트 제거
5. 연속 공백 정리
6. trim
7. 빈 문자열 확인 → 빈 경우 세그먼트 삭제
```

### 처리 원칙

- 태그 내부의 텍스트는 보존한다 (태그만 벗긴다)
- `<c>word</c>` → `word`
- `<v Speaker>Hello</v>` → `Hello`
- 화자 이름(v 태그의 속성)은 제거한다
- 태그 제거는 비언어 텍스트 제거보다 먼저 수행한다

## 6.3 비언어 텍스트 제거

### 제거 대상 예시

- [Music]
- [Applause]
- [Laughter]
- (Laughs)
- ♪ ♪
- 배경 설명 괄호 텍스트

### 처리 정책

- 전체가 비언어 → 세그먼트 삭제
- 일부 포함 → 해당 부분만 제거
- 제거 후 빈 문자열 → 삭제

## 6.4 짧은 세그먼트 필터링

- duration < 0.5초 → 삭제
- 또는 text length < 2 → 삭제
- Listening 목적에 불필요한 초단위 세그먼트 제거

---

# 7️⃣ Translation Engine

## 7.1 모델 선택

| 구분 | 기본 모델 | 대체 모델 |
|------|-----------|-----------|
| 모델명 | `gpt-5-nano` | `gpt-5-mini` |
| Input 단가 | $0.05 / 1M tokens | $0.25 / 1M tokens |
| Output 단가 | $0.40 / 1M tokens | $2.00 / 1M tokens |
| Cached Input | $0.005 / 1M tokens | $0.025 / 1M tokens |
| 용도 | 기본 번역 | nano 품질 불만족 시 수동 전환 |

모델 전환은 설정 파일(`config.yaml`)에서 수행한다. 런타임 자동 전환은 하지 않는다.

## 7.2 번역 정책

- 세그먼트 단위 번역 (병합/분리 금지)
- 과도한 의역 금지
- 구조 추적 가능 유지
- 자연스러움 유지

## 7.3 비용 추정 (TED-Ed 기준)

일반적인 TED-Ed 영상 (5분, 약 150 세그먼트) 기준:

- 세그먼트당 평균 English 텍스트: ~15 words (~20 tokens)
- 컨텍스트 포함 배치 (20개 묶음): ~600 tokens input / ~400 tokens output
- 영상 1개당 총: ~5,000 input tokens + ~3,000 output tokens
- **gpt-5-nano 기준 영상 1개당 비용: $0.001 이하**
- **gpt-5-mini 기준 영상 1개당 비용: ~$0.007**

## 7.4 배치 전략

### 기본 단위: 10 세그먼트 1배치

- 세그먼트를 10개씩 묶어 1회 API 호출
- 각 세그먼트에 index 번호를 부여하여 1:1 매핑 보장
- 응답 형식: JSON array로 강제

### 배치 크기 선택 근거

| 배치 크기 | 장점 | 단점 |
|-----------|------|------|
| 1 (개별) | 실패 범위 최소 | 호출 수 과다, 느림 |
| 10 | 속도와 안정성 균형 | — |
| 20+ | 호출 수 최소 | 응답 파싱 실패 위험 증가 |

### 요청 형식 (개념)

```
System: 아래 영어 자막 세그먼트들을 한국어로 번역하라.
  - context_before: 이전 3개 세그먼트 (참고용, 번역하지 않음)
  - segments: 번역 대상 10개
  - context_after: 이후 3개 세그먼트 (참고용, 번역하지 않음)
  - 각 세그먼트의 index를 유지하여 JSON array로 반환
```

### Rate Limit 대응

- 요청 간 최소 간격: 200ms (configurable)
- 429 응답 시: `Retry-After` 헤더 기반 대기
- 대기 후 해당 배치만 재시도

## 7.5 컨텍스트 기반 번역 (Sliding Window)

### 문제 정의

단독 세그먼트는 문맥이 부족해 번역 품질이 떨어진다.

예시:
- "It does." → 앞 문맥 없이는 "그렇습니다" vs "그것이 합니다" 판단 불가
- "Right." → 동의(맞아요) vs 방향(오른쪽) 구분 불가

### Sliding Window 설계

```
전체 세그먼트: [1] [2] [3] [4] [5] [6] [7] [8] [9] [10] [11] [12] [13] ...

배치 1 번역 요청:
  context_before: (없음)
  ┌─────────────────────────┐
  │ translate: [1]~[10]     │ ← 실제 번역 대상
  └─────────────────────────┘
  context_after: [11] [12] [13]

배치 2 번역 요청:
  context_before: [8] [9] [10]
  ┌─────────────────────────┐
  │ translate: [11]~[20]    │ ← 실제 번역 대상
  └─────────────────────────┘
  context_after: [21] [22] [23]
```

### Window 파라미터

| 파라미터 | 값 | 설명 |
|----------|-----|------|
| `batch_size` | 10 | 한 번에 번역할 세그먼트 수 |
| `context_before` | 3 | 앞쪽 참고 세그먼트 수 |
| `context_after` | 3 | 뒤쪽 참고 세그먼트 수 |

### 프롬프트 내 구분

- 컨텍스트 세그먼트는 `[CONTEXT]` 태그로 명시
- 번역 대상 세그먼트는 `[TRANSLATE]` 태그로 명시
- LLM이 컨텍스트까지 번역하는 것을 방지

### Edge Cases

- 영상 시작: `context_before` 없이 진행
- 영상 끝: `context_after` 없이 진행
- 총 세그먼트 ≤ 10: 단일 배치, 컨텍스트 없음

## 7.6 응답 검증

### JSON 응답 보장

- OpenAI API의 `response_format: { type: "json_object" }` 옵션을 사용하여 JSON 형식을 강제한다
- Fallback: JSON 모드가 적용되지 않거나 마크다운 코드 블록(` ```json ... ``` `)으로 감싸진 경우, 파싱 전에 앞뒤 코드 블록을 strip한다

### 검증 규칙

- 반환된 배열 길이 == 요청 세그먼트 수 확인
- 각 항목이 빈 문자열이 아닌지 확인
- 검증 실패 시 해당 배치 전체 재시도 (최대 3회)
- 3회 실패 시 해당 세그먼트들은 Korean 컬럼 비워두고 진행
- 실패 세그먼트는 로그에 기록

### 배열 길이 불일치 처리

| 상황 | 처리 |
|------|------|
| 길이 일치 | 정상 사용 |
| 길이 부족 (< N) | 재시도 (컨텍스트까지 번역을 생략한 경우 등) |
| 길이 초과 (> N) | 앞에서 N개만 잘라서 사용, 초과분 버림 + 경고 로그 |

길이 초과는 LLM이 `[CONTEXT]` 세그먼트까지 번역한 경우에 발생할 수 있다. 앞에서 N개를 자르는 이유는 번역 대상 세그먼트가 응답 배열의 앞쪽에 위치하도록 프롬프트를 설계하기 때문이다.

---

# 8️⃣ Master.xlsx 구조

## 8.1 파일 내부 구조

```
Master.xlsx
│
├── _metadata          (시스템 처리 이력 — CLI 전용)
├── _study_log         (학습 추적 — CLI 초기값 + 사용자 편집)
├── How DNA Works      (영상별 데이터 시트)
├── Why Do We Procras… (영상별 데이터 시트)
└── ...
```

## 8.2 데이터 시트 Column 구조

| Column | 타입 | 설명 |
|--------|------|------|
| `Index` | int | 세그먼트 순번 |
| `Start` | string | 시작 타임스탬프 (HH:MM:SS.mmm) |
| `End` | string | 종료 타임스탬프 (HH:MM:SS.mmm) |
| `English` | string | 원본 영어 텍스트 |
| `Korean` | string | 한국어 번역 |

Reverse Translation column 없음.

## 8.3 Sheet Naming 규칙

### Excel 시트 이름 제약 조건

| 제약 | 내용 |
|------|------|
| 최대 길이 | 31자 |
| 금지 문자 | `/ \ ? * [ ] :` |
| 금지 이름 | 빈 문자열, 앞뒤 작은따옴표(`'`) |

### Naming 형식

```
{SanitizedTitle}
```

- VideoID는 시트 이름에 포함하지 않는다
- VideoID → sheet_name 매핑은 `_metadata` 시트에서 관리
- **Title 가용 공간**: 최대 **31자**

### Title Truncation 규칙

1. 원본 제목에서 금지 문자 치환 (아래 표 참고)
2. 연속 공백을 단일 공백으로 압축
3. 앞뒤 공백 제거 (trim)
4. 31자 초과 시 앞에서 30자 잘라내고 `…` (U+2026) 1자 추가
5. 잘라낸 결과가 공백으로 끝나면 해당 공백도 제거

### 특수문자 치환 정책

| 원본 문자 | 치환 결과 | 사유 |
|-----------|-----------|------|
| `/` | `-` | Excel 시트명 금지 |
| `\` | `-` | Excel 시트명 금지 |
| `?` | `` (삭제) | Excel 시트명 금지 |
| `*` | `` (삭제) | Excel 시트명 금지 |
| `[` | `(` | Excel 시트명 금지 |
| `]` | `)` | Excel 시트명 금지 |
| `:` | `-` | Excel 시트명 금지 |
| `'` (선두/후미) | `` (삭제) | Excel 시트명 선후 따옴표 금지 |

### 시트명 중복 처리

VideoID가 시트 이름에 없으므로, 동일 제목 영상 간 충돌 가능성이 있다.

```
{SheetName} → {SheetName}(2) → {SheetName}(3)
```

- 접미사 추가로 31자를 초과하면 Title 부분을 더 짧게 자른다
- 어떤 시트가 어떤 영상인지는 `_metadata` 시트의 `video_id` ↔ `sheet_name` 매핑으로 확인

### 예시

| 원본 제목 | 결과 시트명 |
|-----------|-------------|
| `How DNA Works` | `How DNA Works` (14자, OK) |
| `The Incredible Journey of a Red Blood Cell` | `The Incredible Journey of a R…` (31자) |
| `What is 1/0?` | `What is 1-0` (?삭제, /→- 치환) |
| `How DNA Works` (동일 제목 2번째) | `How DNA Works(2)` |

---

# 9️⃣ Metadata Sheet 설계

## 9.1 시트 이름

`_metadata` (언더스코어 접두사로 데이터 시트와 시각적 구분)

## 9.2 Column 구조

| Column | 타입 | 설명 |
|--------|------|------|
| `video_id` | string | YouTube Video ID (11자) |
| `video_title` | string | 원본 영상 제목 |
| `video_url` | string | 전체 YouTube URL |
| `channel_name` | string | 채널 이름 |
| `video_duration` | string | 영상 길이 (HH:MM:SS) |
| `sheet_name` | string | 생성된 시트 이름 |
| `processed_at` | datetime | 처리 완료 시각 (ISO 8601) |
| `total_segments` | int | 필터링 후 최종 세그먼트 수 |
| `filtered_segments` | int | 필터링으로 제거된 세그먼트 수 |
| `translation_success` | int | 번역 성공 세그먼트 수 |
| `translation_failed` | int | 번역 실패 세그먼트 수 |
| `model_used` | string | 사용된 LLM 모델명 |
| `tool_version` | string | CLI 도구 버전 |

## 9.3 Master.xlsx 초기화 및 무결성 검증

### 파일 존재 확인

Duplicate Check 진입 전에 Master.xlsx의 존재와 구조적 무결성을 먼저 확인한다.

```
Master.xlsx 경로 확인 (config.yaml 또는 --master 옵션)
→ 파일 없음 → 신규 생성
→ 파일 있음 → 무결성 검증
```

### 신규 파일 생성

Master.xlsx가 존재하지 않는 경우 (최초 실행):

```
1. 빈 Master.xlsx 생성
2. _metadata 시트 생성
   - 헤더 행 (13개 컬럼) 기입
   - 스타일 정책 적용 (헤더 #F2F2F2, 11pt Bold, Freeze Top Row, Auto Filter)
   - 컬럼 너비 설정
3. _study_log 시트 생성
   - 헤더 행 (8개 컬럼) 기입
   - 스타일 정책 적용 (동일)
   - 컬럼 너비 설정
4. Sheet Tab Color 적용 (_metadata: 회색, _study_log: 파랑)
5. 저장
```

CLI 출력:

```
📋 Checking Master.xlsx...
   ⚠ File not found at ./Master.xlsx
   ✅ Created new Master.xlsx with _metadata and _study_log sheets
```

### 기존 파일 무결성 검증

Master.xlsx가 존재하는 경우, 필수 시트의 존재를 확인한다.

```
Master.xlsx 열기
→ _metadata 시트 존재 확인
   → 없음 → _metadata 시트 헤더 포함 신규 추가
→ _study_log 시트 존재 확인
   → 없음 → _study_log 시트 헤더 포함 신규 추가
→ 누락된 시트가 있었다면:
   → 스타일 정책 적용 + 저장
   → CLI에 복구 사실 안내
→ 모두 정상이면: 정상 진행
```

CLI 출력 (시트 복구 시):

```
📋 Checking Master.xlsx...
   ⚠ _study_log sheet missing — recreated with headers
   ✅ Master.xlsx structure verified
```

### 기존 데이터 시트 보호

무결성 검증 시 기존에 존재하는 시트(데이터 시트, _metadata, _study_log)의 내용은 절대 수정하지 않는다. 누락된 시트만 새로 추가한다.

_metadata 시트가 누락되어 재생성하는 경우, 기존 데이터 시트들의 처리 이력이 소실된다. 이 상황을 CLI에서 경고한다:

```
⚠ WARNING: _metadata sheet was missing and has been recreated.
Previously processed video records are lost.
Existing data sheets are preserved but will not appear in metadata.
```

### 파일 잠금 사전 검증 (Fail-fast)

초기화 및 무결성 검증이 완료된 후, 파일에 대한 쓰기 권한을 사전 검증한다.
사용자가 Excel에서 Master.xlsx를 열어둔 채 CLI를 실행하는 실수를 조기에 차단하기 위함이다.

```
Master.xlsx를 쓰기 모드로 열기 시도
→ 성공: 즉시 닫고 정상 진행
→ 실패 (PermissionError 등):
    ❌ ERROR: Master.xlsx is locked or read-only.
    Please close the file in Excel and retry.
    Aborting.
```

**주의사항:**

- 이 검증은 best-effort다. 사전 검증 통과 후 번역 도중 사용자가 파일을 여는 경우는 막을 수 없다.
- 최종 Excel 쓰기 단계의 retry 정책(2회, Fixed 1s)은 그대로 유지한다.
- 사전 검증은 번역 API 호출 전에 수행하여, 파일 잠금으로 인한 API 비용 낭비를 최소화한다.

## 9.4 중복 체크 로직

초기화 및 무결성 검증이 완료된 후 수행한다.

```
_metadata 시트에서 video_id 컬럼 검색
→ 입력된 video_id 존재 시:
    ℹ INFO: This video has already been processed.
    Sheet: {sheet_name}
    Processed at: {processed_at}
    Aborting extraction.
→ 미존재 시: 정상 진행
```

---

# 🔟 학습 로그 시트 (_study_log) 설계

## 10.1 설계 원칙

**시스템 데이터와 사용자 데이터의 분리**

- `_metadata`: CLI가 자동으로 기록하는 처리 이력 (시스템 영역, 사용자 편집 금지)
- `_study_log`: 사용자가 직접 기록하는 학습 이력 (사용자 영역, CLI는 행 추가만)

이 분리로 CLI가 새 영상을 추가할 때 사용자의 학습 기록을 덮어쓸 위험을 제거한다.

## 10.2 시트 이름

`_study_log`

## 10.3 Column 구조

| Column | 타입 | 작성 주체 | 설명 |
|--------|------|-----------|------|
| `No` | int | CLI 자동 | 자동 증가 번호 |
| `Study Date` | date | CLI 자동 | 처리 날짜 (YYYY-MM-DD) |
| `Video Title` | string | CLI 자동 | 영상 제목 |
| `Duration` | string | CLI 자동 | 영상 길이 (MM:SS) |
| `Segments` | int | CLI 자동 | 세그먼트 수 |
| `Status` | string | **사용자** | Not Started / In Progress / Completed |
| `Review Count` | int | **사용자** | 복습 횟수 |
| `Notes` | string | **사용자** | 메모 (어려운 표현, 발음 포인트 등) |

## 10.4 CLI 동작 규칙

### 새 영상 추가 시

```
1. _study_log 시트 마지막 행 찾기
2. No = 마지막 No + 1
3. Study Date, Video Title, Duration, Segments 자동 기입
4. Status = "Not Started" (기본값)
5. Review Count = 0 (기본값)
6. Notes = 빈 셀
```

### 사용자 편집 필드 보호

- CLI는 Status, Review Count, Notes 컬럼을 **절대 읽거나 수정하지 않는다**
- CLI가 건드리는 건 새 행 추가 시 No ~ Segments까지의 5개 컬럼만
- 기존 행의 어떤 셀도 수정하지 않는다

### 기존 행 존재 확인

- CLI는 _study_log에서 중복 체크를 하지 않는다 (그건 _metadata의 역할)
- _study_log 행 추가는 _metadata 기록 성공 후에만 수행

## 10.5 학습 워크플로우 (사용자 시점)

```
1. CLI로 새 영상 추가
2. Excel 열기 → _study_log에서 "Not Started" 영상 확인
3. 해당 시트로 이동하여 학습
4. 학습 후 Status → "In Progress" 또는 "Completed" 변경
5. 복습할 때마다 Review Count +1
6. 어려웠던 표현을 Notes에 기록
```

## 10.6 _study_log vs _metadata 역할 비교

| 관점 | _metadata | _study_log |
|------|-----------|------------|
| 작성 주체 | CLI 전용 | CLI 초기값 + 사용자 편집 |
| 목적 | 처리 이력, 중복 방지 | 학습 추적, 동기부여 |
| CLI 수정 범위 | 전체 컬럼 | No ~ Segments만 (새 행 추가 시) |
| 사용자 편집 | 금지 | Status, Review Count, Notes 자유 |
| 필터/정렬 | video_id, model 등으로 기술 조회 | Status, Date 등으로 학습 관리 |

---

# 1️⃣1️⃣ Excel 스타일 정책

## 11.1 폰트 설정

### 폰트 선택 로직

Excel은 CSS와 달리 font-family fallback chain을 지원하지 않는다.
셀당 단일 폰트만 지정 가능하므로, CLI 실행 시점에 시스템 폰트를 탐지하여 결정한다.

```
CLI 시작
→ config.yaml에 font 명시 → 해당 폰트 강제 사용
→ config.yaml에 font 미지정 (auto):
  → 시스템에 "Noto Sans KR" 설치 여부 확인
  → 설치됨: font = "Noto Sans KR"
  → 미설치: font = "Malgun Gothic" (Windows 기본)
```

### 폰트 탐지 방법

- `matplotlib.font_manager` 또는 OS별 폰트 디렉토리 스캔
- Windows: `C:\Windows\Fonts` 에서 `NotoSansKR-*.ttf` 존재 확인
- 탐지 실패 시 Malgun Gothic으로 안전하게 fallback
- 선택된 폰트를 CLI 시작 시 표시: `Font: Noto Sans KR (auto-detected)`

### 폰트 크기

| 대상 | 크기 | 비고 |
|------|------|------|
| 헤더 행 | 11pt Bold | 데이터 시트, _metadata, _study_log 공통 |
| 데이터 본문 | 10pt Regular | 밀도와 가독성 균형 |

## 11.2 헤더 스타일

장시간 학습 용도이므로 눈 피로를 최소화하는 연한 톤을 사용한다.

| 속성 | 값 | 사유 |
|------|-----|------|
| 배경색 | `#F2F2F2` (연한 회색) | 눈 피로 최소화 |
| 글자색 | `#333333` (진한 회색) | 흰 배경 대비 부드러운 대비 |
| 굵기 | Bold | 데이터 영역과 시각적 분리 |
| 하단 테두리 | `#BFBFBF` 1pt solid | 헤더-데이터 경계 |

## 11.3 데이터 영역 스타일

| 속성 | 값 |
|------|-----|
| 배경색 | 없음 (흰색) |
| 테두리 | `#E0E0E0` thin (연한 회색, 수평선만) |
| 수직 정렬 | Top (위쪽) |
| 자동 줄바꿈 | On (Wrap Text) |

수직 정렬을 Top으로 고정하는 이유: Wrap Text로 English/Korean이 여러 줄이 될 때,
기본 Bottom 정렬이면 양쪽 시작 위치가 어긋나서 대조 학습이 불편하다.

## 11.4 컬럼 너비 및 정렬

### 데이터 시트 (영상별)

| 컬럼 | 너비 | 정렬 | 포맷 |
|------|------|------|------|
| Index | 7 | 가운데 | 정수 |
| Start | 13 | 가운데 | 텍스트 (`HH:MM:SS.mmm`) |
| End | 13 | 가운데 | 텍스트 (`HH:MM:SS.mmm`) |
| English | 50 | 왼쪽 | 텍스트 |
| Korean | 45 | 왼쪽 | 텍스트 |

### Timestamp 저장 형식

- 형식: `HH:MM:SS.mmm` (예: `00:01:23.456`)
- Excel 셀 서식: **텍스트**로 저장 (숫자/시간 서식 사용 금지)
- 사유: Excel이 시간 값으로 자동 해석하면 밀리초가 손실되거나 포맷이 깨짐

### _metadata 시트

| 컬럼 | 너비 | 정렬 |
|------|------|------|
| video_id | 14 | 왼쪽 |
| video_title | 35 | 왼쪽 |
| video_url | 40 | 왼쪽 |
| channel_name | 20 | 왼쪽 |
| video_duration | 12 | 가운데 |
| sheet_name | 30 | 왼쪽 |
| processed_at | 20 | 가운데 |
| total_segments | 10 | 가운데 |
| filtered_segments | 10 | 가운데 |
| translation_success | 10 | 가운데 |
| translation_failed | 10 | 가운데 |
| model_used | 15 | 왼쪽 |
| tool_version | 12 | 가운데 |

## 11.5 공통 스타일

| 항목 | 설정 |
|------|------|
| Freeze Top Row | 모든 시트 적용 |
| Auto Filter | _metadata, _study_log 시트에 적용 |
| Sheet Tab Color | 데이터 시트: 없음, _metadata: 회색, _study_log: 파랑 |

## 11.6 Conditional Formatting

### 번역 실패 표시 (데이터 시트)

- 조건: Korean 컬럼이 비어 있는 행
- 스타일: 행 전체 배경 `#FFF2F2` (연한 빨간색)
- 사유: 사용자가 Excel을 열었을 때 번역 누락 구간을 즉시 식별

### 학습 미완료 표시 (_study_log 시트)

- 조건: Status 컬럼이 `Not Started`인 행
- 스타일: Status 셀 배경 `#FFF8E1` (연한 노란색)

---

# 1️⃣2️⃣ 오류 처리 종합

## 12.1 전체 파이프라인 Retry 정책

| 단계 | 최대 재시도 | 대기 전략 | 실패 시 동작 |
|------|-----------|-----------|-------------|
| API 키 확인 | 0 | — | 즉시 종료 (설정 안내 메시지) |
| URL 파싱 | 0 | — | 즉시 종료 (사용자 입력 오류) |
| 영상 메타데이터 조회 | 3 | Exponential (1s, 2s, 4s) | 종료 + 네트워크 확인 안내 |
| Master.xlsx 초기화 | 0 | — | 즉시 종료 (파일 시스템 오류) |
| 파일 잠금 사전 검증 | 0 | — | 즉시 종료 (파일 닫기 안내) |
| 자막 목록 조회 | 3 | Exponential (1s, 2s, 4s) | 종료 + 네트워크 확인 안내 |
| 자막 다운로드 | 3 | Exponential (1s, 2s, 4s) | 종료 + 네트워크 확인 안내 |
| VTT 파싱 | 0 | — | 즉시 종료 (데이터 오류) |
| 세그먼트 필터링 | 0 | — | 즉시 종료 (로직 오류) |
| 번역 (배치 단위) | 3 | Exponential (1s, 2s, 4s) + Retry-After 존중 | 해당 배치 Korean 비워두고 계속 |
| Excel 쓰기 | 2 | Fixed (1s) | 종료 + 파일 잠금 확인 안내 |
| Master.xlsx 저장 | 2 | Fixed (1s) | 종료 + 파일 잠금 확인 안내 |
| Study Log 기록 | 2 | Fixed (1s) | 경고 후 계속 (학습 로그 누락은 치명적이지 않음) |

## 12.2 공통 Retry 원칙

- **Exponential Backoff**: 기본 간격 × 2^(시도 횟수 - 1)
- **Jitter**: 각 대기 시간에 0~500ms 랜덤 추가 (API 동시 요청 분산)
- **Retry-After 우선**: HTTP 429 응답의 `Retry-After` 헤더가 있으면 해당 값 사용
- **비 Retryable 오류 즉시 종료**: 400 Bad Request, 401 Unauthorized, 403 Forbidden

## 12.3 네트워크 vs 로직 오류 분류

| 유형 | 예시 | Retry 여부 |
|------|------|-----------|
| 네트워크 오류 | Timeout, Connection Reset, DNS 실패 | O |
| 서버 오류 | 500, 502, 503 | O |
| Rate Limit | 429 | O (Retry-After 대기) |
| 클라이언트 오류 | 400, 401, 403 | X (즉시 종료) |
| 데이터 오류 | 파싱 실패, 포맷 불일치 | X (즉시 종료) |

## 12.4 주요 에러 메시지

### 자막 없음

```
❌ ERROR: No manually uploaded English captions found.
```

### Timestamp 누락

VTT에서 timestamp가 없는 세그먼트 발견 시 즉시 종료한다.

### 필터링 후 세그먼트 0개

```
❌ ERROR: No valid spoken segments remain after filtering.
```

---

# 1️⃣3️⃣ CLI UX 설계

## 13.1 전체 실행 흐름 표시

```
$ yt-excel https://youtube.com/watch?v=xxxx

🔑 API key verified

🔍 Fetching video info...
   Title: How DNA Works
   Channel: TED-Ed
   Duration: 4:52

📝 Checking captions...
   ✅ Manual English captions found

📋 Checking Master.xlsx...
   ✅ File found — structure verified — writable

🔎 Checking duplicates...
   ✅ New video — not processed before

⬇️  Downloading captions...
   ✅ Downloaded (142 cue segments)

🧹 Processing segments...
   Markup stripped: 12 tags removed
   Non-verbal removed: 8 segments
   Short segments removed: 3 segments
   ✅ 131 valid segments remaining

🌐 Translating (gpt-5-nano)...
   ████████████████████████░░░░░░░░  78% (102/131)

   ✅ Translation complete (131 success, 0 failed)

💾 Writing to Master.xlsx...
   Sheet: How DNA Works
   Font: Noto Sans KR (auto-detected)
   ✅ Data sheet saved
   ✅ Metadata updated
   ✅ Study log updated

📊 Summary
   Segments: 131 / 142 original
   Translation: 131 ✅  0 ❌
   Cost: ~$0.0008
   Time: 12.3s
```

## 13.2 Progress Bar 설계

번역 단계에서 progress bar를 표시한다.

- 라이브러리: `rich` (Python)
- 단위: 세그먼트 기준 (배치 내부 세그먼트 수 반영)
- 표시 정보: 퍼센트, 완료/전체 수, 예상 잔여 시간

## 13.3 에러 표시 규칙

| 수준 | 접두사 | 색상 | 용도 |
|------|--------|------|------|
| INFO | `ℹ` | 파랑 | 일반 안내 (이미 처리됨 등) |
| WARNING | `⚠` | 노랑 | 일부 실패, 계속 진행 가능 |
| ERROR | `❌` | 빨강 | 치명적 오류, 종료 |
| SUCCESS | `✅` | 초록 | 단계 완료 |

## 13.4 Verbose 모드

`--verbose` 또는 `-v` 플래그로 상세 로그 출력.

- 기본 모드: 단계별 요약만 표시
- Verbose 모드: 각 세그먼트 처리 상세, API 응답 시간, 제거된 태그 목록 등

## 13.5 Quiet 모드

`--quiet` 또는 `-q` 플래그로 최소 출력.

- 오류와 최종 결과만 표시
- 파이프라인 연동이나 cron 실행 시 활용

## 13.6 CLI 인터페이스 요약

```
사용법:
  yt-excel <YouTube_URL> [옵션]

옵션:
  --master, -m <path>    Master.xlsx 경로 (기본: ./Master.xlsx)
  --model <name>         번역 모델 (기본: gpt-5-nano)
  --verbose, -v          상세 로그 출력
  --quiet, -q            최소 출력
  --dry-run              번역/저장 없이 자막 분석만 수행
  --version              버전 정보
  --help, -h             도움말
```

## 13.7 Dry Run 모드

`--dry-run` 플래그로 실제 번역과 Excel 저장 없이:

- 자막 다운로드 가능 여부 확인
- 세그먼트 필터링 결과 미리보기
- 예상 비용/시간 표시
- API 키 검증을 건너뛴다

번역 API를 호출하지 않으므로 비용 없이 사전 점검 가능.

---

# 1️⃣4️⃣ Config 파일 설계

`config.yaml`로 런타임 파라미터를 관리한다.

```yaml
# 번역 설정
translation:
  model: "gpt-5-nano"          # gpt-5-nano 또는 gpt-5-mini
  batch_size: 10                # 배치당 세그먼트 수
  context_before: 3             # 앞쪽 컨텍스트 세그먼트 수
  context_after: 3              # 뒤쪽 컨텍스트 세그먼트 수
  request_interval_ms: 200      # API 요청 간 최소 대기 (ms)
  max_retries: 3                # 배치별 최대 재시도

# 필터링 설정
filter:
  min_duration_sec: 0.5         # 최소 세그먼트 길이 (초)
  min_text_length: 2            # 최소 텍스트 길이 (문자)

# 파일 설정
file:
  master_path: "./Master.xlsx"  # Master Excel 기본 경로

# 스타일 설정
style:
  font: "auto"                  # auto = Noto Sans KR → Malgun Gothic fallback
                                # 또는 직접 폰트명 지정 (예: "Arial")

# UX 설정
ui:
  default_mode: "normal"        # normal / verbose / quiet
```

API 키는 config.yaml에 저장하지 않는다. 환경 변수 `OPENAI_API_KEY`로만 관리한다.

---

# 확정 사항

**핵심 원칙:**
- English = Source of Truth
- Timestamp는 원본에서만 온다
- 자동 생성 자막 사용하지 않는다
- VTT 세그먼트 그대로 유지 (병합/분리 금지)
- 긴 세그먼트도 분할하지 않는다
- 데이터 무결성 최우선
- LLM은 번역 엔진 역할만 수행한다
- Master Excel은 Immutable Data Layer다

**구현 정책:**
- 자동 생성 자막 감지 시 사용자 친화적 메시지와 함께 종료
- 번역은 gpt-5-nano 기본, config에서 gpt-5-mini로 전환 가능
- Sliding Window 방식으로 문맥 기반 번역
- 시트 이름은 영상 제목만 사용 (31자 이내, 금지 문자 치환), VideoID는 _metadata에서 관리
- _metadata 시트에 13개 필드로 처리 이력 관리
- _study_log 시트로 학습 추적 (시스템 데이터와 사용자 데이터 분리)
- HTML/WebVTT 마크업은 비언어 필터링 이전에 strip
- 단계별 차등화된 retry 정책 (네트워크 계층만 retry)
- Progress bar, Verbose/Quiet 모드, Dry Run 지원
- 폰트 auto-detect (Noto Sans KR → Malgun Gothic fallback)
- 연한 회색 헤더 + Conditional Formatting으로 번역 실패/학습 미완료 시각화
- Master.xlsx 미존재 시 자동 생성, 시트 누락 시 기존 데이터 보존하며 복구
- API 키는 환경 변수로 관리 (.env 파일 지원, 시스템 환경 변수 우선), config.yaml 및 로그에 노출 금지
- 영어 자막 언어 코드는 en 정확 일치 우선, en-* 변종도 수용
- Master.xlsx 파일 잠금 사전 검증으로 API 비용 낭비 방지 (best-effort)
- 번역 응답은 JSON 모드 강제 + 마크다운 블록 fallback strip