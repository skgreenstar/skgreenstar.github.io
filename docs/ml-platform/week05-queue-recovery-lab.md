---
title: "24 · 실험: Worker 장애와 작업 복구"
outline: deep
prev:
  text: '23 · Job 재시도와 멱등성 실험'
  link: '/ml-platform/week05-idempotency-lab'
next:
  text: 'ML Platform 개요'
  link: '/ml-platform/'
---

# 24 · Worker가 죽으면 가져간 작업은 어디로 갈까?

CH10 Background Processing · 직접 실행한 로컬 큐 복구 실험

## 1. 실험 질문

지난 실험에서는 Job 재시도가 외부 DB에 중복 기록을 만들 수 있음을 확인했다. 이번에는 반대 상황을 다룬다. **Worker가 큐에서 작업을 가져온 직후 프로세스가 종료되면 처리하지 못한 작업을 다시 찾을 수 있을까?**

실제 별도 Python 프로세스를 실행해 `os._exit(17)` 장애를 만들고, 두 가지 소비 방식을 비교했다. Redis 서버나 Kubernetes Job에서 실행한 결과가 아니라 **SQLite의 실제 트랜잭션을 이용해 큐의 수명주기를 모델링한 실험**이다.

## 2. 아키텍처

~~~mermaid
flowchart TD
  A["Ready 작업"] --> B{"소비 방식"}
  B --> C["A · 가져오며 DELETE"]
  B --> D["B · claimed + lease_until"]
  C --> E["DB COMMIT → Worker crash"]
  D --> F["DB COMMIT → Worker crash"]
  E --> G["큐에 작업 없음 → 유실"]
  F --> H["Lease 만료"]
  H --> I["다음 Worker 재획득"]
  I --> J["처리 완료 → ACK / done"]
~~~

- **단순 Dequeue:** 읽고 삭제한 작업은 Worker가 죽어도 큐에 복구할 기록이 남지 않는다.
- **Lease + ACK:** 작업을 곧바로 삭제하지 않고 `claimed`로 표시한다. 제한 시간 내 완료되지 않으면 재획득할 수 있고, 실제 완료 후에만 `done` 처리한다.

## 3. 실제 실험 환경

| 항목 | 설정 |
|---|---|
| 언어 | Python 3.13.5 |
| 상태 저장소 | SQLite + 명시적 COMMIT |
| 장애 재현 | 별도 subprocess에서 `os._exit(17)` |
| 작업 ID | `train-batch-001` |
| Lease TTL | 논리 시간 10 |
| 재시도 시점 | 논리 시각 101, 111 |
| 수행 대상 | Redis·Kubernetes가 아닌 로컬 큐 시뮬레이션 |

논리 시각을 사용하므로 실제 10초를 대기하거나 처리 시간을 측정한 것은 아니다.

## 4. 실행 결과

| 비교 | 단순 Dequeue | Lease + ACK |
|---|---|---|
| 첫 프로세스 | exit 17 | exit 17 |
| 장애 직후 DB | **작업 없음** | claimed, lease_until=110 |
| 즉시 재시도 (101) | exit 3, 작업 없음 | exit 3, Lease 유지 |
| 만료 뒤 재시도 (111) | exit 3, 작업 없음 | exit 0, 처리 완료 |
| 최종 상태 | 작업 유실 | **done, attempts=2** |

같은 스크립트를 두 차례 실행해 assertion이 통과함을 확인했다. 종료 코드 3은 실험 스크립트에서 정의한 '가져올 작업 없음'을 뜻한다.

## 5. 원인과 운영 적용

~~~text
destructive dequeue
  Ready → DELETE + commit → crash → no work

lease + ACK
  Ready → claimed + commit → crash
    → lease expiration → reclaim → done
~~~

Redis List의 `BLPOP` 역시 소비 시 항목을 제거하므로 별도 처리 기록 없이 사용하면 비슷한 유실 위험이 있다. Redis Streams consumer groups의 pending 목록과 ACK·claim은 이를 다룰 수 있지만, 이 실험에서 Redis 명령을 직접 측정한 것은 아니다.

중요한 차이는 **복구 가능성이 정확히 한 번 처리 보장은 아니라는 점**이다. 처리 중 시간이 길어져 Lease가 만료되면 다른 Worker가 동일 작업을 잡을 수 있다. 실제 운영에서는 결과 저장의 멱등성, Lease 갱신, fencing token, 재시도 한도와 DLQ가 필요하다.

## 6. 코드 재현

- [Python 실험 코드](https://github.com/skgreenstar/skgreenstar.github.io/blob/main/docs/ml-platform/week05-queue-recovery/demo.py)
- [실행 결과 JSON](https://github.com/skgreenstar/skgreenstar.github.io/blob/main/docs/ml-platform/week05-queue-recovery/results.json)
- [실험 재현 안내](https://github.com/skgreenstar/skgreenstar.github.io/blob/main/docs/ml-platform/week05-queue-recovery/README.md)

~~~bash
python demo.py
~~~

## 7. 결론

**실행 실패를 다시 시도할 수 있다는 것과, 실패한 작업 자체를 다시 찾을 수 있다는 것은 다르다.** 이번 로컬 실험에서 단순 제거 방식은 작업이 사라졌고, Lease + ACK 방식은 만료 후 재획득해 완료했다.

[5주차 학습 정리](/ml-platform/study-week-05) · [20 · Queue와 Worker](/ml-platform/week05-queue-worker) · [23 · 재시도 중복 저장 실험](/ml-platform/week05-idempotency-lab)
