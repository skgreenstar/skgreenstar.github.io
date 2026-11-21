---
title: "5주차 · CH10~11 백그라운드 작업과 GitOps"
outline: deep
prev:
  text: '4주차 학습 정리'
  link: '/ml-platform/study-week-04'
next:
  text: '19 · Job·CronJob'
  link: '/ml-platform/week05-job-cronjob'
---

# 5주차 · Job이 성공했다고 ML 파이프라인도 성공한 걸까?

CH10 Background Processing · CH11 GitOps: Configuration as Code

Kubernetes에서 모델 학습을 실행하는 것은 어렵지 않다. 하지만 시간이 걸리는 학습 요청을 API에서 분리하고, 중복 실행을 막고, 실패를 복구하고, 승인되지 않은 모델이 운영에 배포되지 않게 만드는 것은 서로 다른 문제다. 이번 주는 **실행의 성공, 결과의 유효성, 운영 반영의 승인**을 분리해서 살펴본다.

> 핵심 질문: Job의 `Complete` 상태가 곧 '서비스 가능한 모델'이라는 뜻일까? 아니다. 컨테이너가 정상 종료했다는 것과 데이터·품질·승격 조건을 만족했다는 것은 다르다.

## 1. 학습 범위와 읽는 순서

| 챕터 | 주요 개념 | 이번 주 핵심 질문 |
|---|---|---|
| CH10 | Background Processing, Deployment Worker, Queue | 응답과 장기 작업을 왜 분리할까? |
| CH10 | Job, CronJob, Parallelism, Retry | 동일한 작업이 다시 실행되면 안전할까? |
| CH11 | GitOps, 선언형 구성, Reconciliation | Git에 무엇을 저장하고 무엇을 남겨둘까? |
| CH11 | Namespace, ConfigMap, Secret | 환경과 권한, 설정을 어떻게 분리할까? |

교재 범위를 따라가되, Redis 작업 큐의 구현 자체보다 **처리 보장·멱등성·작업 수명**에 초점을 맞춘다. GitOps는 '모든 실행 결과를 Git에 넣는 방식'이 아니라 변경 가능한 운영 환경의 선언 상태를 관리하는 방법으로 이해한다.

## 2. 전체 구조: 요청·실행·승격은 서로 다르다

~~~mermaid
flowchart TD
    A["사용자 또는 일정 트리거"] --> B{"작업 유형?"}
    B -->|"정해진 일회성 작업"| C["Kubernetes Job"]
    B -->|"정기 실행"| D["CronJob → Job"]
    B -->|"지속적 비동기 요청"| E["Queue → Worker Deployment"]
    C --> F["Training / Validation"]
    D --> F
    E --> F
    F --> G{"품질 및 데이터 검증"}
    G -->|"미달"| H["실패 또는 승격 거부 기록"]
    G -->|"충족"| I["MLflow Registry 모델 버전"]
    I --> J["배포 승인 및 고정 버전 선택"]
    K["Git: 코드 / 이미지 / 매니페스트"] --> L["GitOps Controller"]
    L --> M["Kubernetes 서빙 환경"]
    J --> M
    M --> N["Readiness / 버전 확인 / 운영 검증"]
~~~

Job 컨트롤러는 프로세스 종료 코드를 본다. 반면 ML 파이프라인 품질 게이트는 데이터 스키마, 기준 지표, 후보 모델, 실제 서빙 버전까지 봐야 한다. **'실행되었다', '검증되었다', '운영 중이다'는 반드시 다른 상태로 취급한다.**

## 3. CH10 · Background Processing

### 19. Job과 CronJob: 실패와 중복 실행의 경계

[19 · Job은 성공했는데 결과가 잘못될 수도 있을까?](/ml-platform/week05-job-cronjob)

Job은 종료 조건이 정해진 배치에 적합하고, CronJob은 지정된 시각에 Job을 생성한다. `backoffLimit`, `parallelism`, `completions`, `concurrencyPolicy`, `startingDeadlineSeconds`의 작동 범위를 구별한다. Job 재시도는 정확히 한 번 실행을 보장하지 않는다.

### 20. Queue와 Worker: 중복 작업과 복구

[20 · Redis Queue로 학습 작업을 처리하면 무엇이 달라질까?](/ml-platform/week05-queue-worker)

Deployment는 지속적으로 작업을 소비하는 Worker에 적합하다. `RPUSH`와 `BLPOP` 예제는 간단하지만, Pop 후 처리 전에 Worker가 죽으면 작업을 잃을 수 있다. 처리 확인, 재전달, 멱등 키와 Dead Letter Queue를 함께 설계해야 한다.

## 4. CH11 · GitOps

### 21. GitOps: 설정 배포와 모델 승격 사이

[21 · GitOps로 모델 배포까지 완전히 통제할 수 있을까?](/ml-platform/week05-gitops)

Git이 관리하기 좋은 것은 매니페스트·이미지 digest·정책·승인된 모델 버전이다. 학습 결과, 메트릭 시계열, 레지스트리 alias 상태, 실행 이력은 외부 시스템에 남는다. 자동 승격과 Git 기반 고정 버전 배포는 어느 쪽도 무조건 정답이 아니라 **승격 책임이 어디에 있는지** 결정하는 선택이다.

### 22. 구성과 비밀정보: 운영 실수를 방지하는 경계

[22 · Namespace와 Secret만 분리하면 안전할까?](/ml-platform/week05-config-secrets)

Namespace는 리소스 이름과 운영 범위를 나누지만 강한 보안 경계 자체는 아니다. RBAC, NetworkPolicy, ResourceQuota, Admission 정책, Secret 암호화·회전, GitOps 권한을 같이 설계해야 한다.

## 5. 운영 상태를 어떻게 정의할까?

| 계층 | 성공 신호 | 추가 확인 |
|---|---|---|
| Kubernetes Job | Complete 조건 | 실행한 입력·버전, 결과 검증 |
| 학습 파이프라인 | Validation 통과 | 데이터 계보, 오염 여부, 기준 모델 |
| Registry | 모델 등록 | 승인된 버전·재현 가능한 아티팩트 |
| GitOps | Synced | Healthy, Ready, 실제 모델 버전 |
| Inference API | HTTP 정상 | 샘플 예측, 품질, p95/p99, 오류율 |

예를 들어 품질 기준 미달을 Python에서 단순 `return`으로 처리하면 Job은 성공으로 끝날 수 있다. 승격 거부를 정상적인 비즈니스 결과로 기록하되, 파이프라인의 성공·실패 기준을 명시적으로 관리하는 편이 좋다.

## 6. 이번 주 설계 과제

1. 정기 재학습은 CronJob, 수동 재학습은 Job, 요청 기반 작업은 Queue/Worker로 설계하고 각 이유를 설명한다.
2. 동일한 `dataset_hash + training_config + code_revision` 조합에 대해 재시도를 안전하게 처리할 멱등 키와 결과 저장 규칙을 정한다. 의도적인 재학습 실행은 별도 `run_id`로 추적한다.
3. 모델 승인 경계와 배포 반영 경계를 구분하고, GitOps가 관장할 파일·레지스트리 상태를 명시한다.
4. 권한·환경별 설정·민감정보를 분리하고 장애 시 복구 경로를 문서화한다.

### 확인할 명령어

~~~bash
kubectl get cronjobs,jobs,pods -n mlops
kubectl describe cronjob retrain -n mlops
kubectl get events -n mlops --sort-by=.lastTimestamp
kubectl logs job/retrain-manual -n mlops --all-containers
kubectl auth can-i create jobs -n mlops
~~~

위 명령어는 **환경에 해당 리소스가 존재할 경우** 사용한다. 이 문서에는 실행하지 않은 결과를 실제 검증값처럼 기재하지 않는다.

## 7. 결론

CH10은 **작업 실행·재시도·수명**에 대한 질문이고, CH11은 **운영 변경의 출처·검토·복원**에 대한 질문이다. 이 둘을 연결하려면 모델 품질을 확인하는 별도의 게이트가 필요하다.

**Kubernetes는 작업 실행을 관리하고, ML 시스템은 결과의 적합성을 판단하며, GitOps는 승인한 운영 상태를 반복적으로 맞춘다.** 세 책임을 섞지 않는 것이 이번 주의 핵심이다.

참고: [Kubernetes Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/) · [CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/) · [GitOps Principles](https://opengitops.dev/) · [Kubernetes ConfigMap](https://kubernetes.io/docs/concepts/configuration/configmap/) · [Kubernetes Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
