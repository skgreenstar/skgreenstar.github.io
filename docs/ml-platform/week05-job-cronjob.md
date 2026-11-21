---
title: "19 · Job과 CronJob의 실행 보장"
outline: deep
prev:
  text: '5주차 학습 정리'
  link: '/ml-platform/study-week-05'
next:
  text: '20 · Queue와 Worker'
  link: '/ml-platform/week05-queue-worker'
---

# 19 · Job은 성공했는데 결과가 잘못될 수도 있을까?

CH10 Background Processing · Job / CronJob

## 1. Deployment와 Job의 차이

| 워크로드 | 원하는 상태 | 어울리는 작업 |
|---|---|---|
| Deployment | 지정한 Pod 수를 계속 유지 | API 서버, 큐 소비자 |
| Job | 정해진 완료 횟수 달성 | 데이터 전처리, 모델 학습 |
| CronJob | 일정에 따라 Job 생성 | 정기 배치, 재학습 |

Job의 `Complete`는 성공적으로 종료한 Pod 실행 횟수의 조건을 뜻하며, 모델 검증 결과까지 보장하지 않는다.

~~~mermaid
flowchart LR
    A["CronJob Schedule"] --> B["Job 생성"]
    B --> C["Pod 실행"]
    C --> D{"종료 코드"}
    D -->|"비정상"| E["재시도 정책"]
    E --> C
    D -->|"정상"| F["Job Complete"]
    F --> G{"모델 품질 게이트"}
    G -->|"통과"| H["Registry 후보 등록"]
    G -->|"거부"| I["승격 제외 / 사유 기록"]
~~~

## 2. Job 핵심 필드

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: retrain-manual
  namespace: mlops
spec:
  completions: 1
  parallelism: 1
  backoffLimit: 2
  activeDeadlineSeconds: 3600
  ttlSecondsAfterFinished: 86400
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: trainer
          image: ghcr.io/example/ml-trainer@sha256:REPLACE_WITH_DIGEST
          command: ["python", "-m", "pipeline.train"]
          env:
            - name: DATASET_VERSION
              value: "dataset-2026-11"
          resources:
            requests:
              cpu: "500m"
              memory: "1Gi"
            limits:
              memory: "2Gi"
~~~

`REPLACE_WITH_DIGEST`는 실제 이미지 digest로 바꿔야 한다. `activeDeadlineSeconds`는 전체 Job 실행 시간 상한이며, `ttlSecondsAfterFinished`는 완료 후 Job 오브젝트 정리다. 결과 데이터 보존 정책을 대신하지 않는다.

`parallelism`은 동시에 실행할 Pod의 상한, `completions`는 필요한 성공 완료 횟수다. `backoffLimit`은 실패 재시도를 제한한다. 프로세스가 외부 DB에 결과를 쓴 뒤 오류로 종료하면 재시도가 동일한 데이터를 다시 쓸 수 있다.

## 3. CronJob에서 주의할 점

~~~yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: retrain
  namespace: mlops
spec:
  schedule: "0 2 * * 1"
  timeZone: "Asia/Seoul"
  concurrencyPolicy: Forbid
  startingDeadlineSeconds: 1800
  successfulJobsHistoryLimit: 2
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      backoffLimit: 2
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: trainer
              image: ghcr.io/example/ml-trainer@sha256:REPLACE_WITH_DIGEST
              command: ["python", "-m", "pipeline.train"]
~~~

| 설정 | 의미 | 주의 |
|---|---|---|
| Allow | 겹치는 Job도 생성 가능 | 동시 모델 등록 충돌 |
| Forbid | 이전 Job 진행 중 새 일정 건너뜀 | 놓친 실행이 자동 순차 처리되는 큐는 아님 |
| Replace | 기존 Job을 대체 | 중간 checkpoint·결과 정합성 |
| startingDeadlineSeconds | 시작이 늦어진 일정 허용 구간 | 컨트롤러 지연과 missed schedule 고려 |

CronJob은 일반적인 정확히 한 번 실행 보장을 제공하지 않는다. 같은 예정 시각에 여러 Job이 생성되거나 Job이 누락되는 경우를 고려해 **각 실행을 멱등하게 설계**해야 한다. `Forbid`도 서로 다른 CronJob이나 수동 Job끼리의 동시 실행을 막지는 않는다.

## 4. 모델 결과와 실행 결과를 분리

~~~text
job_status = Complete
quality_status = Rejected
promotion_status = NotPromoted
serving_version = unchanged
~~~

품질 거부가 예상된 업무 결과라면 이를 구조화된 결과 파일에 기록하고 KFP/상위 워크플로가 읽게 한다. 반대로 검증 필수 단계 자체가 수행되지 못했다면 실행 실패로 처리해야 한다. 모든 모델 평가 미달을 컨테이너 오류와 같은 것으로 표현하지 않는다.

## 5. 운영 확인 순서

~~~bash
kubectl get jobs -n mlops -o wide
kubectl describe job retrain-manual -n mlops
kubectl get pods -n mlops -l job-name=retrain-manual
kubectl get events -n mlops --sort-by=.lastTimestamp
kubectl logs job/retrain-manual -n mlops
~~~

원인 분리는 Pending(스케줄러/볼륨), ImagePullBackOff(이미지·인증), OOMKilled(메모리), non-zero exit(애플리케이션), Complete 이후 품질 거부(모델 검증) 순으로 한다.

## 6. 설계 결론

**Job은 계산을 끝내는 컨트롤러이지 모델을 승인하는 컨트롤러가 아니다.** 완료 조건과 품질 게이트, 결과 저장, 재시도 멱등성을 분리해야 한다.

[5주차 학습 정리](/ml-platform/study-week-05)

참고: [Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/) · [CronJobs](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)
