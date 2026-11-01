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
**확장 실습:** kind의 Probe·배포 전략·CPU·메모리·QoS, KServe·vLLM 개념

이번 주의 핵심은 **선택한 모델과 피처를 근거와 함께 관리하고, 같은 입력으로 추론을 반복하는 흐름**이다. MLflow에서 모델의 선택 근거와 버전을 남기고, Feast로 피처 정의·시점을 맞춘 뒤, KFP로 조회·추론·결과 저장을 연결한다. Kubernetes 운영 실습은 이 흐름이 자원 제한과 장애 속에서 어떻게 실행되는지를 다룬다.

![MLflow·Feast·KFP와 Kubernetes 실행 관계](/images/week02-system.svg)

도식은 전체 학습의 목표 구조다. 현재 직접 실행을 확인한 범위는 MLflow와 Kubernetes 운영 실습이며, Feast·KFP는 이어서 구성할 조회·파이프라인 설계로 구분한다.

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

## 4. 직접 실행한 MLflow 기록

MLflow 서버를 kind의 Deployment·Service·PVC로 배포하고 Kubernetes Job에서 세 후보 학습·비교·등록 모델 재로딩을 실행했다. 초기 서버 OOM을 복구한 뒤 Job은 **Complete 1/1, 9초**로 종료했다. 당시 서버는 **1/1 Running, 재시작 0**이었다.

세 Run과 모델 연결 화면, kubectl 출력, 서버 복구 기록은 [05. MLflow 실습 화면 ①](/ml-platform/mlflow-model-lifecycle)에 모았다. 같은 화면을 여러 페이지에 반복하지 않고 상세 글에서 확인한다. CI의 수치 결과는 그 글의 별도 접힘 영역에 구분했다.

## 5. 실습 화면은 세 곳에만 남긴다

| 위치 | 담을 화면 | 현재 구성 |
|---|---|---|
| ① MLflow | 세 Run과 모델 연결 | 제공한 실제 화면 반영 |
| ② Feast | 같은 Entity의 Historical·Online 조회 비교 | [Feast 장의 캡처 안내](/ml-platform/model-pipeline) |
| ③ KFP | 실행 DAG와 최종 파일 검사 요약 | [KFP 장의 캡처 안내](/ml-platform/kfp-batch-inference) |

개념 설명·계약·검증 기준은 본문과 도식으로 완성하고, Feast·KFP 실행 뒤에는 위 두 곳의 안내만 실제 화면과 해석으로 교체한다. 공개 화면에는 인증값을 포함하지 않으며 내부 IP는 설명에 필요하지 않으면 마스킹한다.

## 6. 확장 실습 · 실행을 운영으로 연결하기

| 연결 글 | 확인한 내용 |
|---|---|
| [09. 운영 자동화](/ml-platform/week-04) | Readiness 트래픽 제외·복귀, Liveness 재시작, RollingUpdate·Rollback·Recreate |
| [10. 리소스 관리](/ml-platform/week-05) | CPU throttling, 메모리 OOM, Guaranteed·Burstable·BestEffort |
| [11. KServe·vLLM](/ml-platform/week-06) | 모델 서빙·GPU·토큰 생성의 개념 확장 |

이미 수행한 운영 실습의 실제 관찰은 상세 글에 유지했다. KServe·vLLM은 개념 학습 범위다. 모델 파이프라인을 연결한 다음에는 모델 로딩 후 Ready, 고정 모델 버전 복원, 추론 부하에 따른 CPU·메모리 동작으로 확장할 수 있다.

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

좋은 점수의 모델 파일만 남기는 것으로 학습이 끝나지 않는다. 데이터·피처·설정·평가 기준이 연결되어야 선택 이유를 설명할 수 있다. 같은 버전의 모델과 피처로 반복 실행하고 결과 파일에서 입력·모델·실행 근거까지 추적할 수 있을 때 다음 운영 단계로 이어진다.

참고: [MLflow](https://mlflow.org/docs/latest/ml/), [Feast](https://docs.feast.dev/), [Kubeflow Pipelines](https://www.kubeflow.org/docs/components/pipelines/)
