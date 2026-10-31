# k3s 실제 실행·증적 수집 가이드

> 작성 시점 현재 이 문서는 **실행 계획**이다. 작성 환경은 cgroup v2가 읽기 전용이고 k3s 바이너리 및 외부 다운로드가 없어 Kubernetes 실험을 실행하지 못했다. 아래 코드를 실제 k3s 호스트에서 실행하고 결과를 수집해야 한다.

## 전제
Ubuntu/Linux VM 또는 물리 호스트, sudo 권한, 인터넷, 2 vCPU/2GiB 이상의 기본 k3s 서버 자원(실제 부하 실험은 더 많은 여유가 필요). Mac에서는 Linux VM을 사용한다. 운영 클러스터에서는 실행하지 않는다.

## 환경 구성
```bash
curl -sfL https://get.k3s.io | sh -
sudo k3s kubectl get nodes -o wide
sudo k3s kubectl create namespace week02
# 저장소 루트에서
sudo k3s kubectl apply -f docs/ml-platform/week-02-lab/01-app.yaml
sudo k3s kubectl -n week02 rollout status deploy/probe-demo
```

### Probe 장애 재현
```bash
sudo k3s kubectl -n week02 get pods,svc,endpoints -o wide
sudo k3s kubectl -n week02 exec deploy/probe-demo -- wget -qO- localhost:8080/traffic-off
sudo k3s kubectl -n week02 get endpoints probe-demo
sudo k3s kubectl -n week02 exec deploy/probe-demo -- wget -qO- localhost:8080/traffic-on
sudo k3s kubectl -n week02 exec deploy/probe-demo -- wget -qO- localhost:8080/server-error
sudo k3s kubectl -n week02 get pods -w
sudo k3s kubectl -n week02 describe pod -l app=probe-demo
```

### CPU 및 메모리 제한
```bash
sudo k3s kubectl apply -f docs/ml-platform/week-02-lab/02-cpu-stress.yaml
sudo k3s kubectl apply -f docs/ml-platform/week-02-lab/03-memory-oom.yaml
sudo k3s kubectl -n week02 get pods -o wide
sudo k3s kubectl -n week02 describe pod memory-oom
sudo k3s kubectl -n week02 logs pod/memory-oom --previous
```
`--previous`는 이전 컨테이너가 있을 때만 유효하다. OOMKilled 상태를 확인할 때 `kubectl get pod -o json`의 `lastState.terminated.reason`도 확인한다. CPU throttling은 `cpu.stat`에서 `nr_throttled` 및 `throttled_usec` 델타를 측정한다.

## 증거 수집
```bash
mkdir -p results/k3s
sudo k3s kubectl version > results/k3s/version.txt
sudo k3s kubectl get nodes -o wide > results/k3s/nodes.txt
sudo k3s kubectl -n week02 get pods -o wide > results/k3s/pods.txt
sudo k3s kubectl -n week02 get events --sort-by=.lastTimestamp > results/k3s/events.txt
sudo k3s kubectl -n week02 describe deploy probe-demo > results/k3s/deployment.txt
sudo k3s kubectl -n week02 get pods -o json > results/k3s/pods.json
```

실제 실행 전에는 결과 디렉터리에 아무런 성공 출력도 넣지 않는다. 개인 환경의 호스트명, IP, 내부 경로 및 토큰이 로그에 노출되지 않도록 업로드 전에 검토한다.

참고: https://docs.k3s.io/installation/requirements
