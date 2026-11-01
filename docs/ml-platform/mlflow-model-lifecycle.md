---
title: "MLflow · 학습에서 모델 등록과 재로딩까지"
outline: deep
prev:
  text: '2주차 · 학습 정리'
  link: '/ml-platform/study-week-02'
next:
  text: 'Feast·KFP 연결'
  link: '/ml-platform/model-pipeline'
---

# MLflow · 학습에서 모델 등록과 재로딩까지

**CH4 · 실험 추적과 모델 관리**

이번 실습의 질문은 **어떤 데이터와 설정으로 선택한 모델을, 나중에 같은 입력으로 다시 사용할 수 있는가?**다. 기존 Kubernetes 실습의 운영 기록에 모델 버전과 데이터 계보를 연결한다.

## 1. 데이터와 비교 기준

seed 42로 생성한 **합성 제조 품질 데이터 1,000행**을 사용한다. 실제 공장 측정값이나 성능을 의미하지 않는다. 온도·압력·속도로 가상의 다음 시점 품질을 예측하고, 데이터 생성식을 실행 코드에 공개했다.

| 항목 | 구성 |
|---|---|
| Entity / 시각 | equipment_id / event_timestamp, prediction_timestamp |
| 입력 / 목표 | temperature, pressure, speed / quality |
| 시간 순서 분할 | 학습 700 / 검증 150 / 최종 평가 150 |
| 후보 | 평균 기준 모델 / Ridge / RandomForest |
| 선택 | 검증 RMSE 최솟값, 선택 이후 최종 평가 |

## 2. 실험마다 남기는 근거

MLflow Run에 파라미터·검증 RMSE/MAE/R²·학습 시간을 기록한다. 모델에는 signature와 입력 예시를 포함하고, CSV·SHA-256·입력 계약·실제 설치 패키지 버전도 저장한다. test 점수로 후보를 고르지 않도록 선택과 최종 평가를 분리했다.

## 3. PC에서 실행

Python 3.10 이상에서 전용 가상환경을 사용한다. DB와 산출물은 아래 작업 폴더에 생성된다.

```bash
mkdir -p ~/mlops-week02-mlflow
cd ~/mlops-week02-mlflow
curl -fL https://raw.githubusercontent.com/skgreenstar/skgreenstar.github.io/main/labs/week02-mlflow/requirements.txt -o requirements.txt
curl -fL https://raw.githubusercontent.com/skgreenstar/skgreenstar.github.io/main/labs/week02-mlflow/train_compare_register.py -o train_compare_register.py
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python train_compare_register.py
```

실행 스크립트는 세 후보의 비교표와 선택한 모델의 등록·재로딩 검증을 출력한다. 결과 점수는 실행 시 생성하는 comparison.csv와 selection.json을 근거로 해석한다.

```bash
mlflow ui --backend-store-uri sqlite:///mlflow.db --host 127.0.0.1 --port 5050
```

브라우저에서 http://127.0.0.1:5050 을 연다. Experiments에서 세 Run, Models에서 ManufacturingQualityDemo의 등록 버전을 확인한다.

## 4. 등록 모델 재로딩 검증

검증 점수로 선택한 모델을 등록한 뒤 고정 버전 URI로 다시 로드한다. 등록 전·후 모델에 같은 최종 평가 입력을 주고, 예측값이 허용 오차 안에서 일치하는지 assert로 검사한다. 재실행 시 새 모델 버전이 생길 수 있으므로 후속 단계는 selection.json의 model_uri를 사용한다.

| 산출물 | 다음 단계에서 쓰는 이유 |
|---|---|
| synthetic_manufacturing.csv | Feast에서도 사용하는 동일 원본 |
| dataset_contract.json | 엔터티·시각·피처·데이터 해시 |
| comparison.csv | 후보별 검증 점수와 Run 비교 |
| selection.json | 고정 모델 URI·재로딩 검증·최종 평가 |
| test_predictions.csv | 후속 배치 추론 결과와 대조 |
| requirements-resolved.txt | 실제 설치 버전 기록 |

## 5. 다음 단계

[Feast·KFP 연결 설계](/ml-platform/model-pipeline)에서 같은 데이터 계약과 등록 모델 URI를 사용한다. 등록한 모델을 Kubernetes에 올리면 기존 CPU·메모리·배포 실습을 모델 운영 검증으로 확장할 수 있다.

- [실행 코드](https://github.com/skgreenstar/skgreenstar.github.io/tree/main/labs/week02-mlflow)
- [MLflow Tracking](https://mlflow.org/docs/latest/ml/tracking/)
- [Model Registry](https://mlflow.org/docs/latest/ml/model-registry/workflow/)
