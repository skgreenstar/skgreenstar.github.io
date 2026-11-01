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
| Readiness 실패 | EndpointSlice 준비 조건 변경 | 실제 확인: Pod 0/1 Running, RESTARTS=0, ready=false → 복구 후 1/1·ready=true |
| Liveness 실패 | 임계값 이후 컨테이너 재시작 | 실제 확인: HTTP 503 → Killing → 동일 Pod RESTARTS=1, 1/1 Running 복구 |
| RollingUpdate | Ready 신규 Pod 기준 교체 | 실행 후 기록 |
| Recreate | 기존 Pod 종료 후 새 버전 시작 | 실행 후 기록 |

## 실제 kind 실행 기록 {#kind-readiness-result}

개인 PC에서 실행한 터미널 출력을 기록했다. Docker는 `linux / aarch64`, 클러스터는 `mlops-lab`, 컨텍스트는 `kind-mlops-lab`이다. 노드 `mlops-lab-control-plane`은 Kubernetes v1.37.0, containerd 2.3.4에서 Ready 상태였다.

### 실행 명령

기존 클러스터에 전용 네임스페이스를 만들고 저장소의 실습 앱을 배포했다.

```bash
kubectl --context kind-mlops-lab create namespace week02 \
  --dry-run=client -o yaml |
kubectl --context kind-mlops-lab apply -f -

k() {
  kubectl --context kind-mlops-lab -n week02 "$@"
}

k apply -f https://raw.githubusercontent.com/skgreenstar/skgreenstar.github.io/main/docs/ml-platform/week-02-lab/01-app.yaml
k rollout status deployment/probe-demo --timeout=180s
k get pods -o wide
k get endpointslices -l kubernetes.io/service-name=probe-demo \
  -o 'jsonpath={range .items[*].endpoints[*]}{.addresses}{" ready="}{.conditions.ready}{"\n"}{end}'
```

앱 내부 주소를 호출해 Readiness만 실패하도록 변경한 뒤 Pod와 EndpointSlice를 확인했다. Python은 HTTP 503도 출력하도록 예외를 처리했다.

```bash
k exec deployment/probe-demo -- python -c '
import urllib.request
import urllib.error
base = "http://127.0.0.1:8080"
for path in ["/traffic-off", "/healthz", "/readyz"]:
    try:
        with urllib.request.urlopen(base + path, timeout=3) as response:
            print(path, response.status, response.read().decode())
    except urllib.error.HTTPError as error:
        print(path, error.code, error.read().decode())
'
k wait --for=condition=Ready=false pod -l app=probe-demo --timeout=45s
k get pods
k get endpointslices -l kubernetes.io/service-name=probe-demo \
  -o 'jsonpath={range .items[*].endpoints[*]}{.addresses}{" ready="}{.conditions.ready}{"\n"}{end}'
```

```bash
k exec deployment/probe-demo -- python -c '
import urllib.request
with urllib.request.urlopen(
    "http://127.0.0.1:8080/traffic-on", timeout=3
) as response:
    print(response.status, response.read().decode())
'
k wait --for=condition=Ready=true pod -l app=probe-demo --timeout=45s
k get pods
k get endpointslices -l kubernetes.io/service-name=probe-demo \
  -o 'jsonpath={range .items[*].endpoints[*]}{.addresses}{" ready="}{.conditions.ready}{"\n"}{end}'
```

### 1. 정상 배포 · 실제 출력

```text
namespace/week02 created
configmap/probe-script created
deployment.apps/probe-demo created
service/probe-demo created
Waiting for deployment "probe-demo" rollout to finish: 0 of 1 updated replicas are available...
deployment "probe-demo" successfully rolled out

NAME                          READY   STATUS    RESTARTS   AGE   IP
probe-demo-68c54c584d-62p2t     1/1     Running   0          6s    <POD_IP>

["<POD_IP>"] ready=true
```

Pod 출력에서는 이름·상태·재시작 횟수·AGE·IP 열을 발췌했다. 공개용 로그의 Pod IP는 `<POD_IP>`로 마스킹했으며, 같은 표시는 동일한 Pod 주소를 뜻한다. 상태값과 측정 결과는 원래 출력대로 유지했다.

### 2. Readiness 장애 · 실제 출력

```text
/traffic-off 200 traffic disabled
/healthz 200 healthy
/readyz 503 unready
pod/probe-demo-68c54c584d-62p2t condition met

NAME                          READY   STATUS    RESTARTS   AGE
probe-demo-68c54c584d-62p2t     0/1     Running   0          30s

["<POD_IP>"] ready=false
```

### 3. 복구 · 실제 출력

```text
200 traffic enabled
pod/probe-demo-68c54c584d-62p2t condition met

NAME                          READY   STATUS    RESTARTS   AGE
probe-demo-68c54c584d-62p2t     1/1     Running   0          48s

["<POD_IP>"] ready=true
```

### 4. Liveness 장애 감지 · 실제 출력

`/server-error` 호출로 앱의 healthy 상태를 false로 변경했다.

```text
200 liveness failure enabled

NAME                          READY   STATUS    RESTARTS   AGE
probe-demo-68c54c584d-62p2t     1/1     Running   0          2m2s

restarts=0 lastReason= exitCode=
```

Events에서 다음 메시지를 확인했다. 아래는 TYPE·REASON·MESSAGE를 발췌한 것이다.

```text
Warning  Unhealthy  Liveness probe failed: HTTP probe failed with statuscode: 503
Normal   Killing    Container app failed liveness probe, will be restarted
```

**판정:** Liveness 실패 감지와 컨테이너 종료 요청은 확인됐다. 그러나 이 출력 시점에는 `RESTARTS=0`이고 `lastState.terminated`가 비어 있어 재시작 완료를 단정하지 않는다. 종료 유예와 다음 기동·상태 갱신을 거친 후 재시작 횟수와 Ready 복구를 추가 확인한다. Readiness와 healthy 상태를 별도로 관리하는 실습 앱이므로, Liveness 실패 시점에도 READY가 1/1로 표시될 수 있다.

### 5. Liveness 재시작 완료 · 실제 출력

종료 요청 직후의 관찰에 이어 상태를 다시 조회했다.

```bash
k get pods -l app=probe-demo
k get pods -l app=probe-demo \
  -o 'jsonpath={range .items[*].status.containerStatuses[*]}{"restarts="}{.restartCount}{" lastReason="}{.lastState.terminated.reason}{" exitCode="}{.lastState.terminated.exitCode}{"\n"}{end}'
```

```text
NAME                          READY   STATUS    RESTARTS        AGE
probe-demo-68c54c584d-62p2t     1/1     Running   1 (4m32s ago)   6m57s

restarts=1 lastReason=Error exitCode=137
```

**최종 판정:** 동일 Pod 안에서 컨테이너가 한 번 재시작됐고, 다시 Ready 상태가 됐다. 앞서 수집한 Liveness HTTP 503 및 Killing 이벤트와 연결해 **장애 주입 → 실패 감지 → 종료 요청 → 컨테이너 재시작 → Ready 복구**를 확인했다. 재시작 직후 HTTP 엔드포인트를 별도로 호출한 결과나 Service 경유 가용성은 이번 출력에 포함되지 않는다.

이전 컨테이너의 종료 사유는 `Error`, 종료 코드는 `137`로 기록됐다. **종료 코드만으로 OOM이라고 판단하지 않는다.** 이번 기록에는 Liveness 실패에 따른 Killing 이벤트가 있으며 `OOMKilled` 사유는 관찰되지 않았다. 출력의 `4m32s ago`와 AGE는 조회 시점의 상대 시간이며 장애 복구에 4분 32초가 걸렸다는 뜻이 아니다.

### Readiness 관찰 결과와 해석

| 관찰 대상 | 정상 → 장애 → 복구 | 해석 |
|---|---|---|
| Pod 이름 | 세 단계 모두 동일 | Pod 교체 없이 상태 전환 |
| READY | 1/1 → 0/1 → 1/1 | 트래픽 수신 준비 상태 변경 |
| STATUS | Running 유지 | 컨테이너 실행 상태와 준비 상태는 다름 |
| RESTARTS | 0 → 0 → 0 | Readiness 실패로 재시작되지 않음 |
| EndpointSlice | ready=true → false → true | 주소는 유지되며 준비 조건 변경 |

**직접 확인한 범위:** Readiness 실패 중 `/healthz=200`과 `/readyz=503`이 동시에 관찰됐고, 컨테이너 재시작 없이 Pod와 EndpointSlice의 준비 상태가 바뀌었다.

**추가 검증 범위:** 이번 요청은 Pod 내부 주소로 실행했다. Service 경유 요청 차단 여부나 실패율은 직접 측정하지 않았다. 표의 AGE는 각 출력 시점의 Pod 나이이며, 장애 감지·복구 소요시간을 정밀 측정한 값은 아니다. Liveness는 후속 출력에서 재시작과 Ready 복구까지 확인했다. RollingUpdate·롤백 결과는 후속 실습에서 별도로 수집한다.


---

[2주차 학습 정리로 돌아가기](/ml-platform/study-week-02)
