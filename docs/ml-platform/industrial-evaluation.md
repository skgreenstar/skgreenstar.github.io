---
title: "MAPE는 낮은데 R²는 왜 낮을까?"
description: "산업 시계열 회귀 모델의 평가 지표, 기준 모델, 구간별 성능 검증"
date: 2026-10-25
outline: deep
---

# MAPE는 낮은데 R²는 왜 낮을까?

공정 데이터를 예측하는 회귀 모델에서 MAPE는 낮은데 R²는 기대보다 낮게 나오는 경우가 있다. 서로 모순되는 결과는 아니다. **두 지표가 서로 다른 질문에 답하기 때문**이다.

MAPE는 실제값 대비 상대 오차를 보고, R²는 평가셋의 평균값을 예측하는 단순한 기준과 비교해 잔차제곱합이 얼마나 줄었는지 본다. 목표값이 좁은 범위에서 움직이는 산업 데이터라면 두 값의 차이가 특히 크게 느껴질 수 있다.

## 1. 같은 예측을 서로 다르게 평가하는 이유

| 지표 | 계산 개념 | 무엇을 판단할 때 유용한가 |
|---|---|---|
| MAE | 절대오차 평균 | 실제 단위로 허용 오차를 정할 때 |
| RMSE | 제곱오차 평균의 제곱근 | 큰 오차가 위험한 공정일 때 |
| MAPE | 절대백분율오차 평균 | 실제값이 0에서 충분히 떨어져 있을 때 상대 오차 비교 |
| R² | 1 − SSE / SST | 평가셋 평균 예측 대비 개선 여부 |

**R²는 음수가 될 수 있다.** 후보 모델의 제곱오차 합이 평가셋 평균값을 예측하는 기준보다 크면 음수가 된다. 목표값의 변동폭이 작아 SST가 작을 때는, 절대오차가 작아도 R²가 낮게 나타날 수 있다.

MAPE는 실제값이 0이면 정의되지 않고, 0에 가까우면 매우 불안정하다. 음수나 0 근처의 목표값이 존재하는 문제라면 MAE·RMSE처럼 원래 단위로 해석할 수 있는 지표를 함께 사용해야 한다.

## 2. 작은 예제로 직접 비교하기

```python [regression_metrics.py]
import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

y_true = np.array([100.0, 101.0, 99.0, 100.5])
y_pred = np.full_like(y_true, 100.0)

mae = mean_absolute_error(y_true, y_pred)
rmse = np.sqrt(mean_squared_error(y_true, y_pred))
r2 = r2_score(y_true, y_pred)
mape = np.mean(np.abs((y_true - y_pred) / y_true)) * 100

print(f"MAE={mae:.3f}")
print(f"RMSE={rmse:.3f}")
print(f"MAPE={mape:.3f}%")
print(f"R2={r2:.3f}")
```

```bash [terminal]
python -m pip install numpy scikit-learn
python regression_metrics.py
```

**예상 출력**

```text [output]
MAE=0.625
RMSE=0.750
MAPE=0.624%
R2=-0.029
```

평균 부근의 상수만 예측해도 상대 오차는 작다. 그러나 평가 데이터의 변화를 제대로 설명하지 못해 R²는 음수가 될 수 있다. 이 수치는 지표를 비교하기 위한 예시이며 실제 공정의 측정 결과는 아니다.

## 3. 산업 시계열에서는 평가셋을 먼저 설계한다

무작위 분할은 시간적으로 인접한 관측값을 학습·평가 양쪽에 배치할 수 있다. 센서 데이터가 자기상관을 가진다면 실제 미래 성능보다 낙관적인 결과가 나올 수 있다.

- **미래 시점 일반화:** 과거 학습 → 이후 검증 → 더 이후의 최종 평가로 나눈다.
- **설비·배치 일반화:** 새로운 설비나 배치에 적용할 계획이라면 그룹 분리도 검토한다.
- **시점 정합성:** 예측 시점 이후에 수집된 값이나 목표값에서 계산한 피처를 사용하지 않는다.
- **전처리 누수:** 스케일러·결측치 대체기·피처 선택은 학습 구간에서만 학습한다.

![산업 시계열의 시간 기준 검증](/diagrams/industrial-validation.svg)

시간 분할과 피처 생성 예제는 [ML Lifecycle 글](/ml-platform/week-01)에서 이어서 볼 수 있다.

## 4. 평균 점수보다 중요한 실패 구간

전체 MAE나 MAPE가 양호해도 특정 운전 조건에서만 큰 오차가 발생할 수 있다. 특히 모델의 출력을 공정 조건 변경에 활용한다면 다음을 함께 확인해야 한다.

| 확인 대상 | 검토 질문 |
|---|---|
| 기준 모델 | 직전값 유지·이동 평균 등 단순 예측보다 나은가? |
| 운전 구간 | 온도·압력·부하 조건별 오차가 다른가? |
| 변화 방향 | 상승·하락 전환 시점을 포착하는가? |
| 제약 | 예측이나 권고가 물리적·업무적 한계를 위반하는가? |
| 데이터 품질 | 결측, 센서 교체, 수집 지연이 평가에 영향을 주는가? |

운영 목적이 단순한 상태 모니터링인지, 실제 최적화 의사결정인지에 따라 중요한 오류도 달라진다. **좋은 평가란 가장 높은 점수를 찾는 것이 아니라, 모델이 사용될 조건에서 실패를 발견할 수 있는 평가**다.

## 정리

산업 AI 회귀 평가에서는 MAE·RMSE·MAPE·R²를 함께 읽되, 서로 같은 의미의 점수로 취급하지 않는다. 데이터의 변동폭, 예측 시점, 운영 구간, 기준 모델을 고정한 뒤 비교해야 결과를 해석할 수 있다.

**관련 글:** [ML Lifecycle](/ml-platform/week-01) · [MLOps의 릴리스 게이트](/ml-platform/week-02)

### 참고 자료

- [scikit-learn — Regression metrics](https://scikit-learn.org/stable/modules/model_evaluation.html#regression-metrics)
- [scikit-learn — TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html)
