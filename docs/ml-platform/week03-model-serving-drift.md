---
title: "11 · 정상 응답하는 모델이 잘못된 예측을 한다면?"
outline: deep
prev:
  text: '10 · 요청 경로'
  link: '/ml-platform/week03-traffic'
---

# 11 · 정상 응답하는 모델이 잘못된 예측을 한다면?

**3주차 확장 주제 · BentoML × Data Drift × Prediction Drift × Concept Drift × Model Performance × Evidently**

이번 글은 교재 CH6·7을 대체하는 본문이 아니라 **우리만의 확장 학습**이다. CH6·7의 인프라 확장·트래픽 처리에서 한 단계 더 나아가, 모델이 빠르고 정상적으로 응답하는데도 예측 신뢰도가 떨어지는 상황을 다룬다.

## 1. 가용성과 예측 품질은 서로 다른 축이다

![BentoML 서빙에서 Data Drift 대응까지](/images/week03-drift-architecture.svg)

*이 그림은 개념 관계를 보여주는 학습용 아키텍처이며, 실제 실행·측정 결과가 아닙니다.*

| 측정 | 질문 | 대표 지표 | 도구 |
|---|---|---|---|
| 서비스 신뢰성 | 응답이 정상 도착했나? | RPS, p95, 5xx | Prometheus, Grafana |
| 인프라 용량 | 부하를 감당하나? | CPU, memory, HPA replicas | Kubernetes |
| 데이터 건강성 | 입력 조건이 바뀌었나? | 결측률, 범위 위반, 분포 차이 | Evidently |
| 모델 품질 | 예측이 실제 정답과 일치하나? | RMSE, MAE, MAPE, R² | MLflow, 정답 지연 수집 |

HTTP 200과 모델 성능 유지 사이에는 직접적인 보증 관계가 없다. **드리프트 탐지 결과만으로 모델 성능 저하가 확정되는 것도 아니다.**

## 2. BentoML: 모델 코드에서 재현 가능한 API로

BentoML은 `@bentoml.service`와 `@bentoml.api`로 모델 추론 인터페이스를 정의하고, 서빙 환경을 패키징하여 실행하는 프레임워크다. Kubernetes의 Service·HPA 자체를 대체하는 도구는 아니다. **BentoML은 애플리케이션 서빙 계층, Kubernetes는 배치·네트워킹·스케일링 계층**이라는 책임 분리가 중요하다.

```python
# 개념 예제: 실제 제조 모델이 아닌 합성 점수 서비스
import bentoml

@bentoml.service(resources={"cpu": "1"}, traffic={"timeout": 10})
class QualityScore:
    @bentoml.api
    def predict(self, temperature: float, pressure: float, speed: float) -> float:
        return float(0.2 * temperature + 0.3 * pressure + 0.5 * speed)
```

```bash
# 독립 가상환경에서 공식 문서 버전에 맞춰 설치
python3 -m venv .venv
source .venv/bin/activate
pip install bentoml
bentoml serve service:QualityScore
```

위 식은 서빙 구조 설명을 위한 예제이며 학습 모델도 실측 결과도 아니다. 실제 2주차 RandomForest를 연결한다면 모델 버전 URI, 입력 피처 순서, 자료형, 예측 로그의 모델 ID를 고정해야 한다. `bentoml build`·`containerize`는 사용하는 BentoML 버전의 권장 패키징 방식을 먼저 확인한다.

### FastAPI / BentoML / KServe / vLLM의 책임

| 도구 | 핵심 책임 | 채택 기준 |
|---|---|---|
| FastAPI | 범용 Python API | 자유로운 API 구현·기존 웹 서비스 통합 |
| BentoML | ML 서빙 API와 패키징 | 모델 중심 서비스 관리·배포 구조 |
| KServe | Kubernetes 모델 서빙 추상화 | 여러 모델·팀의 서빙 운영 표준화 |
| vLLM | LLM 토큰 생성 엔진 | GPU 추론·배칭·KV 캐시 효율 최적화 |

한 시스템에서 여러 도구를 조합할 수 있지만, 기능 중복·운영 복잡도·실제 성능을 측정하고 선택해야 한다.

## 3. Data Drift · 운영 데이터가 학습 데이터와 달라지는 현상

### 3.1 개념과 역할

**Data Drift(데이터 드리프트)**는 모델에 들어오는 입력 데이터의 통계적 분포가 기준 데이터와 달라지는 현상이다. 대표적으로 기준 기간의 입력 분포를 \(P_{ref}(X)\), 운영 기간을 \(P_{current}(X)\)로 두면 둘의 차이를 관찰한다. 여기서 \(X\)는 단일 피처일 수도, 여러 피처의 결합 분포일 수도 있다.

**ML 플랫폼에서의 역할은 모델이 학습할 때와 다른 입력 환경에 노출되는지를 조기에 감지하는 것**이다. 정답 라벨이 도착하기 전에도 입력 피처만으로 검사할 수 있기 때문에 운영 초기에 유용하다.

| 항목 | 설명 |
|---|---|
| 감시 대상 | temperature·pressure·speed 등의 피처 분포, 결측 비율, 값의 허용 범위 |
| 주요 원인 | 센서 교체·보정, 원자재 변경, 생산 조건·계절·고객 집단의 변화, 데이터 파이프라인 오류 |
| 감지 방법 | 기준 데이터와 현재 데이터의 히스토그램·분위수 비교, PSI·KS·Wasserstein distance 등 |
| 판단에 필요한 데이터 | 기준 기간 입력 데이터 + 현재 입력 데이터. 정답 \(Y\)는 필수 아님 |
| 플랫폼 역할 | 데이터 계약 검사, 기준 기간 관리, 피처별 경보, 모델 성능 검증의 우선순위 설정 |
| 한계 | 입력 분포가 달라졌다는 사실만으로 예측 성능 저하를 확정할 수 없음 |

**제조 예시:** 학습 데이터의 주요 운전 온도가 200℃ 부근이었는데 최근 220℃ 부근으로 이동했다. 이때 온도 분포에 변화가 있음을 탐지할 수 있다. 다만 모델이 220℃에서도 정확히 예측한다면 재학습이 반드시 필요한 것은 아니다.

### 3.2 Data Drift 운영 절차

1. 레퍼런스 구간을 고정하고 제품·생산 라인·설비별 비교 대상을 정의한다.
2. 누락값·타입·물리적 상하한·단위가 맞는지 **데이터 품질 검증을 먼저** 한다.
3. 입력 분포 차이와 변화량을 비교하고 계절성·표본 수·세그먼트 차이를 확인한다.
4. 변화가 크면 실제 라벨 확보 후 모델 성능 지표를 대조한다.
5. 필요한 경우 재학습 후보를 평가하되 **드리프트 경보만으로 모델을 자동 교체하지 않는다.**

## 4. Prediction Drift · 모델의 출력 패턴이 달라지는 현상

### 4.1 개념과 역할

**Prediction Drift(예측 드리프트)**는 배포된 모델이 생성한 예측값 \(\hat Y\)의 분포가 과거와 비교해 달라지는 현상이다. 입력뿐 아니라 모델이 실제로 어떤 출력을 내고 있는지 감시한다는 점에서 Data Drift와 다르다.

| 항목 | 설명 |
|---|---|
| 감시 대상 | 회귀 예측값의 평균·분산·분위수, 분류 예측 확률과 클래스 비율 |
| 감지 방법 | 기준/현재 예측값 분포 비교, 세그먼트별 점수·등급 비율 |
| 플랫폼 역할 | 모델 출력의 편향·이상 변화 조기 포착, 모델 버전 변경 영향 확인 |
| 정답 필요 여부 | 분포 비교에는 필요 없음 |
| 한계 | 출력 분포가 달라져도 실제 정답이 같은 방향으로 바뀌었다면 성능은 정상일 수 있음 |

**제조 예시:** 예측한 품질 점수의 평균이 최근 상승했다. 실제 품질 개선인지, 운전 온도 변화인지, 모델 버전 변경인지 확인하기 전에는 원인을 결정할 수 없다.

## 5. Concept Drift · 입력과 실제 정답의 관계가 달라지는 현상

### 5.1 개념과 역할

**Concept Drift(개념 드리프트)**는 동일하거나 비슷한 입력 \(X\)에 대한 실제 정답 \(Y\)의 생성 관계, 즉 \(P(Y\mid X)\)가 시간이 흐르며 달라지는 현상이다.

| 항목 | 설명 |
|---|---|
| 감시 대상 | 운전 조건별 실제 품질, 조건부 오차, 라벨과 예측값의 관계 |
| 주요 원인 | 설비 노후화, 공정 규칙 변경, 환경적·업무적 관계 변화 |
| 감지 방법 | 라벨 확보 후 시점·제품·설비별 오차 및 조건부 관계 분석 |
| 플랫폼 역할 | 기존 모델의 학습된 규칙이 현재도 유효한지 검증하고 재학습 필요성 판단 |
| 한계 | 입력 데이터 분포만 보는 Data Drift 검사에서는 놓칠 수 있음 |

**제조 예시:** 같은 온도·압력·속도로 생산해도 설비 마모로 실제 품질이 낮아진다. 입력 분포가 거의 변하지 않았더라도 모델의 예측 규칙은 더 이상 정확하지 않을 수 있다.

Concept Drift를 의심할 때도 라벨 정합성, 전처리 버그, 측정 방식 변경을 먼저 배제해야 한다.

## 6. Model Drift · 모델의 유효성과 실제 예측 성능 변화

### 6.1 개념과 역할

**Model Drift(모델 드리프트)**라는 용어는 문헌이나 제품에 따라 Data Drift·Concept Drift까지 포괄하는 넓은 의미로도 사용된다. 이 글에서는 혼동을 막기 위해 **실제 예측 성능이 시간이 지나며 악화되는 현상**을 *Model Performance Degradation(모델 성능 저하)*으로 별도 표기한다.

즉, Data Drift는 **입력의 변화**, Concept Drift는 **정답 생성 관계의 변화**, Model Performance Degradation은 **현재 운영에서 나타난 예측 오차의 악화**를 관찰한다.

| 항목 | 설명 |
|---|---|
| 감시 대상 | \(Y\)와 \(\hat Y\)의 오차, 제품·설비·기간별 성능 |
| 대표 지표 | 회귀: MAE·RMSE·R²·MAPE / 분류: Precision·Recall·F1·ROC AUC 등 |
| 필요 데이터 | 예측 당시 모델 버전·입력 시각·예측값 + 이후 확보한 실제 라벨 |
| 플랫폼 역할 | 운영 품질 검증, 성능 하락 경보, 후보 모델의 비교·승인·롤백 근거 |
| 주요 원인 후보 | Data Drift, Concept Drift, 학습/서빙 불일치, 데이터·코드 버그, 라벨 품질 문제 |
| 한계 | 성능 저하는 **결과**를 보여줄 뿐 발생 원인을 자동으로 특정하지 않음 |

**제조 예시:** 기준 기간 RMSE보다 최근 RMSE가 유의미하게 높아졌다면 모델 성능 저하를 의심할 수 있다. 하지만 원인이 온도 범위 확대인지, 설비 노후화인지, 입력 변환 오류인지 알아내려면 추가 진단이 필요하다.

### 6.2 모델 성능을 운영에서 확인하는 절차

1. 추론 이벤트에 \(equipment_id\), 예측 시각, 모델 버전, 예측값을 기록한다.
2. 사후에 확보된 실제 품질 \(Y\)를 **동일 설비·동일 시점의 예측과 정확히 조인**한다.
3. 시간 구간별 MAE·RMSE·R²를 검증 기준선과 비교한다.
4. 특정 제품·설비·온도 구간에서만 악화됐는지 세그먼트별로 분석한다.
5. 원인 확인 후 MLflow에서 후보 모델을 평가하고 품질 게이트를 통과한 버전만 배포한다.

**주의:** 실측 라벨이 늦게 들어오는 상황에서는 현재 성능을 실시간으로 확정할 수 없다. 입력·예측 분포는 조기 경보로 활용하고 실제 성능 판단은 라벨 확보 후 수행한다.

## 7. Training–Serving Skew · 학습과 운영 데이터 계약 불일치

이는 엄밀히 말해 시간에 따른 통계적 드리프트와 같은 개념이 아니다. 학습과 추론에서 **단위·전처리·피처 순서·결측 처리·스키마·버전**이 서로 다르면 모델이 잘못된 입력을 받을 수 있다.

**제조 예시:** 학습 때 200℃로 처리한 온도를 서빙에서는 392℉로 받아놓고 같은 수치 체계로 해석한다. 통계 검정 전에 피처 계약부터 확인해야 한다.

역할은 **MLflow 모델 버전, Feast 피처 정의, BentoML API 스키마, 학습·서빙 변환 로직의 일치성을 보증**하는 것이다.

## 8. Drift 유형별 차이를 한눈에 비교하기

![입력 데이터, 출력 데이터, 관계 변화, 모델 성능 저하의 도식](/images/week03-drift-types.svg)

*파랑은 기준 기간, 주황은 현재 기간을 나타내는 학습용 개념 그림이다. 실제 실험 측정값이 아니다.*

| 구분 | 확인 질문 | 변화 대상 | 라벨 필요? | 담당 모니터링 |
|---|---|---|---|---|
| Data Drift | 입력이 달라졌는가? | \(P(X)\) | 아니오 | Data / Feature Monitoring |
| Prediction Drift | 모델 출력이 달라졌는가? | \(P(\hat Y)\) | 아니오 | Prediction Monitoring |
| Concept Drift | 같은 조건의 정답 규칙이 달라졌는가? | \(P(Y\mid X)\) | 일반적으로 필요 | Concept / Quality Monitoring |
| Model Performance Degradation | 실제 예측이 더 틀리고 있는가? | \(L(Y,\hat Y)\) | **예** | Model Performance Monitoring |
| Training–Serving Skew | 학습·서빙 입력 처리가 같은가? | 변환·스키마·피처 계약 | 실제 정답은 불필요 | Data Contract / Lineage |

### 서로 다르게 나타나는 운영 사례

| 상황 | Data Drift | Concept Drift | 성능 저하 |
|---|---|---|---|
| 운전 온도 범위는 바뀌었지만 모델이 잘 일반화 | 발생 | 없을 수 있음 | 없을 수 있음 |
| 같은 운전 조건에서 설비 마모로 품질만 변화 | 없을 수 있음 | 발생 | 발생 가능 |
| 예측 평균과 실제 품질 모두 같은 방향으로 이동 | 발생 가능 | 확정 불가 | 없을 수 있음 |
| 학습·운영의 온도 단위가 서로 다름 | 검정 이전에 데이터 계약 위반 | 확정 불가 | 발생 가능 |

**운영 원칙:** 드리프트 알림은 곧바로 재학습 명령이 아니다. **입력 변화 탐지 → 출력 변화 확인 → 정답 기반 성능 평가 → 원인 진단 → 후보 모델 비교 → 배포 승인** 순으로 판단한다.

## 9. 드리프트 유형별 모니터링 아키텍처

![라벨 유무에 따른 드리프트 모니터링 및 대응 흐름도](/images/week03-drift-decision.svg)

*정답을 늦게 얻는 제조 공정을 가정한 진단 흐름. 실제 실행된 파이프라인이 아니라 설계 아키텍처다.*

### 9.1 라벨 없이 빠르게 감지할 수 있는 것

- 입력 피처의 레퍼런스 대비 분포, 결측 비율, 데이터 타입, 물리적 허용 범위
- 모델 예측값 분포 및 예측 확률 변화
- 설비·라인·제품·운전 조건별 세그먼트 변화
- 모델 버전, 피처 생성 파이프라인 버전, 스키마 해시

이는 **위험 신호(Proxy)**다. 정답이 없으면 RMSE를 직접 측정할 수 없으므로 데이터 드리프트만으로 성능이 나빠졌다고 단언하지 않는다.

### 9.2 라벨이 확보되면 평가하는 것

```text
MAE  = mean(|Y - Ŷ|)
RMSE = sqrt(mean((Y - Ŷ)²))
R²   = 1 - SSE/SST
```

각 지표를 **학습/검증 기준선과 운영 기간, 라인·제품별로** 비교한다. 라벨이 일정 기간 지연되어 들어오는 제조 환경에서는 **예측 발생 시점과 실제 품질 측정 시점을 entity_id로 결합**해야 한다. 예측 당시에는 없던 미래 피처를 붙이면 누수가 발생한다.

### 9.3 실무 조치 매트릭스

| 관찰 | 가능한 원인 | 우선 조치 |
|---|---|---|
| 입력 드리프트만 발생, 모델 성능 유지 | 정상적인 운전 구간 확대 | 감시 강화, 즉시 재학습 보류 |
| 입력 드리프트와 성능 저하 동시 발생 | 미학습 운전 영역, 결측·품질 문제 | 데이터 검증 후 후보 재학습 |
| 입력 드리프트 없음, 성능 저하 | Concept Drift, 라벨 오류, 코드/스키마 변경 | 조건부 관계와 계보 조사 |
| 예측값 드리프트만 발생 | 모델 버전, 입력 구성 변화 | champion 버전·데이터 구간 비교 |
| 예측값 변화 없음, 성능 저하 | 숨겨진 Concept Drift 가능 | 실제 라벨·잔차·세그먼트 분석 |
| 모델 성능 정상, p95 지연 증가 | 서빙/네트워크/용량 문제 | HPA·큐·Pod·Endpoint 확인 |

### 9.4 독립적인 네 개의 관찰 축

- **Input Monitoring:** Evidently 등으로 feature drift·데이터 품질 검사.
- **Output Monitoring:** 예측 점수/등급/확률 분포 모니터링.
- **Performance Monitoring:** 라벨 확보 후 오차/정확도와 세그먼트별 안정성 평가.
- **Serving Monitoring:** Prometheus·Grafana로 p95·RPS·오류율·HPA 상태 분석.

분포 비교를 제공하는 도구로 Evidently를 사용할 수 있지만, **실제 성능 검증을 하려면 라벨과 모델 예측을 별도로 연결**해야 한다. 자동 재학습의 실행 여부는 품질 게이트에서 판단한다.

### 9.5 지표 해석에서 주의할 점

PSI·KS 등의 분포 검정은 기준 기간 선택, 표본 크기, 세그먼트 구성에 민감하다. 동일한 분포에서도 표본이 매우 크면 미세한 변화를 감지할 수 있고, 표본이 작으면 중요한 변화를 놓칠 수 있다. **통계적 변화량·업무적 영향·모델 성능**을 함께 판단한다.

관련 근거: [IBM Model Drift](https://www.ibm.com/think/topics/model-drift), [Evidently ML Observability](https://learn.evidentlyai.com/ml-observability-course/module-2-ml-monitoring-metrics/data-prediction-drift-in-ml), [IEEE Concept Drift](https://technav.ieee.org/topic/concept-drift/).

## 10. Evidently로 Reference와 Current 비교

Evidently는 reference dataset과 current dataset을 비교해 입력·출력 분포의 변화를 분석하고 리포트로 출력한다. 도구 버전에 따라 API가 달라지므로 이전 `DataDriftPreset` 문법을 무조건 최신 버전으로 가정하지 않는다.

```python
# Evidently 최신 API 계열의 개념 예시. 설치 버전과 import 경로 확인 필요.
from evidently import Report, Dataset
from evidently.presets import DataDriftPreset
import pandas as pd

reference_df = pd.read_csv("reference.csv")
current_df = pd.read_csv("current.csv")
report = Report([DataDriftPreset()])
result = report.run(
    current_data=Dataset.from_pandas(current_df),
    reference_data=Dataset.from_pandas(reference_df),
)
result.save_html("drift-report.html")
```

학습용 CSV는 2주차 합성 제조 데이터 계약과 동일한 피처명 `temperature`, `pressure`, `speed`를 사용하도록 맞춘다. 실제 비교 전에는 reference의 선택 시점과 현행 데이터의 기간·표본 수·결측·시즌성을 기록한다.

### 드리프트 탐지 설계

| 실험 | 변화시킬 조건 | 기대하는 확인 사항 |
|---|---|---|
| 기준선 | 동일 생성 규칙, 다른 표본 | 정상 데이터에서도 검정 오탐 가능성 |
| 운전 구간 이동 | temperature 평균 이동 | 분포 차이 감지 |
| 분산 증가 | pressure 변동 폭 확대 | 평균만 보면 놓치는 변화 |
| 범위 외 입력 | speed가 계약 상한 초과 | 통계 검정 전에 데이터 계약 위반 |
| Concept 변화 | 동일 X, 다른 Y 생성식 | X 드리프트만으로는 미탐 가능 |

데이터 드리프트의 검정 임계값과 표본 크기는 탐지 민감도에 영향을 준다. 여러 피처를 동시에 검사할 때 다중 비교와 계절성도 검토한다. 실제 품질 이슈의 크기와 통계적 유의성을 구분해야 한다.

## 11. 경보는 재학습 명령이 아니다

단일 drift flag로 재학습을 바로 실행하면 불필요한 배포·학습 비용이나 잘못된 모델 교체로 이어질 수 있다. 운영 정책은 **관찰 → 검증 → 후보 모델 생성 → 오프라인 비교 → 배포 승인 → 카나리 검증** 순서로 설계한다.

| 조건 | 권장 조치 |
|---|---|
| Drift 감지, 성능 정답 없음 | 로그·표본 확인, 드리프트 원인 조사 |
| Drift 감지 + 성능 악화 | 피처·라벨 지연·세그먼트 분석 후 재학습 후보 |
| Drift 미감지 + 성능 악화 | concept drift, skew, 버그 점검 |
| Drift 감지 + 성능 정상 | 모니터링 강화, 즉각 배포 보류 가능 |
| 서비스 오류율 증가 + Drift 없음 | 서빙·네트워크·자원 문제 우선 |

## 12. 2주차 산출물과 연결할 때 유지할 계약

- **MLflow:** 학습 run, 모델 버전, 선정 이유, 원본 해시
- **Feast:** entity, event_timestamp, feature names, online/offline 기준
- **KFP:** 검증 단계, 예측 파일, drift report artifact의 입출력 계약
- **BentoML:** 추론 API 스키마와 고정 모델 아티팩트 로딩
- **Evidently:** reference/current 메타데이터, 피처 별 결과, 리포트 생성 시점
- **Kubernetes:** 이미지 다이제스트, Service 경로, replica/Ready 및 운영 지표

모델 품질 이력을 확인하려면 각 예측에 모델 버전·데이터 시각·요청 추적 ID를 연결해야 한다. 다만 개인정보나 민감한 원문 데이터를 모니터링 로그에 그대로 남기는 설계는 피한다.

## 13. 검증 범위와 후속 실습

이 글은 설계·코드 초안이다. **BentoML 실제 서비스 실행, Evidently drift HTML 생성, Kubernetes 배포, 성능 측정은 아직 수행하지 않았다.** 실행 성공을 주장하려면 CLI 버전, 데이터 생성 스크립트, 실제 보고서, 결과 수치와 GitHub Actions/클러스터 로그를 추가해야 한다.

[3주차 학습 정리로 돌아가기](/ml-platform/study-week-03)

공식 참고: [BentoML Service](https://docs.bentoml.com/en/latest/build-with-bentoml/services.html), [Bento Packaging](https://docs.bentoml.com/en/latest/get-started/packaging-for-deployment.html), [Evidently Docs](https://docs.evidentlyai.com/), [Evidently API](https://evidentlyai.github.io/evidently/api-reference/main/evidently/core/report.html)
