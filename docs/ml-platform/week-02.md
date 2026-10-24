---
title: "모델 학습에 CI/CD만 적용하면 충분할까?"
description: "DevOps와 MLOps의 차이를 변경 관리와 재학습 관점에서 정리"
date: 2026-10-25
outline: deep
---

# 모델 학습에 CI/CD만 적용하면 충분할까?

일반적인 애플리케이션에서는 코드 변경이 배포의 주요 출발점이다. 머신러닝 시스템은 조금 다르다. 코드가 그대로여도 학습 데이터가 바뀌면 모델이 달라지고, 모델이 그대로여도 운영 데이터가 바뀌면 품질이 떨어질 수 있다.

MLOps는 DevOps를 대체하는 개념이 아니다. **코드 외에 데이터와 모델도 변경 관리의 대상으로 확장**하는 접근에 가깝다.

## 1. 무엇이 달라지는가

| 구분 | 일반적인 서비스 | ML 기반 서비스 |
|---|---|---|
| 주요 변경 요소 | 코드·설정 | 코드·설정·데이터·피처·모델 |
| 테스트 | 기능·통합·성능 | 기능 테스트 + 데이터·모델 검증 |
| 릴리스 산출물 | 애플리케이션 이미지 | 이미지 + 모델 + 전처리·피처 정의 |
| 운영 이상 신호 | 오류·지연·가용성 | 오류·지연 + 데이터 변화·예측 품질 |
| 롤백 | 애플리케이션 버전 | 코드·모델·피처 호환성 함께 검토 |

모델 파일만 이전 버전으로 되돌려도 입력 스키마가 달라졌다면 서비스는 복구되지 않을 수 있다. **롤백 가능한 단위**를 어떻게 정의할지부터 생각해야 한다.

## 2. CI, CD, CT를 구분하는 이유

- **CI(Continuous Integration):** 코드와 파이프라인 변경이 기존 계약을 깨뜨리지 않는지 검증한다.
- **CD(Continuous Delivery/Deployment):** 검증된 애플리케이션과 모델을 운영 환경에 전달한다.
- **CT(Continuous Training):** 새 데이터나 정해진 조건에 따라 모델 후보를 다시 학습하고 평가한다.

![변경 검증과 배포 흐름](/diagrams/gitops-pipeline.svg)

여기서 **Continuous Delivery**는 배포 가능한 상태를 지속적으로 준비하는 것이며, 운영 반영 전에 수동 승인이 있을 수 있다. **Continuous Deployment**는 검증된 변경을 운영까지 자동 반영한다. 둘 다 CD로 표기될 수 있으므로 문맥을 구분해야 한다.

CT를 자동화하더라도 **재학습 성공 = 배포 승인**은 아니다. 새 모델은 기존 모델과 동일한 평가셋에서 비교하고, 중요한 구간에서 성능이 후퇴하지 않았는지 확인해야 한다.

## 3. 데이터 검증에서 릴리스 승인까지

![ML 모델 변경 시 품질 게이트](/diagrams/ml-release-gates.svg)

처음부터 모든 과정을 복잡한 워크플로로 만들 필요는 없다. 실패 비용이 큰 단계부터 자동화하는 편이 낫다.

```text
Change detected
  ↓
Code / data contract tests
  ↓
Train candidate model
  ↓
Evaluate against baseline
  ↓
Register versioned artifact
  ↓
Approve release
  ↓
Deploy → Monitor → Roll back if needed
```

예를 들어 데이터 스키마가 변경되었는데 학습을 먼저 시작하면 자원만 소비하고 뒤늦게 실패할 수 있다. 반대로 값의 범위가 바뀌었지만 스키마가 같다면 단위 테스트는 통과해도 모델 품질은 달라질 수 있다.

그래서 **데이터 계약 검증과 모델 평가를 별도의 게이트**로 둬야 한다.

## 4. 모델을 배포할 때 묶어야 할 버전

배포 이력을 기록할 때 모델 이름과 버전만으로는 부족할 수 있다.

| 대상 | 필요한 이유 |
|---|---|
| 모델 아티팩트 | 어떤 가중치를 사용했는가 |
| 추론 이미지 | 어떤 코드와 라이브러리에서 실행했는가 |
| 피처 스키마 | 입력 컬럼과 전처리 규칙이 호환되는가 |
| 평가 데이터셋 | 어떤 기준으로 승인했는가 |
| 배포 설정 | 자원, 타임아웃, 트래픽 분배가 무엇인가 |

이 연결이 있어야 특정 릴리스에서 발생한 품질 저하를 조사할 수 있다.

## 5. 재학습 여부를 판단하는 기준

주기적으로 재학습하는 것이 항상 최선은 아니다. 새로운 데이터가 들어왔다는 사실만으로 새 모델이 더 좋아지는 것도 아니다.

재학습을 검토할 때는 데이터 품질, 라벨 확보 시점, 기존 모델의 구간별 성능, 재학습 비용을 함께 확인한다. 특히 정답이 늦게 확보되는 업무에서는 실시간 품질 평가 자체가 어렵기 때문에 대체 지표와 사후 검증을 구분해야 한다.

**자동화의 목적은 사람이 판단할 일을 없애는 것이 아니라, 판단에 필요한 증거를 반복 가능하게 만드는 것**이라고 생각한다.

### 산업 AI에서는 재학습보다 검증 조건이 먼저다

설비 데이터는 시간이 지날수록 누적되지만, 새 데이터가 항상 새 정보를 뜻하지는 않는다. 안정된 운전 구간의 데이터만 계속 추가되면 모델이 특정 구간에 더 편향될 수도 있다.

재학습 후보를 평가할 때는 다음과 같은 **운영 조건별 게이트**를 둘 수 있다.

| 게이트 | 확인 내용 | 실패 시 조치 |
|---|---|---|
| 데이터 | 센서 결측·범위·수집 주기 | 학습 중단 및 수집 경로 점검 |
| 시점 | 예측 시점 이후의 변수 사용 여부 | 피처 생성 로직 수정 |
| 성능 | 기준 모델 대비 MAE·RMSE·R², 구간별 오차 | 후보 모델 보류 |
| 제약 | 업무상 허용되지 않는 예측·권고 발생 여부 | 배포 차단 |
| 운영 | 응답 지연·메모리·비용 | 서빙 구성 재검토 |

예를 들어 목표값의 분산이 작은 공정에서 MAPE만 개선되었다면 충분한 배포 근거가 되지 않는다. **평가셋의 기간과 운전 조건을 고정하고, 기준 모델과 같은 조건에서 비교**해야 한다. 이때 수치 임계값은 업무 위험도와 실제 데이터 분포를 바탕으로 정해야 한다.

## 6. 코드로 보는 첫 번째 품질 게이트

CI에서 가장 먼저 확인할 것은 거창한 학습 파이프라인보다 **입력 데이터가 약속한 형식을 지키는가**다. 아래는 필수 컬럼과 결측치를 확인하는 최소 예시다.

```python [validate_data.py]
import pandas as pd

REQUIRED_COLUMNS = {"timestamp", "temperature", "target"}

def validate(df: pd.DataFrame) -> None:
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")
    if df[sorted(REQUIRED_COLUMNS)].isna().any().any():
        raise ValueError("Null values in required columns")

if __name__ == "__main__":
    validate(pd.read_csv("train.csv"))
    print("Data contract passed")
```

```bash [terminal]
python -m pip install pandas
python validate_data.py
```

이 코드는 **필수 컬럼·결측치만 확인하는 최소 데이터 계약 검사**다. 모델 학습이나 성능 평가를 수행하지 않으며, 실제 운영에서는 값의 범위·데이터 타입·시점 정합성·분포 변화 검증과 별도의 모델 평가 Job 및 릴리스 승인이 필요하다.

```yaml [data-check.yml]
name: Data contract
on: [push, pull_request]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python -m pip install pandas
      - run: python validate_data.py
```

이 워크플로는 **데이터 검증용 CI**이며 CT·CD를 수행하지 않는다. 저장소 루트에 `validate_data.py`와 `train.csv`가 있어야 한다.

GitHub Actions에서는 `.github/workflows/data-check.yml`에 저장한다.


---

**이전 글:** [모델을 만들고 나서 시작되는 일들](/ml-platform/week-01)  
**다음 글:** [ML 플랫폼을 설계할 때 먼저 정할 것들](/ml-platform/week-03)

### 참고 자료

- [Google — MLOps: Continuous Delivery and Automation Pipelines in Machine Learning](https://cloud.google.com/architecture/mlops-continuous-delivery-and-automation-pipelines-in-machine-learning)
- [MLflow Documentation](https://mlflow.org/docs/latest/index.html)
