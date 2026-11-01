---
title: "05. MLflow · 학습에서 모델 등록과 재로딩까지"
outline: deep
prev:
  text: '04 · 실행 환경'
  link: '/ml-platform/week02-environment'
next:
  text: '06 · Feast 피처 관리'
  link: '/ml-platform/model-pipeline'
---

# 05. MLflow · 학습에서 모델 등록과 재로딩까지

**CH4 · 실험 추적과 모델 관리**

이번 실습의 질문은 **어떤 데이터와 설정으로 선택한 모델을, 나중에 같은 입력으로 다시 사용할 수 있는가?**다. 기존 Kubernetes 실습의 운영 기록에 모델 버전과 데이터 계보를 연결한다.

## MLflow의 역할과 데이터 흐름

MLflow는 학습 알고리즘이 아니라 실험 추적과 모델 관리를 돕는 도구다. 실제 학습은 scikit-learn 코드가 수행하고, MLflow는 실행 근거를 기록한다.

![데이터와 Run에서 등록 모델·재로딩 검증으로 이어지는 흐름](/images/week02-mlflow.svg)

| 개념 | 남기는 정보 | 판단에 쓰는 이유 |
|---|---|---|
| Experiment | 관련 Run의 묶음 | 동일 문제의 실험 탐색 |
| Run | 파라미터·지표·태그·실행 이력 | 후보 간 차이 비교 |
| Parameter | 모델 종류·하이퍼파라미터·seed | 어떤 설정으로 학습했는지 재현 |
| Metric | RMSE·MAE·R² 등 수치 | 검증 기준에 따라 모델 선택 |
| Artifact | 모델·CSV·그래프·계약 파일 | 실행 근거와 산출물 보관 |
| Model Registry | 이름 아래의 모델 버전 | 선택 모델의 고정 버전 재사용 |

등록 모델 URI는 예를 들어 `models:/ManufacturingQualityDemo/1`처럼 구체적인 버전을 가리킨다. 버전 번호는 예시이며 후속 작업에서는 실제 `selection.json` 값을 사용한다. Registry 등록만으로 추론 서비스가 배포되지는 않는다. 배포와 트래픽 전환은 별도 운영 작업이다.

## 학습 전에 확인할 데이터와 EDA

EDA에서는 시간 범위·설비별 행 수·결측·분포·목표값 관계를 확인한다. 시각화는 원본의 이상이나 분할 편향을 찾기 위한 근거다. 합성 데이터의 생성식 때문에 높은 점수가 나오는 상황을 실제 설비에 대한 일반화 성능으로 해석하지 않는다.

원본 데이터·전처리·피처 순서·분할 기준이 다르면 모델 점수만 직접 비교하기 어렵다. 같은 시간 분할을 유지한 채 검증 점수로 후보를 선택하고, 최종 평가 데이터는 선택 이후 확인한다. 평균 예측 모델을 기준으로 두어 복잡한 모델이 실제로 개선했는지 비교한다.

MLflow의 데이터 입력 메타데이터 기록이 원본 CSV 전체 복사를 자동 보장하지는 않는다. 이 실습은 CSV와 SHA-256·입력 계약을 별도 산출물로 저장한다. EDA 그림을 추가할 때도 Run의 아티팩트로 저장해 데이터 버전과 함께 추적한다.

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

## Kubernetes 실행 결과 · 실습 화면 ①

개인 PC의 kind 클러스터에서 MLflow 서버를 Deployment·Service·PVC로 배포하고, 학습·실험 비교·모델 등록·재로딩을 Kubernetes Job으로 실행했다. 서버 OOM을 복구한 뒤 학습 Job이 **9초 만에 Complete(1/1)**로 종료됐고, UI에서 세 Run과 모델 연결을 확인했다.

![kind 위 MLflow 3.17.2 UI: random_forest, ridge, baseline_mean 세 Run](/images/week02-mlflow-kind-runs.png)

**화면 확인:** MLflow 3.17.2의 week02-manufacturing-quality 실험에 random_forest·ridge·baseline_mean이 기록됐다. random_forest 행에서 ManufacturingQualityDemo 모델 연결도 확인된다.

| 확인 항목 | 실행 결과 |
|---|---|
| 학습 실행 위치 | kind-mlops-lab / week02 / Kubernetes Job |
| 학습 Job | mlflow-train · Complete · 1/1 · DURATION 9s |
| 서버 Pod | 1/1 Running · RESTARTS 0 · 조회 시 AGE 3m15s |
| 서버·산출물 저장 | mlflow-data 2Gi / mlflow-results 1Gi · 두 PVC Bound |
| 복구 후 health | HTTP 200 세 번 |
| 복구 후 서버 메모리 | 354.9 → 355.2 → 354.7 MiB |
| 모델 학습·비교 | baseline_mean / ridge / random_forest 세 Run |
| 등록·재로딩 흐름 | 등록 모델 로드·예측 일치 assert를 포함한 학습 Job 완료 |
| UI 접근 | Service port-forward 후 브라우저 접속 확인 |

Job의 9초는 전체 작업 수행 시간이며, UI에 표시된 개별 Run 시간과 구분한다. 서버 메모리 세 표본은 복구 후 건강 검사 구간의 관측값이다.

#### 최종 kubectl 출력

```text
job.batch/mlflow-train condition met
NAME           STATUS     COMPLETIONS   DURATION   AGE
mlflow-train   Complete   1/1           9s         9s

NAME                         READY   STATUS    RESTARTS   AGE
mlflow-548b585c74-pjblp       1/1     Running   0          3m15s
```

#### 장애에서 복구까지

| 단계 | 관찰·조치 |
|---|---|
| 초기 장애 | 서버 OOMKilled / CrashLoopBackOff, 학습 Job API 연결 거부 |
| 설정 보완 | 서버 request 512Mi / limit 2Gi, 내장 Job 실행기 비활성화 |
| 서버 확인 | health 200 세 번, 메모리 약 355MiB, 재시작 0 |
| 학습 재실행 | 실패 Job 정리 후 재생성, Complete(1/1) 확인 |
| 화면 확인 | MLflow 실험 세 Run과 모델 연결, UI 접속 정상 |

서버 저장 PVC를 유지한 채 복구했다. 메모리 조정과 내장 실행기 비활성화를 함께 적용했으므로 각각의 효과를 분리해서 단정하지 않는다.

::: details CI 코드 검증 결과 · 참고

### 자동 실행 검증 결과

GitHub Actions의 Ubuntu / Python 3.12 환경에서 전체 스크립트를 실행했다. 패키지는 MLflow 3.17.2, scikit-learn 1.9.1, pandas 2.3.3, NumPy 2.5.4였다. 아래는 **CI 실행 결과**이며 개인 PC의 실행 결과와 구분한다.

| 후보 | 검증 RMSE | 검증 MAE | 검증 R² |
|---|---:|---:|---:|
| 평균 기준 모델 | 4.251555 | 3.302727 | -0.006292 |
| Ridge | 3.297208 | 2.811120 | 0.394769 |
| RandomForest | 0.983442 | 0.786182 | 0.946157 |

검증 RMSE로 RandomForest를 선택해 ManufacturingQualityDemo 버전 1로 등록했다. 등록 모델 재로딩 후 예측값의 최대 절대 차이는 **0.0**이었고, 최종 평가 RMSE는 **0.923904**, MAE는 **0.774785**, R²는 **0.940139**였다. 이는 합성 데이터에서의 결과이며 실제 제조 예측 성능을 의미하지 않는다.

모델 저장 과정에서 직접 학습한 RandomForest의 sklearn.tree._tree.Tree 타입만 skops 신뢰 목록에 지정했다. 외부에서 받은 임의 모델 타입을 일괄 허용하는 코드는 사용하지 않는다.

[자동 실행 로그와 산출물](https://github.com/skgreenstar/skgreenstar.github.io/actions/runs/41328495691)


:::

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

PVC는 기본 StorageClass를 사용한다. `WaitForFirstConsumer`에서는 Job이 사용하는 mlflow-results가 소비 Pod 생성 전까지 Pending일 수 있다. 서버 데이터 PVC와 서버 Ready를 먼저 확인하고 Job 생성 후 결과 PVC의 Bound 상태·이벤트를 확인한다.

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

kind에서 Job Complete와 UI의 세 Run·모델 연결을 확인했다. 실행별 비교표·선택 모델 URI·재로딩 검증은 Job 로그와 MLflow 아티팩트로 추적한다. 접어둔 CI 표는 별도의 코드 검사 결과다.
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

## Kubernetes 서버 OOM 복구 기록

kind 배포 후 서버 Pod에서 CrashLoopBackOff, restarts=5, lastReason=OOMKilled, exitCode=137을 관찰했다. 서버가 종료된 동안 학습 Job은 experiments/get-by-name API의 Connection refused로 실패했다. 서버 로그의 Starlette 경고와 OOM 종료 사유를 구분했다.

| 관찰 | 대응 |
|---|---|
| 서버 memory limit 1Gi에서 OOMKilled | request 512Mi / limit 2Gi로 조정 |
| 서버 내장 job executor 초기화 로그 | 학습은 Kubernetes Job이 담당하므로 내장 실행 기능 비활성화 |
| 클라이언트 API 연결 실패 | 서버 Ready와 메모리 상태 확인 후 실패한 학습 Job 재생성 |
| 서버 데이터와 결과 저장 | 기존 PVC 유지 |

OOM의 정확한 프로세스별 메모리 원인은 별도 계측이 필요하다. 내장 executor가 원인이라고 단정하지 않으며, 불필요한 기능을 제외하고 메모리 여유를 확보하는 복구 구성이다. 환경변수 MLFLOW_SERVER_ENABLE_JOB_EXECUTION=false는 MLflow 내부 실행기를 끄는 설정이며 Kubernetes Job 실행과는 별개다.

```bash
curl -fL https://raw.githubusercontent.com/skgreenstar/skgreenstar.github.io/main/labs/week02-mlflow/mlflow-server.yaml -o mlflow-server.yaml
k apply -f mlflow-server.yaml
k rollout status deployment/mlflow --timeout=300s
k get pods -l app=mlflow
```

서버 안정화 후 실패한 mlflow-train Job을 정리하고 같은 train-job.yaml로 다시 실행한다. Pod 메모리·restartCount와 학습 로그를 함께 확인한다. 아래 서버 복구 확인에서 적용 후 health와 메모리·재시작 상태를 기록했다.
### 서버 복구 확인

수정된 YAML을 적용한 뒤 새 서버 Pod가 1/1 Running, RESTARTS=0으로 기동했다. 서버 컨테이너 내부에서 10초 간격으로 health 응답과 cgroup 메모리 사용량을 세 차례 확인했다.

| 표본 | HTTP health | memory.current |
|---|---|---:|
| 1 | 200 | 354.9 MiB |
| 2 | 200 | 355.2 MiB |
| 3 | 200 | 354.7 MiB |

검사 후 Pod AGE 38s 시점에도 1/1 Running, RESTARTS=0이었다. **관찰 구간에서 서버 응답과 재시작 상태가 안정화됐음을 확인**했다. 메모리 limit 상향과 내장 실행기 비활성화를 함께 적용했으므로 각각의 효과를 분리해 단정하지 않는다. 이 값은 서버 기동 후 관찰이며 학습 중 최대 메모리나 장기 안정성 측정으로 해석하지 않는다.

이후 학습 Job을 재생성해 같은 서버 Service에 연결했고, 위 Kubernetes 실행 결과처럼 Complete(1/1)와 UI 접속을 확인했다.

## 6. 다음 단계

[Feast 피처 관리](/ml-platform/model-pipeline)에서 같은 데이터 계약을 사용하고, [KFP 배치 추론](/ml-platform/kfp-batch-inference)으로 등록 모델 URI를 넘긴다. 등록한 모델을 Kubernetes에 올리면 기존 CPU·메모리·배포 실습을 모델 운영 검증으로 확장할 수 있다.

- [실행 코드](https://github.com/skgreenstar/skgreenstar.github.io/tree/main/labs/week02-mlflow)
- [MLflow Tracking](https://mlflow.org/docs/latest/ml/tracking/)
- [Model Registry](https://mlflow.org/docs/latest/ml/model-registry/workflow/)

