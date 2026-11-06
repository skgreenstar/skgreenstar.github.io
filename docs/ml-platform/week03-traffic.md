---
title: "10 · 요청은 어느 Pod까지 도달하는가?"
outline: deep
prev:
  text: '09 · 추론 부하와 확장'
  link: '/ml-platform/week03-autoscaling'
---

# 10 · 요청은 어느 Pod까지 도달하는가?

## 1. ClusterIP와 Endpoint를 다르게 보기

Service가 살아 있다는 사실만으로 모든 Pod가 요청을 처리할 수 있는 것은 아니다. Pod의 readiness와 EndpointSlice의 상태를 확인한다.

```bash
kubectl -n week03 get svc infer-api -o wide
kubectl -n week03 get pods -l app=infer-api -o wide
kubectl -n week03 get endpointslice -l kubernetes.io/service-name=infer-api -o yaml
kubectl -n week03 port-forward svc/infer-api 8080:80
# 다른 터미널
curl -fsS http://localhost:8080/readyz
curl -fsS 'http://localhost:8080/infer?mode=wait'
```

## 2. Readiness와 라우팅 장애 실험

1. 모든 Pod Ready·EndpointSlice ready=true 상태를 저장한다.
2. `READY_DELAY_SECONDS` 환경변수를 이용해 준비가 지연된 새 Pod 배포를 시험한다.
3. 생성 시각과 ready=true가 된 시각의 차이를 기록한다.
4. EndpointSlice 및 Service 경유 요청의 성공 여부를 대조한다.
5. 이미 맺어진 장기 연결과 새로운 연결의 경로는 별도로 해석한다.

현재 제공된 API에는 readiness를 **강제로 실패시키는 런타임 토글은 없다**. 시작 시 지연 후 Ready 전환하는 동작으로 확인한다. 동적 readiness 강제 실패와 복구 실험은 별도 코드 보완이 필요하다.

## 3. DNS·Ingress·Gateway API

ClusterIP는 클러스터 내부 서비스 접근에 사용한다. DNS `infer-api.week03.svc.cluster.local`과 실제 Pod IP를 구별한다. 외부 호스트·경로 라우팅은 Ingress Controller 또는 Gateway API 구현체가 있어야 작동한다. 단순히 Ingress/HTTPRoute YAML만 만드는 것은 실제 노출 검증이 아니다.

Gateway API의 GatewayClass·Gateway·HTTPRoute는 역할과 라우팅 정책을 분리하지만 구현체 설치와 ReferenceGrant 등 교차 namespace 권한 조건이 중요하다. TLS Secret에는 실제 운영 인증 정보를 GitHub에 노출하지 않는다.

## 4. 검증 기록

| 관찰 | 기대 | 실제 상태 |
|---|---|---|
| 생성 직후 readiness 지연 | 미준비 Endpoint 제외 | 미실행 |
| 준비 완료 | Ready Endpoint 등록 | 미실행 |
| Service 경유 호출 | Ready 대상 호출 | 미실행 |
| Ingress 외부 접근 | 구현체 설정 후 가능 | 선택 실습·미실행 |

[3주차 학습 정리로 돌아가기](/ml-platform/study-week-03)
