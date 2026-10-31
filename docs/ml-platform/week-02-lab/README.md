# Week 02 Kubernetes Hands-on

실습은 로컬 kind 클러스터에서 수행한다. 실제로 실행하기 전에 Docker, kind, kubectl을 준비한다.

```bash
kind create cluster --name ml-platform-week02
kubectl create namespace week02
kubectl apply -f docs/ml-platform/week-02-lab/01-app.yaml
kubectl -n week02 rollout status deployment/probe-demo
kubectl -n week02 port-forward svc/probe-demo 8080:80
```

별도 터미널:

```bash
curl -i localhost:8080/
curl -i localhost:8080/traffic-off
kubectl -n week02 get endpoints probe-demo
# Service 대상에서 빠진 후 복구하려면 exec 사용
kubectl -n week02 exec deploy/probe-demo -- wget -qO- localhost:8080/traffic-on
kubectl -n week02 exec deploy/probe-demo -- wget -qO- localhost:8080/server-error
kubectl -n week02 get pod -w
```

자원 실험:

```bash
kubectl apply -f docs/ml-platform/week-02-lab/02-cpu-stress.yaml
kubectl apply -f docs/ml-platform/week-02-lab/03-memory-oom.yaml
kubectl -n week02 get pods -w
kubectl -n week02 describe pod memory-oom
```

**주의:** `02-cpu-stress.yaml`은 CPU 소비 실습 예제이고, 실제 throttle 횟수 관찰은 Metrics Server 또는 cgroup metrics가 필요하다. `03-memory-oom.yaml`은 메모리 제한 실패를 재현할 수 있으므로 프로덕션에 적용하지 않는다. 실행 결과는 별도로 기록한다.

```bash
kind delete cluster --name ml-platform-week02
```
