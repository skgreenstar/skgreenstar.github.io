---
title: "10 · 요청은 어느 Pod까지 도달하는가?"
outline: deep
prev:
  text: '09 · 확장 전략'
  link: '/ml-platform/week03-autoscaling'
---

# 10 · 요청은 어느 Pod까지 도달하는가?

**CH7 Internal Services and Load Balancing · 서비스 발견 → 라우팅 → 장애 추적**

Pod 수가 늘어나도 Service가 올바른 백엔드를 선택하지 못하면 요청은 실패한다. DNS부터 서비스 엔드포인트 선택, 외부 HTTP 라우팅까지 순서대로 확인한다.

## 1. 요청 경로를 계층별로 분리한다

![요청 한 건이 추론 Pod에 도착하기까지](/images/week03-traffic-architecture.svg)

*트래픽 경로와 컨트롤 플레인의 상태 정보를 함께 표현했다. EndpointSlice는 요청이 직접 통과하는 프록시가 아니다.*

| 단계 | 역할 | 검사 질문 |
|---|---|---|
| CoreDNS | 클러스터 내부 서비스 이름 해석 | FQDN이 ClusterIP로 해석되는가? |
| Service | 안정적인 VIP와 백엔드 연결 | selector가 올바른 Pod를 선택하는가? |
| EndpointSlice | 백엔드 주소와 readiness 조건 보관 | Ready endpoint가 실제로 존재하는가? |
| kube-proxy / 네트워크 구현 | 서비스 트래픽 전달 | 정책·프록시 규칙·CNI 영향이 있는가? |
| Ingress/Gateway | 외부 트래픽 수신·라우팅 | 컨트롤러, host/path, TLS가 정상인가? |

Service는 L4 연결 전달의 추상화이며, 항상 균등하게 **HTTP 요청 단위**로 라운드로빈한다고 가정하면 안 된다. 연결 재사용과 세션 유지·클라이언트 동작에 따라 Pod별 요청 수가 달라질 수 있다.

## 2. ClusterIP / NodePort / LoadBalancer 비교

| 유형 | 접근 방식 | 적합한 경우 | 오해 방지 |
|---|---|---|---|
| ClusterIP | 클러스터 내부 IP·DNS | 내부 모델 API, feature service | 인터넷에 직접 노출되지 않음 |
| NodePort | Node의 특정 포트 | 로컬 테스트·외부 LB의 백엔드 | 운영 보안과 노출 범위 검토 |
| LoadBalancer | 제공업체 로드 밸런서 연계 | 외부 서비스 | kind에 클라우드 LB가 자동 생성되지는 않음 |
| Headless | ClusterIP 없이 endpoint 발견 | Stateful 서비스·클라이언트 측 선택 | VIP 부하 분산과 다름 |

우리 모델 API는 기본적으로 **ClusterIP만** 사용한다. 이는 내부 API 구성에 유리하며, 외부 트래픽을 받으려면 Ingress/Gateway 또는 별도 접속 경로가 필요하다.

## 3. DNS가 정상이어도 Pod가 응답하지 않을 수 있다

내부 FQDN 예: `infer-api.week03.svc.cluster.local`

```bash
kubectl -n week03 get svc infer-api -o wide
kubectl -n week03 get pods -l app=infer-api -o wide
kubectl -n week03 get endpointslice -l kubernetes.io/service-name=infer-api -o yaml

# 임시 진단 Pod로 내부 DNS 확인
kubectl -n week03 run dns-check --rm -i --restart=Never \
  --image=busybox:1.36 -- nslookup infer-api.week03.svc.cluster.local

# 내부 호출 (BusyBox wget 지원)
kubectl -n week03 run http-check --rm -i --restart=Never \
  --image=busybox:1.36 -- wget -qO- http://infer-api.week03.svc.cluster.local/readyz
```

이 명령에서 이미지 pull이 실패하거나 클러스터 밖으로 접근 불가하면 그것은 **진단 도구 실행 실패**다. 즉시 DNS 장애라고 판정하지 않는다.

### CoreDNS가 느리거나 실패할 때

```bash
kubectl -n kube-system get deploy,pods -l k8s-app=kube-dns
kubectl -n kube-system logs deploy/coredns --tail=80
kubectl -n week03 get pods -o wide
```

Pod의 `/etc/resolv.conf` search domain, `ndots`로 인한 불필요한 질의, 외부 DNS 대기, CoreDNS 포화, NodeLocal DNSCache 적용 여부를 분리해 본다. NodeLocal DNSCache는 DNS 캐시 계층을 추가하는 접근이지 모든 네트워크 장애를 자동 해결하는 기능은 아니다.

## 4. EndpointSlice와 Readiness의 관계

![Readiness와 EndpointSlice 상태의 갱신 과정](/images/week03-readiness-sequence.svg)

Kubelet이 readinessProbe 결과를 Pod 상태에 반영하면 컨트롤 플레인이 EndpointSlice 상태를 갱신한다. 서비스 트래픽 전달 계층은 준비된 엔드포인트 정보를 활용하며, 기존 연결을 즉시 끊는다는 뜻은 아니다.

우리 API의 `READY_DELAY_SECONDS` 설정으로 시작 단계의 모델 예열을 *모의*할 수 있다. 같은 Pod에서 readiness를 임의로 토글하는 별도 API는 아직 구현돼 있지 않다.

```bash
# 예열 지연을 추가해 새 Pod의 Ready 전환을 관찰
kubectl -n week03 set env deployment/infer-api READY_DELAY_SECONDS=20
kubectl -n week03 rollout status deployment/infer-api
kubectl -n week03 get pods -w

# 다른 터미널에서 EndpointSlice 변화 확인
kubectl -n week03 get endpointslice \
  -l kubernetes.io/service-name=infer-api -w

# 원래 설정으로 복원
kubectl -n week03 set env deployment/infer-api READY_DELAY_SECONDS-
kubectl -n week03 rollout status deployment/infer-api
```

**측정 범위:** Pod 생성, Ready 변환, endpoint 등록, 실제 신규 요청 응답을 시간순으로 기록해야 한다. `kubectl get` 출력의 AGE만으로 정확한 중단 시간이나 요청 실패 비율을 측정했다고 표현하지 않는다.

## 5. 내부 서비스 간 통신: 분리와 연결

2주차 모델 운영 서비스를 여러 컴포넌트로 나누었다고 가정하자.

![추론 API와 내부 피처 서비스의 호출 관계](/images/week03-internal-services.svg)

서비스 분리에는 서로 다른 배포 주기, 독립 확장, 장애 격리라는 장점이 있다. 그 대가로 네트워크 왕복, 인증, timeout, 재시도, 버전 호환성 문제가 생긴다. 특히 Agent처럼 다단계 요청을 호출할 경우 타임아웃과 재시도의 곱셈 효과를 계산해야 한다.

**서비스 통신 계약에 포함할 것:** URL/FQDN, timeout, idempotency, retry budget, correlation ID, 모델 버전, 응답 스키마, health/readiness 의미.

## 6. Ingress: 외부 HTTP를 내부 Service에 연결

```yaml
# 예제: Ingress Controller가 설치된 클러스터에서만 작동
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: infer-api
  namespace: week03
spec:
  ingressClassName: nginx
  rules:
    - host: infer.local.test
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: infer-api
                port:
                  number: 80
```

Ingress 리소스 생성과 **실제 Controller 운영은 별개**다. kind의 네트워크 포트 매핑, Controller 설치·버전·IngressClass, host DNS 또는 Host header, Service endpoint까지 확인해야 한다. 특정 ingress-nginx 릴리스가 해당 Kubernetes 버전을 지원하는지 확인 없이 예전 manifest를 그대로 적용하지 않는다.

### TLS 종료

클라이언트에서 Ingress로 들어오는 HTTPS를 TLS termination하는 경우, Ingress는 인증서와 키를 참조한다. 테스트용 self-signed 인증서는 신원 검증을 제공하지 못하므로 운영에 그대로 사용하지 않는다.

```bash
# 발급된 실제 인증서/키 파일이 있을 때의 명령 형태
kubectl -n week03 create secret tls infer-tls \
  --cert=path/to/tls.crt --key=path/to/tls.key
```

**인증서 개인키는 GitHub 저장소에 커밋하지 않는다.** TLS를 Ingress에서 종료하면 Ingress 이후 Service까지의 트래픽이 자동으로 암호화되는 것도 아니다. 내부 구간 암호화가 필요하다면 별도 설정이 필요하다.

## 7. Gateway API가 추가하는 설계 차이

기존 Ingress는 단순 HTTP 호스트/경로 라우팅에 편리하다. Gateway API는 **인프라 제공자·클러스터 운영자·애플리케이션 개발자의 역할**과 경로 정책을 더 세밀하게 나눈다.

| 리소스 | 담당 역할 | 예 |
|---|---|---|
| GatewayClass | Gateway 구현/클래스 | 관리형 Gateway Controller |
| Gateway | Listener·접속점 | 80/443 포트 |
| HTTPRoute | host/path/header 기반 HTTP 라우팅 | `/infer` → 모델 Service |
| ReferenceGrant | 허용된 교차 namespace 참조 | 다른 namespace의 backend 참조 |
| Service | 최종 backend | infer-api:80 |

![GatewayClass · Gateway · HTTPRoute의 관계](/images/week03-gateway-roles.svg)

운영 전략상 여러 팀이 공용 Gateway를 쓰고 각 팀이 자신의 HTTPRoute를 관리하게 하는 구조를 생각할 수 있다. 다만 실제 분리와 권한 모델은 `allowedRoutes`, RBAC, Controller 정책에 달려 있다. Gateway API 리소스만 설치했다고 보안 격리가 완성되는 것은 아니다.

### 무엇을 선택할까?

- 단순하고 검증된 기존 HTTP 진입점이면 Ingress도 충분하다.
- 여러 팀의 역할 분리, 복잡한 라우팅 정책, 확장 가능한 공용 진입점이 필요하면 Gateway API를 검토한다.
- **성능 비교는 실제 Controller, 동시성, 요청 크기, TLS 조건을 통제한 다음**에 가능하다. Gateway API 사용 자체가 지연 감소를 보장하지 않는다.

## 8. 요청 실패 시 진단 순서

![추론 요청 실패 시 진단 순서](/images/week03-traffic-diagnosis.svg)

이 순서로 로그·이벤트·메트릭을 확보하면 '모델 서버가 느리다'와 '모델 서버까지 요청이 도착하지 않았다'를 구분할 수 있다.

## 9. 현재 검증 상태와 기록 양식

| 관찰 | 필요한 증거 | 상태 |
|---|---|---|
| Service DNS 해석 | nslookup 실제 출력 | 미실행 |
| Ready endpoint | EndpointSlice conditions | 미실행 |
| 준비 지연 시 변화 | Pod/Endpoint 타임라인 | 미실행 |
| Ingress 접근 | controller/log/curl/host | 미실행 |
| Gateway API 실험 | Controller와 Route status | 개념 학습만 |

이론을 읽은 것과 클러스터에서 재현한 것을 구분한다. 화면 캡처를 찍었다고 실패 원인이 설명되는 것은 아니므로, **예상 → 실행 명령 → 실제 출력 → 해석 → 한계**를 한 세트로 정리한다.

[3주차 학습 정리로 돌아가기](/ml-platform/study-week-03)

공식 참고: [Services](https://kubernetes.io/docs/concepts/services-networking/service/) · [EndpointSlice](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/) · [Ingress](https://kubernetes.io/docs/concepts/services-networking/ingress/) · [Gateway API](https://gateway-api.sigs.k8s.io/) · [DNS](https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/)
