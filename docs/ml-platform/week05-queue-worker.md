---
title: "20 · Queue와 Worker의 멱등성"
outline: deep
prev:
  text: '19 · Job·CronJob'
  link: '/ml-platform/week05-job-cronjob'
next:
  text: '21 · GitOps와 모델 승격'
  link: '/ml-platform/week05-gitops'
---

# 20 · Redis Queue로 학습 작업을 처리하면 무엇이 달라질까?

CH10 Background Processing · Deployment / Redis Queue

## 1. 왜 요청과 실행을 분리할까?

모델 학습을 HTTP 요청 안에서 직접 끝내려고 하면 클라이언트 연결의 수명이 작업 실행 시간에 종속된다. API는 요청을 검증하고 작업 ID를 반환하며, Worker는 별도의 생명주기로 실행한다.

~~~mermaid
flowchart LR
    A["Client"] --> B["FastAPI"]
    B --> C[("Job DB")]
    B --> D[("Redis Queue")]
    D --> E["Worker Deployment"]
    E --> F["학습 / 추론 작업"]
    F --> G[("Artifacts / MLflow")]
    E --> C
    B --> H["202 + job_id"]
~~~

API가 작업을 DB에 적재하고 큐에 넣는 두 단계 사이에서 실패할 수 있다. DB와 메시지 브로커 간 원자성이 없기 때문에 운영 환경에서는 transactional outbox 또는 reconciliation 처리를 검토해야 한다.

## 2. Redis RPUSH / BLPOP의 의미

~~~bash
redis-cli RPUSH ml-tasks '{"job_id":"train-001","dataset":"v3"}'
redis-cli BLPOP ml-tasks 0
~~~

`RPUSH`는 오른쪽에 적재하고 `BLPOP`은 왼쪽에서 꺼낸다. 기본 예제는 이해하기 쉽지만, `BLPOP` 직후 메시지가 큐에서 사라진다. Worker가 처리 전에 죽으면 별도 복구 장치 없이는 재처리가 불가능하다.

~~~text
Ready Queue → Worker Pop → Training
                     |
                  Worker Crash
                     |
             작업 유실 가능 (기본 BLPOP)
~~~

운영에서는 Redis Streams consumer groups 및 `XACK`/pending reclaim, 또는 검증된 작업 큐 솔루션을 고려한다. Redis를 쓴다고 작업의 내구성이나 정확히 한 번 처리가 자동 보장되지는 않는다.

## 3. 멱등성 키와 요청 추적

~~~python
import hashlib
import json

def work_key(dataset_version: str, model_config: dict, code_sha: str) -> str:
    payload = {
        "dataset": dataset_version,
        "config": model_config,
        "code": code_sha,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()
~~~

이 값은 동일 조건의 작업 중복 감지에 사용할 수 있다. 다만 실험적으로 여러 번 학습할 목적이라면 `run_id`를 별도로 만들어 각 실행을 보존한다. 결정론이 보장되지 않는 학습 결과가 무조건 동일하다고 가정해서는 안 된다.

일반적인 상태 흐름은 `QUEUED → RUNNING → SUCCEEDED / FAILED / CANCELLED`이며, 품질 검증과 모델 승격은 별도의 상태 필드로 관리한다. Worker가 종료되었는데 DB에 RUNNING이 남으면 heartbeat와 lease 만료를 보고 복구한다.

## 4. 어디에 어떤 워크로드를 사용할까?

| 요구사항 | 권장 기본 구조 | 이유 |
|---|---|---|
| 정해진 데이터 배치 1회 | Job | 완료·실패 조건 명료 |
| 매주 정기 학습 | CronJob | 시각 기반 실행 |
| 빈번한 비동기 작업 | Queue + Worker Deployment | 작업 생산·소비 분리 |
| 사용자별 자원 격리 학습 | Queue + Job 생성 제어기 | 요청별 CPU/GPU·수명 정책 |
| 복잡한 다단계 학습 | KFP/워크플로 엔진 | DAG·아티팩트·단계 재시도 |

한 요청당 Kubernetes Job을 생성하면 격리는 좋지만 API Server 오브젝트 수, 스케줄링 비용, 정리 정책을 관리해야 한다. 초당 짧은 작업이 수천 개라면 Queue Worker 쪽이 적합할 수 있다.

## 5. 장애 대응 체크

1. 작업이 **대기 중**인지, 소비되었는지, 실제 실행 중인지 구분한다.
2. 적어도 한 번 전달 모델이라면 **중복 실행 가능성**을 전제로 결과 쓰기를 설계한다.
3. 재시도 횟수·지수 백오프·영구 실패 저장소(DLQ)를 구분한다.
4. 모델 파일을 임시 Pod 디스크에만 남기지 않고 외부 저장소에 버전별 저장한다.
5. 사용자에게 작업 ID와 진행 상태를 제공하되 API의 202 응답을 결과 성공으로 표시하지 않는다.

## 6. 실제 검증 · Worker가 큐에서 작업을 가져온 직후 죽으면?

[24 · Worker 장애와 작업 복구 실험](/ml-platform/week05-queue-recovery-lab)에서 별도 프로세스를 `exit 17`로 중단해 작업 유실과 Lease 기반 회복을 비교했다. 단순 제거 방식은 작업을 복원하지 못했으며, Lease·ACK 방식은 만료 이후 재시도에 성공했다. SQLite 기반 로컬 시뮬레이션이며 Redis 서버를 직접 측정한 결과는 아니다.

## 7. 결론

**큐를 추가하면 요청 지연 문제는 줄일 수 있지만 작업 유실·중복·결과 정합성을 새로 책임져야 한다.** Worker 수와 재시도 횟수뿐 아니라 처리 확인 시점과 상태 저장 경계를 설계해야 한다.

[5주차 학습 정리](/ml-platform/study-week-05)

참고: [Kubernetes Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/) · [Redis Streams](https://redis.io/docs/latest/develop/data-types/streams/) · [Redis Lists](https://redis.io/docs/latest/develop/data-types/lists/)
