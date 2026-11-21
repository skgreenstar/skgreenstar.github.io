---
title: "23 · 실험: Job 재시도와 멱등성"
outline: deep
prev:
  text: '22 · 구성과 Secret'
  link: '/ml-platform/week05-config-secrets'
next:
  text: 'ML Platform 개요'
  link: '/ml-platform/'
---

# 23 · Job 재시도 시 결과는 중복 저장될까?

CH10 · Background Processing · 직접 실행한 최소 재현 실험

## 1. 문제 정의

모델 학습이 끝나고 외부 데이터베이스에 메타데이터를 기록한 순간, 컨테이너가 실패한다면 어떻게 될까? Kubernetes Job은 실패한 실행을 재시도할 수 있지만 **이미 DB에 저장된 레코드를 자동으로 되돌리지 않는다.**

이번 실험에서는 별도 프로세스를 실제로 두 번 실행하여 정상 INSERT와 멱등 INSERT를 비교했다. **Kubernetes 클러스터에서 실행한 결과가 아니라, Job 재시도로 인한 중복 부수효과를 로컬 subprocess로 재현한 결과**다.

## 2. 실험 구성

- 환경: Python 3.13.5, SQLite, 표준 라이브러리 `subprocess`, `sqlite3`
- `job_id`: `retrain-2026w05`
- `model_uri`: `models:/price-predictor/17` (실험용 고정 문자열)
- 1차 실행: DB에 `COMMIT`한 직후 `os._exit(17)`로 의도적으로 실패
- 재시도: 동일한 ID로 한 번 더 INSERT한 뒤 `exit 0`
- 조건 A: 일반 INSERT
- 조건 B: `UNIQUE(job_id)` + `ON CONFLICT DO NOTHING`

~~~mermaid
flowchart TD
    A["같은 job_id로 첫 번째 프로세스 실행"] --> B["SQLite INSERT + COMMIT"]
    B --> C["강제 종료: exit 17"]
    C --> D["같은 job_id로 재시도: exit 0"]
    D --> E{"중복 제약 존재?"}
    E -->|"없음"| F["결과 2건: 중복 발생"]
    E -->|"UNIQUE + ON CONFLICT"| G["결과 1건: 중복 방지"]
~~~

## 실험 토폴로지 · 외부 쓰기와 Job 종료는 독립적이다

~~~mermaid
flowchart LR
  RUN["재시도 실행기 · 로컬 subprocess"] --> W1["1차 Worker"]
  W1 -->|"INSERT + COMMIT"| DB[("SQLite DB")]
  W1 -->|"exit 17"| FAIL["실패"]
  FAIL --> W2["2차 Worker"]
  W2 -->|"동일 job_id INSERT"| DB
  DB --> X{"DB 제약"}
  X -->|"일반 INSERT"| TWO["결과 행 2건"]
  X -->|"UNIQUE + 충돌 무시"| ONE["결과 행 1건"]
~~~

이번 실험에서 **실제 구현한 요소는 subprocess, SQLite, COMMIT, 종료 코드**다. Kubernetes Job Controller, MLflow 및 원격 DB는 실험하지 않았다.

### 실행 시퀀스와 커밋 경계

~~~mermaid
sequenceDiagram
  participant O as Local Orchestrator
  participant P1 as Worker 1
  participant DB as SQLite
  participant P2 as Worker 2
  O->>P1: 동일 job_id 실행
  P1->>DB: INSERT
  P1->>DB: COMMIT
  DB-->>P1: 기록 확정
  P1--xO: exit 17
  O->>P2: 같은 job_id 재시도
  P2->>DB: INSERT
  alt UNIQUE 제약 없음
    DB-->>P2: 새 행 추가
  else UNIQUE + ON CONFLICT
    DB-->>P2: 중복 기록 방지
  end
  P2-->>O: exit 0
~~~


## 3. 실제 실행 결과

| 비교 조건 | 첫 실행 종료 코드 | 재시도 종료 코드 | 저장된 결과 건수 |
|---|---:|---:|---:|
| 일반 INSERT | 17 | 0 | **2건** |
| 멱등 INSERT | 17 | 0 | **1건** |

~~~text
naive
  first attempt → commit → exit 17
  retry         → commit → exit 0
  SELECT COUNT(*) WHERE job_id = 'retrain-2026w05' → 2

idempotent
  first attempt → commit → exit 17
  retry         → conflict ignored → exit 0
  SELECT COUNT(*) WHERE job_id = 'retrain-2026w05' → 1

assertions_passed = true
~~~

실험은 로컬에서 두 차례 동일 시나리오로 실행했고, 각 차례의 검증 조건을 모두 통과했다. 실제 기록과 실행 가능한 코드는 아래에 남겼다.

- [실험 코드 demo.py](https://github.com/skgreenstar/skgreenstar.github.io/blob/main/docs/ml-platform/week05-lab/demo.py)
- [실행 결과 results.json](https://github.com/skgreenstar/skgreenstar.github.io/blob/main/docs/ml-platform/week05-lab/results.json)
- [실험 재현 안내 README](https://github.com/skgreenstar/skgreenstar.github.io/blob/main/docs/ml-platform/week05-lab/README.md)

~~~bash
# GitHub 저장소에서 실행
cd docs/ml-platform/week05-lab
python demo.py
~~~

## 4. 왜 중복 실행이 발생할까?

Job 컨트롤러는 종료 코드와 성공 완료 횟수를 기준으로 작업을 관리한다. 외부 DB에 기록한 결과가 유효한지, 이미 같은 기록이 존재하는지까지 알지는 못한다.

~~~text
프로세스 종료 = 실패
DB 트랜잭션 = 이미 성공적으로 COMMIT

두 상태는 독립적이므로 재시도 시 데이터 중복 가능
~~~

`UNIQUE(job_id)`는 이번 실험처럼 동일 ID의 **결과 기록**이 중복되지 않게 한다. 하지만 모델 학습 자체의 재수행, 아티팩트 중복 업로드, 다른 API 호출까지 정확히 한 번 처리한다는 보장은 아니다.

## 5. 실제 ML 플랫폼에서는 무엇을 더 해야 할까?

| 계층 | 위험 | 방어 방법 |
|---|---|---|
| Job 재시도 | 동일 실행 여러 번 | 명시적 run_id와 retry 횟수 |
| 결과 DB | 동일 결과 여러 건 | 고유 키, 원자적 UPSERT |
| Artifact Store | 중복 파일·불일치 | 임시 경로 후 원자적 확정 전략 |
| MLflow Registry | 중복 모델 등록 | 승인·승격 단계의 상태 검증 |
| 외부 알림 / API | 중복 요청 | API idempotency key 지원 여부 확인 |
| CronJob | 같은 스케줄 겹침 | concurrencyPolicy + 애플리케이션 잠금 |

학습 결과 품질 검증까지 포함하려면 단순히 Job이 `Complete`인지 보는 대신 별도의 `quality_status`와 `promotion_status`를 확인하는 것이 안전하다.

## 6. 실험 한계와 후속 확장

이 환경에는 Docker, kind, kubectl이 없어 실제 Job 컨트롤러의 스케줄링·재시도·Pod 수명은 측정하지 못했다. 대신 **실패한 실행의 외부 부수효과가 재시도 후 어떻게 남는지**를 실제 subprocess와 SQLite로 검증했다.

후속 실험에서는 kind 클러스터에 동일한 스크립트를 Job으로 제출하고 `backoffLimit`, `restartPolicy`와 PVC/DB 기록을 비교할 수 있다. CronJob의 `Forbid`가 수동 Job과 중복 실행을 막지는 않는지도 확인할 수 있다.

## 7. 결론

**Kubernetes가 실패한 Job을 다시 실행하는 것과, 외부 시스템의 데이터를 정확하게 유지하는 것은 별개의 문제다.** 이번 로컬 실험에서는 동일 작업의 재시도가 일반 INSERT에서 2건의 중복 기록을 만들었고, 고유 키 기반 멱등 처리에서 1건만 남겼다.

[5주차 학습 정리](/ml-platform/study-week-05) · [19 · Job과 CronJob](/ml-platform/week05-job-cronjob)
