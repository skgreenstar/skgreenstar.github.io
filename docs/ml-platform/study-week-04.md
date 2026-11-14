---
title: "Week 04 · 학습 Pod는 어디에 배치되고 데이터는 어떻게 살아남을까?"
outline: deep
prev:
  text: '3주차 · 학습 정리'
  link: '/ml-platform/study-week-03'
next:
  text: '13 · 데이터 전달'
  link: '/ml-platform/week04-artifacts'
---

# Week 04 · 학습 Pod는 어디에 배치되고 데이터는 어떻게 살아남을까?

교재 범위: *Machine Learning Platform Engineering* CH8 · Node Feature Selection / CH9 · Stateful Applications  
핵심 질문: 학습·추론 Pod를 원하는 하드웨어에 배치하고, 장애에도 상태를 보존하려면 어떤 Kubernetes 조건이 필요한가?  
실행 상태: 아래 구성은 학습·실습 설계다. 실제 실행 로그나 측정값을 확보하기 전에는 실행 결과로 기술하지 않는다.

2주차에는 MLflow·Feast·KFP의 모델·피처 버전 연결을, 3주차에는 추론 서비스의 확장과 트래픽을 살펴봤다. 4주차는 파이프라인 내부의 데이터 이동과 품질 승인으로 돌아간다. **Pipeline Succeeded는 실행 완료이지 모델 승인과 동일하지 않다.**

## 이번 주에 실제로 공부할 핵심 범위

이 주차의 중심은 **CH8 Scheduler/Node Feature Selection과 CH9 Stateful Applications**다. 다른 스터디원의 KFP·MLflow 파이프라인 사례는 앞선 2주차의 연장선에서 연결하는 **응용 학습**으로 분리했다. 공유받은 노션에서 요구하는 주제를 우선해서 학습한다.

| 교재 | 상세 학습 글 | 반드시 이해할 내용 |
|---|---|---|
| CH8.1 | [17 · Filter, Score, Node Affinity](/ml-platform/week04-placement) | Node selector, required/preferred, Taints/Tolerations |
| CH8.2 | [17 · Pod 배치와 Topology Spread](/ml-platform/week04-placement) | Pod Affinity/Anti-Affinity, maxSkew, zone/hostname |
| CH8.3 | [17 · Pending 문제 진단](/ml-platform/week04-placement) | FailedScheduling, Node/Pod 조건 불일치 |
| CH9.1 | [18 · PV/PVC/StorageClass](/ml-platform/week04-statefulset) | volume 수명, 접근 모드, binding |
| CH9.2 | [18 · StatefulSet](/ml-platform/week04-statefulset) | ordinal, Headless Service, volumeClaimTemplates |
| CH9.3 | [19 · 디스크 복구](/ml-platform/week04-recovery) | Retain/Delete, PV 재바인딩, 장애 복구 |
| CH9.4 | [19 · 임시 볼륨](/ml-platform/week04-recovery) | emptyDir와 Generic Ephemeral Volume |

## 실습 중심 학습: 설명한 정책을 실제로 반증할 수 있을까?

[20 · Scheduler와 StatefulSet 통합 검증 실습](/ml-platform/week04-practical-lab)에서는 **필수 Node 조건 → Pending → 레이블 변경 → 재스케줄링**, **Hard Anti-Affinity → Replica와 Node 수 충돌**, **StatefulSet → Pod 재생성 전후 SHA-256 비교**를 한 번에 검증하는 절차를 제공한다.

실습 결과를 아직 확보하지 못했으므로, 해당 글의 기대 현상과 실제 출력은 명확히 구분했다. 이번 주의 완료 기준은 YAML 작성이나 Pipeline 컴파일이 아니라 **실행 환경·명령·실제 Event·원인 분석을 함께 기록하는 것**이다.

## 학습 아키텍처: Node 배치 + 상태 저장

~~~text
                     Kubernetes Cluster
                             |
                 Scheduler: Filter → Score → Bind
                             |
             ┌───────────────┴─────────────────┐
             |                                 |
        CPU Worker Node                  GPU / ML Node
             |                                 |
       Preprocessing Job               Training / Inference
             |                                 |
       ephemeral scratch                   Dataset / Model
             |                                 |
             └───────────────┬─────────────────┘
                             |
                   Artifact / Storage Layer
                  ┌──────────┴───────────┐
                  |                      |
             Object Storage       PVC → PV → Disk
                  |                      |
           versioned artifact      StatefulSet / DB
~~~

이 구조는 **설계 예시**이고 실제 GPU Node가 있는 클러스터에서 재현했다는 뜻은 아니다. Mac Apple Silicon + kind에서는 노드 라벨·Taint, Pod placement, PVC/StatefulSet의 기본 동작은 테스트할 수 있지만 GPU 학습의 실제 성능은 별도 환경이 필요하다.

### 학습에서 확인해야 하는 인과관계

1. Pod 생성과 실행은 같은 사건이 아니다. Scheduler가 Filter 조건을 모두 통과한 Node에 Bind하고, 이후 kubelet이 컨테이너를 준비한다.
2. Node Affinity의 required와 preferred는 별개다. 필수 규칙이 성립하지 않으면 점수가 높아도 배치할 수 없다.
3. Toleration은 Taint가 있는 Node를 **허용**할 뿐 해당 Node에 배치를 **강제**하지 않는다.
4. Replica가 여러 개여도 동일 장애 도메인에 집중하면 고가용성이 아니다. Pod Anti-Affinity와 Topology Spread가 필요할 수 있다.
5. StatefulSet이 Pod별 PVC와 identity를 관리하더라도 데이터베이스 복제와 백업이 자동으로 제공되는 것은 아니다.
6. Pod 삭제, PVC 삭제, PV 삭제, 실제 클라우드 디스크 삭제는 독립된 사건이므로 복구 정책을 분리해야 한다.

### 실습을 어떻게 증명할 것인가

| 실습 | 입력 변경 | 기대되는 관찰 | 검증 명령 |
|---|---|---|---|
| Node Affinity | 존재하지 않는 workload label 요구 | Pending / FailedScheduling | kubectl describe pod |
| Taint | Node에 NoSchedule 부여 | 미허용 신규 Pod 배치 차단 | kubectl describe node |
| Topology | Pod Anti-Affinity / maxSkew | 도메인 분산 또는 Pending | kubectl get pods -o wide |
| StatefulSet | Pod 삭제 후 재생성 | 동일 PVC 재연결 및 데이터 보존 | kubectl get pvc / exec |
| PV Recovery | Retain 설정 후 PVC 재생성 | 재바인딩 및 checksum 검증 | kubectl get pv,pvc |
| Ephemeral | Pod 생성·삭제 | scratch PVC 수명 관찰 | kubectl get pvc |

**현재 위 항목은 재현 가능한 실습 설계이고 실제 검증 결과는 아직 확보하지 않았다.** 명령 실행 및 출력 확인 후 결과와 해석을 별도로 기록한다.

## KFP / MLflow 응용: 왜 이 내용을 MLOps에서 배우는가?

CH8에서 CPU/GPU Node placement를 잘못 설계하면 KFP training task가 Pending되고, CH9에서 영속 데이터를 제대로 보존하지 않으면 MLflow DB나 모델 artifact가 사라질 수 있다. 그 위에 데이터 전달, 학습 품질 게이트, 스토리지 정책을 연결하는 것이 다음 네 개의 응용 글이다.

## 추가 응용 · KFP 파이프라인과 검증

![Week 04 파이프라인](/images/week04-pipeline.svg)

*개념 아키텍처이며 실제 클러스터 실행 결과가 아니다.*

| 주제 | 상세 글 | 운영에서 확인할 질문 |
|---|---|---|
| 데이터 전달 | [13 · KFP 아티팩트](/ml-platform/week04-artifacts) | Pod 사이에서 Parameter와 Dataset을 어떻게 전달할까? |
| 모델 검증 | [14 · 학습·평가·승인](/ml-platform/week04-training-validation) | 실행이 성공해도 등록을 막아야 하는 조건은? |
| 저장소 설계 | [15 · PVC와 스토리지](/ml-platform/week04-storage) | 아티팩트 저장소와 공유 볼륨을 언제 사용할까? |
| Pod 배치 | [16 · Scheduler와 상태 저장](/ml-platform/week04-scheduling) | Pending이 발생했을 때 어떤 이벤트를 살펴볼까? |

## 응용 1. 작은 값과 큰 파일은 서로 다른 계약으로 이동한다

| 항목 | Parameter | Artifact |
|---|---|---|
| 대상 | 숫자·문자열·작은 직렬화 값 | Dataset·Model·Metrics 등 |
| 전달 | 작업 인자·반환 값 | 파일과 메타데이터·URI |
| 주의 | 너무 큰 값으로 메타데이터 부담 | 업로드·다운로드, 저장 비용, 권한 |
| 예시 | 학습률, snapshot ID, 승인 여부 | 원천 데이터, 모델 가중치, 평가 파일 |

Artifact의 로컬 path와 스토리지 URI는 구별해야 한다. 실질적인 바이트 전송 경로는 KFP 실행 백엔드와 저장소 설정에 따라 달라진다.

## 응용 2. 학습에서 등록까지 안전하게 연결하기

~~~text
[원천 데이터·snapshot] → [Prepare] → [Split] → [Train] → [Evaluate]
                             |                                  |
                        검증된 Dataset                    Metrics·Model
                                                                |
                                         [기준 모델과 비교 + Quality gate]
                                              |             |
                                           Rejected      Approved
                                              |             |
                                             종료       [MLflow Registry]
~~~

- Prepare는 스키마·행 수·체크섬 검증, Split은 시간·그룹 누수 방지.
- Train은 데이터 버전·이미지 digest·시드·학습 파라미터 기록.
- Evaluate는 고정된 검증 데이터로 기준 모델과 후보를 동일하게 비교.
- Gate는 품질 미달(정상적인 거절)과 시스템 오류(실행 실패)를 별도로 기록.
- Register는 승인된 모델의 아티팩트·실험 Run ID를 연결.

## 응용 3. 스토리지와 캐시는 운영 정책이다

KFP 아티팩트 저장소는 실행 결과를 보관하고 추적하는 데, PVC는 Pod가 접근할 파일시스템을 제공하는 데 사용한다. PVC만 붙였다고 lineage가 생기지 않으며 Artifact를 사용해도 파일 전송 비용이 사라지지 않는다.

KFP 캐시는 동일한 실행을 재사용하는 최적화이지 입력 데이터의 동일성을 보장하는 검증 도구가 아니다. 가변 데이터 URI를 사용할 경우 snapshot ID·checksum을 파라미터로 전달하거나 캐시를 제한한다.

## 실습 환경 확인

Mac Apple Silicon + 기존 kind 환경을 기준으로 하되 클러스터 이름과 설치 여부는 실제 환경에서 확인한다.

~~~bash
kind get clusters
kubectl config current-context
kubectl get nodes -o wide
kubectl get storageclass,pv,pvc -A
kubectl get pods -A | grep -Ei 'pipeline|workflow|mlflow' || true
python -c 'import kfp; print(kfp.__version__)'
~~~

컴파일 성공, KFP Run 성공, 아티팩트 업로드, 모델 품질 승인, 레지스트리 등록은 **각각 다른 검증 단계**다.

| 검증 | 필요한 증거 | 현재 문서 |
|---|---|---|
| 파이프라인 컴파일 | 생성된 YAML과 KFP 버전 | 실행 필요 |
| 클러스터 실행 | KFP Run ID, Pod 로그·이벤트 | 실행 필요 |
| 데이터 품질 | schema, row count, checksum | 실행 필요 |
| 모델 승인 | baseline/후보 metric, 판정 결과 | 실행 필요 |
| 모델 등록 | registry version, MLflow Run ID | 실행 필요 |

## 4주차 학습 결론

1주차의 ML Lifecycle·CI/CD/CT, 2주차의 실험·피처 추적, 3주차의 확장·서빙을 하나로 연결하려면 데이터 스냅샷→학습 이미지→평가 지표→승인 결과→등록 모델을 역추적할 수 있어야 한다. 4주차의 중심은 자동 실행보다 **올바른 실패를 안전하게 막는 파이프라인**이다.

참고: [KFP Artifacts](https://www.kubeflow.org/docs/components/pipelines/user-guides/data-handling/artifacts/) · [Kubernetes PV](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)
