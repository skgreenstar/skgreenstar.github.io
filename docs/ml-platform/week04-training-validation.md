---
title: "14 · Pod는 왜 모으고, 왜 분산해야 할까?"
outline: deep
prev: { text: '13 · Node 선택', link: '/ml-platform/week04-artifacts' }
next: { text: '15 · Pod Pending 진단', link: '/ml-platform/week04-storage' }
---

# 14 · Pod는 왜 모으고, 왜 분산해야 할까?

CH8.2 Placing Pods

**Pod의 개수가 같아도 장애 허용 범위는 다를 수 있다.** 추론 API가 세 개의 replica를 갖더라도 같은 Node에서 실행된다면 Node 한 대의 장애로 모두 중단될 수 있다. 반대로 서로 통신이 많은 서비스들을 지나치게 분리하면 네트워크 지연과 비용이 증가한다.

## 1. Node 배치와 Pod 관계를 분리해 생각하기

~~~text
Zone A                            Zone B
  node-a1: infer-0, cache-0          node-b1: infer-2
  node-a2: infer-1                   node-b2: cache-1
~~~

Node Affinity는 Node **자체의 속성**으로, Pod Affinity/Anti-Affinity는 **다른 Pod의 위치**로 배치를 결정한다. Topology Spread는 특정 레이블을 가진 Pod 수를 각 도메인에서 얼마나 균형 있게 유지할지를 결정한다.

| 제어 방법 | 질문 | 예시 |
|---|---|---|
| Node Affinity | 어떤 하드웨어인가? | NVMe 또는 GPU |
| Pod Affinity | 어떤 Pod 근처인가? | 읽기 API와 캐시 같은 Zone |
| Pod Anti-Affinity | 어떤 Pod와 떨어져야 하나? | 추론 replica는 다른 Node |
| Topology Spread | 몇 개씩 분산해야 하나? | Zone 간 maxSkew=1 |

## 2. Pod Affinity: 함께 배치

~~~yaml
spec:
  affinity:
    podAffinity:
      preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 75
        podAffinityTerm:
          labelSelector:
            matchLabels:
              app: feature-cache
          topologyKey: topology.kubernetes.io/zone
~~~

위 항목은 Pod spec에 삽입하는 예제다. feature-cache가 실행 중인 **같은 Zone을 선호**한다. 필수가 아닌 선호 조건이므로 캐시 Pod가 없어도 다른 스케줄링 조건을 만족하면 배치될 수 있다. 근접성을 강제할 필요가 없다면 네트워크 효율과 가용성의 균형을 위해 preferred를 고려한다.

## 3. Pod Anti-Affinity: 장애 도메인을 분리

~~~yaml
spec:
  affinity:
    podAntiAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
      - labelSelector:
          matchLabels:
            app: inference
        topologyKey: kubernetes.io/hostname
~~~

추론 Pod들이 같은 Node에 놓이지 않도록 강제하는 예시다. Node가 두 개뿐인데 replica를 세 개 요구하면 세 번째 Pod가 Pending이 될 수 있다. **고가용성 제약은 배치 가능한 Node 수보다 강하면 가용 용량을 오히려 줄인다.**

Pod 레이블의 namespace 범위와 topologyKey의 실제 레이블 존재 여부가 중요하다. Zone 단위 강제 Anti-Affinity는 환경의 admission 정책 제약도 확인해야 한다.

## 4. TopologySpreadConstraints: 분산의 편차를 수치화

~~~yaml
spec:
  topologySpreadConstraints:
  - maxSkew: 1
    topologyKey: topology.kubernetes.io/zone
    whenUnsatisfiable: DoNotSchedule
    labelSelector:
      matchLabels:
        app: inference
~~~

이 항목도 Pod spec에 삽입한다. 대상 Pod가 실행되는 eligible topology domain 사이의 차이를 제한한다. 여기서 skew는 단순히 전체 Pod를 전체 Node 수로 나눈 편차가 아니다. **eligible domains, minDomains, node affinity 및 taint 정책**에 영향을 받는다.

- DoNotSchedule: 배치 조건을 충족하지 못하는 Node는 제외.
- ScheduleAnyway: 불균형을 줄이는 방향으로 선호도를 부여하지만 배치를 금지하지 않음.
- maxSkew: 1: 대상 Pod 집합의 허용 불균형 크기.

두 수준의 균형이 필요하다면 hostname과 zone 제약을 별도 항목으로 결합할 수 있다.

## 5. RollingUpdate와 Pod 배치가 충돌할 때

Pod Anti-Affinity를 required로 설정하고 이미 모든 eligible Node가 사용 중인 상태에서 RollingUpdate의 maxSurge로 새 Pod가 만들어지면 새 Pod의 배치가 제한될 수 있다. 서비스의 Ready Pod 수를 유지하면서 업데이트할 여유 Node가 없기 때문이다.

롤링 업데이트 이전에 **추가 Pod를 놓을 Node가 있는지**, maxSurge/maxUnavailable과 Anti-Affinity가 충돌하지 않는지 확인해야 한다. PDB는 자발적 중단에 대한 보호 수단이지 어떤 상황에서도 가용성을 보장하는 장치는 아니다.

## 6. 운영 정책 선택

| 워크로드 | 우선 고려할 제약 | 주의할 점 |
|---|---|---|
| 실시간 inference API | Node/Zone Topology Spread | 새 Pod가 Pending되지 않을 여유 용량 |
| GPU 학습 Job | Node affinity + GPU 요청 | GPU 비용·리소스 단편화 |
| API + feature cache | soft Pod affinity | 같은 Zone에 장애 집중 가능 |
| 분산 DB | StatefulSet + topology + 개별 PVC | 저장소 토폴로지와 복제 방식 |
| 비중요 배치 Job | 선호 조건 중심 | 재시도·checkpoint |

## 요약

**가까워야 성능이 좋아지는 Pod와 멀어져야 가용성이 좋아지는 Pod를 구분**한다. 배치 제약은 replica 증가, 롤링 업데이트, 볼륨 topology와 함께 고려해야 한다.

[4주차 학습 정리](/ml-platform/study-week-04)

참고: [Inter-Pod Affinity](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/#inter-pod-affinity-and-anti-affinity) · [Pod Topology Spread](https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints/)
