---
title: "21 · GitOps와 모델 승격"
outline: deep
prev:
  text: '20 · Queue와 Worker'
  link: '/ml-platform/week05-queue-worker'
next:
  text: '22 · ConfigMap·Secret'
  link: '/ml-platform/week05-config-secrets'
---

# 21 · GitOps로 모델 배포까지 완전히 통제할 수 있을까?

CH11 GitOps: Configuration as Code

## 1. GitOps에서 Git은 무엇의 기준인가?

GitOps는 원하는 시스템 상태를 Git에 선언하고 Controller가 클러스터 실제 상태를 그 선언으로 조정하는 방식이다. 모델 학습 결과까지 전부 Git에 저장한다는 뜻은 아니다.

~~~mermaid
flowchart TD
  A["App Git / CI"] --> B["Container image digest"]
  B --> C["GitOps Repo: Deployment + Model version"]
  C --> D["Flux / Argo CD"]
  D --> E["Kubernetes Deployment"]
  E --> F["Inference Pod"]
  G["Training Job"] --> H["MLflow Runs / Registry"]
  H --> I{"Quality Gate + Approval"}
  I -->|"Approved"| C
  I -->|"Rejected"| J["Keep serving current version"]
  F --> K["Model version in response / metrics"]
~~~

소스 코드 변경은 이미지 빌드·테스트를 거쳐 배포 선언을 바꾸고, 모델 변경은 품질 검증·승인을 거쳐 **고정된 버전**을 배포 선언에 반영하는 구조로 연결할 수 있다.

## GitOps 2계층 아키텍처 · 학습 제어면과 배포 제어면

~~~mermaid
flowchart LR
  subgraph Train["학습·검증 제어면"]
    CODE["Training Code"]
    PIPE["Job / KFP"]
    RUNS[("MLflow Runs")]
    QA{"품질 검증"}
    CODE --> PIPE --> RUNS --> QA
  end
  subgraph Release["배포 선언 제어면"]
    PR["PR · 모델 버전 고정"]
    REVIEW{"승인"}
    REPO[("Git Desired State")]
    RECON["GitOps Reconciler"]
    K8S["Serving Deployment"]
    PR --> REVIEW -->|"승인"| REPO --> RECON --> K8S
  end
  QA -->|"통과한 고정 모델 ID"| PR
  QA -->|"미달"| REJECT["승격 거부"]
  K8S --> CHECK["Readiness / 실제 버전 확인"]
~~~

**GitOps의 배포 성공은 모델 품질 통과와 별개**다. 모델 승인 없이 단순히 레지스트리 alias를 변경해서 서빙 컨테이너가 자동 재로딩되기를 기대하면 운영 상태가 불명확해질 수 있다.

### 선언 상태와 실제 상태가 다를 때

~~~mermaid
sequenceDiagram
  participant G as Git Repository
  participant R as GitOps Reconciler
  participant K as Kubernetes API
  participant O as Operator
  G-->>R: desired replicas=2 / model v17
  R->>K: 매니페스트 적용
  O->>K: kubectl scale replicas=1
  Note over K: Live state diverges
  R->>G: Git 선언 재조회
  R->>K: Reconcile · replicas=2 복원
  Note over K: 복원 동작은 관리 정책·설정에 따름
~~~

이것은 **예상 동작을 설명하는 설계 시퀀스**이며, 실제 Flux·Argo CD 클러스터에서 측정한 기록은 아니다. 자동 수정 여부는 Controller의 reconciliation 및 self-heal 설정, ignore 규칙에 따라 달라질 수 있다.


## 2. Git 안과 밖을 나누기

| 대상 | 기준 시스템 | 판단 근거 |
|---|---|---|
| Deployment / CronJob YAML | Git | 코드 리뷰, 재현, revert |
| Container image digest | Registry + Git 참조 | 불변 배포 확인 |
| 승인한 모델 버전 URI | Registry + Git 참조 | 재시작 후 같은 버전 |
| 데이터 원본·특성 스냅샷 | Dataset/Object Store | 빈번한 변경·대용량 |
| MLflow run, metrics | MLflow | 학습 실행 메타데이터 |
| `champion` alias | MLflow Registry | 가변 참조이므로 감사 로그 필요 |
| Secret 값 | Secret Manager/암호화 저장소 | 키 회전과 접근 제어 |

`MODEL_URI=models:/price-model@champion`은 편리하지만 alias가 바뀌어도 이미 메모리에 적재한 모델이 자동 교체되는 것은 아니다. 또한 Pod가 재시작하는 시점에 따라 서로 다른 모델을 읽을 수 있다.

운영 추적성을 우선한다면 `MODEL_URI=models:/price-model/17`처럼 검증한 고정 버전을 배포 매니페스트에 기록하는 방식을 고려한다. 단, Registry의 모델 아티팩트와 접근 권한도 장기 유지되어야 한다.

## 3. GitOps는 동기화와 품질 평가가 다르다

~~~text
Git Commit → Sync 완료 → Deployment Updated
                               |
                          Pod Ready
                               |
                    실제 모델 버전 일치?
                               |
                    예측 API 정상/품질 확인?
~~~

Controller가 `Synced`와 `Healthy`를 보고하더라도 새 모델이 의미상 적합한지를 보증하지는 않는다. Git revert로 Kubernetes 매니페스트를 되돌릴 수 있어도 이미 처리한 데이터나 외부 Registry alias 변경을 자동으로 복원하지는 않는다.

## 4. 배포 변경의 작은 예시

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: price-predictor
  namespace: mlops-prod
spec:
  replicas: 2
  selector:
    matchLabels:
      app: price-predictor
  template:
    metadata:
      labels:
        app: price-predictor
    spec:
      containers:
        - name: predictor
          image: ghcr.io/example/predictor@sha256:REPLACE_WITH_DIGEST
          env:
            - name: MODEL_URI
              value: "models:/price-model/17"
          readinessProbe:
            httpGet:
              path: /readyz
              port: 8080
~~~

`/readyz`는 단순 프로세스 생존이 아니라 요청 처리 준비가 끝난 상태를 표시해야 한다. 서빙 서비스에서는 모델 로딩, 의존 API 상태, 모델 ID를 구분해서 진단한다.

## 5. 모델 승인 경계에 대한 선택

| 설계 | 장점 | 위험/보완 |
|---|---|---|
| Registry alias를 운영에서 조회 | 데이터 기반 자동 승격 용이 | 언제 새 모델이 로딩되는지 불명확 |
| Git에 모델 버전 고정 | 재현·승인·롤백 감사 용이 | 승격 자동화와 PR 생성 필요 |
| 서빙 중 동적 교체 | 중단 최소화 가능 | 버전 섞임, 동시성, 캐시 정리 복잡 |

GitOps는 기술 도입보다 **승인 주체와 최종 변경 경로를 명확히 하는 정책**에 가깝다.

## 6. 적용 시 확인할 것

~~~bash
kubectl -n mlops-prod rollout status deployment/price-predictor
kubectl -n mlops-prod get deployment price-predictor -o yaml
kubectl -n mlops-prod get pods -l app=price-predictor -o wide
~~~

GitOps Controller의 상태와 애플리케이션이 실제 반환하는 `model_version`을 함께 확인해야 한다. 이 문서는 클러스터 배포 성공을 주장하지 않는다.

## 7. 결론

**GitOps는 운영 상태의 선언과 동기화를 관리한다. 모델 승격은 품질 판단의 문제이므로 두 프로세스를 연결하는 명시적 승인 게이트가 필요하다.**

[5주차 학습 정리](/ml-platform/study-week-05)

참고: [OpenGitOps](https://opengitops.dev/) · [Flux](https://fluxcd.io/) · [Argo CD](https://argo-cd.readthedocs.io/) · [MLflow Model Registry](https://mlflow.org/docs/latest/ml/model-registry/)
