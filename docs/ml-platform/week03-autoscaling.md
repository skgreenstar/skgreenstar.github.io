---
title: "09 · Pod를 늘리는 것과 용량을 늘리는 것은 다르다"
outline: deep
prev:
  text: '3주차 · 학습 정리'
  link: '/ml-platform/study-week-03'
next:
  text: '10 · 요청 경로'
  link: '/ml-platform/week03-traffic'
---

# 09 · Pod를 늘리는 것과 용량을 늘리는 것은 다르다

CH6 Scaling Up · 이론 → 실험 조건 → 운영 검증

## 1. Pod 확장과 노드 용량

Kubernetes에서 Pod는 애플리케이션 실행 단위이고 Node는 그 실행 용량이다. 둘은 다른 스케일링 대상이다.

![HPA · 복제본 수와 실제 서비스 용량의 차이](/images/week03-hpa-architecture.svg)

*이 그림은 개념 관계를 보여주는 학습용 아키텍처이며, 실제 실행·측정 결과가 아닙니다.*

HPA가 관리하는 Deployment에서는 수동으로 replicas를 조정해도 HPA가 다시 바꿀 수 있다. 따라서 아래 수동 확장 실험은 HPA 리소스를 제거한 상태에서 진행한다. 이후 CPU 기반 자동 확장 실험에서는 HPA를 다시 적용한다.

```bash
kubectl -n week03 delete hpa infer-api --ignore-not-found
kubectl -n week03 scale deployment infer-api --replicas=4
kubectl -n week03 get deploy,rs,pod -o wide
kubectl -n week03 get events --sort-by=.metadata.creationTimestamp
kubectl -n week03 describe pod <PENDING_POD_NAME>
```

`Pending`을 모두 CPU 부족으로 해석하지 않는다. 노드 selector, taints/tolerations, PVC, affinity와 이미지 pull의 영향도 확인한다. Node autoscaler는 제공업체에 따라 다른 구현을 사용한다. kind에 클라우드 자동 노드 증설 기능이 기본 제공되는 것으로 가정하면 안 된다.

## 2. HPA를 계산식과 실제 동작으로 나누어 이해하기

HPA가 CPU utilization을 이용하는 경우 설명 가능한 기본 계산식은 다음과 같다.

$
r_{\mathrm{desired}} =
\left\lceil
r_{\mathrm{current}} \times
\frac{u_{\mathrm{observed}}}{u_{\mathrm{target}}}
\right\rceil
$

여기서 $r_{\mathrm{current}}$는 현재 복제본 수, $u_{\mathrm{observed}}$는 관측된 평균 CPU 사용률, $u_{\mathrm{target}}$은 설정한 목표 CPU 사용률이다. 사용률은 CPU limit이 아닌 각 Pod의 CPU request를 기준으로 계산한다.

예를 들어 복제본이 2개이고 CPU 사용률이 80%, 목표가 50%라면 다음과 같이 계산한다.

$
r_{\mathrm{desired}} =
\left\lceil 2 \times \frac{80}{50} \right\rceil
= 4
$

- 이 계산은 실제 HPA의 모든 동작을 설명하지 않는다. tolerance, 메트릭 누락, 시작 초기화, min/max와 scale 정책이 결과를 바꾼다.
- `kubectl get hpa`의 TARGETS와 `kubectl describe hpa`의 Conditions/Events를 함께 본다.

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: infer-api
  namespace: week03
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: infer-api
  minReplicas: 2
  maxReplicas: 6
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 50
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 180
```

실제 파일: [HPA manifest](https://github.com/skgreenstar/skgreenstar.github.io/blob/main/labs/week03/hpa.yaml)

## 3. CPU 부하와 대기 부하를 같은 조건에서 비교한다

```bash
kind get clusters
kubectl config current-context
docker build -t week03-infer:local labs/week03
kind load docker-image week03-infer:local --name myk8s

kubectl create namespace week03 --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f labs/week03/deployment.yaml
kubectl apply -f labs/week03/hpa.yaml
kubectl -n week03 rollout status deployment/infer-api

# 터미널 A: 변화 관찰
kubectl -n week03 get hpa,pod -w
# 터미널 B: CPU 메트릭
kubectl -n week03 top pod
# 터미널 C: 로컬 연결
kubectl -n week03 port-forward svc/infer-api 8080:80
# 터미널 D: 조건별 부하
python3 labs/week03/load.py --url 'http://127.0.0.1:8080/infer?mode=cpu&iterations=2000000' --requests 300 --concurrency 20
python3 labs/week03/load.py --url 'http://127.0.0.1:8080/infer?mode=wait&wait_ms=500' --requests 300 --concurrency 20
```

`300`회 일회성 부하만으로 HPA 증설을 확인할 수 있다고 보장하지 않는다. 실제 비교에서는 일정 시간 지속 부하를 걸고 HPA 관측 주기와 Pod 준비 시간을 포함한다. port-forward와 부하 발생기 자체가 병목이면 결과를 폐기하거나 조건을 바꾼다.

### 측정 항목

| 항목 | 이유 | 수집 방법 |
|---|---|---|
| 전체 완료 RPS | 처리량 기준 | load.py 출력 |
| 성공/실패, p50/p95 | 사용자 체감 | load.py 출력 |
| CPU utilization | HPA 트리거 확인 | kubectl top pod / HPA status |
| desired/current/ready | 증설 목표와 실효 용량 구분 | get hpa/deploy |
| pod creation/Ready | 콜드 스타트 | pod condition timestamps |
| Node allocatable | 스케줄 여유 | describe nodes |

`load.py`의 p95는 실패 요청 시간까지 포함한 전체 완료 요청의 분위수다. 성공 요청만의 p95를 따로 계산하지 않으므로 다른 벤치마크와 직접 비교할 때 이 조건을 밝혀야 한다.

## 4. CPU 사용률과 응답 지연이 일치하지 않는 경우

RAG·Agent는 벡터 검색, DB 조회, 외부 LLM API 호출처럼 I/O를 기다리는 시간이 길 수 있다. 이때 CPU만 보고 복제본을 늘리지 않는 것이 이상한 동작은 아니다. CPU 사용률만으로 실제 대기 시간을 설명하기 어렵기 때문이다.

![CPU 사용률이 낮아도 추론 대기 시간이 길 수 있는 이유](/images/week03-cpu-wait-comparison.svg)

커스텀/외부 메트릭을 쓰려면 단순히 Prometheus를 설치하는 것만으로 끝나지 않는다. 어댑터와 적절한 API 등록, metric 이름·selector·권한·실제 샘플이 모두 필요하다. 현재 저장소 예제에는 이 어댑터가 구현돼 있지 않다.

## 5. Prometheus와 Grafana: 측정 시스템의 계층 구분

모니터링에서는 리소스 사용량, Kubernetes 객체 상태, 애플리케이션 지표를 구분해야 한다. metrics-server는 HPA용 리소스 메트릭을 제공하지만 범용 시계열 저장소는 아니다.

| 구성 | 무엇을 보는가 | AI 서비스에서의 활용 |
|---|---|---|
| metrics-server | 리소스 메트릭 API | CPU HPA, kubectl top |
| Prometheus | 시계열 메트릭 수집·쿼리 | CPU, RPS, latency, queue 등 |
| kube-state-metrics | Kubernetes 객체 상태 | desired/available replicas 등 |
| node-exporter | Node OS 메트릭 | CPU, memory, filesystem |
| Grafana | 데이터 소스 기반 대시보드 | HPA·오류율·지연 추세 연계 |
| Prometheus Adapter | 메트릭→K8s custom/external API | RPS/queue 기반 HPA 실험 |

시간축 하나에 HPA replica, Ready replica, p95, 오류율을 맞추고, CPU와 RPS를 별도 패널에 배치한다. 각 이벤트 전후 1~5분 창을 보며 인과관계를 검토한다. 같은 시각에 관측됐다는 이유만으로 곧바로 인과관계로 판단하지 않는다.

설치 자체는 노션에 소개된 Helm chart를 참조하되 버전 호환성과 이미지·메모리 사용량을 확인한다. 설치하지 않은 컴포넌트를 작동했다고 기록하지 않는다.

## 6. VPA와 Node Autoscaling 비교

| 기술 | 무엇을 바꾸는가 | 장점 | 주의점 |
|---|---|---|---|
| HPA | replica count | 병렬 처리 능력 증가 | 시작 지연·지표 불일치 |
| VPA | CPU/memory requests 중심 | 자원 할당 최적화 | 적용 방식에 따라 재생성/재시작 가능 |
| Cluster Autoscaler | node pool의 node 수 | Pending 용량 해소 | 클라우드 프로비저닝 지연 |
| Karpenter | 요구 사항에 맞는 Node 제공 | 다양한 워크로드에 맞는 용량 선택 | 지원 환경·정책 확인 필요 |
| Placeholder Pods | 낮은 우선순위 용량 예약 | 버스트 시 선점 가능한 여유 | 유휴 자원 비용·우선순위 정책 |

VPA의 CPU 조정과 CPU HPA를 결합할 때는 둘이 같은 자원 기반으로 간섭하지 않는지 살펴본다. 특히 Pod 축소 때는 PDB, graceful termination, in-flight 요청, 스케줄 여유와 비용을 함께 검토한다.

### Placeholder Pod를 쓰는 이유

![Placeholder Pod가 제공하는 선점 가능한 여유 공간](/images/week03-placeholder-scheduling.svg)

단순히 PriorityClass를 정의한다고 노드가 예약되는 것은 아니다. 실제 낮은 우선순위 Pod를 스케줄해야 하고, 우선순위·선점·PDB·비용 정책이 맞아야 한다. GPU 모델의 길고 비싼 warmup에는 별도의 예열 전략이 필요할 수 있다.

## 7. Stateless와 Twelve-Factor 관점

- 일회성: Pod는 삭제·재생성될 수 있다. 시작과 종료가 예측 가능해야 한다.
- 상태 외부화: 사용자 세션, 중간 결과, 모델 버전 포인터 등은 필요한 경우 DB/스토리지에 보관한다. Pod 로컬 파일에 의존하면 replica별 상태가 달라진다.
- 설정 분리: endpoint, feature flag, 모델 URI, secret을 이미지 코드에서 분리한다.
- 종료 안전성: SIGTERM을 받으면 신규 요청을 차단하고 진행 중인 요청은 정해진 시간 내 마무리한다.

AI 추론에서는 ‘stateless’가 모델을 메모리에 올리지 않는다는 뜻이 아니다. 모델 가중치는 메모리 캐시로 존재할 수 있지만 요청의 정합성을 로컬 Pod에만 의존하지 않도록 설계해야 한다.

## 8. 증상별 확인 순서

| 증상 | 성급한 해석 | 더 나은 판단 |
|---|---|---|
| HPA replicas 6 | 확장 성공 | Ready 6인가, 정상 RPS가 늘었는가? |
| CPU 30% | 여유 충분 | 외부 호출·큐·memory·GPU 지표는? |
| Pod Pending | Pod 문제 | scheduler 이벤트로 Node/규칙 확인 |
| p95 하락 | HPA 효과 | 동시에 요청량 감소·cache hit 변화가 있었나? |

### 실행 결과 기록

현재 공개된 실습 코드는 준비돼 있으나 3주차의 실제 수치 측정은 미실행이다. 실습을 마친 후 최소한 명령어 원문, 이미지 태그, 부하 인자, 시작/종료 시각, HPA 이벤트, 측정 결과, 실패 조건을 함께 게시한다.

[3주차 학습 정리로 돌아가기](/ml-platform/study-week-03)

공식 참고: [HPA](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/) · [VPA](https://github.com/kubernetes/autoscaler/tree/master/vertical-pod-autoscaler) · [Node Autoscaling](https://kubernetes.io/docs/concepts/cluster-administration/node-autoscaling/) · [Pod Priority](https://kubernetes.io/docs/concepts/scheduling-eviction/pod-priority-preemption/)
