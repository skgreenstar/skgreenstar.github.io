---
title: "11 · BentoML 모델 서빙"
outline: deep
prev:
  text: '10 · 요청 경로'
  link: '/ml-platform/week03-traffic'
next:
  text: '12 · 데이터와 모델 드리프트'
  link: '/ml-platform/week03-model-serving-drift'
---

# 11 · BentoML 모델 서빙

3주차에서 살펴본 Kubernetes 확장과 서비스 라우팅을 실제 모델 API에 연결하는 단계다. BentoML은 모델을 호출할 수 있는 서비스 인터페이스와 실행 환경을 구성한다. 이 문서에서는 BentoML의 책임을 정리하고, 제조 품질 예측 API의 실습 절차를 설계한다.

## 1. 모델 서빙 계층의 위치

![3주차 모델 서빙과 운영 모니터링 개요](/images/week03-drift-architecture.svg)

Kubernetes의 Deployment·Service·HPA는 애플리케이션을 배치하고 연결하며 확장한다. BentoML은 그 위에서 모델 로딩과 추론 API를 정의한다. 모델 서빙 서비스가 준비되었다는 사실만으로 예측의 정확도가 보장되지는 않는다. 예측 품질 감시는 [12 · 데이터와 모델 드리프트](/ml-platform/week03-model-serving-drift)에서 별도로 다룬다.

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

도구를 함께 사용할 수 있지만 모델 패키징, 서빙 엔진, Kubernetes 사이의 중복 기능과 운영 비용을 확인해야 한다.


## 3. 2주차 MLflow 모델을 연결하는 설계

이전 주차에서 선택한 모델을 API에 연결할 때에는 학습 시점의 피처 계약과 모델 버전을 유지해야 한다.

| 확인 항목 | 내용 |
|---|---|
| 모델 아티팩트 | MLflow에 기록한 모델 버전·URI와 파일 무결성 |
| 입력 계약 | `temperature`, `pressure`, `speed`의 순서·타입·단위 |
| 추론 API | 요청 스키마, 잘못된 입력의 오류 응답, 타임아웃 |
| 실행 환경 | BentoML·Python·모델 패키지 버전 고정 |
| Kubernetes | readiness, CPU/memory requests, Pod 준비 시간 |
| 관측 | 요청 ID, 모델 버전, 지연 시간, 오류율, 호출 건수 |

### 실습 설계

1. 고정된 모델 버전을 로딩하는 BentoML 서비스를 작성한다.
2. 정상 입력과 스키마 오류를 각각 API에 전달해 반환값을 확인한다.
3. 로컬 추론 결과를 동일 모델의 배치 추론 결과와 비교한다.
4. 컨테이너로 패키징한 뒤 Kubernetes Deployment·Service에 연결한다.
5. 모델 로딩 전후의 readiness와 응답 지연을 구분해 기록한다.

여기까지는 **실습 절차를 설계한 단계**다. 위에 작성한 `QualityScore` 서비스도 실제 학습 모델이 아니라 추론 인터페이스를 설명하기 위한 간단한 예제다.

## 4. 서빙 이후의 운영 검증

서비스가 HTTP 200을 반환하고 Pod가 Ready인 경우에도 입력 분포나 실제 예측 성능은 변할 수 있다. 이에 대한 통계적 판단과 Evidently 모니터링 설계는 [12 · 데이터와 모델 드리프트](/ml-platform/week03-model-serving-drift)로 분리했다.

[3주차 학습 정리](/ml-platform/study-week-03)

공식 참고: [BentoML Service](https://docs.bentoml.com/en/latest/build-with-bentoml/services.html) · [Bento Packaging](https://docs.bentoml.com/en/latest/get-started/packaging-for-deployment.html)
