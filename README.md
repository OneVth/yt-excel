# yt-excel

YouTube 영상의 수동 영어 자막을 다운로드하고, 한국어로 번역하여 Master Excel 파일에 누적 저장하는 CLI 도구입니다.
영어 리스닝/쉐도잉 학습을 위한 개인 데이터베이스 구축을 목적으로 합니다.

## 주요 기능

- YouTube URL에서 **수동 업로드된 영어 자막**만 자동 감지 및 다운로드 (자동 생성 자막 거부)
- VTT 파싱 — HTML/WebVTT 마크업 제거, 비언어 텍스트(`[Music]` 등) 필터링, 짧은 세그먼트 제거
- OpenAI API를 활용한 **Sliding Window 배치 번역** (컨텍스트 기반 고품질 한국어 번역)
- **Master.xlsx**에 영상별 시트로 누적 저장 — 메타데이터 및 학습 로그 자동 관리
- 원본 timestamp 100% 보존, 세그먼트 병합/분리 없음
- 중복 영상 자동 감지, 파일 잠금 사전 검증
- `--dry-run` 모드로 번역 없이 비용 추정 가능

## 요구 사항

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (패키지 매니저)
- OpenAI API 키

## 설치

```bash
# 저장소 클론
git clone https://github.com/OneVth/yt-excel.git
cd yt-excel

# 의존성 설치
uv sync
```

## 설정

### API 키

`.env.example`을 복사하여 `.env` 파일을 만들고 OpenAI API 키를 입력합니다.

```bash
cp .env.example .env
```

```
OPENAI_API_KEY=sk-xxxxxxxxxxxx
```

> 시스템 환경 변수에 `OPENAI_API_KEY`가 설정되어 있으면 `.env`보다 우선 적용됩니다.

### config.yaml

번역, 필터링, 파일 경로, 스타일, UI 모드를 설정할 수 있습니다.

```yaml
translation:
  model: "gpt-5-nano"          # gpt-5-nano 또는 gpt-5-mini
  batch_size: 10                # 배치당 세그먼트 수
  context_before: 3             # 앞쪽 컨텍스트 세그먼트 수
  context_after: 3              # 뒤쪽 컨텍스트 세그먼트 수
  request_interval_ms: 200      # API 요청 간 최소 대기 (ms)
  max_retries: 3                # 배치별 최대 재시도

filter:
  min_duration_sec: 0.5         # 최소 세그먼트 길이 (초)
  min_text_length: 2            # 최소 텍스트 길이 (문자)

file:
  master_path: "./Master.xlsx"  # Master Excel 기본 경로

style:
  font: "auto"                  # auto = Noto Sans KR → Malgun Gothic fallback

ui:
  default_mode: "normal"        # normal / verbose / quiet
```

## 사용법

```bash
# 기본 사용
yt-excel "https://www.youtube.com/watch?v=VIDEO_ID"

# 옵션
yt-excel "URL" --master ./output/Master.xlsx   # Excel 경로 지정
yt-excel "URL" --model gpt-5-mini              # 번역 모델 변경
yt-excel "URL" --verbose                       # 상세 로그 출력
yt-excel "URL" --quiet                         # 최소 출력
yt-excel "URL" --dry-run                       # 번역 없이 분석만 (비용 추정)
```

### 파이프라인 흐름

```
URL 입력 → API 키 검증 → 메타데이터 조회 → 자막 확인 → Master.xlsx 검증
→ 자막 다운로드 → VTT 파싱/필터링 → 번역 → Excel 저장 → 요약 출력
```

## Excel 출력 구조

### 데이터 시트 (영상별)

| Index | Start | End | English | Korean |
|-------|-------|-----|---------|--------|
| 1 | 00:00:01.200 | 00:00:03.500 | Hello everyone | 안녕하세요 여러분 |
| 2 | 00:00:03.500 | 00:00:06.100 | Welcome to my channel | 제 채널에 오신 것을 환영합니다 |

### _metadata 시트

처리된 모든 영상의 메타데이터를 기록합니다 (Video ID, Title, Channel, Duration, 번역 통계 등).

### _study_log 시트

학습 진도 추적을 위한 시트입니다 (Status, Review Count, Notes 컬럼은 사용자가 직접 관리).

## 개발

### 테스트

```bash
# 전체 테스트 실행
uv run pytest

# 특정 모듈 테스트
uv run pytest tests/test_vtt.py

# 상세 출력
uv run pytest -v
```

현재 336개의 테스트가 포함되어 있으며, 외부 API 호출은 모두 mock 처리됩니다.

### 프로젝트 구조

```
yt-excel/
├── src/yt_excel/
│   ├── cli.py          # CLI 엔트리포인트, 파이프라인 오케스트레이션
│   ├── config.py       # config.yaml 로딩, 기본값 관리
│   ├── environment.py  # API 키 검증
│   ├── youtube.py      # URL 파싱, 메타데이터 조회, 자막 다운로드
│   ├── vtt.py          # VTT 파싱, 마크업/비언어 제거, 필터링
│   ├── translator.py   # Sliding Window 배치 번역
│   ├── excel.py        # Excel 읽기/쓰기, 스타일, 무결성 검증
│   └── retry.py        # 공통 retry 데코레이터
├── tests/              # pytest 기반 유닛/통합 테스트 (336개)
├── docs/               # 설계 문서, 로드맵
├── config.yaml         # 기본 설정
└── pyproject.toml      # 프로젝트 메타데이터, 의존성
```

### 기술 스택

| 구분 | 기술 |
|------|------|
| 런타임 | Python 3.12+ |
| 패키지 매니저 | uv |
| 자막 다운로드 | yt-dlp |
| Excel 처리 | openpyxl |
| 번역 | OpenAI API (gpt-5-nano / gpt-5-mini) |
| CLI 출력 | rich |
| 설정 관리 | PyYAML, python-dotenv |

## 라이선스

이 프로젝트는 개인 학습 도구로 개발되었습니다.
