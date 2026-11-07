---
title: "Week 03 · 느린 추론의 원인은 Pod 수일까, 요청 경로일까?"
outline: deep
prev:
  text: '2주차 · 학습 정리'
  link: '/ml-platform/study-week-02'
next:
  text: '09 · 확장 전략'
  link: '/ml-platform/week03-autoscaling'
---

# Week 03 · 느린 추론의 원인은 Pod 수일까, 요청 경로일까?

**교재 범위:** *Machine Learning Platform Engineering* CH6 · Scaling Up / CH7 · Internal Services and Load Balancing  
**핵심 질문:** Kubernetes에서 제공하는 모델 API가 느려질 때, 확장해야 하는 것은 Pod·Node·모델 서버·네트워크 경로 중 무엇인가?  
**실습 상태:** 실제로 실행한 기록과 **설계한 실험**을 구분한다. 아직 3주차 kind 부하 실험 수치를 확보하지 않았으므로 정량 결과를 만들어 넣지 않는다.

2주차에서는 MLflow에서 고정된 모델을 선택하고 Feast·KFP에서 동일한 피처·모델 버전으로 예측을 반복하는 흐름을 만들었다. 3주차는 그 다음 질문으로 시작한다. **모델이 정확하고 재현 가능하더라도 추론 서비스가 빠르고 안정적이라는 뜻은 아니다.**

같은 ‘응답 지연’도 CPU 포화, 외부 I/O 대기, 모델 초기 로딩, Pod Pending, DNS 오류, EndpointSlice의 미준비 엔드포인트 등 서로 다른 원인에서 발생한다. 이 원인을 구분하지 않고 HPA의 maxReplicas만 늘리는 것은 문제를 키울 수도 있다.

## 1. 추론 지연을 네 계층으로 나눠 진단하기

![Week 03 · ML 플랫폼 운영 루프](/images/week03-platform-architecture.svg)

*이 그림은 개념 관계를 보여주는 학습용 아키텍처이며, 실제 실행·측정 결과가 아닙니다.*

| 관측 증상 | 가능한 원인 | 먼저 확인할 근거 | 성급한 해결책 |
|---|---|---|---|
| CPU 높고 p95 증가 | CPU bound·thread pool 포화 | requests, throttling, pod별 CPU | 무조건 노드만 증설 |
| CPU 낮은데 p95 증가 | 외부 API·DB 대기, queue | 요청 추적, concurrency, queue depth | CPU HPA만 적용 |
| 증설됐지만 오류 지속 | Pod warming, readiness 불일치 | creation→Ready→첫 성공 응답 | replicas 값만 확인 |
| Pod가 Pending | 자원 부족·taint·affinity·PVC | describe의 FailedScheduling | HPA 최대치만 증가 |
| Pod는 정상인데 접근 실패 | Service selector·DNS·route | EndpointSlice, CoreDNS, Ingress | 모델 코드 재배포 |

## 2. 교재 범위와 실습 구성

| 순서 | 핵심 주제 | 상세 글 | 확인할 증거 |
|---|---|---|---|
| 09-A | Pod 수동 확장·Node 증설·Pending 분석 | [09. Scaling up](/ml-platform/week03-autoscaling) | replicas, scheduler Events |
| 09-B | HPA/VPA/Node autoscaling과 운영 안전장치 | [09. Scaling up](/ml-platform/week03-autoscaling) | CPU target, Ready 시점, PDB |
| 09-C | Prometheus·Grafana와 커스텀 메트릭 | [09. Scaling up](/ml-platform/week03-autoscaling) | metrics 출처와 시간축 |
| 10-A | ClusterIP·Service DNS·EndpointSlice·Load balancing | [10. Internal services](/ml-platform/week03-traffic) | DNS, ready endpoints, 실제 응답 |
| 10-B | Ingress·TLS·Gateway API·트래픽 경로 | [10. Internal services](/ml-platform/week03-traffic) | 라우팅 규칙 및 Controller 상태 |
| 통합 | CPU 부하 vs I/O 대기 vs 모델 로딩 지연 | [09](/ml-platform/week03-autoscaling) · [10](/ml-platform/week03-traffic) | RPS·p95·오류율·확장 이벤트 |

## 3. 같은 API에서 CPU와 대기 병목 비교

이번 실습은 **학습한 모델을 흉내 내는 합성 API**를 사용한다. 실제 모델의 정확도나 제조 품질 지표를 추론 부하 실험 결과와 혼동하지 않기 위해서다. 동일한 FastAPI 컨테이너에 CPU 계산 경로와 대기 경로를 두고, 같은 Service·Deployment·HPA를 공유하도록 설계했다.

![CPU 부하와 대기 부하가 HPA에 미치는 영향](/images/week03-cpu-wait-comparison.svg)

세 가설을 구분한다.

1. **연산형:** CPU 사용률이 요청 대비 상승하면 CPU HPA가 반응할 수 있다. 그러나 증설 효과는 노드 여유 용량·준비 시간·부하 분산에 좌우된다.
2. **대기형:** p95가 커져도 CPU 이용률은 낮을 수 있다. 이때 CPU HPA는 실제 지연에 둔감할 수 있으므로 queue나 in-flight requests 같은 다른 지표가 필요하다.
3. **초기화형:** Desired replicas가 늘었다고 요청을 받을 수 있는 Ready replicas가 동시에 늘지는 않는다. 모델 로딩이 길수록 차이가 커진다.

**반증 조건:** CPU load에서도 HPA가 반응하지 않으면 먼저 metrics-server, CPU requests, 지속 부하 시간, 최대 replica 제한을 확인한다. Wait load에서도 CPU가 상승하면 부하 생성기·애플리케이션 구현·HTTP 요청 처리 비용을 분리해서 측정한다. 기대한 결과를 강제로 맞추지 않는다.

## 4. 단계별 실행 환경

Mac Apple Silicon + 기존 kind 클러스터를 기준으로 한다. 2주차에서 사용한 클러스터가 남아 있다면 새로 생성할 필요가 없다.

```bash
kind get clusters
kubectl config current-context
kubectl get nodes -o wide
kubectl get apiservices | grep metrics.k8s.io || true
kubectl top nodes || true

docker build -t week03-infer:local labs/week03
kind load docker-image week03-infer:local --name myk8s
kubectl create ns week03 --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f labs/week03/deployment.yaml
kubectl apply -f labs/week03/hpa.yaml
kubectl -n week03 rollout status deploy/infer-api
kubectl -n week03 get deploy,pod,svc,hpa -o wide
```

> `myk8s`는 예시 클러스터 이름이다. `kind get clusters` 결과와 다르면 실제 이름으로 교체한다. metrics-server 설치와 통신이 완료되지 않으면 CPU 기반 HPA 실험이 불가능하다. 또한 macOS에서 `kubectl`과 `kind`를 실행하는 것과 노드 내부 Linux 컨테이너에서 실행하는 것은 별개다.

## 5. 관측 지표와 기록 방식

| 관측 항목 | 정의 | 실수하기 쉬운 점 |
|---|---|---|
| RPS | 완료된 요청 수 ÷ 벽시계 시간 | 성공 RPS와 전체 완료 RPS 구분 |
| p95 latency | 전체 요청 지연의 95백분위 | 실패 요청 포함 여부를 명시 |
| 오류율 | 실패 요청 ÷ 전체 요청 | timeout도 실패로 집계 |
| HPA desired/current | autoscaler의 목표/현 상태 | Ready Pod 수와 동일하지 않음 |
| CPU utilization | 측정 CPU 사용량 ÷ requests.cpu | CPU limit 기준이 아님 |
| Ready latency | 생성부터 Ready까지 시간 | 모델 워밍업 후 실제 정상 응답 시점은 별도 |
| Endpoint readiness | EndpointSlice의 condition | 기존 연결의 즉시 종료를 보장하지 않음 |

### 정량 비교 기록 양식

| 실험 | 조건 | RPS | p95 ms | 에러율 | Ready replicas | HPA 목표 |
|---|---|---|---|---|---|---|
| 기준선 | 2 Pod, low concurrency | 미실행 | 미실행 | 미실행 | 미실행 | 미실행 |
| A | CPU, 높은 동시성 | 미실행 | 미실행 | 미실행 | 미실행 | 미실행 |
| B | 500ms wait, 동일 동시성 | 미실행 | 미실행 | 미실행 | 미실행 | 미실행 |
| C | 모델 준비 지연 시뮬레이션 | 미실행 | 미실행 | 미실행 | 미실행 | 미실행 |

## 6. CH6과 CH7을 운영 의사결정으로 연결하기

| 원인 | 우선순위 높은 조치 | 조건·주의 |
|---|---|---|
| CPU 포화 | HPA 또는 효율적인 병렬화 | 스케줄 가능한 노드 용량과 실행 준비 확인 |
| GPU 추론 큐 | batching, queue-aware autoscaling | GPU util만으로 TTFT·ITL 보장 안 됨 |
| 모델 로딩 지연 | startupProbe, readiness, prewarming | 너무 이른 Ready 금지 |
| 외부 API 병목 | timeout, pool, backpressure, circuit breaker | Pod 복제가 외부 API 압박을 키울 수 있음 |
| Endpoint 없음 | selector, Pod 상태, readiness 확인 | Service IP 정상이어도 백엔드 0개 가능 |
| 외부 HTTP 오류 | host/path, controller, TLS, DNS 확인 | Ingress YAML만으로 라우팅 불가 |

## 7. 운영 중 확인할 질문

**Q1. HPA를 걸면 갑작스러운 요청 폭주도 해결될까?** 관측→판단→Pod 생성→스케줄→이미지·모델 로딩→Ready까지 지연이 있다. 최소 replica·예열·부하 차단·큐잉을 함께 고려한다.

**Q2. VPA와 HPA를 동시에 켜도 될까?** 동일 CPU·메모리 자원을 동시에 조정하면 상호 영향이 있을 수 있다. VPA 권고 모드로 requests를 분석하거나 다른 지표로 HPA를 구성하는 등의 분리를 검토한다.

**Q3. Pod가 Ready면 추론 가능한가?** 반드시 그렇지 않다. readiness가 실제 모델 로딩·핵심 의존성 상태를 반영하도록 설계해야 한다. 너무 무거운 readiness 자체도 비용이다.

**Q4. CoreDNS가 장애를 일으키면?** DNS 해석 실패와 이미 얻은 ClusterIP로의 연결 실패를 분리하고, `ndots`, search domain, NodeLocal DNSCache를 살핀다.

**Q5. Ingress에서 Gateway API로 옮기면 성능이 빨라지나?** API 모델은 라우팅·역할 분리를 개선하지만 성능은 실제 컨트롤러 구현·설정·트래픽 패턴에 따라 달라진다.

## 8. BentoML 서빙과 모델 모니터링

확장과 라우팅은 처리량과 가용성을 다룬다. [11. BentoML 서빙과 모델 모니터링](/ml-platform/week03-model-serving-drift)에서는 별도로 입력 분포, 예측값 분포, 실제 성능을 나누어 확인한다. 교재 CH6~7에서 확장한 응용 학습이다.

## 9. 이번 주 결론

**확장은 숫자를 늘리는 작업이 아니라 병목을 분류하고, 트래픽을 받을 준비가 된 용량을 확보하는 작업이다.** 2주차의 모델 선택·재현성 기준을 3주차의 추론 서비스에서도 유지하려면 모델 버전, Pod 준비 시각, Service 경로, 정량 성능을 하나의 운영 기록으로 연결해야 한다.

추가 참고: [Kubernetes HPA](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/) · [Services](https://kubernetes.io/docs/concepts/services-networking/service/) · [EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/) · [Gateway API](https://gateway-api.sigs.k8s.io/)
