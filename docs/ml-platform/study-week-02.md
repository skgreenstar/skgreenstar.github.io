---
title: "2주차 · CH4~5 Kubernetes 운영 자동화와 리소스 관리"
description: "Health Probe, Rolling Update, Requests/Limits와 QoS를 직접 재현하는 MLOps 스터디"
date: 2026-11-01
outline: deep
prev:
  text: '1주차 · ML 시스템의 기반'
  link: '/ml-platform/study-week-01'
next: false
---

# 2주차 · CH4~5 Kubernetes 운영 자동화와 리소스 관리

> **학습 방식:** 핵심 개념 → 동작 구조 → 가설 → kind 실습 → 관찰/해석. 아래의 출력은 *예상 동작*이며, 직접 측정한 결과와 구분한다.

::: tip 이번 주 학습 목표
- Startup / Readiness / Liveness Probe의 역할을 구분하고 장애를 재현한다.
- RollingUpdate·Recreate의 가용성 차이를 검증하고 롤백한다.
- CPU·Memory Requests/Limits, QoS와 자원 경합을 관찰한다.
- AI 모델 서빙에 적용할 때의 설계 선택을 설명한다.
:::

## 전체 운영 구조

![Kubernetes 운영 구조](/diagrams/week02-architecture.svg)

| 설정 | 핵심 질문 | Kubernetes 동작 |
|---|---|---|
| startupProbe | 초기화가 끝났는가? | 성공 전 liveness/readiness 검사 지연, 지정 횟수 실패 시 재시작 |
| readinessProbe | 지금 트래픽을 받을 수 있는가? | 실패 시 Service의 정상 Endpoint에서 제외 |
| livenessProbe | 현재 컨테이너를 재시작해야 하는가? | 연속 실패 임계값 충족 시 컨테이너 재시작 |
| requests | 어디에 배치할 수 있는가? | Scheduler의 자원 적합성 판단 기준 |
| limits | 얼마나 쓸 수 있는가? | CPU quota 기반 제어, Memory 초과 시 OOM 가능 |

## 실습 환경 준비

Docker, kind, kubectl이 필요하다. 실습 파일은 같은 저장소의 [week-02-lab](./week-02-lab/README.md)에 정리했다.

```bash
kind create cluster --name ml-platform-week02
kubectl cluster-info --context kind-ml-platform-week02
kubectl create namespace week02
kubectl get nodes -o wide
```

## Chapter 4. Automated Operations — 운영 자동화

### 1. 헬스체크를 왜 나누는가?

- **Startup**: 모델 로딩·DB 초기 연결처럼 시작이 오래 걸릴 때 조기 재시작을 막는다.
- **Readiness**: 컨테이너가 실행 중이라도 DB·모델 가중치·초기 캐시가 준비되지 않았다면 트래픽을 차단한다.
- **Liveness**: 애플리케이션 내부가 회복 불가한 상태라면 재시작한다. 외부 DB 장애만으로 실패하도록 만들면 연쇄 장애를 유발할 수 있다.

![Health Probe 동작](/diagrams/week02-probes.svg)

### 2. Probe 실습: 정상 상태 → 트래픽 중단 → 장애

실습 코드와 Deployment를 배포한다.

```bash
kubectl apply -f docs/ml-platform/week-02-lab/01-app.yaml
kubectl -n week02 rollout status deployment/probe-demo --timeout=120s
kubectl -n week02 get pods,svc,endpoints -o wide
kubectl -n week02 port-forward svc/probe-demo 8080:80
```

별도 터미널에서:

```bash
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/healthz
curl -i http://localhost:8080/traffic-off
kubectl -n week02 get endpoints probe-demo -w
curl -i --max-time 3 http://localhost:8080/
```

**주의:** Service를 통한 요청에서 readiness 실패를 유도하면 Pod가 Endpoint에서 빠져 이후 `/traffic-on`에 접근하지 못할 수 있다. `kubectl -n week02 exec deploy/probe-demo -- ...` 로 내부 상태를 바꾸거나 Pod에 직접 port-forward한 후 복구한다.

```bash
kubectl -n week02 exec deploy/probe-demo -- wget -qO- http://127.0.0.1:8080/traffic-on
kubectl -n week02 get endpoints probe-demo -w
kubectl -n week02 exec deploy/probe-demo -- wget -qO- http://127.0.0.1:8080/server-error
kubectl -n week02 get pods -w
kubectl -n week02 describe pod -l app=probe-demo
```

**관찰할 항목:** Ready 전환 시점, Endpoint 주소 변화, Restart Count, Events의 `Unhealthy`, `Killing`. 단일 replica에서는 readiness 실패 중 요청이 불가능할 수 있다.

### 3. RollingUpdate vs Recreate

![Deployment 배포 전략 비교](/diagrams/week02-deploy.svg)

| 전략 | 장점 | 비용·위험 |
|---|---|---|
| RollingUpdate | 단계적으로 교체, Ready 확인 가능 | 신·구 버전 동시 호환 필요 |
| Recreate | 리소스 여유가 적고 버전 공존이 어려울 때 단순 | 서비스 공백 발생 가능 |
| Blue/Green | 신규 환경 검증 후 빠른 절체·복귀 | 별도 Deployment/라우팅 관리 및 이중 자원 필요 |

`maxSurge`: desired replicas를 초과하여 만들 수 있는 Pod 수. **백분율은 올림**.  
`maxUnavailable`: 업데이트 동안 가용하지 않아도 되는 Pod 수. **백분율은 내림**.

예: replicas=4, maxSurge=2, maxUnavailable=1이면 최대 Pod 6개, 최소 가용 Pod 3개가 설정상 경계다.

```yaml
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxSurge: 1
    maxUnavailable: 0
```

```bash
kubectl -n week02 set image deployment/probe-demo app=nginx:1.27-alpine
kubectl -n week02 rollout status deployment/probe-demo
kubectl -n week02 rollout history deployment/probe-demo
kubectl -n week02 rollout undo deployment/probe-demo
```

::: warning 실습 주의
위 이미지 변경은 *의도적으로 호환되지 않는 예*다. 기존 app의 포트·Probe 경로와 nginx가 일치하지 않아 rollout이 정상 완료되지 않을 수 있다. 실제 검증에서는 **동일 API를 제공하는 v2 이미지를 제작**하여 업데이트하고, 잘못된 이미지로 인한 실패는 별도 장애 실험으로 구분하자.
:::

### 4. 기록 표

| 테스트 | 예상 현상 | 실제 관찰 |
|---|---|---|
| Startup 실패 | Liveness/Readiness 동작 보류, 반복 실패 시 재시작 | 실행 후 기록 |
| Readiness 실패 | Service Endpoint 제외 | 실행 후 기록 |
| Liveness 실패 | 임계값 이후 컨테이너 재시작 | 실행 후 기록 |
| RollingUpdate | Ready 신규 Pod 기준 교체 | 실행 후 기록 |
| Recreate | 기존 Pod 종료 후 새 버전 시작 | 실행 후 기록 |

## Chapter 5. Resource Management — 리소스 관리

### 1. Scheduler와 Requests/Limits

Scheduler는 Pod에 선언한 resource **requests**와 Node의 allocatable·이미 예약된 requests를 바탕으로 배치 가능 여부를 결정한다. Limit은 런타임 제어 기준이며 스케줄링 예약량과 다르다.

```yaml
resources:
  requests:
    cpu: 200m
    memory: 250Mi
  limits:
    cpu: 300m
    memory: 400Mi
```

CPU 1000m는 1 CPU에 해당한다. CPU는 경합·한도에 따라 실행 시간이 제한될 수 있지만 메모리는 동일 방식으로 압축되지 않아 OOM으로 이어질 수 있다.

### 2. QoS와 Eviction

| QoS | 조건(일반적인 Pod 수준) | 의미 |
|---|---|---|
| Guaranteed | 모든 컨테이너 CPU·Memory request=limit 지정 | 자원 압박 시 비교적 높은 보호 |
| Burstable | 위 조건은 아니지만 request/limit 존재 | 자원 경합과 사용량에 따라 축출 가능 |
| BestEffort | CPU·Memory request/limit 없음 | 자원 압박 시 먼저 축출될 가능성 |

Node-pressure Eviction은 Priority, Requests 초과 사용 여부, 상대 사용량 등을 고려한다. QoS만으로 모든 축출 순서가 결정되는 것은 아니다. PriorityClass의 `preemptionPolicy: Never`는 **선점을 금지**하지만 높은 우선순위의 스케줄링 순서 자체를 포기하는 것은 아니다.

### 3. CPU Throttling 및 OOM 실습

```bash
kubectl apply -f docs/ml-platform/week-02-lab/02-cpu-stress.yaml
kubectl apply -f docs/ml-platform/week-02-lab/03-memory-oom.yaml
kubectl -n week02 get pods -w
kubectl -n week02 top pods
kubectl -n week02 describe pod cpu-stress
kubectl -n week02 describe pod memory-oom
```

`kubectl top`은 Metrics Server가 설치되어 있어야 한다. 최소 kind 클러스터에서 작동하지 않으면 `kubectl describe`·컨테이너 cgroup 통계·재시작 이벤트를 활용한다. **Memory OOM은 실제 할당 패턴과 노드 환경에 따라 재현 여부가 달라질 수 있다.**

### 4. CPU Overcommit / Replica × Worker

![Replica 및 Worker 분산 비교](/diagrams/week02-replica.svg)

복제본 증가가 무조건 좋은 것은 아니다. 프로세스 시작·모델 가중치·캐시가 Pod마다 중복될 수 있다. 특히 vLLM·GPU 모델 서빙에서는 **가중치 메모리 중복 비용**까지 고려해야 한다.

CPU overcommit은 request를 실제 피크보다 낮게 설정해 더 많은 Pod를 배치하는 방법이다. 유휴 시간이 긴 웹 워크로드에는 유효할 수 있지만 동시 부하 시 레이턴시 변동성이 커질 수 있다. CPU limit 미설정은 throttling을 완화할 수 있으나 **클러스터 격리·공정성 정책 검토 후** 적용해야 한다.

### 5. Rightsizing 실험 기록

| 단계 | CPU 사용 | Memory 사용 | p95 latency | Restart / OOM |
|---|---|---|---|---|
| 초기화 | 실측 | 실측 | 해당 없음 | 실측 |
| 정상 부하 | 실측 | 실측 | 실측 | 실측 |
| 피크 부하 | 실측 | 실측 | 실측 | 실측 |
| 설정 변경 후 | 실측 | 실측 | 실측 | 실측 |

관찰한 워크로드 특성에 따라 CPU request를 조정하고, Memory는 정상 부하의 장기 최대값과 누수·스파이크를 고려한다. 특정 블로그의 **Memory request=limit, CPU request만 설정** 패턴을 모든 워크로드에 적용하는 것은 피한다.

## 직접 실행한 기록 — FastAPI 로컬 기준선

::: tip 실험 상태
**실제로 실행한 범위:** FastAPI/Uvicorn HTTP Health Check와 동시 요청 부하 테스트  
**아직 실행하지 않은 범위:** Docker/kind의 Pod, CPU Throttling, OOMKilled, RollingUpdate, Kubernetes Endpoint 변화
:::

### 실험 환경 및 목적

실습 환경은 로컬 Python 3.13/Uvicorn 서버다. Docker·kind·kubectl·k6가 없는 실행 환경에서 Kubernetes를 사용하지 않고, 먼저 **애플리케이션의 초기 상태와 CPU 연산량별 HTTP 응답 특성**을 측정했다.

| 항목 | 실행 조건 |
|---|---|
| 측정 기록 시각 | 2026-11-01 05:24 KST |
| 클라이언트 | HTTP 병렬 요청, 동시성 8 |
| 부하 조건 | 연산 반복 20K / 120K / 300K |
| 각 조건 요청 | 100건, 1회 측정 |
| 관찰 지표 | 성공 건수, RPS, p50/p95/p99 |
| 원본 데이터 | [실제 측정 JSON](https://github.com/skgreenstar/skgreenstar.github.io/blob/main/docs/ml-platform/week-02-advanced/results/local-baseline-2026-11-01.json) |

### 실험 A. 서버는 살아 있지만 트래픽 준비가 안 된 경우

`READY_DELAY=2`로 초기화 지연을 부여하고 `/healthz`와 `/readyz`를 요청했다.

| 요청 시점 | Endpoint | 실제 응답 | 해석 |
|---|---|---|---|
| 초기화 지연 중 | `/healthz` | **200 OK** | 프로세스는 살아 있음 |
| 초기화 지연 중 | `/readyz` | **503** | 트래픽 수신 준비 미완료 |
| 초기화 지연 이후 | `/readyz` | **200 OK** | 트래픽 수신 가능한 상태 |

이 실험은 **애플리케이션 레벨의 응답 상태**를 검증한 것이다. Kubernetes Service가 실제 Endpoint를 제거하는 과정은 아직 측정하지 않았다.

### 실험 B. 요청당 계산량과 Tail Latency

요청당 CPU 연산량만 변경하고 요청 수와 동시성은 고정했다.

| 연산 횟수 | 성공 | 처리량 | p50 | p95 | p99 |
|---:|---:|---:|---:|---:|---:|
| 20,000 | 100/100 | 608.37 RPS | 12.69ms | 16.46ms | 19.14ms |
| 120,000 | 100/100 | 130.56 RPS | 58.45ms | 76.60ms | 97.84ms |
| 300,000 | 100/100 | 56.39 RPS | 137.67ms | 208.59ms | 254.56ms |

![실제 로컬 측정: 연산량에 따른 p95·p99](/diagrams/week02-local-measured.svg)

**관찰 결과:** 연산량이 20K에서 300K로 증가할 때 처리량은 608.37 → 56.39 RPS로 줄고, p95 지연은 16.46 → 208.59ms로 늘었다. 기준선 실험에서는 요청 실패가 없었다.

**원인에 대한 해석:** 요청당 수행하는 CPU 연산이 늘어난 것이 직접적인 변화 조건이다. 그러나 CPU Limit 변경이나 cgroup throttling을 실험하지 않았으므로 **CPU Throttling의 결과로 해석하면 안 된다.**

**한계:** 단일 실행·100요청 기준이므로 실행 환경 노이즈, 워밍업, 반복 측정, 신뢰구간은 검증하지 않았다. 이후 kind 환경에서 동일한 API·동일한 부하를 실행해 Kubernetes resource limit의 차이를 비교해야 한다.

## 운영 가설을 검증하는 심화 실험

기존 Probe·Deployment·Requests/Limits 실습은 기능 이해를 위한 **기초 검증**으로 두고, 실제 학습의 중심은 성능과 운영 안정성을 비교하는 세 가지 실험에 둔다.

**실행 코드:** [FastAPI + k6 + 분석 스크립트](https://github.com/skgreenstar/skgreenstar.github.io/tree/main/docs/ml-platform/week-02-advanced) · [실습 가이드](https://github.com/skgreenstar/skgreenstar.github.io/blob/main/docs/ml-platform/week-02-advanced/README.md)

### 1. CPU 제한이 Tail Latency에 미치는 영향

가설: CPU-bound 요청을 처리할 때 낮은 CPU Limit은 CPU Throttling과 Tail Latency 증가로 이어질 수 있다.

- **독립 변수:** CPU limits = 250m / 500m / (확장 실험: 1000m / 제한 없음)
- **통제 변수:** 동일 API 이미지·RPS·Replica·요청 작업량·시험 시간, 워밍업
- **종속 변수:** p50·p95·p99, 처리량, 오류율, dropped iterations, throttling 비율
- **실험 프로토콜:** 각 조건 3회 이상 반복하고 변인 순서를 교차한다. 컨테이너 cgroup 또는 Prometheus의 throttling 계측과 k6 지연시간을 비교한다.

```bash
k6 run -e RATE=30 -e DURATION=60s \
  --summary-export results/cpu250-run1.json \
  docs/ml-platform/week-02-advanced/loadtest.js
python docs/ml-platform/week-02-advanced/analyze.py results/*.json
```

::: info 검증 포인트
CPU 사용률이 높다는 사실만으로 Throttling을 입증할 수 없다. CPU quota가 설정된 환경에서 실제 throttled periods 또는 시간 증가를 확인해야 한다.
:::

### 2. 무중단 배포에서 사용자가 실제로 경험한 실패는?

가설: Deployment rollout 성공 여부와 사용자 관측 오류율은 다를 수 있다.

정상 트래픽을 계속 보낸 상태에서 새로운 Pod의 초기화 지연을 유도하고 `maxSurge`·`maxUnavailable`를 조정한다.

- **측정:** 배포 시작·완료 시각, 요청 실패율, p95/p99, Endpoint 변화
- **분석:** readiness 통과 시점, 종료 중 연결 처리, 자원 부족으로 인한 Pod Pending 여부
- **비교:** `maxUnavailable: 0`과 `1`, 준비 시간 0초와 8초

```bash
# 첫 번째 터미널: 부하
k6 run -e RATE=30 -e DURATION=180s \
  --summary-export results/rollout.json \
  docs/ml-platform/week-02-advanced/loadtest.js
# 두 번째 터미널: rollout
kubectl -n week02 set env deploy/performance-api READY_DELAY=8
kubectl -n week02 rollout status deploy/performance-api
```

### 3. Replicas 증가가 장애 내성을 얼마나 개선할까?

같은 요청률에서 Replica 2개와 4개를 비교하고 Pod 하나가 사라졌을 때 남은 처리 용량, 오류율, 회복시간을 살펴본다.

![Pod 분산과 장애 영향 비교](/diagrams/week02-replica.svg)

현재 배포 이미지는 worker 1개이므로 Replica 비교 결과는 **동일 총 Worker 비교가 아님**을 명시한다. 총 Worker를 고정하는 비교는 Pod당 uvicorn worker 수도 바꾸는 후속 실험으로 구분한다.

### 4. 자동 분석 산출물

```text
results/
├── cpu250-run1.json
├── cpu500-run1.json
├── rollout.json
├── replicas2.json
├── replicas4.json
└── summary.csv     # analyze.py가 생성
```

| 측정 항목 | 질문 | 판정 기준 |
|---|---|---|
| p95/p99 | CPU 제한 또는 배포 중 꼬리 지연이 악화됐는가? | 동일 부하 조건에서 비교 |
| HTTP 실패율 | rollout 중 사용자 오류가 발생했는가? | 시간대별·조건별 비교 |
| RPS / dropped iterations | 목표 부하를 실제로 만들었는가? | k6 생성기 한계 확인 |
| CPU throttling | 실제 CPU quota 제어가 발생했는가? | cgroup/Prometheus 별도 수집 |
| 회복시간 | 장애 이후 정상 처리량으로 복귀했는가? | 장애 주입 시각을 기록 |

**현재 상태:** 재현용 코드와 측정 자동화는 저장소에 반영했지만, 실습을 실제 kind 클러스터에서 수행한 측정값은 아직 없다. 따라서 숫자를 임의로 기입하거나 가상의 그래프를 실측으로 표시하지 않는다.

## KServe와 vLLM: ML 모델을 서비스로 운영하는 방법

앞서 다룬 Probe, Deployment, Requests/Limits는 웹 애플리케이션뿐 아니라 **ML·LLM 모델 서빙**에도 그대로 중요하다. 다만 모델 서버에는 일반 웹 서비스와 다른 특성이 있다. 모델 파일을 메모리나 GPU에 적재해야 하고, 긴 추론 요청을 처리하며, 응답 지연이 토큰 수와 캐시 상태에 크게 영향을 받는다.

### 1. Model Serving이란?

모델 학습이 끝나면 가중치 파일이나 직렬화된 모델 아티팩트를 얻는다. **Serving은 이 모델을 메모리에 올리고, 요청을 받아 전처리 → 추론 → 후처리 → 응답하는 지속 실행 서비스로 만드는 과정**이다.

```text
Training / Registry
      │ 검증된 모델 버전
      ▼
Model Artifact Storage ── 모델 로딩 ──► Inference Server
                                             ▲
Client → API Gateway → Service / Routing ───┘
                                             │
                                      Prediction / Tokens
                                             │
                                     Logs · Metrics · Traces
```

학습에서는 재현성과 모델 품질이 핵심이라면, 서빙에서는 요청 성공률, 지연시간, 처리량, 자원 사용량, 업데이트 중 가용성이 중요하다. 코드가 정상이더라도 **모델을 다운로드하지 못하면 준비되지 않은 서비스**라는 점이 일반적인 HTTP API와 다르다.

### 2. KServe란 무엇인가?

**KServe는 Kubernetes 위에서 머신러닝 추론 서비스를 배포하고 관리하는 오픈소스 모델 서빙 플랫폼**이다. 기본 Kubernetes에서는 Deployment·Service·HPA·스토리지 연결을 개발자가 조합해야 한다. KServe는 모델 중심의 선언적 리소스를 추가하여 배포·실행 환경·트래픽 관리 등 반복 작업을 표준화한다.

KServe를 이해하려면 두 영역을 구분해야 한다.

| 구분 | 의미 | 실제 역할 |
|---|---|---|
| Control Plane | 어떤 모델을 어떻게 운영할지 결정 | InferenceService 해석, Pod 및 네트워크 리소스 관리 |
| Data Plane | 실제 사용자의 추론 요청 처리 | Predictor, Transformer, 모델 서버 |
| InferenceService | '이 모델을 이 설정으로 제공해줘'라는 선언 | 모델 URI·리소스·런타임 선택 등 |
| ServingRuntime | 어떤 이미지로 모델을 실행할지 정의 | 예: MLServer, Triton 또는 사용자 정의 런타임 |
| LLMInferenceService | 대규모 LLM을 위한 특화 리소스 | GPU 기반 LLM 운영, 라우팅, 분리형 서빙 등 |

**동작 흐름:** 사용자가 InferenceService를 생성하면 KServe Controller가 스펙을 감시하고, 실행 모드에 맞게 Deployment, Service 등의 Kubernetes 리소스를 구성한다. Pod가 모델을 적재한 뒤 준비 상태가 되면 트래픽을 받는다. 사용자는 일반적인 웹 서버 배포 YAML보다 **모델 자체와 서빙 요구사항**에 집중할 수 있다.

```text
사용자: InferenceService 생성
        │
        ▼
Kubernetes API ─────► KServe Controller (Control Plane)
                             │ 원하는 상태 Reconcile
                             ▼
                    Deployment / Service / Gateway
                             │
                             ▼
                   Predictor Pod (Data Plane)
                    모델 다운로드 → 초기화
                             │
                    Readiness → 요청 수신
```

**KServe의 배포 방식:** Standard Mode는 일반적인 Deployment/Service 등 Kubernetes 리소스를 활용해 제어하기 쉽고, Knative Mode는 서버리스 특성 및 scale-to-zero를 활용할 수 있다. LLM은 모델 초기화가 무겁고 GPU 자원 할당이 복잡해 일반적으로 Standard/LLM 전용 구성을 먼저 검토한다. KServe 버전에 따라 CRD 구조와 지원 기능이 달라질 수 있다.

### 3. vLLM이란 무엇이며 왜 쓰는가?

**vLLM은 대규모 언어 모델을 빠르고 효율적으로 추론하기 위한 오픈소스 엔진 및 서버**다. Transformers로 모델을 단순 실행하는 것과 달리, 동시에 들어오는 여러 요청의 GPU 메모리와 연산 스케줄을 효율적으로 관리한다.

LLM 요청은 크게 두 단계로 구성된다.

- **Prefill:** 입력 Prompt 토큰을 한 번에 처리해 Attention 계산과 KV Cache를 만든다. 입력이 길수록 첫 토큰까지 걸리는 시간(TTFT)에 영향을 준다.
- **Decode:** 앞선 토큰과 KV Cache를 참조하며 다음 토큰을 반복적으로 생성한다. 출력 토큰 수와 동시 요청량에 따라 TPOT가 달라진다.

vLLM의 핵심 기술을 동작 원리까지 살펴보자.

| 기술 | 개념 | 효과와 주의점 |
|---|---|---|
| **PagedAttention** | KV Cache를 고정된 블록 단위로 관리하고 논리적 토큰 위치와 실제 메모리 블록을 매핑 | 긴 요청과 다양한 길이의 요청에서 메모리 낭비 감소 |
| **Continuous Batching** | 요청 전체가 끝날 때까지 기다리지 않고, 실행 중인 배치에 요청을 동적으로 넣고 뺌 | GPU 활용과 처리량 향상, 요청별 대기시간은 부하에 따라 달라짐 |
| **KV Cache** | 이전 토큰의 Key/Value 계산 결과를 저장 | 재계산 감소 대신 GPU 메모리 점유 증가 |
| **Tensor Parallelism** | 하나의 모델 연산을 여러 GPU에 분할 | 대규모 모델 실행 가능, GPU 간 통신비용 증가 |
| **OpenAI-compatible API** | 채팅·완성형 요청 등 지원 엔드포인트 제공 | 기존 클라이언트 연결 쉬움, 모든 API 기능의 완전 호환을 의미하지 않음 |

```text
Request A: [Prefill] [Decode] [Decode] [Done]
Request B:            [Prefill] [Decode] [Decode] ...
Request C:                     [Prefill] [Decode] ...
                              ▼
                     Continuous Scheduler
                              ▼
                   GPU Compute + KV Cache Blocks
```

**왜 일반 API보다 메모리 관리가 중요할까?** LLM 서버의 GPU 메모리는 모델 가중치뿐 아니라 KV Cache와 추론 버퍼가 점유한다. 컨텍스트 길이와 동시 요청이 늘면 KV Cache 요구량도 증가한다. 따라서 단순히 'GPU 사용률이 80%'라는 정보만으로 충분하지 않고, 사용 가능한 KV Cache, 대기 요청, 토큰 처리 속도를 함께 봐야 한다.

### 4. KServe와 vLLM의 관계

**KServe가 모델을 어떻게 운영할지 관리한다면, vLLM은 모델 내부의 실제 추론을 실행한다.** 둘은 경쟁 기술이 아니며 함께 사용할 수 있다.

| 책임 | KServe | vLLM |
|---|---|---|
| Kubernetes 배포·상태 조정 | 주 역할 | 자체적으로 수행하지 않음 |
| GPU Pod·라우팅/스케일링 연계 | 담당 또는 주변 컴포넌트 활용 | 서버 내부 요청 스케줄링 담당 |
| 모델 가중치 로딩 | 서빙 아티팩트 경로·런타임 설정 | 실제 엔진 로딩 |
| 토큰 생성 | 모델 서버에 위임 | Prefill / Decode 수행 |
| 관찰 지표 | Pod·서비스·라우팅 상태 | TTFT, TPOT, KV Cache, 토큰 처리량 |

```text
사용자 / RAG Agent
       │
       ▼
API Gateway (Auth / Rate Limit)
       │
       ▼
KServe (배포 정책 / 라우팅 / Scaling)
       │
       ▼
vLLM GPU Pod
       ├─ Model Weights + Tokenizer
       ├─ Prefill / Decode Scheduler
       ├─ KV Cache (PagedAttention)
       └─ OpenAI-compatible Inference API
       │
       ▼
Metrics / Logs / Traces → SLO 검증 및 알림
```

### 5. 실무에서 가장 먼저 봐야 하는 성능 지표

| 지표 | 어떤 문제를 설명하나? | 확인할 원인 |
|---|---|---|
| **TTFT (Time to First Token)** | 첫 응답 토큰이 늦게 옴 | 긴 입력, Prefill 병목, 대기열 |
| **TPOT (Time per Output Token)** | 응답 생성 자체가 느림 | Decode 경합, GPU 메모리·대역폭 |
| **Tokens/s** | 실제 토큰 처리량 | 연산 효율, batching, 동시성 |
| **KV Cache 사용량** | 요청을 얼마나 더 받을 수 있는가 | 긴 Context, 동시 세션 수 |
| **Request Queue** | 이미 처리 용량을 넘었는가 | 실행 중 요청, 대기시간 |
| **OOM / Restarts** | 자원 부족이나 프로세스 장애 | 모델 크기, 캐시 구성, GPU 메모리 |

예를 들어 RAG의 응답이 느린 상황에서 **TTFT만 증가했다면** 검색 결과가 길어져 Prompt가 커졌거나 요청 대기열이 늘었을 수 있다. 반면 **TPOT가 증가한다면** Decode 단계의 동시 실행 경합과 KV Cache 사용량을 먼저 분석하는 편이 합리적이다. 원인 확정은 각 메트릭을 함께 확인해야 한다.

### 6. Kubernetes 운영과 연결되는 핵심 문제

**① Startup Probe: 모델 로딩이 긴 경우**  
대형 모델은 컨테이너가 실행되어도 가중치 다운로드, GPU 메모리 적재, 엔진 준비가 끝나지 않았을 수 있다. Startup Probe의 충분한 실패 허용시간과 Readiness 조건을 설정해야 초기화 중 불필요한 재시작을 방지한다.

**② GPU RollingUpdate: 새 Pod가 Pending인 경우**  
GPU 2개가 있는 클러스터에서 GPU Pod 2개가 이미 실행 중인데 `maxSurge: 1`, `maxUnavailable: 0`으로 업데이트하면 새 Pod가 요구하는 추가 GPU를 확보하지 못해 배포가 진행되지 않을 수 있다. 해결책은 배포용 GPU 여유 확보, Blue/Green 환경, 모델 사전 캐싱, 단계별 트래픽 절체 등이다.

**③ 종료 중 스트리밍 응답이 끊기는 경우**  
LLM 스트리밍 응답은 수 초~수십 초 연결을 유지할 수 있다. Pod가 종료되기 전에 새 요청 수신을 중단하고 기존 요청을 처리하는 draining 전략이 필요하다. `terminationGracePeriodSeconds`만 늘린다고 자동으로 해결되지는 않는다.

**④ Scale-out하면 처리량이 선형 증가할까?**  
그렇지 않을 수 있다. 각 replica마다 가중치와 캐시가 중복되어 GPU 메모리가 소비되고, 새 replica 로딩·네트워크·라우터 병목도 발생하기 때문이다. 성능 평가에서는 입력/출력 토큰 길이 분포를 고정하고 TTFT p95, TPOT p95, Tokens/s, 실패율을 함께 비교해야 한다.

### 7. 실행 및 관찰 예제

GPU가 있는 별도 서버라면 vLLM을 먼저 단독으로 검증한 후 KServe 통합을 진행하는 것이 문제 분리에 유리하다.

```bash
# GPU 및 호환 버전이 준비된 서버에서 실행 (예시)
vllm serve <MODEL_ID> --host 0.0.0.0 --port 8000

# 추론 서버 및 메트릭 확인
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/v1/models
curl -fsS http://localhost:8000/metrics | head
```

아래는 별도 설치된 KServe 클러스터에서 구조를 확인하는 명령이다.

```bash
kubectl get crd | grep -E 'inferenceservice|servingruntime'
kubectl get inferenceservices -A
kubectl get servingruntimes -A
kubectl get deployments,pods,svc -A
```

이는 **실행 가이드**이며 이번 환경에서 vLLM·KServe 또는 GPU 성능을 직접 실행한 결과는 아니다. 설치 방식과 API 스펙은 KServe 버전에 따라 달라지므로 공식 문서를 확인하고 적용한다.

### 8. 설계 판단 정리

일반적인 회귀·분류 모델을 안정적으로 제공하려면 KServe의 기본 InferenceService와 표준 런타임을 우선 검토한다. 고성능 LLM 추론이 목표라면 vLLM 단독 배포로 성능 병목을 먼저 측정한 뒤, **여러 모델·여러 팀의 배포 표준화와 라우팅·운영 거버넌스가 필요할 때** KServe를 결합하는 접근이 실용적이다.

공식 참고: [KServe Architecture](https://kserve.github.io/website/docs/intro), [KServe ServingRuntime](https://kserve.github.io/website/docs/concepts/resources/servingruntime), [KServe LLMInferenceService](https://kserve.github.io/website/docs/concepts/architecture/control-plane-llmisvc), [vLLM Documentation](https://docs.vllm.ai/)

## 실험 결과에서 확인한 점

### Readiness와 Liveness의 상태 차이

로컬 FastAPI 서버에 초기화 지연 2초를 설정한 후 상태 엔드포인트를 호출했다. 초기화 중 `/healthz`는 **HTTP 200**, `/readyz`는 **HTTP 503**을 반환했고, 초기화 완료 후 `/readyz`가 **HTTP 200**으로 바뀌었다.

이 결과로 *프로세스가 실행 중인 상태(Alive)*와 *실제 요청을 처리할 준비가 된 상태(Ready)*를 구분할 필요성을 확인했다.

### 요청당 계산량에 따른 응답 지연

동시 요청 8개, 조건별 100개 요청을 보내고 연산량을 변경했다. 20K에서 300K로 증가할 때 **p95는 16.46ms → 208.59ms**, 처리량은 **608.37 → 56.39 RPS**로 변화했다.

이는 로컬 API 성능 기준선의 관찰 결과이며, Kubernetes CPU 제한을 적용해 얻은 값은 아니다. CPU 제한과 배포 전략의 실제 영향은 별도 Kubernetes 실험에서 검증해야 한다.

## Q&A · 학습하며 확인한 질문

**Q. Readiness와 Liveness는 왜 별도 엔드포인트여야 할까?**

A. 외부 서비스가 잠깐 실패한 상황과 실제 프로세스 교착을 구분하기 위해서다. 외부 의존성 오류를 무조건 Liveness 실패로 연결하면 불필요한 재시작이 이어질 수 있다.

**Q. `maxUnavailable: 0`이면 모든 요청이 반드시 성공할까?**

A. 아니다. 준비 상태와 실제 요청 성공에는 종료 처리, 커넥션 draining, 앱 오류, 노드 문제 등의 차이가 존재한다.

**Q. CPU Limits를 없애면 모든 문제가 해결될까?**

A. CPU quota로 인한 throttling은 줄일 수 있지만, 노드 경쟁·테넌트 간 간섭·비용·SLO 문제는 따로 고려해야 한다.

## 실험 결과 해석과 회고

이번 실습에서 확인할 핵심 가설은 **'설정값을 조정하면 단순히 자원 사용량만 달라지는 것이 아니라, 가용성과 업데이트 성공 여부도 바뀐다'**는 것이다.

실험마다 스크린샷과 `kubectl get/describe/logs`를 추가한 후 아래 질문에 답한다.

1. Readiness 실패 중 컨테이너는 살아 있는데 요청은 왜 실패했는가?
2. Startup Probe가 없으면 초기화가 긴 모델 서버에 어떤 일이 생기는가?
3. maxUnavailable=0인데 롤아웃이 멈추는 조건은 무엇인가?
4. CPU throttling이 Health Probe 실패로 이어질 수 있는가?
5. replicas와 worker 수를 어떻게 정해야 단일 장애 영향과 메모리 비용 사이에서 균형을 얻는가?

**개인적 정리:** Kubernetes의 운영 자동화는 실패를 없애는 기능이 아니라, 실패를 올바르게 판단하고 사용자 영향 범위를 최소화하도록 설계하는 기능이다. Probe, 배포 전략, 자원 설정은 별도의 YAML 항목이 아니라 하나의 SLO를 달성하기 위한 연관된 결정들이다.

## 실습 코드 및 참고자료

실험은 이론 이해를 위한 기초 검증과 성능·가용성 비교를 위한 심화 실험으로 구분했다. 실제 측정 결과를 얻으면 같은 문서에 로그와 그래프를 추가한다.

- [기초 실습 코드 · Probe와 Deployment](https://github.com/skgreenstar/skgreenstar.github.io/tree/main/docs/ml-platform/week-02-lab)
- [심화 실험 코드 · FastAPI / k6 / 결과 분석](https://github.com/skgreenstar/skgreenstar.github.io/tree/main/docs/ml-platform/week-02-advanced)

::: details 공식 문서 참고
- [Kubernetes Health Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)
- [Deployment와 롤링 업데이트](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [컨테이너 리소스 관리](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)
- [Pod QoS](https://kubernetes.io/docs/concepts/workloads/pods/pod-qos/)
:::

