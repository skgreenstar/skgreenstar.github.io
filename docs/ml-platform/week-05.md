---
title: "리소스 설정은 성능과 안정성을 어떻게 바꿀까?"
description: "Requests/Limits, QoS와 FastAPI 성능 측정 및 운영 가설 실험"
date: 2026-11-01
outline: deep
prev:
  text: '컨테이너가 실행 중이면 서비스도 정상일까?'
  link: '/ml-platform/week-04'
next:
  text: 'KServe와 vLLM으로 모델을 어떻게 운영할까?'
  link: '/ml-platform/week-06'
---

# 리소스 설정은 성능과 안정성을 어떻게 바꿀까?

**심화 · 운영:** Kubernetes 리소스 관리와 성능 검증  
**핵심 질문:** 자원 예약·사용 한도·복제본 수는 지연시간과 장애 영향에 어떻게 연결될까?

## 실행 환경

CPU·메모리·QoS 관찰은 `kind-mlops-lab`의 `week02`에서 수행했다. 아래 함수로 명령의 실행 대상을 고정한다.

```bash
k() { kubectl --context kind-mlops-lab -n week02 "$@"; }
```

## Kubernetes 리소스 관리

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
k apply -f https://raw.githubusercontent.com/skgreenstar/skgreenstar.github.io/main/docs/ml-platform/week-02-lab/02-cpu-stress.yaml
k apply -f https://raw.githubusercontent.com/skgreenstar/skgreenstar.github.io/main/docs/ml-platform/week-02-lab/03-memory-oom.yaml
k get pods -w
k top pods
k describe pod cpu-stress
k describe pod memory-oom
```

`kubectl top`은 Metrics Server가 설치되어 있어야 한다. 최소 kind 클러스터에서 작동하지 않으면 `kubectl describe`·컨테이너 cgroup 통계·재시작 이벤트를 활용한다. **Memory OOM은 실제 할당 패턴과 노드 환경에 따라 재현 여부가 달라질 수 있다.**

### 4. CPU Overcommit / Replica × Worker

![Replica 및 Worker 분산 비교](/diagrams/week02-replica.svg)

복제본 증가가 무조건 좋은 것은 아니다. 프로세스 시작·모델 가중치·캐시가 Pod마다 중복될 수 있다. 특히 vLLM·GPU 모델 서빙에서는 **가중치 메모리 중복 비용**까지 고려해야 한다.

CPU overcommit은 request를 실제 피크보다 낮게 설정해 더 많은 Pod를 배치하는 방법이다. 유휴 시간이 긴 웹 워크로드에는 유효할 수 있지만 동시 부하 시 레이턴시 변동성이 커질 수 있다. CPU limit 미설정은 throttling을 완화할 수 있으나 **클러스터 격리·공정성 정책 검토 후** 적용해야 한다.

### 5. 실행 결과로 정리한 자원 설정

| 실습 | 설정 | 실행 결과 |
|---|---|---|
| CPU 부하 | request 50m / limit 100m | 10.006초 동안 CPU 약 1.002초 사용, 100개 주기에서 throttling |
| 메모리 할당 | request 32Mi / limit 64Mi | 160Mi 할당 시 OOMKilled, exitCode 137 |
| QoS 비교 | 자원 설정 세 가지 | Guaranteed·Burstable·BestEffort 각각 확인 |

CPU는 quota에 의해 실행 시간이 제한됐고, 메모리는 한도 초과 시 종료됐다. 아래 로그에서 설정·출력·해석을 연결한다.

## kind 실습 기록 · CPU Limit과 Throttling {#kind-cpu-result}

개인 PC의 `kind-mlops-lab` 클러스터, `week02` 네임스페이스에서 저장소의 `cpu-stress` Pod를 실행했다. 이미지 `python:3.12-alpine`은 반복 CPU 연산을 수행한다. Pod는 `1/1 Running`, 재시작 횟수 0으로 확인됐다.

| 설정 | 값 |
|---|---|
| CPU request / limit | 50m / 100m |
| Memory request / limit | 32Mi / 128Mi |
| 관찰 대상 | 컨테이너 cgroup v2의 cpu.max, cpu.stat |
| 측정 방식 | 10초 대기 전후 누적 카운터 차이 |

### 실행 명령

```bash
k apply -f https://raw.githubusercontent.com/skgreenstar/skgreenstar.github.io/main/docs/ml-platform/week-02-lab/02-cpu-stress.yaml
k wait --for=condition=Ready pod/cpu-stress --timeout=180s
k get pod cpu-stress

k exec cpu-stress -- python -c '
from pathlib import Path
import time
root = Path("/sys/fs/cgroup")
def read_stat():
    return {
        key: int(value)
        for key, value in (
            line.split() for line in (root / "cpu.stat").read_text().splitlines()
        )
    }
print("cpu.max:", (root / "cpu.max").read_text().strip())
before = read_stat()
start = time.monotonic()
time.sleep(10)
after = read_stat()
elapsed = time.monotonic() - start
print("elapsed_seconds:", round(elapsed, 3))
for key in ["usage_usec", "nr_periods", "nr_throttled", "throttled_usec"]:
    print(key, "delta=", after.get(key, 0) - before.get(key, 0))
'
```

### 실행 로그

```text
pod/cpu-stress created
pod/cpu-stress condition met

NAME         READY   STATUS    RESTARTS   AGE
cpu-stress   1/1     Running   0          0s

cpu.max: 10000 100000
elapsed_seconds: 10.006
usage_usec delta= 1001782
nr_periods delta= 100
nr_throttled delta= 100
throttled_usec delta= 1262760
```

### 측정값 해석

| 관찰값 | 계산 / 의미 |
|---|---|
| cpu.max = 10000 100000 | 100,000μs 주기당 CPU 실행 예산 10,000μs, 비율 0.1 CPU = 100m |
| usage_usec 증가 1,001,782 | 10.006초 동안 CPU 사용 시간 약 1.002초 |
| 평균 CPU 사용 | 1.001782 / 10.006 ≈ 0.100 CPU, 약 100m |
| nr_periods 증가 100 | 측정 구간의 대역폭 제어 주기 100개 |
| nr_throttled 증가 100 | 100개 주기 모두에서 throttling이 기록됨 |
| throttled_usec 증가 1,262,760 | 누적 throttling 시간 약 1.263초 증가 |

**확인한 점:** 선언한 CPU limit 100m가 cgroup quota에 반영됐고, 해당 측정 구간의 평균 CPU 사용량이 약 100m였으며 throttling 카운터가 실제로 증가했다.

**해석의 경계:** 주기 기준 throttling 비율 100%는 **매 주기 한 번 이상 제한이 기록됐다**는 뜻이다. CPU가 전체 벽시계 시간의 100% 동안 정지했다는 뜻이 아니다. 이 수치는 동일 컨테이너에서 실행한 측정용 Python 프로세스의 자원 사용도 포함한다. 단일 구간 관찰이며, CPU limit별 비교나 HTTP p95/p99 지연 영향은 아직 측정하지 않았다.

## kind 실습 기록 · 메모리 제한과 OOMKilled {#kind-memory-result}

CPU 부하 Pod를 삭제한 뒤, 같은 `week02` 네임스페이스에서 저장소의 `memory-oom` Pod를 실행했다. 메모리 limit 64Mi에 대해 Python이 160Mi 크기의 bytearray를 할당하도록 구성했다.

### 실행 명령

```bash
k delete pod cpu-stress
k apply -f https://raw.githubusercontent.com/skgreenstar/skgreenstar.github.io/main/docs/ml-platform/week-02-lab/03-memory-oom.yaml
k wait --for=jsonpath='{.status.phase}'=Failed pod/memory-oom --timeout=120s
k get pod memory-oom

k get pod memory-oom -o 'jsonpath={range .status.containerStatuses[*]}{"reason="}{.state.terminated.reason}{" exitCode="}{.state.terminated.exitCode}{" restarts="}{.restartCount}{"\n"}{end}'
k get pod memory-oom -o 'jsonpath={range .spec.containers[*]}{"memory request="}{.resources.requests.memory}{" limit="}{.resources.limits.memory}{"\n"}{end}{"QoS="}{.status.qosClass}{" restartPolicy="}{.spec.restartPolicy}{"\n"}'
```

### 실행 로그

```text
pod "cpu-stress" deleted from week02 namespace
pod/memory-oom created
pod/memory-oom condition met

NAME         READY   STATUS      RESTARTS   AGE
memory-oom   0/1     OOMKilled   0          2s

reason=OOMKilled exitCode=137 restarts=0
memory request=32Mi limit=64Mi
QoS=Burstable restartPolicy=Never
```

### 관찰 결과

| 항목 | 실제 확인 | 해석 |
|---|---|---|
| Memory request / limit | 32Mi / 64Mi | 예약량과 사용 한도는 다른 값 |
| 프로그램의 할당 시도 | YAML에 160Mi bytearray 할당 | 메모리 limit보다 큰 할당을 의도 |
| 종료 사유 | OOMKilled | 메모리 OOM 종료를 직접 확인 |
| 종료 코드 | 137 | 종료 사유와 함께 해석 |
| 재시작 횟수 | 0 | restartPolicy=Never에서 종료 후 재시작하지 않음 |
| QoS | Burstable | CPU·메모리 request와 limit이 같지 않은 구성 |

**CPU 제한 실습과 비교:** CPU 부하 Pod는 Running을 유지하면서 throttling이 기록됐다. 메모리 실습에서는 프로세스가 OOMKilled로 종료됐다. 두 자원 한도가 다른 방식으로 나타나는 것을 실제 관찰했다.

**Liveness 실습과 비교:** 앞선 Probe 앱은 Liveness 실패·Killing 후 `lastReason=Error exitCode=137`을 남기고 재시작됐다. 이번에는 `reason=OOMKilled`와 `restartPolicy=Never`를 확인했다. 같은 종료 코드 137만으로 두 사건의 원인을 동일하게 취급하지 않는다.

**검증 범위:** 컨테이너의 메모리 한도 초과 실험이며, 노드 전체 메모리 압박에 따른 eviction 순서나 QoS 등급별 보호 효과를 실측한 결과는 아니다. AGE 2s는 조회 시점의 Pod 나이이며 정밀한 OOM 발생 시간 측정값으로 사용하지 않는다.

## kind 실습 기록 · QoS 세 등급 비교 {#kind-qos-result}

앞선 OOM 실습의 Burstable Pod에 더해 비교용 Pod 두 개를 생성했다. 동일한 `week02` 네임스페이스에서 CPU·메모리 request와 limit 설정에 따른 QoS 등급을 조회했다.

### 비교용 Pod 생성

```bash
k apply -f - <<'YAML'
apiVersion: v1
kind: Pod
metadata:
  name: qos-guaranteed
  labels:
    lab: qos-demo
spec:
  restartPolicy: Never
  containers:
    - name: app
      image: python:3.12-alpine
      command: ["python", "-c", "import time; time.sleep(3600)"]
      resources:
        requests:
          cpu: 50m
          memory: 32Mi
        limits:
          cpu: 50m
          memory: 32Mi
---
apiVersion: v1
kind: Pod
metadata:
  name: qos-besteffort
  labels:
    lab: qos-demo
spec:
  restartPolicy: Never
  containers:
    - name: app
      image: python:3.12-alpine
      command: ["python", "-c", "import time; time.sleep(3600)"]
YAML

k wait --for=condition=Ready pod -l lab=qos-demo --timeout=180s
```

```text
pod/qos-guaranteed created
pod/qos-besteffort created
pod/qos-besteffort condition met
pod/qos-guaranteed condition met
```

### QoS 조회와 실제 출력

```bash
k get pods qos-guaranteed qos-besteffort memory-oom -o 'custom-columns=NAME:.metadata.name,QOS:.status.qosClass,CPU_REQUEST:.spec.containers[0].resources.requests.cpu,CPU_LIMIT:.spec.containers[0].resources.limits.cpu,MEM_REQUEST:.spec.containers[0].resources.requests.memory,MEM_LIMIT:.spec.containers[0].resources.limits.memory'
```

```text
NAME             QOS          CPU_REQUEST   CPU_LIMIT   MEM_REQUEST   MEM_LIMIT
qos-guaranteed   Guaranteed   50m           50m         32Mi          32Mi
qos-besteffort   BestEffort   <none>        <none>      <none>        <none>
memory-oom       Burstable    20m           200m        32Mi          64Mi
```

### 확인한 점

| Pod | 실제 QoS | 해당 설정과의 연결 |
|---|---|---|
| qos-guaranteed | Guaranteed | 단일 컨테이너의 CPU·메모리 request와 limit이 각각 같음 |
| qos-besteffort | BestEffort | CPU·메모리 request와 limit을 지정하지 않음 |
| memory-oom | Burstable | CPU·메모리 request와 limit이 서로 다름 |

세 등급이 실제로 부여되는 것을 확인했다. 앞서 OOMKilled로 종료된 Pod에도 Burstable 등급이 기록돼 있었다. **Guaranteed라는 이름이 무조건적인 생존이나 OOM 방지를 뜻하는 것은 아니다.** 이번 실습에서는 노드 메모리 압박이나 eviction을 유도하지 않았으므로 등급별 축출 순서·보호 효과를 실측했다고 쓰지 않는다.

## 애플리케이션 부하 기준선

자원 한도 관찰과 HTTP 지연 측정은 질문이 다르다. 아래 별도 실험에서는 요청당 계산량만 바꾸어 처리량과 지연의 변화를 확인했다.

::: details FastAPI 로컬 기준선 · 조건과 측정 결과
### 실험 환경 및 목적

별도의 Python 3.13/Uvicorn 환경에서 애플리케이션의 초기 상태와 요청당 연산량에 따른 HTTP 응답을 측정했다. 이는 위 kind 자원 제한 실험과 실행 조건이 다른 애플리케이션 기준선이다.

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

이 실험은 **애플리케이션 레벨의 응답 상태**를 검증한 것이다. 이 로컬 실험에서는 Kubernetes Endpoint 변화를 측정하지 않았다. 이후 kind의 Readiness 실습에서 EndpointSlice의 ready 조건 변경을 별도로 확인했다.

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

:::

::: details 후속 성능 실험 설계와 실행 코드

### 후속 성능 실험 설계

앞에서 확인한 자원 한도와 준비 상태를 바탕으로, 동일 HTTP 부하에서 지연·배포·Replica의 영향을 비교할 수 있도록 후속 프로토콜을 정리했다.

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
k set env deploy/performance-api READY_DELAY=8
k rollout status deploy/performance-api
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

위 실측은 CPU quota·메모리 한도·QoS 검증이다. 이 절은 요청 지연과 Replica 비교를 위한 후속 프로토콜이다.


:::

## 자원별 동작을 구분해서 해석하기

CPU limit 100m에서는 평균 CPU 사용이 약 100m였고 제어 주기마다 throttling이 기록됐다. 메모리 limit 64Mi에서는 160Mi 할당 시도 후 OOMKilled로 종료됐다. QoS 비교에서는 선언한 request·limit 관계에 따라 세 등급이 부여되는 것을 확인했다.

CPU 제한은 실행 시간을 제어하고, 메모리 제한은 한도 초과 시 종료로 이어질 수 있다. QoS는 자원 압박 상황의 판단 요소이며 생존을 보장하지 않는다. 별도 FastAPI 실험의 p95·처리량은 애플리케이션 부하 기준선으로 읽고, Kubernetes의 quota 관찰과 직접 같은 원인으로 묶지 않는다.


---

[2주차 학습 정리로 돌아가기](/ml-platform/study-week-02)
