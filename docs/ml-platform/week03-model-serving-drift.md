---
title: "11 · BentoML 서빙과 모델 모니터링"
outline: deep
prev:
  text: '10 · 요청 경로'
  link: '/ml-platform/week03-traffic'
---

# 11 · BentoML 서빙과 모델 모니터링

BentoML로 모델을 API 형태로 제공하고, 운영 데이터와 모델 성능의 변화를 어떻게 감시할지 정리했다. 실습 모델은 제조 품질 회귀 문제를 기준으로 한다.

6~7장에서 다룬 배포와 트래픽 처리는 서비스의 가용성을 높인다. 하지만 API가 정상 응답하더라도 입력 데이터가 달라지거나 예측 품질이 떨어질 수 있다. 이러한 변화는 서빙 지표와 별도로 관찰해야 한다.

## 1. 서빙 상태와 예측 성능은 별도로 확인한다

![BentoML 서빙에서 Data Drift 대응까지](/images/week03-drift-architecture.svg)

*모델 관리와 운영 모니터링의 연결 구조.*

| 측정 | 질문 | 대표 지표 | 도구 |
|---|---|---|---|
| 서비스 신뢰성 | 응답이 정상 도착했나? | RPS, p95, 5xx | Prometheus, Grafana |
| 인프라 용량 | 부하를 감당하나? | CPU, memory, HPA replicas | Kubernetes |
| 데이터 건강성 | 입력 조건이 바뀌었나? | 결측률, 범위 위반, 분포 차이 | Evidently |
| 모델 품질 | 예측이 실제 정답과 일치하나? | RMSE, MAE, MAPE, R² | MLflow, 정답 지연 수집 |

HTTP 응답 코드나 p95 지연만으로는 예측이 정확한지 알 수 없다. 입력 분포의 변화와 실제 예측 오차도 분리해서 기록한다.

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

## 3. Drift: 무엇이 달라졌는지부터 확인

Drift는 기준 시점과 현재 시점 사이에서 관측되는 변화다. 모델 운영에서는 데이터 분포, 예측값 분포, 입력과 정답의 관계, 모델 성능을 각각 살핀다. 어떤 항목이 변했는지 먼저 확인해야 원인과 대응을 구분할 수 있다.

입력 분포가 변했다면 Data Drift, 예측값 분포가 변했다면 Prediction Drift다. 동일한 입력 조건과 실제 결과 사이의 관계가 변하면 Concept Drift이고, 실제 정답과 비교한 예측 오차가 악화된 상태는 모델 성능 저하로 따로 기록한다.

### 비교에 사용하는 기호

| 기호 | 의미 | 제조 품질 회귀 예제 |
|---|---|---|
| $X$ | 모델의 입력 피처 | 온도, 압력, 생산 속도 |
| $Y$ | 현실에서 관측한 실제 정답 | 생산 후 측정된 실제 품질 |
| $\hat Y$ | 모델이 계산한 예측값 | 사전에 예측한 품질 점수 |
| Reference | 비교 기준 구간 | 학습/검증 기간 |
| Current | 지금 운영 중인 구간 | 최근 7일 또는 최근 생산 Lot |

분포 변화가 관측되더라도 그 자체가 성능 하락을 뜻하지는 않는다. 재학습 여부는 실제 정답과의 비교, 데이터 계약 검증, 공정 변경 여부를 확인한 뒤 판단한다.

![드리프트 개념의 전체 분류 및 연관 관계](/images/week03-drift-concept-map.svg)

*입력·출력·실제 성능의 관계. 화살표는 가능한 영향 경로를 표시한다.*

## 4. Data Drift: 입력 분포의 변화

### 정의와 발생 원인

**Data Drift(데이터 드리프트)**는 모델이 학습할 때 보았거나 기준으로 삼았던 **입력 데이터의 분포**와 실제 운영 환경에 유입되는 입력 분포가 달라지는 현상이다. 통계적으로는 기준 시점과 현재의 $P(X)$ 차이를 본다. 이를 **Feature Drift**라고도 부른다.

제조 품질 예측 모델의 예를 들면, 기존에는 200℃ 부근에서 생산했는데 최근에는 220℃ 부근에서 생산하거나, 원재료 교체로 압력 분포가 달라진 상황이다.

**발생 원인:** 새로운 고객·제품 구성, 계절성, 신규 공정 조건, 설비·센서 보정, 운영 정책 변경, 업스트림 데이터 품질 오류 등.

### Data Drift 모니터링의 역할

- **조기 경보:** 실제 품질 정답이 아직 도착하지 않아도 학습 시점과 다른 운전 조건인지 확인
- **입력 품질 점검:** 피처별 결측률·이상값·단위·범위·스키마 변화 확인
- **문제 원인 추적:** 이후 모델 성능 저하가 확인되면 어떤 입력 피처가 먼저 바뀌었는지 조사
- **재학습 평가 근거:** 기존 학습 데이터가 현재 운영 구간을 충분히 대표하는지 판단할 단서 제공

| 구분 | 구체적 점검 |
|---|---|
| 무엇을 비교? | Reference의 $X$ vs Current의 $X$ |
| 실제 정답 $Y$ 필요? | **아니오** |
| 대표 탐지 | 히스토그램·분위수, PSI, KS 검정, Wasserstein distance |
| 사용 도구 | Evidently, 데이터 품질 검사, 피처 스토어 통계 |
| 탐지 후 | 센서/단위/공정 변경 확인 → 라벨 확보 후 성능 검증 |
| 오해하면 안 되는 점 | **Data Drift가 발생해도 모델 성능은 유지될 수 있다.** |

### 예시: 온도가 200℃ → 220℃로 이동한다면?

학습 구간과 다른 입력이 들어왔다는 **Data Drift 신호**는 발생할 수 있다. 하지만 학습한 모델이 새로운 범위에서도 품질을 정확히 예측한다면 **Model Drift(성능 저하)는 발생하지 않았을 수 있다.** 먼저 입력 차이가 실제 품질 오차에 영향을 주는지 확인한다.

## 5. Prediction Drift: 예측값 분포의 변화

### 정의와 운영 역할

**Prediction Drift(예측 드리프트)**는 배포된 모델의 **예측 출력 분포** $P(\hat Y)$가 기준 기간과 달라지는 현상이다. Data Drift가 *입력*을 본다면 Prediction Drift는 *출력*을 본다.

예를 들어 평균 품질 예측 점수가 75점에서 82점으로 올라갈 수 있다. 이는 좋은 변화일 수도 있고, 입력 데이터 문제나 모델 버전 변경의 결과일 수도 있다.

| 구분 | 구체적 점검 |
|---|---|
| 무엇을 비교? | Reference의 $\hat Y$ vs Current의 $\hat Y$ |
| 실제 정답 $Y$ 필요? | **아니오** |
| 플랫폼 역할 | 예측 분포 변화 감시, 예측 점수 편향·이상 변화의 조기 발견 |
| 주요 지표 | 예측값 평균·분산·분위수, 분류라면 클래스/확률 분포 |
| 오해하면 안 되는 점 | 예측 분포가 달라졌다고 **정확도가 낮아졌다는 뜻은 아니다.** |

실제 품질 점수도 같은 방향으로 올라갔는지 판단하려면 **실제 라벨 $Y$**이 필요하다.

## 6. Concept Drift: 입력과 실제 결과의 관계 변화

### 정의와 발생 원인

**Concept Drift(개념 드리프트)**는 **입력 $X$가 같더라도 실제 정답 $Y$가 만들어지는 관계** $P(Y\mid X)$가 달라지는 현상이다. 모델이 학습한 현실의 규칙이 변한 것이다.

예를 들어 기존 설비에서는 온도 200℃·압력 50·속도 10의 조건에서 품질이 85점이었지만, **설비가 마모된 이후 같은 조건에서도 실제 품질이 72점**으로 내려가는 경우다.

### Concept Drift 모니터링의 역할

| 구분 | 구체적 점검 |
|---|---|
| 무엇을 비교? | Reference의 $P(Y\mid X)$ vs Current의 $P(Y\mid X)$ |
| 실제 정답 $Y$ 필요? | **직접적인 검증에는 일반적으로 필요** |
| 플랫폼 역할 | 학습된 입력→출력 규칙이 더 이상 현실을 설명하지 못하는지 진단 |
| 탐지 방법 | 조건별 잔차, 기간별 성능, 조건부 관계 분석, 세그먼트 검증 |
| 대응 방향 | 설비/공정/라벨 변경 확인, 후보 모델 재학습 및 재검증 |
| 오해하면 안 되는 점 | **Data Drift 없이도 Concept Drift가 나타날 수 있다.** |

Concept Drift를 의심한다고 무조건 모델을 재학습하면 안 된다. 센서 측정 변경, 실제 라벨의 기준 변경, 피처 전처리 버그도 동일한 현상처럼 보일 수 있기 때문이다.

## 7. Model Drift: 운영 중 모델 성능의 저하

### 용어의 범위

Model Drift라는 표현은 자료에 따라 의미가 다르다. 데이터·개념의 변화를 포괄하는 의미로 쓰기도 하고, 운영 중 모델 성능이 저하되는 현상을 지칭하기도 한다. 이 글에서는 후자를 **모델 성능 저하(Model Performance Degradation)**로 명시한다.

Data Drift는 입력의 변화, Concept Drift는 현실의 관계 변화, 성능 저하는 그 결과로 나타날 수 있는 오차 변화에 관한 관측이다.

원인이 불분명할 때는 'Model Drift 발생'이라는 표현보다 '운영 RMSE 증가'처럼 확인된 사실을 먼저 기록하는 편이 정확하다.

### 확인할 지표와 운영 역할

| 구분 | 구체적 점검 |
|---|---|
| 무엇을 비교? | Reference와 Current의 실제 모델 예측 성능 |
| 실제 정답 $Y$ 필요? | **예. 실제 성능 확정에 필요** |
| 제조 회귀 모델 지표 | MAE, RMSE, R², MAPE(실제값 0 근처 주의) |
| 분류 모델 지표 | Accuracy, Precision, Recall, F1, ROC AUC 및 Calibration 등 |
| 플랫폼 역할 | 모델 품질 악화 탐지, 비즈니스 위험 관리, 재학습·롤백 판단 근거 |
| 확인할 계보 | MLflow 모델 버전, 피처 버전, 실제 라벨, 예측 타임스탬프 |
| 오해하면 안 되는 점 | **성능이 떨어진 원인은 다른 분석이 필요하다.** |


모델의 예측값을 $\hat y_i$, 이후 관측된 실제값을 $y_i$, 평가 표본 수를 $n$으로 둔다.

$$
\begin{aligned}
\mathrm{MAE} &= \frac{1}{n}\sum_{i=1}^{n}|y_i-\hat y_i| \\[6pt]
\mathrm{RMSE} &= \sqrt{\frac{1}{n}\sum_{i=1}^{n}(y_i-\hat y_i)^2} \\[6pt]
R^2 &= 1-\frac{\sum_{i=1}^{n}(y_i-\hat y_i)^2}{\sum_{i=1}^{n}(y_i-\bar y)^2}
\end{aligned}
$$

MAE는 평균적인 절대 오차를, RMSE는 큰 오차에 더 민감한 값을 보여준다. $R^2$는 비교 구간의 실제값 분산을 기준으로 예측력을 해석하는 지표다. **평가 대상 구간의 분포가 달라지면 $R^2$도 함께 영향을 받으므로 MAE·RMSE와 같이 읽는다.**

제조 현장에서는 예측 당시의 설비 ID, 생산 Lot, 모델 버전과 실제 품질 측정 라벨을 정확히 연결해야 한다. **라벨이 아직 없다면 실시간 Model Drift를 성능으로 확정할 수 없으며**, Data/Prediction Drift를 대리 지표로 관찰한다.

### 오차가 커졌을 때 확인할 항목

가령 기준 기간 RMSE가 1.0인데 최근 같은 평가 조건에서 2.5로 증가했다면 성능 저하를 조사해야 한다. 이 수치는 실험 결과가 아닌 가상 예시다. 원인은 다음과 같이 나누어 본다.

- 새로운 온도 구간에서 학습 데이터가 부족한 **Data Drift 영향**
- 설비 마모로 입력·실제 품질의 관계가 달라진 **Concept Drift 영향**
- 학습/서빙 전처리 불일치, 잘못된 라벨 매칭 등의 **파이프라인 결함**
- 특정 제품·설비 세그먼트에서만 발생한 국소적인 문제

오차가 증가한 사실과 원인은 따로 기록한다. 입력 분포, 조건부 관계, 전처리 버전, 라벨 품질을 확인한 뒤 조치한다.

## 8. Training–Serving Skew: 학습과 서빙의 불일치

**Training–Serving Skew**는 학습과 서빙에서 피처 생성 방식, 단위, 스키마, 피처 순서, 결측 처리 또는 코드 버전이 일치하지 않는 문제다. 반드시 시간에 따라 서서히 변하는 드리프트는 아니다.

**제조 예시:** 학습에 사용한 섭씨 200℃가 서빙에서는 화씨 392℉인데, 변환 없이 수치 392를 모델에 입력한다. 이것은 먼저 **데이터 단위·피처 계약의 위반**으로 조사해야 한다.

**운영 역할:** MLflow 모델 아티팩트, Feast 피처 정의, BentoML 요청 스키마와 전처리 코드가 학습 시점의 계약과 일치하는지 검증한다.

## 9. 드리프트 유형 비교

![Drift 분포·성능별 비교 도식](/images/week03-drift-types.svg)

*입력·예측·관계·성능의 차이를 나타낸 개념도.*

| 개념 | 변화 대상 | 가장 쉬운 질문 | 실제 라벨 필요? |
|---|---|---|---|
| **Data Drift** | $P(X)$ | **들어오는 데이터가 달라졌나?** | 아니오 |
| **Prediction Drift** | $P(\hat Y)$ | **모델이 내는 예측 점수가 달라졌나?** | 아니오 |
| **Concept Drift** | $P(Y\mid X)$ | **같은 조건인데 실제 결과가 달라졌나?** | 직접 확인에는 일반적으로 필요 |
| **Model Drift** | 실제 예측 오차 / 성능 | **모델이 예전보다 많이 틀리나?** | **예** |
| **Training–Serving Skew** | 입력 변환·스키마 | **학습과 운영이 서로 다른 입력 처리를 하나?** | 필요하지 않을 수 있음 |

### 서로 다른 세 가지 상황

| 상황 | 데이터가 바뀌었나? | 모델이 나빠졌나? | 해석 |
|---|---|---|---|
| 운전 온도가 변했지만 예측 오차는 비슷함 | 예 | 아니오 | Data Drift ≠ 자동적인 Model Drift |
| 온도 분포는 같지만 설비 마모로 오차 증가 | 아니오 | 예 | Concept Drift → Model Drift 가능 |
| 데이터는 정상인데 온도 단위 변환이 누락됨 | 통계 비교만으로 판단 곤란 | 예 가능 | 먼저 Training–Serving Skew 점검 |

데이터 계약 검증, 입력·출력 분포 비교, 정답 기반 성능 평가, 원인 조사 순으로 진행하면 불필요한 모델 교체를 줄일 수 있다.

## 10. 드리프트 모니터링 구성

![라벨 유무에 따른 드리프트 모니터링 및 대응 흐름도](/images/week03-drift-decision.svg)

*제조 공정에서 실제 품질 라벨을 늦게 확보하는 상황을 가정한 분석 흐름.*

### 10.1 라벨이 없어도 확인 가능한 항목

- 입력 피처의 레퍼런스 대비 분포, 결측 비율, 데이터 타입, 물리적 허용 범위
- 모델 예측값 분포 및 예측 확률 변화
- 설비·라인·제품·운전 조건별 세그먼트 변화
- 모델 버전, 피처 생성 파이프라인 버전, 스키마 해시

이는 **위험 신호(Proxy)**다. 정답이 없으면 RMSE를 직접 측정할 수 없으므로 데이터 드리프트만으로 성능이 나빠졌다고 단언하지 않는다.

### 10.2 실제 품질 라벨을 확보한 뒤

이 구간에서도 앞서 정의한 MAE, RMSE, $R^2$를 사용한다. 특히 운영 데이터의 라벨이 지연되는 경우에는 예측 시점과 실제 품질 측정 시점을 동일한 생산 Lot·설비 식별자로 연결해야 한다.

각 지표를 **학습/검증 기준선과 운영 기간, 라인·제품별로** 비교한다. 라벨이 일정 기간 지연되어 들어오는 제조 환경에서는 **예측 발생 시점과 실제 품질 측정 시점을 entity_id로 결합**해야 한다. 예측 당시에는 없던 미래 피처를 붙이면 누수가 발생한다.

### 10.3 관측 결과에 따른 대응

| 관찰 | 가능한 원인 | 우선 조치 |
|---|---|---|
| 입력 드리프트만 발생, 모델 성능 유지 | 정상적인 운전 구간 확대 | 감시 강화, 즉시 재학습 보류 |
| 입력 드리프트와 성능 저하 동시 발생 | 미학습 운전 영역, 결측·품질 문제 | 데이터 검증 후 후보 재학습 |
| 입력 드리프트 없음, 성능 저하 | Concept Drift, 라벨 오류, 코드/스키마 변경 | 조건부 관계와 계보 조사 |
| 예측값 드리프트만 발생 | 모델 버전, 입력 구성 변화 | champion 버전·데이터 구간 비교 |
| 예측값 변화 없음, 성능 저하 | 숨겨진 Concept Drift 가능 | 실제 라벨·잔차·세그먼트 분석 |
| 모델 성능 정상, p95 지연 증가 | 서빙/네트워크/용량 문제 | HPA·큐·Pod·Endpoint 확인 |

### 10.4 모니터링 대상

- **Input Monitoring:** Evidently 등으로 feature drift·데이터 품질 검사.
- **Output Monitoring:** 예측 점수/등급/확률 분포 모니터링.
- **Performance Monitoring:** 라벨 확보 후 오차/정확도와 세그먼트별 안정성 평가.
- **Serving Monitoring:** Prometheus·Grafana로 p95·RPS·오류율·HPA 상태 분석.

분포 비교를 제공하는 도구로 Evidently를 사용할 수 있지만, **실제 성능 검증을 하려면 라벨과 모델 예측을 별도로 연결**해야 한다. 자동 재학습의 실행 여부는 품질 게이트에서 판단한다.

### 10.5 통계적 변화와 업무 영향

PSI·KS 등의 분포 검정은 기준 기간 선택, 표본 크기, 세그먼트 구성에 민감하다. 동일한 분포에서도 표본이 매우 크면 미세한 변화를 감지할 수 있고, 표본이 작으면 중요한 변화를 놓칠 수 있다. **통계적 변화량·업무적 영향·모델 성능**을 함께 판단한다.

관련 근거: [IBM Model Drift](https://www.ibm.com/think/topics/model-drift), [Evidently ML Observability](https://learn.evidentlyai.com/ml-observability-course/module-2-ml-monitoring-metrics/data-prediction-drift-in-ml), [IEEE Concept Drift](https://technav.ieee.org/topic/concept-drift/).

## 11. Evidently를 이용한 분포 비교

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

### 비교할 데이터와 조건

| 실험 | 변화시킬 조건 | 기대하는 확인 사항 |
|---|---|---|
| 기준선 | 동일 생성 규칙, 다른 표본 | 정상 데이터에서도 검정 오탐 가능성 |
| 운전 구간 이동 | temperature 평균 이동 | 분포 차이 감지 |
| 분산 증가 | pressure 변동 폭 확대 | 평균만 보면 놓치는 변화 |
| 범위 외 입력 | speed가 계약 상한 초과 | 통계 검정 전에 데이터 계약 위반 |
| Concept 변화 | 동일 X, 다른 Y 생성식 | X 드리프트만으로는 미탐 가능 |

데이터 드리프트의 검정 임계값과 표본 크기는 탐지 민감도에 영향을 준다. 여러 피처를 동시에 검사할 때 다중 비교와 계절성도 검토한다. 실제 품질 이슈의 크기와 통계적 유의성을 구분해야 한다.

## 12. 경보 이후의 판단

단일 drift flag로 재학습을 바로 실행하면 불필요한 배포·학습 비용이나 잘못된 모델 교체로 이어질 수 있다. 운영 정책은 **관찰 → 검증 → 후보 모델 생성 → 오프라인 비교 → 배포 승인 → 카나리 검증** 순서로 설계한다.

| 조건 | 권장 조치 |
|---|---|
| Drift 감지, 성능 정답 없음 | 로그·표본 확인, 드리프트 원인 조사 |
| Drift 감지 + 성능 악화 | 피처·라벨 지연·세그먼트 분석 후 재학습 후보 |
| Drift 미감지 + 성능 악화 | concept drift, skew, 버그 점검 |
| Drift 감지 + 성능 정상 | 모니터링 강화, 즉각 배포 보류 가능 |
| 서비스 오류율 증가 + Drift 없음 | 서빙·네트워크·자원 문제 우선 |

## 13. 2주차 구성과 연결하는 방법

- **MLflow:** 학습 run, 모델 버전, 선정 이유, 원본 해시
- **Feast:** entity, event_timestamp, feature names, online/offline 기준
- **KFP:** 검증 단계, 예측 파일, drift report artifact의 입출력 계약
- **BentoML:** 추론 API 스키마와 고정 모델 아티팩트 로딩
- **Evidently:** reference/current 메타데이터, 피처 별 결과, 리포트 생성 시점
- **Kubernetes:** 이미지 다이제스트, Service 경로, replica/Ready 및 운영 지표

모델 품질 이력을 확인하려면 각 예측에 모델 버전·데이터 시각·요청 추적 ID를 연결해야 한다. 다만 개인정보나 민감한 원문 데이터를 모니터링 로그에 그대로 남기는 설계는 피한다.

## 14. 실습 범위와 확인할 결과

여기까지는 구현 방향과 검증 절차를 정리한 단계다. BentoML 서빙, Evidently 리포트 생성, Kubernetes 배포를 실제로 실행한 기록은 별도로 확보해야 한다. 후속 실습에서는 패키지 버전, 입력 데이터, 실행 로그, 생성 리포트, 실패 사례를 함께 남긴다.

[3주차 학습 정리](/ml-platform/study-week-03)

공식 참고: [BentoML Service](https://docs.bentoml.com/en/latest/build-with-bentoml/services.html), [Bento Packaging](https://docs.bentoml.com/en/latest/get-started/packaging-for-deployment.html), [Evidently Docs](https://docs.evidentlyai.com/), [Evidently API](https://evidentlyai.github.io/evidently/api-reference/main/evidently/core/report.html)
