---
title: "Week 02 · Kubernetes 운영 자동화와 리소스 최적화"
description: "CH4~5 핵심 개념과 운영 실험, KServe·vLLM 모델 서빙을 연결하는 2주차 학습 정리"
date: 2026-11-01
outline: deep
prev:
  text: '1주차 · ML 시스템의 기반'
  link: '/ml-platform/study-week-01'
next:
  text: '04. 컨테이너가 실행 중이면 서비스도 정상일까?'
  link: '/ml-platform/week-04'
---

# Week 02 · Kubernetes 운영 자동화와 리소스 최적화

**학습 범위:** CH4–5 · 운영 자동화, 리소스 관리 + KServe·vLLM 확장 학습

1주차에서 검증된 모델을 배포하는 흐름을 살펴봤다면, 이번에는 **배포한 서비스가 언제 요청을 받고, 어떻게 교체되며, 어느 정도의 자원으로 동작해야 하는지**를 연결한다. 개념과 실습은 세 편의 상세 글로 나누고, 이 페이지에서는 전체 흐름과 학습 기준을 정리한다.

> **학습 방식:** 핵심 개념 → 동작 구조 → 가설 → kind 실습 → 관찰/해석. 실제 실행 결과는 별도 기록하고, 후속 실습의 예상 동작과 구분한다.

::: tip 이번 주 학습 목표
- Startup / Readiness / Liveness Probe의 역할을 구분하고 장애를 재현한다.
- RollingUpdate·Recreate의 가용성 차이를 검증하고 롤백한다.
- CPU·Memory Requests/Limits, QoS와 자원 경합을 관찰한다.
- AI 모델 서빙에 적용할 때의 설계 선택을 설명한다.
:::

## 실제 kind 실습 결과 · Readiness와 Liveness

기존 로컬 FastAPI 기준선에 이어, 개인 PC의 **kind 클러스터에서 Probe 앱을 배포하고 Readiness 장애·복구를 실행**했다. 아래 기록은 PC 터미널에서 실행한 출력을 바탕으로 정리했다.

| 환경 | 확인값 |
|---|---|
| Docker | Linux / aarch64 |
| kind 클러스터 / 컨텍스트 | `mlops-lab` / `kind-mlops-lab` |
| 노드 / Kubernetes | `mlops-lab-control-plane` · Ready / v1.37.0 |
| 컨테이너 런타임 | containerd 2.3.4 |
| 실습 대상 | `week02` 네임스페이스 · `probe-demo` Deployment |

| 단계 | 관찰한 HTTP 응답 | Pod 상태 | RESTARTS | EndpointSlice |
|---|---|---|---:|---|
| 정상 배포 | HTTP 응답 별도 수집 없음 | `1/1 Running` | 0 | `ready=true` |
| Readiness 장애 주입 | `/healthz=200`, `/readyz=503` | `0/1 Running` | 0 | `ready=false` |
| 정상 복구 | `/traffic-on=200` | `1/1 Running` | 0 | `ready=true` |

**확인한 점:** 동일 Pod가 Running 상태를 유지한 채 Ready만 변경됐고, 재시작 횟수는 0으로 유지됐다. EndpointSlice의 주소는 남아 있으면서 `ready` 조건이 false로 변경됐다가 복구됐다.

이번 기록은 **Pod와 EndpointSlice의 상태 전환**을 확인한 결과다. Service 경유 실제 요청의 성공·실패, Recreate, CPU 제한·OOM은 아직 결과를 수집하지 않았다.

**Liveness 재시작·복구 확인:** `/server-error` 호출 후 HTTP 503 실패 감지 → `Killing` 이벤트를 확인했고, 후속 조회에서 동일 Pod의 `RESTARTS=1`, `1/1 Running`을 확인했다. 이전 컨테이너 종료 기록은 `lastReason=Error exitCode=137`이었다. 앞선 Liveness 이벤트와 함께 재시작 경위를 해석하며, 종료 코드 137만으로 OOM을 판정하지 않는다.

**RollingUpdate 완료:** `maxSurge=1`, `maxUnavailable=0`에서 `LAB_VERSION=v2`를 추가했다. 새 Pod가 Pending → ContainerCreating → Running(0/1) → Running(1/1) 순서로 준비된 후 기존 Pod가 Terminating으로 전환됐다. 새 Pod의 `LAB_VERSION=v2`와 revision 1 → 2를 확인했다. 이는 Pod 교체 순서의 검증이며 실제 요청의 무중단 성공을 측정한 결과는 아니다. **롤백도 완료했다.** revision 1을 지정해 되돌린 뒤 새 Pod의 `1/1 Running`, `LAB_VERSION=(unset)`과 새 revision 3을 확인했다. 기존 revision 1 템플릿을 재사용하며 이력 번호는 새로 부여됐다. `last-applied-configuration` 미갱신 경고는 별도로 기록했다.

[실행 명령과 터미널 출력 보기](/ml-platform/week-04#kind-readiness-result)

## 1. 운영 자동화에서 모델 서빙까지

| 주제 | 핵심 질문 | 상세 글 |
|---|---|---|
| 운영 자동화 · CH4 | 언제 트래픽을 받고, 언제 재시작하며, 어떻게 교체하는가? | [04. 컨테이너가 실행 중이면 서비스도 정상일까?](/ml-platform/week-04) |
| 리소스 관리 · CH5 | 자원 설정과 복제본 수가 성능·가용성에 미치는 영향은? | [05. 리소스 설정은 성능과 안정성을 어떻게 바꿀까?](/ml-platform/week-05) |
| 모델 서빙 · 확장 | Kubernetes 운영 원칙을 ML·LLM 서비스에 어떻게 적용하는가? | [06. KServe와 vLLM으로 모델을 어떻게 운영할까?](/ml-platform/week-06) |

## 2. Probe·배포·자원 설정을 하나의 운영 구조로 보기

![Kubernetes 운영 구조](/diagrams/week02-architecture.svg)

| 설정 | 핵심 질문 | Kubernetes 동작 |
|---|---|---|
| startupProbe | 초기화가 끝났는가? | 성공 전 liveness/readiness 검사 지연, 지정 횟수 실패 시 재시작 |
| readinessProbe | 지금 트래픽을 받을 수 있는가? | 실패 시 Service의 정상 Endpoint에서 제외 |
| livenessProbe | 현재 컨테이너를 재시작해야 하는가? | 연속 실패 임계값 충족 시 컨테이너 재시작 |
| requests | 어디에 배치할 수 있는가? | Scheduler의 자원 적합성 판단 기준 |
| limits | 얼마나 쓸 수 있는가? | CPU quota 기반 제어, Memory 초과 시 OOM 가능 |

## 3. 개념에서 실험으로 연결하기

1. **상태를 구분한다.** Startup·Readiness·Liveness로 초기화, 트래픽 수신, 재시작 조건을 나눈다.
2. **변경을 제어한다.** RollingUpdate·Recreate를 비교하고 롤백 경로를 확인한다.
3. **자원을 설계한다.** Requests/Limits와 QoS, Replica·Worker 구성을 함께 살펴본다.
4. **사용자 영향을 측정한다.** 로컬 기준선과 운영 가설 실험을 통해 지연시간·오류율·회복시간을 비교한다.
5. **모델 서빙에 적용한다.** KServe와 vLLM에서 모델 로딩, GPU 자원, 긴 스트리밍 요청을 고려한다.

실습 명령과 배포 예제는 [운영 자동화 글](/ml-platform/week-04)에, **기존 로컬 측정값·그래프와 심화 실험 절차**는 [리소스 관리 글](/ml-platform/week-05)에 모았다. KServe·vLLM의 개념과 실무 지표는 [모델 서빙 글](/ml-platform/week-06)에서 이어서 읽을 수 있다.

## 4. 학습하며 확인한 질문

**Q. Readiness와 Liveness는 왜 별도 엔드포인트여야 할까?**

A. 외부 서비스가 잠깐 실패한 상황과 실제 프로세스 교착을 구분하기 위해서다. 외부 의존성 오류를 무조건 Liveness 실패로 연결하면 불필요한 재시작이 이어질 수 있다.

**Q. `maxUnavailable: 0`이면 모든 요청이 반드시 성공할까?**

A. 아니다. 준비 상태와 실제 요청 성공에는 종료 처리, 커넥션 draining, 앱 오류, 노드 문제 등의 차이가 존재한다.

**Q. CPU Limits를 없애면 모든 문제가 해결될까?**

A. CPU quota로 인한 throttling은 줄일 수 있지만, 노드 경쟁·테넌트 간 간섭·비용·SLO 문제는 따로 고려해야 한다.

## 5. 실험 결과 해석과 회고

이번 실습에서 확인할 핵심 가설은 **'설정값을 조정하면 단순히 자원 사용량만 달라지는 것이 아니라, 가용성과 업데이트 성공 여부도 바뀐다'**는 것이다.

실험마다 스크린샷과 `kubectl get/describe/logs`를 추가한 후 아래 질문에 답한다.

1. Readiness 실패 중 컨테이너는 살아 있는데 요청은 왜 실패했는가?
2. Startup Probe가 없으면 초기화가 긴 모델 서버에 어떤 일이 생기는가?
3. maxUnavailable=0인데 롤아웃이 멈추는 조건은 무엇인가?
4. CPU throttling이 Health Probe 실패로 이어질 수 있는가?
5. replicas와 worker 수를 어떻게 정해야 단일 장애 영향과 메모리 비용 사이에서 균형을 얻는가?

**개인적 정리:** Kubernetes의 운영 자동화는 실패를 없애는 기능이 아니라, 실패를 올바르게 판단하고 사용자 영향 범위를 최소화하도록 설계하는 기능이다. Probe, 배포 전략, 자원 설정은 별도의 YAML 항목이 아니라 하나의 SLO를 달성하기 위한 연관된 결정들이다.

## 실습 코드 및 참고자료

실험은 이론 이해를 위한 기초 검증과 성능·가용성 비교를 위한 심화 실험으로 구분했다. 실제 측정 결과를 얻으면 [리소스 관리와 성능 실험 글](/ml-platform/week-05)에 로그와 그래프를 추가한다.

- [기초 실습 코드 · Probe와 Deployment](https://github.com/skgreenstar/skgreenstar.github.io/tree/main/docs/ml-platform/week-02-lab)
- [심화 실험 코드 · FastAPI / k6 / 결과 분석](https://github.com/skgreenstar/skgreenstar.github.io/tree/main/docs/ml-platform/week-02-advanced)

::: details 공식 문서 참고
- [Kubernetes Health Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)
- [Deployment와 롤링 업데이트](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [컨테이너 리소스 관리](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)
- [Pod QoS](https://kubernetes.io/docs/concepts/workloads/pods/pod-qos/)
:::

