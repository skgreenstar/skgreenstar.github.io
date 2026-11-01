---
title: "Feast·KFP · 같은 피처와 같은 모델로 추론하기"
outline: deep
---

# Feast·KFP · 같은 피처와 같은 모델로 추론하기

**CH4 · Feast / CH5 · Kubeflow Pipelines**

[MLflow 실습](/ml-platform/mlflow-model-lifecycle)의 데이터와 등록 모델을 다음 단계의 입력으로 사용한다. 각 도구마다 다른 샘플을 만드는 대신, 동일한 데이터 계약으로 학습과 추론을 연결한다. 아래는 이어서 실행할 연결 설계다.

## 1. Feast 피처 계약

| 요소 | 대응 |
|---|---|
| Entity | equipment_id |
| 피처 시각 | event_timestamp |
| 예측 기준 시각 | prediction_timestamp |
| FeatureView | temperature, pressure, speed |
| Offline | 예측 시점 이전 피처로 학습·배치 입력 구성 |
| Online | materialization 후 설비별 최신 피처 조회 |

quality는 목표값이므로 온라인 피처에 포함하지 않는다. 동일 CSV로 과거 시점 조회를 실행하고, 미래 데이터가 과거 예측 시점에 결합되지 않는지 검증한다. 이어서 학습 입력을 Feast 조회 결과로 교체하고 MLflow Run·데이터 해시를 연결한다.

## 2. KFP 배치 추론 구성

| 단계 | 입력 | 검증·출력 |
|---|---|
| 입력 검증 | 원본·dataset_contract.json | 해시·필수 컬럼 |
| 피처 조회 | Entity·예측 시각 | Feast 피처 Dataset |
| 모델 추론 | Dataset·고정 model_uri | 예측 Dataset |
| 결과 평가 | 예측·목표값 | RMSE·MAE·R²·결과 파일 |

KFP의 Input/Output 아티팩트로 단계 간 데이터를 전달하고, 모델 URI와 데이터 해시를 실행 파라미터로 기록한다. 이 배치 추론 과정에서 모델을 다시 학습하거나 임의의 최신 버전을 선택하지 않는다.

## 3. 연결 검증

1. MLflow 재로딩 예측과 KFP 결과를 동일 행 기준으로 비교한다.
2. 입력 해시가 다르거나 피처가 누락되면 검증 단계에서 실패시킨다.
3. Feast 조회에 미래 시점 값이 섞이지 않는지 확인한다.
4. KFP에서 단계별 로그·산출물·실패 지점을 확인한다.

실행 순서는 MLflow → Feast → KFP다. 각 단계의 설치 버전과 실제 산출물을 확인한 뒤 다음 단계로 연결한다.

## 4. 기존 운영 실습과 연결

이미 실행한 [Probe·배포·롤백](/ml-platform/week-04), [CPU·OOM·QoS](/ml-platform/week-05)는 모델 파이프라인의 운영 기반이다. 등록한 모델로 실행 대상을 바꿔 모델 로딩 후 Ready 전환, CPU limit별 처리량·지연, 메모리 종료, 모델 버전 복원을 검증하는 방향으로 확장한다.

참고: [Feast](https://docs.feast.dev/), [KFP](https://www.kubeflow.org/docs/components/pipelines/)
