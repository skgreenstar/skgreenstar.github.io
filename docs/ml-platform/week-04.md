---
title: "04. 컨테이너가 실행 중이면 서비스도 정상일까?"
description: "Health Probe, 배포 전략과 롤백을 연결하는 Kubernetes 운영 자동화"
date: 2026-11-01
outline: deep
prev:
  text: '2주차 · 학습 정리'
  link: '/ml-platform/study-week-02'
next:
  text: '05. 리소스 설정은 성능과 안정성을 어떻게 바꿀까?'
  link: '/ml-platform/week-05'
---

# 04. 컨테이너가 실행 중이면 서비스도 정상일까?

**학습 범위:** CH4 · Automated Operations  
**핵심 질문:** 실행 상태, 트래픽 수신 준비, 재시작 필요성을 어떻게 구분할까?

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

---

[2주차 학습 정리로 돌아가기](/ml-platform/study-week-02)
