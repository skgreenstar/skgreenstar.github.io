# Week 02 · Kubernetes 성능·가용성 실험

기초적인 상태 확인에서 더 나아가 **가설 → 통제된 실험 → 자동 측정 → 원인 분석**을 수행한다. 실험 결과는 아직 측정하지 않았다.

## 1. 준비

Docker, kind, kubectl, k6, Python 3가 필요하다. 저장소 최상위 디렉터리에서 실행한다.

```bash
kind create cluster --name ml-platform-week02
kubectl create namespace week02
docker build -t week02-performance:local docs/ml-platform/week-02-advanced
kind load docker-image week02-performance:local --name ml-platform-week02
kubectl apply -f docs/ml-platform/week-02-advanced/deployment.yaml
kubectl -n week02 rollout status deploy/performance-api
kubectl -n week02 port-forward svc/performance-api 8080:80
```

## 2. 실험 A · CPU Limit과 Tail Latency

**가설:** CPU limit이 낮으면 CPU 집약 작업에서 p95·p99 지연이 늘어날 수 있다. 환경별 결과는 다르므로 직접 측정한다.

다른 터미널에서 진행한다. 각 조건은 같은 RPS·지속시간·요청 작업량을 유지하고 워밍업 후 3회 이상 반복한다.

```bash
mkdir -p results
kubectl -n week02 set resources deploy/performance-api --limits=cpu=250m,memory=256Mi --requests=cpu=100m,memory=64Mi
kubectl -n week02 rollout status deploy/performance-api
k6 run -e RATE=30 -e DURATION=60s --summary-export results/cpu250-run1.json docs/ml-platform/week-02-advanced/loadtest.js

kubectl -n week02 set resources deploy/performance-api --limits=cpu=500m,memory=256Mi --requests=cpu=100m,memory=64Mi
kubectl -n week02 rollout status deploy/performance-api
k6 run -e RATE=30 -e DURATION=60s --summary-export results/cpu500-run1.json docs/ml-platform/week-02-advanced/loadtest.js

python docs/ml-platform/week-02-advanced/analyze.py results/*.json
```

실제 CPU throttling의 근거는 `kubectl top`만으로 얻을 수 없다. cgroup v2의 `cpu.stat` 또는 Prometheus의 throttled_periods 지표가 필요하다. 측정 기간의 delta를 사용하고, 워크로드가 CPU-bound인지 함께 확인한다.

## 3. 실험 B · RollingUpdate 중 실제 요청 성공률

**가설:** rollout 성공과 사용자 요청의 오류율 0%는 같은 조건이 아니다.

터미널 A에서 3분 부하를 실행하고 터미널 B에서 신규 Pod 초기화 지연을 추가한다.

```bash
k6 run -e RATE=30 -e DURATION=180s --summary-export results/rollout.json docs/ml-platform/week-02-advanced/loadtest.js
```

```bash
kubectl -n week02 set env deploy/performance-api READY_DELAY=8
kubectl -n week02 rollout status deploy/performance-api --timeout=180s
kubectl -n week02 rollout history deploy/performance-api
```

조건별 `maxSurge` / `maxUnavailable`, Replica, 초기화 지연을 고정·변경하여 오류율과 배포 시간을 비교한다. readiness만으로 모든 연결 종료 상황이 완전히 해결되는 것은 아니며, 기존 요청의 draining과 SIGTERM 처리도 고려한다.

## 4. 실험 C · Replica 분산과 장애 영향

```bash
kubectl -n week02 scale deploy/performance-api --replicas=2
kubectl -n week02 rollout status deploy/performance-api
k6 run -e RATE=30 -e DURATION=60s --summary-export results/replicas2.json docs/ml-platform/week-02-advanced/loadtest.js

kubectl -n week02 scale deploy/performance-api --replicas=4
kubectl -n week02 rollout status deploy/performance-api
k6 run -e RATE=30 -e DURATION=60s --summary-export results/replicas4.json docs/ml-platform/week-02-advanced/loadtest.js
```

동일한 시점에 Pod 1개를 삭제하고 오류율·회복 시간을 비교할 수 있다. 현재 이미지는 **Pod당 worker 1개**이므로 위 실험은 Replica 수의 비교이며 총 Worker 수는 동일하지 않다. 동일 Worker 총량 비교(2 Pods × 2 workers / 4 Pods × 1 worker)는 이미지 CMD의 workers 옵션까지 변경하는 확장 실험으로 분리한다.

## 5. 자동 분석과 증거 수집

```bash
python docs/ml-platform/week-02-advanced/analyze.py results/*.json
cat results/summary.csv
kubectl -n week02 get pods -o wide
kubectl -n week02 describe deploy performance-api
kubectl -n week02 get events --sort-by=.lastTimestamp
```

CSV는 **실제 k6 summary JSON만 읽어 생성**한다. p50·p95·p99, RPS, 오류율, dropped_iterations를 확인한다. 충분한 VU를 확보하지 못하면 목표 RPS가 생성되지 않았을 수 있다. 부하 발생기 자체가 병목인지도 점검한다.

| 가설 | 독립 변수 | 종속 변수 | 주요 통제 |
|---|---|---|---|
| CPU limit → tail latency | 250m / 500m | p95/p99, RPS, throttling | 요청 작업량, Replica, RPS |
| 배포 전략 → 가용성 | maxUnavailable, 지연 | 오류율, 배포시간 | Replica, RPS, CPU |
| 분산 → 장애 영향 | replicas | 실패율, 회복시간 | 트래픽, 이미지, 노드 |

**실습 제한:** kind는 로컬 단일 머신의 CPU와 Docker 설정에 영향을 받는다. 이 결과를 운영 SLA나 GPU 서빙 성능으로 일반화하지 않는다. CPU 측정이 필요하면 환경에 맞는 모니터링 스택을 별도로 설치한다.

정리: `kind delete cluster --name ml-platform-week02`
