---
title: "2주차 · Kubernetes 운영 자동화와 리소스 관리 실습"
description: "Health Probe, Rolling Update, Requests/Limits와 QoS를 직접 재현하는 MLOps 스터디"
date: 2026-11-01
outline: deep
---

# 2주차 · Kubernetes 운영 자동화와 리소스 관리

> **학습 방식:** 핵심 개념 → 동작 구조 → 가설 → kind 실습 → 관찰/해석. 아래의 출력은 *예상 동작*이며, 직접 측정한 결과와 구분한다.

::: tip 이번 주 학습 목표
- Startup / Readiness / Liveness Probe의 역할을 구분하고 장애를 재현한다.
- RollingUpdate·Recreate의 가용성 차이를 검증하고 롤백한다.
- CPU·Memory Requests/Limits, QoS와 자원 경합을 관찰한다.
- AI 모델 서빙에 적용할 때의 설계 선택을 설명한다.
:::

## 0. 전체 아키텍처

![Kubernetes 운영 구조](/diagrams/week02-architecture.svg)

| 설정 | 핵심 질문 | Kubernetes 동작 |
|---|---|---|
| startupProbe | 초기화가 끝났는가? | 성공 전 liveness/readiness 검사 지연, 지정 횟수 실패 시 재시작 |
| readinessProbe | 지금 트래픽을 받을 수 있는가? | 실패 시 Service의 정상 Endpoint에서 제외 |
| livenessProbe | 현재 컨테이너를 재시작해야 하는가? | 연속 실패 임계값 충족 시 컨테이너 재시작 |
| requests | 어디에 배치할 수 있는가? | Scheduler의 자원 적합성 판단 기준 |
| limits | 얼마나 쓸 수 있는가? | CPU quota 기반 제어, Memory 초과 시 OOM 가능 |

## 1. kind 환경 준비

Docker, kind, kubectl이 필요하다. 실습 파일은 같은 저장소의 [week-02-lab](./week-02-lab/README.md)에 정리했다.

```bash
kind create cluster --name ml-platform-week02
kubectl cluster-info --context kind-ml-platform-week02
kubectl create namespace week02
kubectl get nodes -o wide
```

## 2. 애플리케이션 상태 검사와 자동 복구

### 2.1 헬스체크를 왜 나누는가?

- **Startup**: 모델 로딩·DB 초기 연결처럼 시작이 오래 걸릴 때 조기 재시작을 막는다.
- **Readiness**: 컨테이너가 실행 중이라도 DB·모델 가중치·초기 캐시가 준비되지 않았다면 트래픽을 차단한다.
- **Liveness**: 애플리케이션 내부가 회복 불가한 상태라면 재시작한다. 외부 DB 장애만으로 실패하도록 만들면 연쇄 장애를 유발할 수 있다.

![Health Probe 동작](/diagrams/week02-probes.svg)

### 2.2 Probe 실습: 정상 상태 → 트래픽 중단 → 장애

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

### 2.3 RollingUpdate vs Recreate

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

### 2.4 기록 표

| 테스트 | 예상 현상 | 실제 관찰 |
|---|---|---|
| Startup 실패 | Liveness/Readiness 동작 보류, 반복 실패 시 재시작 | 실행 후 기록 |
| Readiness 실패 | Service Endpoint 제외 | 실행 후 기록 |
| Liveness 실패 | 임계값 이후 컨테이너 재시작 | 실행 후 기록 |
| RollingUpdate | Ready 신규 Pod 기준 교체 | 실행 후 기록 |
| Recreate | 기존 Pod 종료 후 새 버전 시작 | 실행 후 기록 |

## 3. 자원 관리와 성능 최적화

### 3.1 Scheduler와 Requests/Limits

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

### 3.2 QoS와 Eviction

| QoS | 조건(일반적인 Pod 수준) | 의미 |
|---|---|---|
| Guaranteed | 모든 컨테이너 CPU·Memory request=limit 지정 | 자원 압박 시 비교적 높은 보호 |
| Burstable | 위 조건은 아니지만 request/limit 존재 | 자원 경합과 사용량에 따라 축출 가능 |
| BestEffort | CPU·Memory request/limit 없음 | 자원 압박 시 먼저 축출될 가능성 |

Node-pressure Eviction은 Priority, Requests 초과 사용 여부, 상대 사용량 등을 고려한다. QoS만으로 모든 축출 순서가 결정되는 것은 아니다. PriorityClass의 `preemptionPolicy: Never`는 **선점을 금지**하지만 높은 우선순위의 스케줄링 순서 자체를 포기하는 것은 아니다.

### 3.3 CPU Throttling 및 OOM 실습

```bash
kubectl apply -f docs/ml-platform/week-02-lab/02-cpu-stress.yaml
kubectl apply -f docs/ml-platform/week-02-lab/03-memory-oom.yaml
kubectl -n week02 get pods -w
kubectl -n week02 top pods
kubectl -n week02 describe pod cpu-stress
kubectl -n week02 describe pod memory-oom
```

`kubectl top`은 Metrics Server가 설치되어 있어야 한다. 최소 kind 클러스터에서 작동하지 않으면 `kubectl describe`·컨테이너 cgroup 통계·재시작 이벤트를 활용한다. **Memory OOM은 실제 할당 패턴과 노드 환경에 따라 재현 여부가 달라질 수 있다.**

### 3.4 CPU Overcommit / Replica × Worker

![Replica 및 Worker 분산 비교](/diagrams/week02-replica.svg)

복제본 증가가 무조건 좋은 것은 아니다. 프로세스 시작·모델 가중치·캐시가 Pod마다 중복될 수 있다. 특히 vLLM·GPU 모델 서빙에서는 **가중치 메모리 중복 비용**까지 고려해야 한다.

CPU overcommit은 request를 실제 피크보다 낮게 설정해 더 많은 Pod를 배치하는 방법이다. 유휴 시간이 긴 웹 워크로드에는 유효할 수 있지만 동시 부하 시 레이턴시 변동성이 커질 수 있다. CPU limit 미설정은 throttling을 완화할 수 있으나 **클러스터 격리·공정성 정책 검토 후** 적용해야 한다.

### 3.5 Rightsizing 실험 기록

| 단계 | CPU 사용 | Memory 사용 | p95 latency | Restart / OOM |
|---|---|---|---|---|
| 초기화 | 실측 | 실측 | 해당 없음 | 실측 |
| 정상 부하 | 실측 | 실측 | 실측 | 실측 |
| 피크 부하 | 실측 | 실측 | 실측 | 실측 |
| 설정 변경 후 | 실측 | 실측 | 실측 | 실측 |

관찰한 워크로드 특성에 따라 CPU request를 조정하고, Memory는 정상 부하의 장기 최대값과 누수·스파이크를 고려한다. 특정 블로그의 **Memory request=limit, CPU request만 설정** 패턴을 모든 워크로드에 적용하는 것은 피한다.

## 4. AI 모델 서빙 적용: KServe / vLLM

- **Startup Probe**: 이미지 시작이 아니라 모델 가중치 로딩 및 엔진 초기화 완료 기준.
- **Readiness Probe**: 모델 로딩, 토크나이저, 요청 처리 준비 여부를 판단. 외부 DB 장애를 적용할지는 실제 요청 경로에 따라 결정.
- **Liveness Probe**: 프로세스 교착·회복 불가능 상태만 감지하도록 가볍게 설계.
- **RollingUpdate**: 모델 가중치 중복 적재 시 GPU 메모리 여유가 없으면 surge Pod가 Pending될 수 있다.
- **자원 최적화**: CPU thread / 동시 요청 / GPU KV cache·배치 크기 / replicas를 함께 측정한다.

## 5. 결과 분석 및 회고

이번 실습에서 확인할 핵심 가설은 **'설정값을 조정하면 단순히 자원 사용량만 달라지는 것이 아니라, 가용성과 업데이트 성공 여부도 바뀐다'**는 것이다.

실험마다 스크린샷과 `kubectl get/describe/logs`를 추가한 후 아래 질문에 답한다.

1. Readiness 실패 중 컨테이너는 살아 있는데 요청은 왜 실패했는가?
2. Startup Probe가 없으면 초기화가 긴 모델 서버에 어떤 일이 생기는가?
3. maxUnavailable=0인데 롤아웃이 멈추는 조건은 무엇인가?
4. CPU throttling이 Health Probe 실패로 이어질 수 있는가?
5. replicas와 worker 수를 어떻게 정해야 단일 장애 영향과 메모리 비용 사이에서 균형을 얻는가?

**개인적 정리:** Kubernetes의 운영 자동화는 실패를 없애는 기능이 아니라, 실패를 올바르게 판단하고 사용자 영향 범위를 최소화하도록 설계하는 기능이다. Probe, 배포 전략, 자원 설정은 별도의 YAML 항목이 아니라 하나의 SLO를 달성하기 위한 연관된 결정들이다.

---

**이전 주차:** [1주차 CH1~3](/ml-platform/study-week-01) · **실습 파일:** [week-02-lab](https://github.com/skgreenstar/skgreenstar.github.io/tree/main/docs/ml-platform/week-02-lab)

참고: [Kubernetes Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/), [Deployment](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/), [Resource Management](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/), [Pod QoS](https://kubernetes.io/docs/concepts/workloads/pods/pod-qos/)
