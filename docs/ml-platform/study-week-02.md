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

## KServe와 vLLM으로 연결하는 모델 서빙 아키텍처

::: tip 두 기술의 역할
**KServe는 Kubernetes 상에서 모델 서비스의 배포·라우팅·확장·운영을 선언적으로 관리하는 플랫폼**, **vLLM은 LLM 추론을 수행하는 고성능 서빙 엔진**이다. 서로 대체 관계가 아니라 KServe가 vLLM 엔진을 운영하는 구성이 가능하다.
:::

### 1. KServe: 모델 배포를 Kubernetes API로 관리하기

KServe는 `InferenceService`, `ServingRuntime` 같은 CRD를 통해 모델 배포를 선언한다. 일반적인 Deployment/Service뿐 아니라 모델 아티팩트 다운로드, 상태 관리, 라우팅, 자동 확장 등을 묶어 운영할 수 있다. KServe 버전 및 배포 모드(Standard/Knative 기반 Serverless, 최신 LLM 전용 API)에 따라 지원 기능과 요구 구성요소는 다르다.

| 기능 | 역할 | 운영 시 확인 사항 |
|---|---|---|
| InferenceService | 모델 서비스의 원하는 상태 선언 | 모델 URI·런타임·리소스·버전 |
| ServingRuntime | 실제 모델 서버 이미지 및 규격 | 지원 모델 형식, 서버 진입점 |
| Storage initializer | 원격 모델 다운로드 | 객체 스토리지 자격 증명, 다운로드 시간 |
| Autoscaling | 요청량/동시성 기반 복제 | GPU 확보 시간, 콜드스타트 비용 |
| Canary / Rollout | 신규 모델 단계적 검증 | 모델 출력 호환성 및 라우팅 정책 |

KServe에서는 모델이 **Pod Ready**여도 요청이 실제 품질과 지연시간 SLO를 충족하는지 별도로 확인해야 한다. 긴 모델 다운로드·초기화, GPU 스케줄링, 외부 저장소 장애가 모두 Cold Start에 영향을 준다.

### 2. vLLM: LLM 요청을 효율적으로 처리하는 엔진

vLLM은 LLM 추론 서버다. 대표적으로 **PagedAttention을 통한 KV Cache 메모리 관리**, **Continuous Batching**, OpenAI 호환 API, Tensor/Pipeline Parallelism 등을 활용해 모델과 하드웨어 특성에 맞춰 처리량을 개선한다.

| 운영 지표 | 의미 | 주된 병목 |
|---|---|---|
| TTFT (Time To First Token) | 첫 토큰까지의 대기시간 | Prefill, 대기열, 모델 초기화 |
| TPOT / ITL | 출력 토큰 생성 지연 | Decode, 배치 크기, 경합 |
| Throughput (tokens/s) | 초당 처리 토큰 수 | GPU 연산, 메모리 대역폭 |
| KV Cache 사용량 | 동시 세션의 캐시 점유 | 컨텍스트 길이, 동시성 |
| Queue / Running requests | 대기 중·처리 중 요청 | 과부하, concurrency |
| GPU Memory / OOM | 가중치·KV Cache 등 메모리 사용 | 긴 입력, 메모리 설정, 복제본 수 |

OpenAI 호환 API가 있다고 해서 API 표면 및 모델 출력이 모든 OpenAI 엔드포인트와 완전히 같지는 않다. 라이브러리 버전에 따라 지원 필드를 검증해야 한다. vLLM은 `/metrics` 엔드포인트를 제공하므로 Prometheus와 연계해 엔진 메트릭을 관찰할 수 있다.

### 3. KServe + vLLM 운영 구조

```text
Client / AI Agent / RAG
        │
        ▼
API Gateway · 인증 · Rate Limit
        │
        ▼
KServe InferenceService / LLMInferenceService
        │
        ├─ Routing / Scaling / Rollout
        │
        ▼
vLLM Serving Pod (GPU)
        ├─ Model weights / Tokenizer
        ├─ Prefill + Decode scheduler
        ├─ KV Cache / Continuous batching
        ├─ /health, /metrics 등 상태·관측 엔드포인트
        └─ OpenAI-compatible inference API
        │
        ▼
Metrics / Logs / Traces + SLO / Alerting
```

**중요:** 위 구조는 개념적 참조 아키텍처다. 실제 `InferenceService`에 vLLM을 등록하는 방식은 KServe 릴리스, 지원 `ServingRuntime`, 설치 모드에 따라 달라진다. 설치 버전에 맞는 공식 예제와 CRD 스키마를 먼저 확인한다.

### 4. Health Probe를 모델 서버에 적용할 때

- **Startup:** 모델 다운로드 및 GPU 초기화가 완료될 시간을 고려한다. 시작에 수 분이 걸리는데 liveness를 일찍 시작하면 무한 재시작에 빠질 수 있다.
- **Readiness:** 모델 엔진이 요청을 처리할 준비가 됐는지 확인한다. 단순 프로세스 생존과 분리한다. 모델의 첫 요청 워밍업이 필요하다면 트래픽을 보내기 전에 처리한다.
- **Liveness:** 프로세스 교착이나 복구 불가능 상태를 판단한다. 단순 대기열 증가나 외부 의존성의 일시 장애만으로 재시작하지 않는다.
- **종료:** SIGTERM, 기존 요청 처리, Endpoint 반영 및 `terminationGracePeriodSeconds`를 함께 설계한다. 생성 중인 스트리밍 응답이 끊기지 않는지 실제로 측정한다.

### 5. GPU에서 RollingUpdate가 실패하는 이유

GPU Pod 2개가 이미 GPU 2개를 점유하는 클러스터를 가정하자. `maxUnavailable: 0`, `maxSurge: 1`이면 새 Pod를 먼저 만들어야 하지만 **추가 GPU가 없다면 Pending 상태**로 머물 수 있다. 반대로 `maxUnavailable: 1`은 진행 가능성을 높이지만 일시적인 모델 처리 용량 감소를 허용한다.

해결 방향: 배포 시 GPU 여유 용량 확보, 별도 노드 풀/Blue-Green, 요청 drain, 모델 아티팩트 사전 준비, **토큰 기준 처리량과 TTFT/TPOT를 모니터링한 단계적 절체**.

### 6. 실무 시나리오: RAG 서비스에서 LLM 응답이 느려질 때

| 현상 | 진단 가설 | 우선 확인 |
|---|---|---|
| TTFT만 상승 | 긴 Prompt, Prefill 병목, Queue | 입력 토큰 길이, 대기 요청 |
| TPOT 상승 | Decode 경합, KV Cache, 배치 크기 | 캐시 점유, 토큰 처리량 |
| 배포 후 503 | 모델 로딩 전 Ready 판정 또는 GPU Pending | startup/readiness, Pod events |
| GPU OOM | KV Cache/Context 또는 모델 중복 적재 | GPU 메모리, max model length |
| 배포 중 스트리밍 끊김 | 종료 처리·커넥션 drain 미흡 | SIGTERM, termination grace, 실제 연결 |
| Scale-out이 느림 | GPU 노드 증설·이미지 및 모델 다운로드 | 노드 오토스케일링, 아티팩트 캐시 |

**성능 평가 방식:** 고정 QPS만으로 비교하지 말고 입력/출력 토큰 길이 분포, 동시 요청 수, TTFT p95, TPOT p95, 성공률, 처리량(tokens/s), GPU 사용량을 함께 측정한다.

### 7. 직접 실행해볼 vLLM 관찰 명령

다음은 **GPU가 있는 별도 서버에서 실행할 예제**이며 여기서는 실행하지 않았다. 모델 및 이미지 버전은 실제 호환 환경에서 검증한다.

```bash
vllm serve <MODEL_ID> --host 0.0.0.0 --port 8000
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/v1/models
curl -fsS http://localhost:8000/metrics | head
```

추론 테스트는 모델 ID, 입력/출력 토큰 수, 동시성을 고정하고 TTFT·TPOT와 GPU 메모리의 변화를 기록한다.

### 8. 실제 Kubernetes 검증을 위한 k3s 가이드

[k3s 운영 실험 및 증적 수집 절차](https://github.com/skgreenstar/skgreenstar.github.io/blob/main/docs/ml-platform/week-02-advanced/K3S-EXPERIMENT.md)

현재 실행 환경은 `/sys/fs/cgroup`이 읽기 전용이며 k3s 바이너리가 없고 패키지 다운로드 DNS가 실패하여 **k3s를 실제 실행하지 못했다.** 따라서 실제 확인된 것은 앞의 로컬 FastAPI 기준선뿐이다. k3s 실험 파일은 실행 방법 및 결과 수집 양식이며 측정 데이터가 아니다.

참고: [KServe 소개](https://www.kubeflow.org/docs/ecosystem/kserve/introduction/), [KServe CRD](https://kserve.github.io/website/docs/reference/crd-api), [vLLM Metrics](https://docs.vllm.ai/en/latest/usage/metrics/), [K3s 요구사항](https://docs.k3s.io/installation/requirements)

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

