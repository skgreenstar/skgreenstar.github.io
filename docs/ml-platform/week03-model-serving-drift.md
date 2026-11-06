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

## 3. Data Drift와 Model Drift를 같은 뜻으로 쓰지 않는 이유

![데이터 드리프트와 모델 성능 저하를 구분하는 네 가지 도식](/images/week03-drift-types.svg)

*파랑은 기준 기간(Reference), 주황은 운영 기간(Current)을 나타내는 개념 그림이다. 그림의 분포와 오차는 측정값이 아닌 이해용 예시다.*

### 3.1 용어의 범위부터 명확히 정의하기

**Model Drift는 문헌·제품마다 용어 범위가 일치하지 않는다.** 일부 자료는 입력 데이터나 개념 변화로 인한 모델 유효성 저하 전체를 지칭하며, 일부 실무 문맥에서는 시간이 지나면서 실제 예측 성능이 떨어지는 **Model Performance Degradation(Performance Drift)**에 초점을 둔다. 이 글에서는 마지막 경우를 **모델 성능 저하**라고 명시해 다른 통계적 변화와 구분한다.

| 분류 | 변화의 대상 | 정답(Label) 필요? | 확인 지표 | 진단의 의미 |
|---|---|---|---|---|
| **Data / Feature Drift** | 입력 분포 `P(X)` | 아니오 | PSI, KS, Wasserstein, 결측·범위 | 학습 때와 다른 입력이 유입되는가? |
| **Prediction Drift** | 예측 출력 분포 `P(Ŷ)` | 아니오 | 예측값 평균·분포·등급 비율 | 모델 출력 행동이 달라졌는가? |
| **Concept Drift** | 실제 조건부 관계 `P(Y | X)` | 대개 필요 | 구간별 잔차, 시간별 조건부 관계, 성능 | 같은 입력에 대한 실제 정답의 규칙이 바뀌었는가? |
| **Model Performance Degradation** | 예측값과 실제값 간 오차·품질 | **필요** | RMSE/MAE 증가, R² 저하 | 모델이 현재 업무에서 실제로 나빠졌는가? |
| **Training–Serving Skew** | 학습·서빙 전처리/스키마 계약 | 비교 데이터 필요 | 피처 순서·타입·변환 해시 | 학습·서빙 입력 생성 방식이 불일치하는가? |

> **핵심:** Data Drift는 성능 저하를 일으킬 수 있지만 충분조건도 필요조건도 아니다. Concept Drift는 입력 분포 변화 없이도 발생한다. Prediction Drift는 출력 변화의 증거일 뿐 실제 성능 저하의 확증은 아니다. 성능 저하는 Concept Drift 외에도 전처리 버그, 데이터 결함, 레이블 품질 저하 등에서 비롯될 수 있다.

### 3.2 제조 품질 회귀 모델로 이해하는 다섯 가지 상황

2주차 합성 제조 예제의 `temperature`, `pressure`, `speed`를 입력 `X`, `quality`를 실제 정답 `Y`, 배포된 모델의 예측값을 `Ŷ`라고 정의한다.

1. **Data Drift만 확인되는 상황:** 온도 운전 구간이 200℃ 부근에서 220℃ 부근으로 이동하지만 모델이 해당 구간에서도 충분히 일반화되어 RMSE는 비슷하게 유지된다. 이 경우 입력 드리프트가 있다고 즉시 모델 교체할 근거는 없다.
2. **Prediction Drift가 나타나는 상황:** 새 생산 라인에서 예측 품질 점수의 평균이 올라간다. 실제 품질도 개선된 것인지, 입력 변화 때문인지, 모델 버전 변경 때문인지는 출력 분포만으로 알 수 없다.
3. **Concept Drift가 발생한 상황:** 설비 마모 때문에 같은 온도·압력·속도에서도 실제 품질이 떨어진다. 입력 `P(X)`는 그대로인데 `P(Y|X)`가 달라져 모델의 잔차가 커질 수 있다.
4. **Model Performance Degradation:** 운영 중 RMSE가 지속 상승한다. 이는 **관측된 결과**이며 원인이 Data Drift인지 Concept Drift인지, 피처 처리 오류인지는 별도로 조사해야 한다.
5. **Training–Serving Skew:** 학습에서는 온도를 섭씨로 썼는데 운영에서는 화씨가 들어온다. 이것은 우선 **입력 계약 위반**이지, 정상적인 환경 변화라고 취급하지 않는다.

### 3.3 두 가지 반례를 반드시 기억하기

| 사례 | Data Drift | Concept Drift | 실제 모델 성능 |
|---|---|---|---|
| 운전 범위 이동, 모델이 잘 일반화 | 있음 | 없음 | 유지 가능 |
| 설비 마모로 같은 조건의 품질 변화 | 없어도 됨 | 있음 | 저하 가능 |
| 예측 평균 상승, 실제 품질도 상승 | 있을 수 있음 | 불명 | 유지 가능 |
| 전처리 스키마 버그 | 정상 비교가 어려움 | 불명 | 저하 가능 |

**즉, Drift Detection과 Model Evaluation은 서로 보완하는 다른 검사다.** 성능 악화라는 현상만 보고 원인을 곧바로 Concept Drift로 확정하지 않는다.

## 4. 드리프트 유형별 모니터링 아키텍처

![라벨 유무에 따른 드리프트 모니터링 및 대응 흐름도](/images/week03-drift-decision.svg)

*정답을 늦게 얻는 제조 공정을 가정한 진단 흐름. 실제 실행된 파이프라인이 아니라 설계 아키텍처다.*

### 4.1 라벨 없이 빠르게 감지할 수 있는 것

- 입력 피처의 레퍼런스 대비 분포, 결측 비율, 데이터 타입, 물리적 허용 범위
- 모델 예측값 분포 및 예측 확률 변화
- 설비·라인·제품·운전 조건별 세그먼트 변화
- 모델 버전, 피처 생성 파이프라인 버전, 스키마 해시

이는 **위험 신호(Proxy)**다. 정답이 없으면 RMSE를 직접 측정할 수 없으므로 데이터 드리프트만으로 성능이 나빠졌다고 단언하지 않는다.

### 4.2 라벨이 확보되면 평가하는 것

```text
MAE  = mean(|Y - Ŷ|)
RMSE = sqrt(mean((Y - Ŷ)²))
R²   = 1 - SSE/SST
```

각 지표를 **학습/검증 기준선과 운영 기간, 라인·제품별로** 비교한다. 라벨이 일정 기간 지연되어 들어오는 제조 환경에서는 **예측 발생 시점과 실제 품질 측정 시점을 entity_id로 결합**해야 한다. 예측 당시에는 없던 미래 피처를 붙이면 누수가 발생한다.

### 4.3 실무 조치 매트릭스

| 관찰 | 가능한 원인 | 우선 조치 |
|---|---|---|
| 입력 드리프트만 발생, 모델 성능 유지 | 정상적인 운전 구간 확대 | 감시 강화, 즉시 재학습 보류 |
| 입력 드리프트와 성능 저하 동시 발생 | 미학습 운전 영역, 결측·품질 문제 | 데이터 검증 후 후보 재학습 |
| 입력 드리프트 없음, 성능 저하 | Concept Drift, 라벨 오류, 코드/스키마 변경 | 조건부 관계와 계보 조사 |
| 예측값 드리프트만 발생 | 모델 버전, 입력 구성 변화 | champion 버전·데이터 구간 비교 |
| 예측값 변화 없음, 성능 저하 | 숨겨진 Concept Drift 가능 | 실제 라벨·잔차·세그먼트 분석 |
| 모델 성능 정상, p95 지연 증가 | 서빙/네트워크/용량 문제 | HPA·큐·Pod·Endpoint 확인 |

### 4.4 독립적인 네 개의 관찰 축

- **Input Monitoring:** Evidently 등으로 feature drift·데이터 품질 검사.
- **Output Monitoring:** 예측 점수/등급/확률 분포 모니터링.
- **Performance Monitoring:** 라벨 확보 후 오차/정확도와 세그먼트별 안정성 평가.
- **Serving Monitoring:** Prometheus·Grafana로 p95·RPS·오류율·HPA 상태 분석.

분포 비교를 제공하는 도구로 Evidently를 사용할 수 있지만, **실제 성능 검증을 하려면 라벨과 모델 예측을 별도로 연결**해야 한다. 자동 재학습의 실행 여부는 품질 게이트에서 판단한다.

### 4.5 지표 해석에서 주의할 점

PSI·KS 등의 분포 검정은 기준 기간 선택, 표본 크기, 세그먼트 구성에 민감하다. 동일한 분포에서도 표본이 매우 크면 미세한 변화를 감지할 수 있고, 표본이 작으면 중요한 변화를 놓칠 수 있다. **통계적 변화량·업무적 영향·모델 성능**을 함께 판단한다.

관련 근거: [IBM Model Drift](https://www.ibm.com/think/topics/model-drift), [Evidently ML Observability](https://learn.evidentlyai.com/ml-observability-course/module-2-ml-monitoring-metrics/data-prediction-drift-in-ml), [IEEE Concept Drift](https://technav.ieee.org/topic/concept-drift/).

## 5. Evidently로 Reference와 Current 비교

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

## 6. 경보는 재학습 명령이 아니다

단일 drift flag로 재학습을 바로 실행하면 불필요한 배포·학습 비용이나 잘못된 모델 교체로 이어질 수 있다. 운영 정책은 **관찰 → 검증 → 후보 모델 생성 → 오프라인 비교 → 배포 승인 → 카나리 검증** 순서로 설계한다.

| 조건 | 권장 조치 |
|---|---|
| Drift 감지, 성능 정답 없음 | 로그·표본 확인, 드리프트 원인 조사 |
| Drift 감지 + 성능 악화 | 피처·라벨 지연·세그먼트 분석 후 재학습 후보 |
| Drift 미감지 + 성능 악화 | concept drift, skew, 버그 점검 |
| Drift 감지 + 성능 정상 | 모니터링 강화, 즉각 배포 보류 가능 |
| 서비스 오류율 증가 + Drift 없음 | 서빙·네트워크·자원 문제 우선 |

## 7. 2주차 산출물과 연결할 때 유지할 계약

- **MLflow:** 학습 run, 모델 버전, 선정 이유, 원본 해시
- **Feast:** entity, event_timestamp, feature names, online/offline 기준
- **KFP:** 검증 단계, 예측 파일, drift report artifact의 입출력 계약
- **BentoML:** 추론 API 스키마와 고정 모델 아티팩트 로딩
- **Evidently:** reference/current 메타데이터, 피처 별 결과, 리포트 생성 시점
- **Kubernetes:** 이미지 다이제스트, Service 경로, replica/Ready 및 운영 지표

모델 품질 이력을 확인하려면 각 예측에 모델 버전·데이터 시각·요청 추적 ID를 연결해야 한다. 다만 개인정보나 민감한 원문 데이터를 모니터링 로그에 그대로 남기는 설계는 피한다.

## 8. 검증 범위와 후속 실습

이 글은 설계·코드 초안이다. **BentoML 실제 서비스 실행, Evidently drift HTML 생성, Kubernetes 배포, 성능 측정은 아직 수행하지 않았다.** 실행 성공을 주장하려면 CLI 버전, 데이터 생성 스크립트, 실제 보고서, 결과 수치와 GitHub Actions/클러스터 로그를 추가해야 한다.

[3주차 학습 정리로 돌아가기](/ml-platform/study-week-03)

공식 참고: [BentoML Service](https://docs.bentoml.com/en/latest/build-with-bentoml/services.html), [Bento Packaging](https://docs.bentoml.com/en/latest/get-started/packaging-for-deployment.html), [Evidently Docs](https://docs.evidentlyai.com/), [Evidently API](https://evidentlyai.github.io/evidently/api-reference/main/evidently/core/report.html)
