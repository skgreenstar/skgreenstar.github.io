---
title: "모델을 만들고 나서 시작되는 일들"
description: "ML Lifecycle을 모델 개발과 운영 사이의 연결 문제로 바라보기"
date: 2026-10-25
outline: deep
---

# 모델을 만들고 나서 시작되는 일들

모델을 학습시키고 성능을 확인하면 개발이 끝난 것처럼 느껴질 때가 있다. 하지만 실제 서비스에서는 그때부터 새로운 질문이 생긴다. **어떤 데이터로 학습했는지, 같은 결과를 다시 만들 수 있는지, 운영 데이터가 바뀌면 무엇을 확인할지.**

ML Lifecycle은 단계를 외우기 위한 개념이라기보다, 이런 질문이 발생하는 위치를 찾는 지도에 가깝다.

## 1. ML Lifecycle을 하나의 흐름으로 보기

![ML 시스템의 주요 단계](/diagrams/ml-lifecycle.svg)

일반적인 흐름은 문제 정의, 데이터 수집·검증, 피처 구성, 학습, 평가, 배포, 모니터링으로 설명할 수 있다. 다만 운영 시스템에서는 이 과정이 일직선으로 끝나지 않는다. 운영 중 발견한 오류가 데이터 정의를 바꾸고, 그 변경이 다시 학습과 평가로 이어진다.

| 단계 | 만드는 것 | 다음 단계로 넘기기 전에 확인할 것 |
|---|---|---|
| 문제 정의 | 목표 지표와 제약 | 예측 결과가 실제 의사결정에 사용되는가 |
| 데이터 | 학습·평가 데이터셋 | 누락, 중복, 시점, 분포 |
| 학습 | 모델과 실행 기록 | 데이터·코드·설정의 재현 가능성 |
| 평가 | 성능 결과와 실패 사례 | 기준 모델 대비 개선, 구간별 회귀 |
| 배포 | 추론 서비스 | 응답 시간, 자원, 장애 대응 |
| 운영 | 로그·모니터링·피드백 | 데이터 변화와 품질 저하를 구분할 수 있는가 |

## 2. ML Engineer는 모델 밖의 문제까지 다룬다

실험 단계에서는 데이터 분석과 모델 선택이 중심이지만, 서비스를 운영하려면 소프트웨어 엔지니어링 역량이 함께 필요하다. 학습 코드를 재현 가능한 작업으로 만들고, 모델과 피처의 버전을 연결하며, API·컨테이너·모니터링까지 설계해야 한다.

| 역량 | 운영 환경에서 필요한 이유 |
|---|---|
| ML·통계 | 모델의 성능과 실패 조건을 판단한다 |
| 데이터 엔지니어링 | 입력 데이터의 품질·시점·계보를 관리한다 |
| 소프트웨어 엔지니어링 | 테스트·패키징·API 계약을 일관되게 유지한다 |
| 인프라·운영 | 배포·권한·확장·장애 복구를 관리한다 |

한 사람이 모든 영역을 전담해야 한다는 뜻은 아니다. **모델 팀과 플랫폼 팀 사이에 어떤 계약이 필요한지 이해하는 것**이 ML Engineering의 중요한 역할이다.

## 3. 실험 성능과 운영 품질은 왜 다를까?

제조 데이터처럼 목표값의 변화 폭이 작다면 평균값에 가까운 예측만으로도 MAPE가 낮게 나올 수 있다. 하지만 설비 조건이 달라졌을 때 변화 방향을 제대로 포착하지 못할 수 있다.

여기서 중요한 건 지표 하나의 높고 낮음보다 **모델을 어디에 사용할 것인가**다. 예측값을 단순 참고 정보로 보여주는지, 운전 조건을 변경하는 판단에 사용하는지에 따라 허용할 오류의 범위가 달라진다.

- 전체 평균 외에 운전 구간별 오차를 확인한다.
- 시간 순서가 중요한 데이터는 검증 분할도 시간 구조를 반영한다.
- 추론 시점에 알 수 없는 변수가 피처에 포함되지 않았는지 확인한다.
- 모델의 출력이 실제 업무 제약을 충족하는지 검증한다.

모델을 바꾸기 전에 데이터 정의와 평가 방법을 확인해야 하는 이유다. 구체적인 지표 비교는 [산업 AI 회귀 평가](/ml-platform/industrial-evaluation)에서 다룬다.

## 3. 재현성은 모델 파일을 저장하는 것으로 끝나지 않는다

동일한 코드라도 데이터 스냅샷, 전처리 방식, 라이브러리 버전이 바뀌면 다른 결과가 나온다. 재현성을 확보하려면 학습 실행을 다음 정보와 연결해야 한다.

```text
run_id
 ├─ code_commit
 ├─ data_snapshot
 ├─ feature_definition
 ├─ environment / dependency_lock
 ├─ parameters / random_seed
 ├─ evaluation_dataset / metrics
 └─ model_artifact
```

이 정보가 남아 있어야 운영 중 품질이 떨어졌을 때 **모델이 바뀐 것인지, 데이터가 바뀐 것인지** 구분할 수 있다.

## 4. 배포 이후의 관측 기준

모델 정확도만 추적해서는 충분하지 않다. 입력 분포와 서비스 동작을 함께 봐야 한다.

| 관찰 대상 | 확인할 질문 |
|---|---|
| 데이터 품질 | 필수 값이 누락되거나 스키마가 바뀌었는가 |
| 데이터 분포 | 학습 시점과 다른 조건이 늘어났는가 |
| 예측 결과 | 출력 분포나 특정 구간의 오차가 달라졌는가 |
| 서빙 | p95 지연시간과 오류율이 허용 범위인가 |
| 비용 | 요청량 증가에 따라 비용이 어떻게 변하는가 |

데이터 드리프트가 감지됐다고 무조건 재학습하는 것은 아니다. 데이터 수집 방식이 바뀐 것인지, 실제 환경이 변한 것인지 먼저 확인해야 한다. **드리프트 탐지는 원인 조사 신호이지 자동 재학습 명령이 아니다.**

## 5. 운영 중 발견하는 변화의 원인

| 개념 | 의미 | 확인할 것 |
|---|---|---|
| **Data Drift** | 입력 변수의 분포가 학습 시점과 달라짐 | 센서 교체, 계절성, 운전 조건 변화 |
| **Concept Drift** | 입력과 목표값 사이의 관계가 달라짐 | 같은 조건에서 결과가 달라지는지, 지연 라벨로 확인 |
| **Training-Serving Skew** | 학습과 추론의 피처 생성·처리 방식이 다름 | 스케일링, 결측치 처리, 피처 정의와 버전 |

Data Drift가 있다고 반드시 성능이 떨어지는 것은 아니고, Concept Drift는 정답 라벨이 늦게 도착하면 즉시 판정하기 어렵다. Training-Serving Skew는 분포 변화가 아니라 **학습·서빙 구현의 불일치**라는 점에서 구분해야 한다.

### 데이터 누수와 학습·서빙 일치성

모델을 학습할 때는 데이터 누수(Data Leakage), 특히 **추론 시점에는 알 수 없는 미래 정보**가 피처에 들어갔는지 확인한다. 모델이 배포된 뒤에는 입력 스키마뿐 아니라 전처리 코드와 피처 정의가 학습 시점과 동일한지도 확인한다.

## 6. 산업 시계열 검증: 분할부터 누수 방지까지

![시간 순서에 따른 학습·검증·평가 구간](/diagrams/industrial-validation.svg)

설비 센서 데이터는 독립적인 행의 집합이 아니다. 온도·압력·유량처럼 시간에 따라 관측되는 변수는 **자기상관(autocorrelation)**을 가질 수 있다. 가까운 시점의 값이 비슷하다는 뜻이다. 따라서 행을 무작위로 나누면 학습 데이터와 평가 데이터가 지나치게 유사해져, 실제 미래 예측 성능을 낙관적으로 볼 위험이 있다.

시계열 회귀 문제에서는 먼저 **예측 시점과 예측 대상 시점**을 구분한다. 예를 들어 10분 뒤 품질을 예측한다면, 예측 시점 이후에 측정된 센서값이나 결과값은 입력으로 사용할 수 없다.

| 확인 항목 | 검증 질문 |
|---|---|
| 시간 기준 | 예측 시점에 실제로 확보 가능한 변수인가? |
| 지연 변수(lag) | 과거값을 만드는 과정에서 미래 행을 참조하지 않았는가? |
| 이동 통계(rolling) | 현재·미래 목표값이 집계에 섞이지 않았는가? |
| 설비·배치 구분 | 같은 배치가 학습·평가에 동시에 포함되어 성능을 부풀리지 않는가? |
| 기준 모델 | 직전값 유지 또는 단순 평균보다 개선되었는가? |

아래는 **현재 시점의 목표값을 예측할 때 직전 시점까지의 센서값만 사용**하도록 만드는 예시다. 센서의 수집 지연이 있다면 실제 가용 시점을 기준으로 지연 폭을 더 늘려야 한다.

```python [causal_features.py]
import pandas as pd

df = pd.read_csv("measurements.csv", parse_dates=["timestamp"])
df = df.sort_values("timestamp").reset_index(drop=True)

# 예측 시점 이전에 관측된 온도만 사용
df["temperature_lag1"] = df["temperature"].shift(1)
df["temperature_mean_3"] = (
    df["temperature"].shift(1).rolling(window=3, min_periods=3).mean()
)

features = df.dropna(subset=["temperature_lag1", "temperature_mean_3"])
print(features[["timestamp", "temperature_lag1", "temperature_mean_3"]].head())
```

여기서는 단일 설비·동일 간격으로 수집된 데이터라고 가정했다. 여러 설비가 섞여 있다면 설비별로 그룹화한 후 지연·이동 통계를 계산해야 한다. 시간 간격이 불규칙하다면 단순 행 기반 rolling 대신 시간 기반 윈도우를 검토한다.

### 시점 기준 분할 예제

같은 모델이라도 데이터를 어떻게 나누느냐에 따라 평가 결과가 달라진다. 시계열 데이터라면 미래 데이터를 학습에 섞지 않도록 시간 순서를 유지하는 것이 출발점이다.

```python [time_split.py]
import pandas as pd

df = pd.read_csv("measurements.csv", parse_dates=["timestamp"])
df = df.sort_values("timestamp").reset_index(drop=True)

# 같은 시각의 관측값이 양쪽에 섞이지 않도록 시각 기준으로 분리
unique_times = df["timestamp"].dropna().unique()
assert len(unique_times) >= 2, "At least two distinct timestamps required"
cutoff = unique_times[int(len(unique_times) * 0.8)] if len(unique_times) >= 5 else unique_times[-1]
train = df[df["timestamp"] < cutoff]
test = df[df["timestamp"] >= cutoff]

assert not train.empty and not test.empty
assert train["timestamp"].max() < test["timestamp"].min()
print(f"train={len(train)}, test={len(test)}")
```

`measurements.csv`는 결측치 없는 `timestamp` 컬럼이 있고 서로 다른 시각이 최소 2개인 데이터를 가정한다. 이 코드는 시간 분할의 기본 형태이며, 시간적으로 인접한 관측치의 누수나 피처 생성 과정의 미래 정보 사용까지 자동으로 방지하지는 않는다.

```bash [terminal]
python -m venv .venv
source .venv/bin/activate
python -m pip install pandas
python time_split.py
```

Windows PowerShell에서는 활성화 명령을 `.venv\Scripts\Activate.ps1`로 바꿔 실행한다.


### 시간 분할만으로 누수가 사라지는 것은 아니다

시간 순서를 지켜 나눴더라도 **전체 데이터로 스케일러를 학습한 뒤 분할**하면 평가 구간의 통계가 학습에 들어간다. 스케일링·결측치 대체·특성 선택 등 학습이 필요한 전처리는 학습 구간에서만 `fit`하고, 검증·평가 구간에는 동일한 변환을 `transform`으로 적용해야 한다.

설비나 배치 간 의존성이 크다면 시간 분할 외에 설비별·배치별 분리 평가도 고려한다. 어떤 검증 방식이 적절한지는 **운영에서 일반화하려는 대상이 미래 시점인지, 새로운 설비인지**에 따라 달라진다.

## 7. 결국 중요한 것은 단계 사이의 연결

ML Lifecycle에서 놓치기 쉬운 부분은 단계 자체보다 **단계 사이의 계약**이다. 데이터팀이 넘긴 피처의 의미가 학습과 서빙에서 같아야 하고, 평가에 사용한 모델과 실제 배포한 모델이 같아야 한다.

그래서 플랫폼을 설계할 때는 도구 목록보다 먼저 세 가지를 확인하려고 한다.

1. 어떤 변경이 발생했는지 추적할 수 있는가?
2. 변경이 성능과 운영에 미치는 영향을 검증할 수 있는가?
3. 문제가 발생했을 때 이전 상태로 되돌릴 수 있는가?

이 세 질문이 다음 글에서 다룰 MLOps 자동화의 출발점이다.


---

**다음 글:** [모델 학습에 CI/CD만 적용하면 충분할까?](/ml-platform/week-02)

### 참고 자료

- [Google — Rules of Machine Learning](https://developers.google.com/machine-learning/guides/rules-of-ml)
- [Hidden Technical Debt in Machine Learning Systems](https://papers.nips.cc/paper/5656-hidden-technical-debt-in-machine-learning-systems)
