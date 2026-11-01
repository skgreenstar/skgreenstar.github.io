---
title: "04. MLflow · 학습에서 모델 등록과 재로딩까지"
outline: deep
prev:
  text: '2주차 · 학습 정리'
  link: '/ml-platform/study-week-02'
next:
  text: '05 · Feast·KFP 연결 설계'
  link: '/ml-platform/model-pipeline'
---

# 04. MLflow · 학습에서 모델 등록과 재로딩까지

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

## 자동 실행 검증 결과

GitHub Actions의 Ubuntu / Python 3.12 환경에서 전체 스크립트를 실행했다. 패키지는 MLflow 3.17.2, scikit-learn 1.9.1, pandas 2.3.3, NumPy 2.5.4였다. 아래는 **CI 실행 결과**이며 개인 PC의 실행 결과와 구분한다.

| 후보 | 검증 RMSE | 검증 MAE | 검증 R² |
|---|---:|---:|---:|
| 평균 기준 모델 | 4.251555 | 3.302727 | -0.006292 |
| Ridge | 3.297208 | 2.811120 | 0.394769 |
| RandomForest | 0.983442 | 0.786182 | 0.946157 |

검증 RMSE로 RandomForest를 선택해 ManufacturingQualityDemo 버전 1로 등록했다. 등록 모델 재로딩 후 예측값의 최대 절대 차이는 **0.0**이었고, 최종 평가 RMSE는 **0.923904**, MAE는 **0.774785**, R²는 **0.940139**였다. 이는 합성 데이터에서의 결과이며 실제 제조 예측 성능을 의미하지 않는다.

모델 저장 과정에서 직접 학습한 RandomForest의 sklearn.tree._tree.Tree 타입만 skops 신뢰 목록에 지정했다. 외부에서 받은 임의 모델 타입을 일괄 허용하는 코드는 사용하지 않는다.

[자동 실행 로그와 산출물](https://github.com/skgreenstar/skgreenstar.github.io/actions/runs/41328495691)

## 3. 로컬 kind에 MLflow 서버 배포

PC에는 코드·YAML을 내려받고 Docker 이미지를 빌드한다. **MLflow 서버와 학습 코드는 모두 Kubernetes Pod 안에서 실행**하며, PC의 Python 가상환경은 사용하지 않는다.

| 구성 | Kubernetes 리소스 | 역할 |
|---|---|---|
| Tracking Server | Deployment / Service | Run·모델 등록 API와 UI |
| DB·모델 아티팩트 | mlflow-data PVC | 서버의 SQLite와 아티팩트 영속화 |
| 학습 실행 | mlflow-train Job | 세 후보 비교·등록·재로딩 |
| 학습 산출물 | mlflow-results PVC | CSV·비교표·선택 결과 저장 |

학습 Job은 클러스터 DNS http://mlflow:5000 으로 연결한다. 아티팩트도 서버 HTTP 프록시를 통해 업로드하며, Job 컨테이너의 로컬 경로를 서버 저장 경로로 전달하지 않는다. SQLite는 단일 서버 학습용 구성이며, 다중 서버 운영 시 공유 DB·오브젝트 스토리지를 설계한다.

### 이미지 준비

```bash
mkdir -p ~/mlops-week02-mlflow
cd ~/mlops-week02-mlflow
for file in requirements.txt train_compare_register.py Dockerfile .dockerignore mlflow-server.yaml train-job.yaml; do
  curl -fL "https://raw.githubusercontent.com/skgreenstar/skgreenstar.github.io/main/labs/week02-mlflow/$file" -o "$file"
done
docker build -t mlops-week02-mlflow:0.1 .
kind load docker-image mlops-week02-mlflow:0.1 --name mlops-lab
```

python:3.12-slim 기반 이미지를 PC의 아키텍처로 빌드한다. 같은 이미지를 서버와 Job이 재사용하며 imagePullPolicy=Never로 kind에 적재한 이미지만 사용한다.

### 서버 배포

```bash
k() { kubectl --context kind-mlops-lab -n week02 "$@"; }
k get storageclass
k apply -f mlflow-server.yaml
k rollout status deployment/mlflow --timeout=300s
k get pvc
k get pods -l app=mlflow
```

PVC는 기본 StorageClass를 사용한다. Pending이면 StorageClass·PVC 이벤트를 확인한 뒤 Job 실행으로 넘어간다.

## 4. Kubernetes Job으로 학습·비교·등록·재로딩

서버가 Ready가 된 뒤 Job을 실행한다. 초기 실습에서 같은 이름의 Job이 없을 때 사용하는 명령이다.

```bash
k apply -f train-job.yaml
k logs -f job/mlflow-train --pod-running-timeout=300s
k wait --for=condition=Complete job/mlflow-train --timeout=900s
k get job mlflow-train
```

동일 실습을 다시 실행할 때는 이전 Job의 로그를 확인한 후 k delete job mlflow-train으로 실행 리소스를 정리하고 재생성한다. 서버 PVC와 등록 모델은 유지된다. 비교 결과와 재로딩 검증은 Job 로그 및 서버 아티팩트에 기록된다.

### UI 확인

```bash
k port-forward svc/mlflow 5050:5000
```

터미널을 유지하고 브라우저에서 http://127.0.0.1:5050 을 연다. PC에서는 UI 접속을 위한 포트 포워딩만 수행한다. Experiments의 세 Run과 Models의 ManufacturingQualityDemo 버전을 확인한다.

### 다음 단계로 넘길 근거

Job Complete, 후보별 비교표, 고정 모델 URI, reload_equal=true 및 reload_max_abs_diff를 함께 확인한다. 앞의 자동 검증 표는 CI 코드 검사 결과이며, PC kind에서 실행한 Job 결과는 해당 로그를 근거로 기록한다.
## 5. 등록 모델 재로딩 검증

검증 점수로 선택한 모델을 등록한 뒤 고정 버전 URI로 다시 로드한다. 등록 전·후 모델에 같은 최종 평가 입력을 주고, 예측값이 허용 오차 안에서 일치하는지 assert로 검사한다. 재실행 시 새 모델 버전이 생길 수 있으므로 후속 단계는 selection.json의 model_uri를 사용한다.

| 산출물 | 다음 단계에서 쓰는 이유 |
|---|---|
| synthetic_manufacturing.csv | Feast에서도 사용하는 동일 원본 |
| dataset_contract.json | 엔터티·시각·피처·데이터 해시 |
| comparison.csv | 후보별 검증 점수와 Run 비교 |
| selection.json | 고정 모델 URI·재로딩 검증·최종 평가 |
| test_predictions.csv | 후속 배치 추론 결과와 대조 |
| requirements-resolved.txt | 실제 설치 버전 기록 |

## 6. 다음 단계

[Feast·KFP 연결 설계](/ml-platform/model-pipeline)에서 같은 데이터 계약과 등록 모델 URI를 사용한다. 등록한 모델을 Kubernetes에 올리면 기존 CPU·메모리·배포 실습을 모델 운영 검증으로 확장할 수 있다.

- [실행 코드](https://github.com/skgreenstar/skgreenstar.github.io/tree/main/labs/week02-mlflow)
- [MLflow Tracking](https://mlflow.org/docs/latest/ml/tracking/)
- [Model Registry](https://mlflow.org/docs/latest/ml/model-registry/workflow/)
