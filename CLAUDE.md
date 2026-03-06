# CLAUDE.md

> 이 프로젝트에 기여하는 AI 어시스턴트와 개발자가 반드시 숙지해야 할 전역 컨벤션 및 프로젝트 컨텍스트.

---

## 프로젝트 개요

YouTube 영상의 수동 영어 자막을 다운로드하고, 한국어로 번역하여 Master Excel 파일에 누적 저장하는 CLI 도구.
영어 리스닝/쉐도잉 학습을 위한 개인 데이터베이스 구축이 목적이다.

---

## 기술 스택

- **런타임**: Python 3.12+
- **패키지 매니저**: uv
- **핵심 의존성**: yt-dlp, openpyxl, openai, rich, pyyaml, python-dotenv
- **번역 모델**: OpenAI gpt-5-nano (기본) / gpt-5-mini (대체)
- **대상 OS**: Windows 11 (개발자 주 환경), Linux/macOS 호환 고려

---

## 프로젝트 구조

```
yt-excel/
├── pyproject.toml
├── config.yaml
├── .env                   # API 키 보관 (gitignore 대상)
├── .env.example           # 필요한 환경 변수 안내 (커밋 대상)
├── CLAUDE.md              # 이 파일
├── README.md
├── logs/                  # 실행 로그 (gitignore 대상, 자동 생성)
├── docs/
│   ├── youtube_master_excel_cli_design_final.md   # 설계 문서
│   └── Roadmap.md                                  # 구현 로드맵
├── src/
│   └── yt_excel/
│       ├── __init__.py
│       ├── cli.py          # CLI 엔트리포인트, 파이프라인 오케스트레이션
│       ├── config.py       # config.yaml 로딩, 기본값 관리
│       ├── environment.py  # API 키 검증 (.env 로딩 + 환경 변수 확인)
│       ├── logger.py       # 파일 로그 시스템 (logging 설정, 핸들러)
│       ├── youtube.py      # URL 파싱, 메타데이터 조회, 자막 다운로드
│       ├── vtt.py          # VTT 파싱, 마크업 strip, 세그먼트 정제
│       ├── translator.py   # Sliding Window 배치 번역 (동기 + 비동기)
│       ├── excel.py        # Excel 읽기/쓰기, 스타일, 초기화, 무결성 검증
│       └── retry.py        # 공통 retry 데코레이터/유틸리티
└── tests/
    ├── __init__.py
    ├── fixtures/
    ├── test_youtube.py
    ├── test_vtt.py
    ├── test_translator.py
    └── test_excel.py
```

각 모듈은 단일 책임을 가진다. 모듈 간 순환 의존을 만들지 않는다.

---

## 핵심 설계 원칙 (위반 금지)

아래 6가지 원칙은 코드의 모든 결정에 우선한다. 편의성을 위해 이 원칙을 타협하지 않는다.

1. **English = Source of Truth** — 영어 텍스트가 모든 데이터의 기준이다.
2. **Timestamp는 원본에서만 온다** — VTT 원본 timestamp를 어떤 이유로도 수정/재계산하지 않는다.
3. **자동 생성 자막은 사용하지 않는다** — auto-caption 감지 시 무조건 종료한다.
4. **데이터 무결성 > 학습 편의성** — 데이터를 깨뜨리는 편의 기능은 추가하지 않는다.
5. **LLM은 번역 엔진 역할만 수행한다** — LLM에게 데이터 구조 변경, 세그먼트 병합/분리 등을 시키지 않는다.
6. **Master Excel은 Immutable Data Layer다** — 한번 기록된 데이터 시트의 셀은 CLI가 수정하지 않는다.

---

## Python 코딩 컨벤션

### 스타일

- PEP 8 준수
- 들여쓰기: 4 spaces (탭 금지)
- 최대 줄 길이: 100자
- 문자열: 큰따옴표(`"`) 기본 사용 — f-string, 딕셔너리 키, 일반 문자열 모두
- import 순서: stdlib → third-party → local (각 그룹 사이 빈 줄)

### 네이밍

| 대상 | 규칙 | 예시 |
|------|------|------|
| 모듈 | snake_case | `youtube.py`, `vtt.py` |
| 함수 | snake_case | `parse_vtt()`, `download_captions()` |
| 클래스 | PascalCase | `TranslationEngine`, `ExcelWriter` |
| 상수 | UPPER_SNAKE_CASE | `MAX_RETRIES`, `BATCH_SIZE` |
| 비공개 | `_` 접두사 | `_strip_markup()`, `_validate_response()` |

### 타입 힌트

- 모든 함수 시그니처에 타입 힌트 작성
- 반환값이 None인 함수도 `-> None` 명시
- 복잡한 타입은 `typing` 또는 `collections.abc`에서 import
- 데이터 전달 객체는 `dataclass` 또는 `TypedDict` 사용

```python
# Good
def parse_vtt(content: str) -> list[Segment]:
    ...

def download_captions(video_id: str, lang_code: str) -> str | None:
    ...

# Bad
def parse_vtt(content):
    ...
```

### dataclass 활용

파이프라인 단계 간 데이터 전달에는 dataclass를 사용한다. dict를 직접 전달하지 않는다.

```python
@dataclass
class Segment:
    index: int
    start: str      # "HH:MM:SS.mmm"
    end: str        # "HH:MM:SS.mmm"
    english: str
    korean: str = ""

@dataclass
class VideoMeta:
    video_id: str
    title: str
    channel: str
    duration: str   # "HH:MM:SS"
```

### docstring

- 모듈, 클래스, 공개 함수에 docstring 작성
- Google 스타일 docstring 사용
- 내부 구현 함수(`_` 접두사)는 한 줄 설명만으로 충분

```python
def strip_markup(text: str) -> str:
    """VTT/HTML 마크업을 제거하고 순수 텍스트만 반환한다.

    Args:
        text: VTT cue 텍스트 (태그 포함 가능).

    Returns:
        태그와 엔티티가 제거된 순수 텍스트.
    """
```

---

## 에러 처리 패턴

### 원칙

- 예외는 발생 지점에서 가장 가까운 곳에서 처리한다.
- 각 모듈은 자신의 에러를 적절히 변환하여 상위로 전달한다.
- `cli.py`(최상위)에서 최종 에러 메시지를 사용자에게 표시한다.
- bare `except:` 또는 `except Exception:` 남용 금지 — 구체적인 예외만 잡는다.

### 커스텀 예외 계층

```python
class YtExcelError(Exception):
    """모든 프로젝트 예외의 기본 클래스."""

class CaptionNotFoundError(YtExcelError):
    """수동 영어 자막이 없는 경우."""

class AutoCaptionOnlyError(YtExcelError):
    """자동 생성 자막만 존재하는 경우."""

class DuplicateVideoError(YtExcelError):
    """이미 처리된 영상인 경우."""

class FileLockError(YtExcelError):
    """Master.xlsx가 잠겨 있는 경우."""

class TranslationError(YtExcelError):
    """번역 배치 실패 (retry 소진 후)."""
```

### retry 패턴

`retry.py`에 공통 retry 로직을 구현한다. 각 모듈에서 retry 로직을 중복 작성하지 않는다.

```python
# 사용 예시 (개념)
@with_retry(max_retries=3, backoff="exponential", retryable=(TimeoutError, ConnectionError))
def fetch_metadata(video_id: str) -> VideoMeta:
    ...
```

---

## 로깅 및 CLI 출력

### 출력 규칙

- CLI 출력에는 `rich` 라이브러리를 사용한다.
- `print()` 직접 호출 금지 — 반드시 프로젝트 내 출력 유틸리티를 통해 출력한다.
- 로그 수준별 접두사:

| 수준 | 접두사 | 용도 |
|------|--------|------|
| SUCCESS | ✅ | 단계 완료 |
| INFO | ℹ | 일반 안내 |
| WARNING | ⚠ | 일부 실패, 계속 진행 |
| ERROR | ❌ | 치명적 오류, 종료 |

### 출력 모드

- `normal`: 단계별 요약 (기본)
- `verbose` (`-v`): 각 세그먼트 상세, API 응답 시간
- `quiet` (`-q`): 오류와 최종 결과만

현재 모드에 따라 출력을 필터링한다. 모듈 내부에서 출력 모드를 직접 판단하지 않고, 출력 유틸리티가 모드를 관리한다.

### 보안

- API 키는 환경 변수(`OPENAI_API_KEY`)로 관리한다. `python-dotenv`로 `.env` 파일 로딩을 지원한다.
- 로딩 우선순위: 시스템 환경 변수 우선 → `.env` fallback (`override=False`).
- `.env` 파일은 `.gitignore`에 포함하여 절대 커밋하지 않는다.
- API 키를 config.yaml, 로그, 에러 메시지에 절대 포함하지 않는다 (verbose 모드 포함).

---

## Excel 관련 규칙

### openpyxl 사용 시 주의사항

- 셀에 Timestamp를 쓸 때 반드시 셀 서식을 텍스트(`@`)로 설정한 후 문자열로 기입한다.
- 숫자처럼 보이는 문자열도 텍스트 서식을 명시한다 (Excel 자동 변환 방지).
- 시트 이름은 반드시 sanitize 후 사용한다 (31자 제한, 금지 문자 치환).

### 스타일 상수

스타일 값은 `excel.py` 상단에 상수로 정의한다. 매직 넘버를 코드 중간에 넣지 않는다.

```python
# 색상
HEADER_BG = "F2F2F2"
HEADER_FG = "333333"
BORDER_COLOR = "E0E0E0"
HEADER_BORDER_COLOR = "BFBFBF"
FAIL_ROW_BG = "FFF2F2"
NOT_STARTED_BG = "FFF8E1"

# 폰트
FONT_SIZE_HEADER = 11
FONT_SIZE_BODY = 10

# 컬럼 너비
COL_WIDTH_INDEX = 7
COL_WIDTH_TIMESTAMP = 13
COL_WIDTH_ENGLISH = 50
COL_WIDTH_KOREAN = 45
```

### 시트 쓰기 순서

1. 데이터 시트 생성 + 데이터 기입
2. 스타일 적용
3. _metadata 행 추가
4. _study_log 행 추가
5. 저장

이 순서를 반드시 지킨다. 스타일 적용 전에 저장하면 Conditional Formatting이 누락될 수 있다.

---

## 번역 관련 규칙

### API 호출

- OpenAI Python SDK (`openai` 패키지)를 사용한다.
- `response_format: { type: "json_object" }` 를 항상 명시한다.
- 시스템 프롬프트에 반환 형식(JSON array, 정확히 N개)을 명확히 지정한다.
- 요청 간 최소 200ms 간격을 둔다 (config로 조정 가능).

### 응답 파싱

1. JSON 모드 응답을 먼저 시도한다.
2. 실패 시 마크다운 코드 블록(` ```json ... ``` `)을 strip한 후 재시도한다.
3. 파싱 성공 후 배열 길이를 검증한다.

### 비용 의식

- 불필요한 API 호출을 하지 않는다.
- `--dry-run` 모드에서는 절대 API를 호출하지 않는다.
- 번역 전에 파일 잠금을 사전 검증하여 비용 낭비를 방지한다.

---

## 테스트 컨벤션

### 구조

- 테스트 파일은 `tests/` 디렉토리에 `test_<모듈명>.py`로 생성한다.
- `pytest`를 사용한다.
- 테스트 함수명: `test_<기능>_<시나리오>` 패턴.

```python
def test_parse_vtt_removes_markup_tags():
    ...

def test_parse_vtt_handles_empty_segment():
    ...

def test_sanitize_sheet_name_truncates_at_31_chars():
    ...
```

### 외부 의존성 격리

- YouTube API/yt-dlp 호출은 mock 처리한다.
- OpenAI API 호출은 mock 처리한다.
- 파일 시스템 테스트는 임시 디렉토리(`tmp_path` fixture)를 사용한다.
- 실제 API를 호출하는 통합 테스트는 별도 마커(`@pytest.mark.integration`)로 분리한다.

### 테스트 데이터

- VTT 샘플 파일은 `tests/fixtures/` 디렉토리에 보관한다.
- 테스트용 VTT는 실제 YouTube VTT에서 추출한 다양한 패턴을 포함해야 한다:
  - 기본 텍스트
  - `<c>` word-level timing
  - `<v>` 화자 태그
  - `[Music]` 비언어 텍스트
  - HTML 엔티티 (`&amp;`, `&#39;`)
  - 다중 라인 텍스트

---

## Git 컨벤션

### 커밋 단위

**기능 단위로 커밋한다.** "이 커밋을 revert하면 하나의 독립된 기능이 깨끗하게 빠진다"가 기준이다.

- ❌ 함수 단위 (너무 작음) — 개별 커밋만 봐서는 뭘 완성한 건지 알 수 없다.
- ❌ Phase 단위 (너무 큼) — 되돌릴 지점이 없고, 며칠간 커밋 없이 작업하게 된다.
- ✅ 기능 단위 — 함수 여러 개가 모여 하나의 완결된 기능을 이루는 단위.

**Phase 3 예시 (VTT 파싱 + 세그먼트 처리):**

```
feat: add VTT parser with timestamp extraction
feat: add HTML/WebVTT markup stripper
feat: add non-verbal text filter
feat: add short segment filter
test: add VTT parser unit tests with fixture files
```

**테스트 커밋 정책:**

- 기능 커밋에 테스트를 함께 포함하거나, 바로 다음 커밋으로 분리한다.
- 테스트 없는 기능 커밋이 여러 개 쌓인 후 테스트를 몰아서 넣지 않는다.

### 커밋 메시지

Conventional Commits 형식을 따른다.

```
<type>: <subject>

<body (optional)>
```

| type | 용도 |
|------|------|
| `feat` | 새 기능 |
| `fix` | 버그 수정 |
| `refactor` | 리팩토링 (기능 변경 없음) |
| `test` | 테스트 추가/수정 |
| `docs` | 문서 변경 |
| `style` | 코드 포맷팅 (기능 변경 없음) |
| `chore` | 빌드, 의존성, 설정 변경 |

```
feat: add VTT markup stripper with HTML entity decoding
fix: handle en-US language code in caption detection
test: add edge case tests for 31-char sheet name truncation
docs: update design doc with file lock pre-validation
```

### 브랜치

**브랜치 전략: feature → dev → main**

main에 직접 커밋하지 않는다. 반드시 기능 브랜치 → dev → main 순서를 거친다.

```
main (안정 — 직접 커밋 금지)
  └── dev (통합 — 기능 검증 후 main에 merge)
        ├── feat/logging-system
        ├── feat/async-translation
        └── fix/batch-retry-timeout
```

| 브랜치 | 역할 | merge 규칙 |
|--------|------|------------|
| `main` | 안정 버전, 배포 가능 상태 | dev에서만 merge, 직접 커밋 금지 |
| `dev` | 개발 통합, 기능 검증 | feat/fix 브랜치에서 merge |
| `feat/<설명>` | 새 기능 개발 | 기능 완료 + 테스트 통과 후 dev에 merge |
| `fix/<설명>` | 버그 수정 | 수정 완료 + 테스트 통과 후 dev에 merge |

**워크플로우:**

```
1. dev에서 기능 브랜치 생성
   git checkout dev
   git checkout -b feat/logging-system

2. 기능 브랜치에서 기능 단위 커밋
   (구현 + 테스트 함께)

3. dev에 merge
   git checkout dev
   git merge feat/logging-system

4. dev에서 통합 테스트 확인
   uv run pytest

5. 문제 없으면 main에 merge
   git checkout main
   git merge dev
```

---

## 참조 문서

| 문서 | 위치 | 설명 |
|------|------|------|
| 설계 문서 (Final) | `docs/youtube_master_excel_cli_design_final.md` | 전체 설계 명세 |
| v1.1 개선 설계 | `docs/v1.1_improvement_design.md` | 로그 시스템 + 비동기 번역 설계 |
| 구현 로드맵 | `docs/Roadmap.md` | Phase별 구현 계획 및 완료 조건 |
| 이 파일 | `CLAUDE.md` | 코딩 컨벤션 및 전역 규칙 (프로젝트 루트) |

설계 문서와 이 파일의 내용이 충돌할 경우, **설계 문서가 우선**한다.

---

## 자주 하는 실수 방지

- ❌ VTT timestamp를 파싱 후 재계산하지 않는다 — 원본 문자열 그대로 사용.
- ❌ Excel 셀에 timestamp를 숫자/시간 서식으로 저장하지 않는다 — 반드시 텍스트.
- ❌ `_metadata` 시트의 기존 행을 수정하지 않는다 — 새 행 추가만.
- ❌ `_study_log` 시트의 Status/Review Count/Notes 컬럼을 CLI에서 읽거나 쓰지 않는다.
- ❌ 자동 생성 자막을 어떤 경우에도 다운로드하지 않는다.
- ❌ config.yaml에 API 키를 저장하지 않는다 — 환경 변수 또는 `.env` 파일 사용.
- ❌ `.env` 파일을 Git에 커밋하지 않는다 — `.gitignore`에 반드시 포함.
- ❌ bare `except:` 로 모든 예외를 삼키지 않는다.
- ❌ 시트 이름을 sanitize 없이 사용하지 않는다.
- ❌ `print()` 를 직접 호출하지 않는다 — 출력 유틸리티 사용.
- ❌ main 브랜치에 직접 커밋하지 않는다 — 반드시 feat → dev → main 순서.
- ❌ 로그 파일에 API 키를 기록하지 않는다.