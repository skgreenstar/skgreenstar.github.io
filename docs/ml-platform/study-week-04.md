---
title: "Week 04 · 학습 파이프라인이 성공했다면 모델도 믿을 수 있을까?"
outline: deep
prev:
  text: '3주차 · 학습 정리'
  link: '/ml-platform/study-week-03'
next:
  text: '13 · 데이터 전달'
  link: '/ml-platform/week04-artifacts'
---

# Week 04 · 학습 파이프라인이 성공했다면 모델도 믿을 수 있을까?

교재 범위: KFP 데이터 전달·학습·검증·저장소, Kubernetes Scheduler 심화  
핵심 질문: 데이터 준비부터 모델 등록까지 성공 상태와 품질 승인을 어떻게 구분하는가?  
실행 상태: 아래 구성은 학습·실습 설계다. 실제 실행 로그나 측정값을 확보하기 전에는 실행 결과로 기술하지 않는다.

2주차에는 MLflow·Feast·KFP의 모델·피처 버전 연결을, 3주차에는 추론 서비스의 확장과 트래픽을 살펴봤다. 4주차는 파이프라인 내부의 데이터 이동과 품질 승인으로 돌아간다. **Pipeline Succeeded는 실행 완료이지 모델 승인과 동일하지 않다.**

## 1. 이번 주의 네 가지 설계 질문

![Week 04 파이프라인](/images/week04-pipeline.svg)

*개념 아키텍처이며 실제 클러스터 실행 결과가 아니다.*

| 주제 | 상세 글 | 운영에서 확인할 질문 |
|---|---|---|
| 데이터 전달 | [13 · KFP 아티팩트](/ml-platform/week04-artifacts) | Pod 사이에서 Parameter와 Dataset을 어떻게 전달할까? |
| 모델 검증 | [14 · 학습·평가·승인](/ml-platform/week04-training-validation) | 실행이 성공해도 등록을 막아야 하는 조건은? |
| 저장소 설계 | [15 · PVC와 스토리지](/ml-platform/week04-storage) | 아티팩트 저장소와 공유 볼륨을 언제 사용할까? |
| Pod 배치 | [16 · Scheduler와 상태 저장](/ml-platform/week04-scheduling) | Pending이 발생했을 때 어떤 이벤트를 살펴볼까? |

## 2. 작은 값과 큰 파일은 서로 다른 계약으로 이동한다

| 항목 | Parameter | Artifact |
|---|---|---|
| 대상 | 숫자·문자열·작은 직렬화 값 | Dataset·Model·Metrics 등 |
| 전달 | 작업 인자·반환 값 | 파일과 메타데이터·URI |
| 주의 | 너무 큰 값으로 메타데이터 부담 | 업로드·다운로드, 저장 비용, 권한 |
| 예시 | 학습률, snapshot ID, 승인 여부 | 원천 데이터, 모델 가중치, 평가 파일 |

Artifact의 로컬 path와 스토리지 URI는 구별해야 한다. 실질적인 바이트 전송 경로는 KFP 실행 백엔드와 저장소 설정에 따라 달라진다.

## 3. 학습에서 등록까지 안전하게 연결하기

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

## 4. 스토리지와 캐시는 운영 정책이다

KFP 아티팩트 저장소는 실행 결과를 보관하고 추적하는 데, PVC는 Pod가 접근할 파일시스템을 제공하는 데 사용한다. PVC만 붙였다고 lineage가 생기지 않으며 Artifact를 사용해도 파일 전송 비용이 사라지지 않는다.

KFP 캐시는 동일한 실행을 재사용하는 최적화이지 입력 데이터의 동일성을 보장하는 검증 도구가 아니다. 가변 데이터 URI를 사용할 경우 snapshot ID·checksum을 파라미터로 전달하거나 캐시를 제한한다.

## 5. 실행 환경을 확인한 뒤 실습하기

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

## 6. 이전 주차와 연결한 결론

1주차의 ML Lifecycle·CI/CD/CT, 2주차의 실험·피처 추적, 3주차의 확장·서빙을 하나로 연결하려면 데이터 스냅샷→학습 이미지→평가 지표→승인 결과→등록 모델을 역추적할 수 있어야 한다. 4주차의 중심은 자동 실행보다 **올바른 실패를 안전하게 막는 파이프라인**이다.

참고: [KFP Artifacts](https://www.kubeflow.org/docs/components/pipelines/user-guides/data-handling/artifacts/) · [Kubernetes PV](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)
