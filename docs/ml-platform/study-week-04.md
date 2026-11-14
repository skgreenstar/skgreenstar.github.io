---
title: "Week 04 · Pod는 어디에 배치되고 데이터는 어떻게 살아남을까?"
outline: deep
prev:
  text: '3주차 학습 정리'
  link: '/ml-platform/study-week-03'
next:
  text: '13 · Scheduler'
  link: '/ml-platform/week04-scheduler'
---

# Week 04 · Pod는 어디에 배치되고 데이터는 어떻게 살아남을까?

학습 범위: *Machine Learning Platform Engineering* CH8 · Node Feature Selection / CH9 · Stateful Applications

1주차에는 ML Lifecycle과 CI/CD, 2주차에는 MLflow·Feast·KFP, 3주차에는 모델 서빙·HPA·요청 경로를 살펴봤다. 4주차의 질문은 다르다. **학습과 추론 작업이 어떤 Node에서 실행되고, Pod가 없어져도 데이터는 어떻게 살아남는가?**

모델 코드가 정확해도 스케줄링 조건이 충돌하면 학습을 시작할 수 없다. 학습을 마쳐도 영속성과 복구 정책이 없다면 모델 아티팩트와 메타데이터를 잃을 수 있다. 그래서 이번 주는 Node 배치와 데이터 수명을 하나의 문제로 연결한다.

## 1. 전체 아키텍처

![Week 04 · Scheduler와 Storage의 책임 경계](/images/week04-scheduling-storage.svg)

*Node 배치와 데이터 수명을 분리해 보여 주는 개념 아키텍처.*

~~~text
                   ML Platform Workloads
           KFP Job / MLflow / Inference API
                           |
                     API Server
                           |
          ┌────────────────┴────────────────┐
          |                                 |
     CH8 Scheduling                    CH9 Storage
          |                                 |
    Filter → Score → Bind            PVC → PV → CSI
          |                                 |
     Node Affinity                 StatefulSet / Disk
     Taint/Toleration              ReclaimPolicy / Backup
     Pod Affinity / Spread         Ephemeral Storage
          |                                 |
     Pod가 실행될 Node                  데이터 수명
          |                                 |
          └────────────────┬────────────────┘
                           |
                 안정적인 ML 플랫폼 운영
~~~

Scheduler는 Node를 선택하고, kubelet은 볼륨과 컨테이너를 준비한다. PV/PVC와 스토리지 제공자는 파일을 어디에 저장하고 어떤 조건에서 유지할지 결정한다. **스케줄링·실행·영속성은 서로 다른 책임이다.**

## 2. CH8 · Node Feature Selection

### 13. Scheduler의 Filter와 Score

[13 · Scheduler는 어떤 Node에 학습 Pod를 배치할까?](/ml-platform/week04-scheduler)

Pod의 CPU·메모리 requests, Node label, Taint, 필수 Node Affinity를 먼저 검사한다. Filter를 통과한 후보만 선호도를 비교한다. NodeSelector와 required Node Affinity는 필수 조건이고 preferred Node Affinity는 후보들의 Score에 영향을 준다. Toleration은 Taint가 설정된 Node를 허용할 뿐, 그 Node 선택을 강제하지 않는다.

### 14. Pod Affinity와 Topology Spread

[14 · Pod는 왜 모으고, 왜 분산해야 할까?](/ml-platform/week04-pod-placement)

Node Affinity는 Node의 속성을 보고, Pod Affinity/Anti-Affinity는 다른 Pod가 어디에 실행되는지를 본다. Topology Spread는 hostname 또는 zone 수준의 replica 배치 불균형을 제한한다.

서빙 Pod가 셋이어도 모두 같은 Node에 있으면 Node 한 대 장애로 전체가 영향을 받을 수 있다. 반대로 Pod를 반드시 서로 다른 Node에 배치하도록 강제하면 Node가 부족할 때 일부 replica는 Pending에 머무를 수 있다. **가용성 정책과 배치 유연성 사이의 균형**이 필요하다.

### 15. Pending 상태의 원인 분리

[15 · Pod가 Pending일 때 어디부터 진단할까?](/ml-platform/week04-pending-diagnosis)

Pending은 스케줄링 이전뿐 아니라 스케줄링 이후 이미지 Pull과 볼륨 준비 중에도 나타난다. PodScheduled 조건과 Events를 먼저 구분해야 한다.

| 단서 | 관련 계층 | 우선 확인 |
|---|---|---|
| Insufficient cpu/memory | Scheduler | requests / allocatable |
| affinity mismatch | Scheduler | Node label / required policy |
| untolerated taint | Scheduler | taint / toleration |
| topology constraint | Scheduler | topologyKey / maxSkew |
| PVC unbound | Storage / VolumeBinding | PVC / PV / StorageClass |
| FailedMount | Kubelet / CSI | volume topology / mount events |
| ImagePullBackOff | Kubelet / Registry | image, credentials, architecture |

**CH8의 핵심:** Scheduler는 성능·비용·장애 허용 범위를 제어하는 정책 엔진이다.

## 3. CH9 · Stateful Applications

### 16. Persistent Volumes와 StorageClass

[16 · PVC와 StorageClass는 데이터 수명을 어떻게 결정할까?](/ml-platform/week04-persistent-storage)

컨테이너 내부 파일, emptyDir, PVC/PV, 원격 객체 저장소는 모두 데이터 수명이 다르다. RWO는 한 Node에서의 읽기·쓰기를 뜻하며 단일 Pod 접근과 동일하지 않다. 지원되는 CSI 환경에서는 RWOP를 검토할 수 있다.

StorageClass의 Immediate와 WaitForFirstConsumer는 볼륨이 언제 바인딩되는지에 영향을 준다. 특정 Zone에만 존재하는 디스크는 Pod의 Node Affinity와 충돌할 수 있으므로 CH8의 배치 원리와 연결된다.

### 17. StatefulSet과 안정적인 식별자

[17 · StatefulSet은 Deployment와 무엇이 다를까?](/ml-platform/week04-stateful-workloads)

StatefulSet은 순서가 있는 Pod 이름, Headless Service 기반 안정적 DNS, volumeClaimTemplates의 Pod별 독립 PVC를 제공한다. Deployment도 PVC를 사용할 수 있지만 각 replica마다 안정적인 식별자가 필요하다면 StatefulSet이 유리하다.

다만 StatefulSet은 Redis·MariaDB의 데이터 복제, 리더 선출, 애플리케이션 백업을 자동으로 제공하지 않는다.

### 18. Disk Recovery와 Ephemeral Volumes

[18 · 디스크를 어떻게 복구하고 임시 볼륨은 언제 쓸까?](/ml-platform/week04-volume-recovery)

Pod 삭제, StatefulSet 삭제, PVC 삭제, PV 제거, 실제 디스크 손상은 각각 다른 사건이다. PV ReclaimPolicy의 Retain은 회수·재연결 가능성을 남기고 Delete는 PVC 해제 뒤 기반 볼륨을 제거할 수 있다. 하지만 Retain은 백업이 아니므로 데이터 정합성과 복구 가능성을 별도로 관리해야 한다.

emptyDir는 Pod의 수명에 종속되고, Generic Ephemeral Volume은 PVC 기능을 사용하면서 Pod 수명에 연결된다. 최종 모델 가중치와 복구 불가능한 메타데이터를 임시 저장소에만 남기면 안 된다.

**CH9의 핵심:** 영속성은 PVC 하나로 완성되지 않는다. 접근 모드·볼륨 Binding·데이터 수명·복구 정책을 함께 설계한다.

## 4. CH8과 CH9를 함께 봐야 하는 이유

~~~text
Training Job
  ├── Required Node Affinity : zone-b
  └── PVC → PV nodeAffinity : zone-a
                      |
          공통으로 만족하는 Node 없음
                      |
                   Pending
~~~

위 구조는 가상의 설계 사례다. GPU Node를 추가하거나 CPU requests를 줄이는 것으로 해결되지 않는다. 학습 Job을 실행할 Zone과 데이터 디스크를 사용할 수 있는 Zone이 일치하도록 배치와 스토리지를 함께 설계해야 한다.

StatefulSet도 비슷하다. 서로 다른 PVC를 가졌더라도 Pod가 한 Zone에 모이면 Zone 장애에 모두 영향을 받을 수 있다. 데이터 복제와 Pod의 장애 도메인 분산도 별도로 고려해야 한다.

## 5. MLOps에 어떻게 연결할까?

| 워크로드 | CH8 배치 정책 | CH9 저장 정책 |
|---|---|---|
| KFP 데이터 준비 | 범용 CPU Node, requests와 Job 재시도 | 임시 scratch / 불변 원본 데이터 |
| GPU Training | GPU Node, device plugin, taint/affinity | checkpoint / 영속 model artifact |
| MLflow Backend DB | Node·프로브·가용성 | DB volume / backup / restore |
| Feature Cache | 읽기 API와 적절한 거리 | 캐시 재생성 / 필요 시 PVC |
| Inference API | Node/Zone 분산, readiness | 모델 버전 / 로컬 캐시 |
| Model Registry | 서비스 가용성 | DB와 artifact 간 일관성 |

학습·서빙·메타데이터 서비스를 같은 Kubernetes에 배치해도 요구사항은 다르다. 일시적인 Training Job과 지속적인 DB, 복제 가능한 Inference API를 똑같이 배치하면 자원과 저장소를 낭비하거나 장애 위험을 높인다.

## 6. 이번 주 결론

- 배치 가능 여부는 Node 자원의 합계가 아니라 **각 Pod 조건을 만족하는 Node가 실제 존재하는지**로 결정된다.
- 선호 조건은 필수 제약을 우회하지 못하며 Toleration은 Node 선택을 강제하지 않는다.
- replica 수 증가가 가용성 증가를 자동 보장하지 않는다. Node와 Zone 분산을 확인해야 한다.
- StatefulSet의 안정적인 식별성과 독립 PVC는 데이터 복제·백업과 다른 기능이다.
- 저장소의 수명과 위치는 Scheduler의 Node 선택 조건과 함께 작동한다.

**Node 선택은 계산 자원의 계약이고 Volume 설계는 데이터 수명의 계약이다. 이 둘의 조건이 맞아야 ML 플랫폼을 안정적으로 운영할 수 있다.**

이 글은 기술 원리와 YAML·명령어 예제 중심의 학습 정리다. 실행 결과를 꾸며 쓰거나 채우지 않은 검증표를 배치하지 않았다.

참고: [Kubernetes Scheduling](https://kubernetes.io/docs/concepts/scheduling-eviction/) · [Assigning Pods to Nodes](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/) · [Topology Spread](https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints/) · [Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/) · [StatefulSet](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/) · [Ephemeral Volumes](https://kubernetes.io/docs/concepts/storage/ephemeral-volumes/)
