---
title: "Week 02 · 실험 추적에서 모델 운영까지"
outline: deep
prev:
  text: '1주차 · 학습 정리'
  link: '/ml-platform/study-week-01'
next:
  text: '04 · 실행 환경'
  link: '/ml-platform/week02-environment'
---

# Week 02 · 실험 추적에서 모델 운영까지

**교재 범위:** CH4 · MLflow와 Feast / CH5 · Kubeflow Pipelines  
**심화 학습:** kind의 Probe·배포 전략·CPU·메모리·QoS, KServe·vLLM 개념

이번 주의 핵심은 **선택한 모델과 피처를 근거와 함께 관리하고, 같은 입력으로 추론을 반복하는 흐름**이다. MLflow에서 모델의 선택 근거와 버전을 남기고, Feast로 피처 정의·시점을 맞춘 뒤, KFP로 조회·추론·결과 저장을 연결한다. Kubernetes 운영 실습은 이 흐름이 자원 제한과 장애 속에서 어떻게 실행되는지를 다룬다.

![MLflow·Feast·KFP와 Kubernetes 실행 관계](/images/week02-system.svg)

핵심 연결은 데이터 계약·피처 시점·고정 모델 버전이다. 학습과 배치 추론이 이 세 기준을 공유하면 선택한 모델의 예측을 같은 근거로 재현할 수 있다.

## 1. 전체 학습 순서

| 단계 | 핵심 질문 | 연결 글 |
|---|---|---|
| A · 실행 환경 | 어디서 실행하고 무엇을 저장하는가? | [04. Kubernetes 환경과 저장 경로](/ml-platform/week02-environment) |
| B · MLflow · CH4 | 어떤 근거로 선택한 모델을 다시 쓰는가? | [05. 학습·실험 비교·등록·재로딩](/ml-platform/mlflow-model-lifecycle) |
| C · Feast · CH4 | 같은 정의로 그 시점에 맞는 피처를 읽는가? | [06. 과거 시점·최신 피처 조회](/ml-platform/model-pipeline) |
| D · KFP · CH5 | 피처 조회와 모델 추론을 반복 실행하는가? | [07. 배치 추론 파이프라인](/ml-platform/kfp-batch-inference) |
| E · 결과 검증 | 실행 성공과 예측 내용의 정확성을 확인했는가? | [08. 결과·재현성·추적성 검증](/ml-platform/week02-verification) |

## 2. 각 도구가 책임지는 범위

MLflow의 Run은 학습 설정·점수·아티팩트를 묶는다. Registry는 선택한 모델 버전을 찾는 경로를 제공한다. Feast는 Entity·시각·피처 정의를 기준으로 과거 이력과 최신 값을 조회한다. KFP는 각 작업을 독립된 컴포넌트로 실행하고 의존 관계와 파일 전달을 관리한다.

| 도구 | 관리하는 대상 | 성공 뒤에도 확인할 것 |
|---|---|---|
| MLflow | 실험·지표·모델 버전 | 선택 기준과 재로딩 예측 일치 |
| Feast | 피처 정의·시점 조회·최신 값 적재 | 미래 값 제외·값 존재·신선도 |
| KFP | 단계·파라미터·아티팩트·실행 | 최종 파일 내용과 입력 계보 |
| Kubernetes | Pod·Service·자원·실행 상태 | 준비 상태·복구·자원 제약 |

모든 도구가 같은 데이터를 자동 공유하는 것은 아니다. 원본 해시, Entity·예측 시각, 피처 이름·순서·자료형, 고정 모델 URI를 명시적으로 연결해야 한다.

## 3. 우리 실습에서 이어받는 데이터 계약

| 항목 | 구성 |
|---|---|
| 문제 | 합성 제조 품질 회귀 예측 |
| 원본 | seed 42로 생성한 1,000행 CSV |
| Entity·시각 | equipment_id / event_timestamp / prediction_timestamp |
| 입력·목표 | temperature·pressure·speed / quality |
| 학습·검증·최종 평가 | 시간 순서 700 / 150 / 150행 |
| 후보·선택 | 평균 기준 모델·Ridge·RandomForest / 검증 RMSE |
| 다음 단계 입력 | CSV·dataset_contract.json·selection.json·test_predictions.csv |

교재의 분류 데이터와 다른 예제지만 실험 추적→피처 관리→배치 추론의 연결 원리는 같다. 합성 데이터 성능을 실제 제조 성능으로 표현하지 않고, 교재의 accuracy·분류 확률과 우리 회귀 지표를 섞지 않는다.

### 저장소 구성 · MinIO

MinIO는 파일을 bucket과 object 단위로 보관한다. KFP의 중간 Dataset·최종 결과는 **MinIO**로 연결하도록 설계했고, Feast의 최신 피처는 **Redis**를 사용한다. kind에서 실행한 MLflow 서버와 학습 산출물은 기존 **PVC**에 유지했다.

| 저장 대상 | 사용할 구성 |
|---|---|
| KFP 중간 Dataset·최종 결과 | MinIO |
| Feast Online 최신 피처 | Redis |
| 현재 MLflow DB·모델 아티팩트 | 기존 mlflow-data PVC |
| 현재 학습 CSV·선택 결과 | 기존 mlflow-results PVC |

### 데이터와 선택 근거를 함께 보기

제조 품질 예제의 온도는 품질과의 선형 상관계수가 약 0.013인데도 중앙 구간이 높은 곡선 관계를 보였다. 상관계수만으로 피처의 유용성을 판단하기 어렵다는 점을 [데이터 탐색 그림](/ml-platform/mlflow-model-lifecycle)에서 확인했다.

![동일 시간 분할에서 세 후보의 검증 RMSE를 비교한 그래프](/images/week02-model-comparison.svg)

평균 모델·Ridge·RandomForest를 같은 입력과 분할에서 비교했고, 검증 RMSE가 가장 낮은 RandomForest를 선택했다. 평균 기준 모델 대비 RMSE는 약 76.9% 감소했다. [MLflow 글](/ml-platform/mlflow-model-lifecycle)에는 원본 피처의 관계와 선택 이유를, [Feast 글](/ml-platform/model-pipeline)에는 시점 조회·키 결합 코드를, [KFP 글](/ml-platform/kfp-batch-inference)에는 컴포넌트 파일 경계와 의존성 코드를 연결했다.

## 4. 직접 실행한 MLflow 기록

MLflow 서버를 kind의 Deployment·Service·PVC로 배포하고 Kubernetes Job에서 세 후보 학습·비교·등록 모델 재로딩을 실행했다. 초기 서버 OOM을 복구한 뒤 Job은 **Complete 1/1, 9초**로 종료했다. 당시 서버는 **1/1 Running, 재시작 0**이었다.

세 후보의 실험 기록, 등록 모델 연결, 서버 배포와 복구 과정은 [05. MLflow · 학습에서 모델 등록과 재로딩까지](/ml-platform/mlflow-model-lifecycle)에서 자세히 정리했다.

### Feast·KFP 연결 검증

동일한 합성 제조 데이터의 평가 대상 **150행**을 Feast로 조회하고 등록 모델의 예측과 비교했다. 예측 최대 절대 차이는 **약 1.42e-14**로 허용 오차를 통과했다. Redis의 최신 피처 값도 확인했으며, KFP의 네 작업은 파일 경계를 나누어 순차 실행하고 YAML 컴파일까지 검증했다.

이 연결 검증은 GitHub Actions 환경에서 수행했다. 상세 결과는 [Feast 조회 기록](/ml-platform/model-pipeline)과 [KFP 컴포넌트 검증](/ml-platform/kfp-batch-inference)에 정리했다.

## 5. 구성도로 이해하는 모델·피처·파이프라인

MLflow는 선택할 모델을, Feast는 입력 피처의 시점을, KFP는 작업의 의존 관계를 고정한다. 각 글에서 같은 제조 품질 데이터를 기준으로 이 연결을 살펴본다.

| 연결 글 | 그림에서 볼 내용 |
|---|---|
| [MLflow 모델 흐름](/ml-platform/mlflow-model-lifecycle) | 동일 데이터 → 후보 비교 → 모델 등록 → 재로딩 검증 |
| [Feast 피처 흐름](/ml-platform/model-pipeline) | 정의 등록 → Historical 조회 / Redis 최신 값 적재 |
| [KFP 배치 추론 흐름](/ml-platform/kfp-batch-inference) | 피처·고정 모델 → 예측 → 검증 → MinIO 저장 |

::: details 피처 조회와 배치 추론의 연결

![Feast·MLflow·MinIO를 연결하는 KFP 배치 추론 구성도](/images/week02-kfp-dag.svg)

:::

모델·피처·파이프라인의 변경을 각각 식별하면 예측이 달라졌을 때 어느 입력과 설정을 먼저 비교할지 좁힐 수 있다.

## 6. 심화 · 운영과 평가로 이어가기

| 연결 글 | 확인한 내용 |
|---|---|
| [운영 자동화](/ml-platform/week-04) | Readiness 트래픽 제외·복귀, Liveness 재시작, RollingUpdate·Rollback·Recreate |
| [리소스 관리](/ml-platform/week-05) | CPU throttling, 메모리 OOM, Guaranteed·Burstable·BestEffort |
| [KServe·vLLM](/ml-platform/week-06) | 모델 서빙·GPU·토큰 생성의 개념 확장 |
| [산업 AI 회귀 평가](/ml-platform/industrial-evaluation) | 기준 모델·회귀 지표·운전 구간별 평가 |
| [RAG / Agent 평가](/ml-platform/evaluation-and-operations) | 검색·생성·Agent의 품질과 배포 기준 |

앞에서 선택하고 검증한 모델을 실제 서비스로 이어갈 때는 준비 상태·자원 제약·서빙 방식·평가 기준을 함께 확인한다. 이미 수행한 운영 실습의 실제 관찰은 상세 글에 유지했다. KServe·vLLM은 개념 학습 범위다. 모델 파이프라인을 연결한 다음에는 모델 로딩 후 Ready, 고정 모델 버전 복원, 추론 부하에 따른 CPU·메모리 동작으로 확장할 수 있다.

::: details 완료한 Kubernetes 관찰 기록
| 실습 | 실행 결과 |
|---|---|
| Readiness 장애·복구 | healthz=200, readyz=503 / Ready 1→0→1 / EndpointSlice ready true→false→true / 재시작 0 |
| Liveness 장애 | HTTP 503 → Killing → 동일 Pod 재시작 1회 → Ready 복구 |
| RollingUpdate | 새 Pod Ready 후 기존 Pod Terminating / LAB_VERSION=v2 / revision 2 |
| Rollback | revision 1 템플릿 복원 / LAB_VERSION 제거 / 새 Pod Ready / revision 3 |
| Recreate | 기존 Pod 종료 상태 이후 신규 Pod 생성·Ready / LAB_VERSION=recreate |
| CPU limit 100m | 10.006초 동안 CPU 1.001782초 사용 / 제어 주기 100개에서 throttling |
| Memory limit 64Mi | 160Mi 할당 시도 → OOMKilled / exitCode=137 / 재시작 0 |
| QoS 등급 | Guaranteed·Burstable·BestEffort 세 구성의 실제 등급 확인 |

실제 요청의 연속 가용성은 Pod 교체 순서만으로 입증하지 않는다. exit code 137도 종료 사유·이벤트와 함께 해석한다. 기존 기록에서 Liveness 재시작과 OOMKilled를 구분했다.
:::

## 7. 이번 주의 핵심 정리

이번 연결에서는 세 가지를 배웠다. 첫째, 상관계수가 작더라도 비선형 관계가 있을 수 있으므로 원본 데이터의 모양과 기준 모델을 먼저 확인해야 한다. 둘째, MLflow의 모델 버전과 Feast의 피처 시점을 함께 고정해야 같은 예측을 재현할 수 있다. 셋째, KFP의 단계 성공뿐 아니라 결과의 Entity·시각·행 수·예측값까지 확인해야 작업 완료를 판단할 수 있다.

모델 파일 하나보다 중요한 것은 그 모델을 선택한 이유와 다시 사용할 수 있는 입력 계약이다. 이 근거가 연결되어야 이후 배포·복구·자원 관리도 특정 모델과 데이터의 운영 문제로 설명할 수 있다.

참고: [MLflow](https://mlflow.org/docs/latest/ml/), [Feast](https://docs.feast.dev/), [Kubeflow Pipelines](https://www.kubeflow.org/docs/components/pipelines/)
