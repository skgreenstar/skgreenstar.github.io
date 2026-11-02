# Kubernetes 운영 실습

기존 kind 클러스터 `mlops-lab`에서 Probe·배포 전략·CPU·메모리·QoS를 확인한 구성이다. 명령의 context와 namespace를 고정해 사용한다.

```bash
kubectl --context kind-mlops-lab get nodes
kubectl --context kind-mlops-lab create namespace week02 \
  --dry-run=client -o yaml | kubectl --context kind-mlops-lab apply -f -
k() { kubectl --context kind-mlops-lab -n week02 "$@"; }

k apply -f https://raw.githubusercontent.com/skgreenstar/skgreenstar.github.io/main/docs/ml-platform/week-02-lab/01-app.yaml
k rollout status deployment/probe-demo --timeout=180s
k get pods -l app=probe-demo
k get endpointslices -l kubernetes.io/service-name=probe-demo
```

## Probe 상태 전환

장애 주입과 복구는 Pod 내부 주소에서 수행한다. `/traffic-off`는 Readiness, `/traffic-on`은 준비 상태 복구, `/server-error`는 Liveness 실패를 유도한다. HTTP 오류와 본문을 함께 볼 수 있도록 Python으로 호출한다.

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
k get endpointslices -l kubernetes.io/service-name=probe-demo
```

```bash
k exec deployment/probe-demo -- python -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8080/traffic-on").read().decode())'
k wait --for=condition=Ready=true pod -l app=probe-demo --timeout=45s
k exec deployment/probe-demo -- python -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8080/server-error").read().decode())'
k get pods -l app=probe-demo -w
```

Pod 상태와 EndpointSlice 준비 조건, Liveness 실패·Killing 이벤트와 재시작 횟수를 연결한다. UI나 API에 접속하기 위한 `port-forward`는 선택한 Pod로 연결하므로, 실제 Service 요청의 준비 상태 반영을 검사하려면 별도 클라이언트 Pod에서 Service DNS로 요청한다.

## 배포 전략

RollingUpdate·Rollback·Recreate는 동일 앱의 `LAB_VERSION` 환경변수를 바꾸어 비교했다. 실행 명령과 상태 전환은 [운영 자동화](../week-04.md)에 정리했다. Probe 경로가 다른 이미지를 섞어 배포 전략의 차이와 앱 호환성 문제를 혼동하지 않는다.

## CPU·메모리·QoS

```bash
k apply -f https://raw.githubusercontent.com/skgreenstar/skgreenstar.github.io/main/docs/ml-platform/week-02-lab/02-cpu-stress.yaml
k wait --for=condition=Ready pod/cpu-stress --timeout=180s
k exec cpu-stress -- cat /sys/fs/cgroup/cpu.max
k exec cpu-stress -- cat /sys/fs/cgroup/cpu.stat

k delete pod cpu-stress
k apply -f https://raw.githubusercontent.com/skgreenstar/skgreenstar.github.io/main/docs/ml-platform/week-02-lab/03-memory-oom.yaml
k wait --for=jsonpath='{.status.phase}'=Failed pod/memory-oom --timeout=120s
k describe pod memory-oom
```

CPU throttling은 cgroup 누적 카운터의 구간별 증가량으로 확인한다. Metrics Server의 `kubectl top`은 사용량 조회용이며 throttling 횟수를 직접 제공하지 않는다. 메모리는 종료 사유·종료 코드·restartPolicy를 함께 확인한다. 실제 측정값과 QoS 비교 매니페스트는 [리소스 관리](../week-05.md)에 정리했다.

이 가이드는 기존 클러스터와 PVC를 유지한다. 실습용 Pod를 정리할 때도 보존할 모델·학습 산출물과 대상 리소스를 구분한다.
