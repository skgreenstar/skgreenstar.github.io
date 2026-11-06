---
title: "09 · 추론이 느려졌을 때 Pod부터 늘려야 할까?"
outline: deep
prev:
  text: '3주차 · 학습 정리'
  link: '/ml-platform/study-week-03'
next:
  text: '10 · 트래픽 경로'
  link: '/ml-platform/week03-traffic'
---

# 09 · 추론이 느려졌을 때 Pod부터 늘려야 할까?

## 1. 실험 가설

| 조건 | 가설 | 주요 관찰 |
|---|---|---|
| CPU 계산 | 사용률 상승 후 CPU HPA가 replica 목표 변경 | CPU utilization, desired/current |
| Wait | 낮은 CPU에도 응답 지연 발생 가능 | p95, RPS, 실패율 |
| Cold start | 복제본 수가 늘어도 즉시 트래픽을 받지 못함 | Pod 생성과 Ready 시각 |

**실행 상태:** 아래는 실험 설계와 코드이며, 수치를 관측했다고 주장하지 않는다.

## 2. Mac Apple Silicon + kind 실행

```bash
kind get clusters
kubectl config current-context
docker build -t week03-infer:local labs/week03
# 기존 클러스터 이름이 myk8s인 경우
kind load docker-image week03-infer:local --name myk8s

kubectl create namespace week03 --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f labs/week03/deployment.yaml
kubectl apply -f labs/week03/hpa.yaml
kubectl -n week03 rollout status deploy/infer-api
kubectl -n week03 get hpa
kubectl -n week03 describe hpa infer-api
kubectl -n week03 top pods
kubectl -n week03 port-forward svc/infer-api 8080:80
```

다른 터미널에서 부하를 생성한다.

```bash
python3 labs/week03/load.py --url 'http://localhost:8080/infer?mode=cpu&iterations=2000000' --requests 300 --concurrency 20
python3 labs/week03/load.py --url 'http://localhost:8080/infer?mode=wait&wait_ms=500' --requests 300 --concurrency 20
```

**전제:** CPU HPA에는 metrics-server가 필요하다. 단발 300건만으로 증설을 보장할 수 없다. 지속 부하, 충분한 관측 시간, CPU requests 설정을 함께 검토한다. port-forward와 로컬 부하 발생기가 결과의 병목이 될 수도 있다.

## 3. 실측 기록 표

| 측정 | Baseline | CPU load | Wait load |
|---|---|---|---|
| 동시성 | 미측정 | 미측정 | 미측정 |
| RPS | 미측정 | 미측정 | 미측정 |
| p95 (ms) | 미측정 | 미측정 | 미측정 |
| 오류율 | 미측정 | 미측정 | 미측정 |
| HPA desired/current | 미측정 | 미측정 | 미측정 |
| Ready Pod 수 | 미측정 | 미측정 | 미측정 |

## 4. HPA의 조건과 한계

CPU utilization의 분모는 resources.requests.cpu다. Pod Pending은 반드시 자원 부족 때문만은 아니므로 `kubectl describe pod`의 Events에서 FailedScheduling의 실제 이유를 확인한다. Node autoscaler는 HPA와 별개다. Scale-down 안정화는 급격한 축소 진동을 줄이지만 트래픽 급증 시의 콜드 스타트를 해결하지는 않는다.

[3주차 학습 정리로 돌아가기](/ml-platform/study-week-03)
