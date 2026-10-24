---
title: "Beyond Model Accuracy — ML Platform Engineering에서 LLMOps까지"
description: "모델 성능을 넘어 재현성, CI/CD/CT, 제조 ML, RAG·Agent 평가와 운영 설계를 연결하는 Week 01 기술 노트"
date: 2026-10-25
outline: deep
---

# Beyond Model Accuracy

**좋은 모델을 만드는 것과 신뢰할 수 있는 AI 시스템을 운영하는 것은 다른 문제다.**

> **Week 01 · ML Platform Engineering / MLOps / LLMOps**
>
> 이 글은 스터디 CH1~CH2의 학습 주제와 연계한 **독립적인 심화 학습 노트**입니다. 강의 원문 전체를 검증한 요약은 아니며, 실무 사례는 특정 조직이나 고객을 식별할 수 없도록 일반화했습니다. 수행하지 않은 실습을 완료했다고 주장하지 않습니다.

## 1. Model Quality와 System Quality는 다르다

오프라인 평가에서 높은 점수를 얻은 모델이 반드시 좋은 서비스를 만들지는 않는다. 운영 환경에서는 데이터의 생성 과정이 바뀌고, 입력 스키마가 변하며, 트래픽·비용·장애·지연시간이 품질을 좌우한다.

| 관점 | 실험 단계 | 운영 단계 |
|---|---|---|
| 핵심 질문 | 예측할 수 있는가? | 안정적으로 신뢰할 수 있는가? |
| 데이터 | 고정된 데이터셋 | 시간에 따라 변하는 입력 |
| 평가 | 정확도·오차 | 품질 + 지연 + 비용 + 장애 |
| 변경 관리 | 실험 코드 | 데이터·모델·설정·배포 버전 |
| 실패 대응 | 재실험 | 탐지·격리·롤백 |

::: tip Core thesis
**Model quality ≠ System quality.** 플랫폼 엔지니어링은 모델을 배포하는 기술이 아니라, 데이터에서 추론 결과까지의 **변경 가능한 전체 시스템**을 관리하는 기술이다.
:::

## 2. ML Platform Engineering의 책임 경계

ML 플랫폼은 Kubernetes나 GPU 자원을 제공하는 인프라 계층에 그치지 않는다. 데이터·실험·아티팩트·배포·모니터링의 반복 작업을 표준화해, 모델 개발자가 공통 문제를 매번 새로 풀지 않게 만드는 **내부 제품(Internal Developer Platform)**이다.

![ml-lifecycle 아키텍처](/diagrams/ml-lifecycle.svg)

*구성 요소 간 관계를 단순화한 개념 다이어그램입니다.*

이때 플랫폼의 성숙도를 설치한 도구의 개수로 측정하면 안 된다. 더 유용한 질문은 **실험을 재현하는 데 걸리는 시간**, **안전한 배포 리드타임**, **실패 복구 시간**, **품질 저하를 발견하기까지 걸리는 시간**이다.

### 플랫폼을 과도하게 추상화하지 않기

공통 파이프라인이 팀의 생산성을 높일 수 있지만, 지나치게 많은 추상화는 장애 원인 파악을 어렵게 한다. 표준화해야 할 부분(로그·권한·모델 등록·배포 게이트)과 도메인별로 열어 둘 부분(피처·모델·평가 기준)을 구분해야 한다.

## 3. 재현성: 코드만 버전 관리하면 충분할까?

같은 Git 커밋을 실행해도 학습 데이터의 스냅샷, 피처 정의, 패키지 버전, 랜덤 시드가 다르면 모델이 달라질 수 있다.

```text
experiment_run
 ├── code_commit
 ├── data_snapshot
 ├── feature_definition + availability_time
 ├── environment + dependency_lock
 ├── hyperparameters + random_seed
 ├── evaluation_dataset + metrics
 └── model_artifact → deployment_revision
```

MLflow 같은 실험 추적 도구는 실행 결과를 연결하는 중심이 될 수 있다. 하지만 데이터 품질 검사, 접근 권한, 배포 승인, 실제 운영 관측은 별도의 설계가 필요하다.

**핵심은 최고 점수 기록이 아니라 변경의 원인을 역추적할 수 있는가**이다.

## 4. CI / CD / CT는 서로 다른 자동화다

| 구분 | 주요 트리거 | 검증 대상 | 산출물 |
|---|---|---|---|
| CI | 코드·설정 변경 | 단위 테스트, 데이터 계약, 이미지 빌드 | 검증된 빌드 |
| CD | 릴리스 승인 | 스테이징, 통합 테스트, 배포 정책 | 운영 배포 |
| CT | 새 데이터·드리프트·주기 | 데이터 검증, 재학습, 후보 모델 평가 | 새로운 모델 후보 |

![gitops-pipeline 아키텍처](/diagrams/gitops-pipeline.svg)

*구성 요소 간 관계를 단순화한 개념 다이어그램입니다.*

CH3의 Kubernetes·CI/CD 학습은 이 흐름을 실제 환경에 연결하기 위한 기반이다. GitOps를 도입할 때도 **Git 상태와 실제 클러스터 상태의 차이를 어떻게 감지·복구할 것인가**가 핵심이다.

::: warning 실습 상태
위 다이어그램은 **개념 아키텍처**이며, Harbor·GitLab Runner·Argo CD 등의 실습 완료를 의미하지 않습니다.
:::

## 5. 제조 ML: 낮은 MAPE가 좋은 모델을 의미할까?

제조·산업 시계열에서는 목표 변수의 변동폭이 좁은 경우가 많다. 이때 평균에 가까운 값만 예측해도 상대 오차(MAPE)는 작게 나올 수 있지만, 실제 운전 변화에 대한 설명력(R²)은 낮을 수 있다.

예를 들어 목표값이 대부분 100 전후에 모여 있다면 100을 계속 출력하는 모델도 낮은 MAPE를 보일 수 있다. 그러나 공정 조건이 바뀌었을 때 목표값이 왜 움직이는지는 포착하지 못한다.

따라서 평가 질문을 다음과 같이 바꿔야 한다.

1. **분포 이동:** 학습 범위를 벗어나는 운전 조건은 무엇인가?
2. **피처 리키지:** 추론 시점에 실제로 확보할 수 없는 정보가 피처에 포함되었는가?
3. **구간별 성능:** 특정 공정·운전 구간에서만 오차가 커지는가?
4. **의사결정 유효성:** 예측값을 현업의 운영 제약 안에서 활용할 수 있는가?

### Point-in-time correctness

시간에 따라 기록되는 센서·공정 데이터에서는 단순한 랜덤 분할보다 시간 기반 검증이 중요할 수 있다. 특히 파생변수를 만들 때 **예측하려는 시점 이후에야 알 수 있는 값**이 섞이지 않았는지 확인해야 한다.

이 문제는 Feast 같은 피처 관리 도구를 공부할 때도 중요하다. 피처 저장소가 존재한다는 사실 자체가 리키지를 자동으로 막아 주는 것은 아니며, 피처 정의와 시점 정합성에 대한 검증이 필요하다.

## 6. LLMOps: LLM만 버전 관리하면 재현 가능한가?

RAG 서비스는 기반 LLM이 같아도 문서 수집 시점, 청킹, 임베딩, 인덱스, 검색 설정, 프롬프트, 재정렬 방식에 따라 결과가 달라진다.

![rag-pipeline 아키텍처](/diagrams/rag-pipeline.svg)

*구성 요소 간 관계를 단순화한 개념 다이어그램입니다.*

운영 시 최소한 다음 변경 단위를 추적할 필요가 있다.

- **데이터:** 문서 스냅샷, 수집·전처리 버전
- **검색:** 임베딩 모델, 인덱스 버전, Top-K, 필터, 재정렬
- **생성:** 모델 버전, 프롬프트 템플릿, 생성 설정
- **Agent:** 도구 스키마, 실행 정책, 권한, 중간 단계 기록
- **평가:** 테스트셋 버전, 평가자, 기준 점수, 회귀 결과

### Agent에서는 최종 답변만 보면 부족하다

Agent가 실패했을 때 원인은 검색 실패, 잘못된 도구 선택, 인자 구성 오류, 권한 거부, 외부 API 장애 등 다양하다. 따라서 **최종 답변 품질**과 **각 단계의 실행 성공률**을 분리해 평가해야 한다.

## 7. Evaluation과 Observability를 구분하기

평가(Evaluation)는 *시스템이 얼마나 잘 동작하는가*를 판단하는 기준이고, 관측 가능성(Observability)은 *왜 그런 결과가 나왔는가*를 조사할 수 있게 하는 능력이다.

| 계층 | 평가 질문 | 관측 대상 |
|---|---|---|
| Retrieval | 관련 문서를 찾았는가? | 검색 쿼리, Top-K, 점수, 인덱스 버전 |
| Generation | 근거에 충실한가? | 프롬프트, 컨텍스트, 응답, 토큰 |
| Agent | 목표를 완수했는가? | 도구 선택, 호출 인자, 오류, 재시도 |
| Serving | 요구 SLO를 만족하는가? | p50/p95 지연, 오류율, 처리량, 비용 |

RAGAS 등의 자동 평가는 유용하지만, **Faithfulness는 제공된 근거에 대한 충실성**을 평가하는 개념이다. 외부 세계에서 사실인지를 자동으로 보장하지는 않는다. 자동 평가와 도메인 골든셋, 사람의 평가를 함께 설계하는 편이 안전하다.

Langfuse 같은 추적 도구를 사용할 때도 개인정보·민감정보 마스킹, 로그 보존 기간, 접근 권한을 설계해야 한다. 모든 요청을 무제한 저장하는 것이 곧 좋은 관측 가능성은 아니다.


## 8. RAG·Agent 평가 지표를 어떻게 설계할까?

LLM 애플리케이션의 평가는 **검색 품질 → 생성 품질 → 작업 성공 → 운영 품질**로 분리하는 편이 진단에 유리하다. 최종 답변 하나만 점수화하면 어느 단계에서 실패했는지 알기 어렵다.

### 8.1 Retrieval: 필요한 근거를 찾아왔는가?

| 지표 | 측정 대상 | 해석 및 주의점 |
|---|---|---|
| **Recall@K** | 정답 관련 문서 중 Top-K에 포함된 비율 | 관련 문서의 정답 라벨이 필요하다. K가 커지면 보통 상승한다. |
| **Precision@K** | Top-K 중 관련 문서의 비율 | 검색 결과에 노이즈가 얼마나 섞였는지 파악한다. |
| **MRR** | 첫 번째 관련 문서의 순위 | 첫 정답 문서가 앞에 나오는 것이 중요한 검색에 적합하다. |
| **nDCG@K** | 관련도 등급과 순위 품질 | 문서별 관련도에 차이가 있을 때 유용하다. |
| **Hit Rate@K** | Top-K에 관련 문서가 하나라도 있는 질의의 비율 | 찾기 성공 여부를 간단히 확인한다. |

**예시:** 관련 문서가 총 4개인데 Top-5 검색 결과에서 2개를 찾았고, 나머지 3개는 무관하다면 **Recall@5 = 2/4 = 0.5**, **Precision@5 = 2/5 = 0.4**이다. 검색이 잘 되었는지와 검색 결과가 얼마나 깨끗한지는 다른 문제다.

::: tip Retrieval 평가의 함정
검색 결과의 **chunk 단위**와 정답의 **document 단위**가 다르면 지표가 왜곡될 수 있다. 평가 전에 관련성의 단위, 중복 청크 처리, 정답 문서 집합을 먼저 정의해야 한다.
:::

### 8.2 Generation: 근거에 충실하고 질문에 답했는가?

| 지표 | 핵심 질문 | Reference 필요 여부 |
|---|---|---|
| **Faithfulness / Groundedness** | 생성된 주장이 검색된 컨텍스트로 뒷받침되는가? | 정답 답변은 없어도 평가 가능하지만 근거 컨텍스트가 필요하다. |
| **Answer Relevancy** | 응답이 사용자 질문에 적절하게 답하는가? | 일반적으로 정답 답변 없이도 평가할 수 있다. |
| **Answer Correctness** | 실제 정답과 의미적으로 일치하는가? | 일반적으로 정답 답변이 필요하다. |
| **Context Precision** | 검색 결과 중 유용한 컨텍스트가 상위에 배치됐는가? | 평가 구현에 따라 정답 답변 또는 관련성 라벨이 필요하다. |
| **Context Recall** | 답변에 필요한 근거가 컨텍스트에 포함됐는가? | 보통 정답 답변이나 근거 라벨이 필요하다. |

**중요:** Faithfulness가 높아도 답변이 사실이라는 보장은 없다. 잘못된 문서에 충실한 답변도 높은 Faithfulness를 받을 수 있다. 반대로 정확한 답변이라도 검색 근거를 벗어나면 Groundedness가 낮아질 수 있다.

또한 RAGAS의 구체적인 메트릭 구현과 입력 필드는 버전에 따라 달라질 수 있으므로, 운영 평가에서는 **메트릭 이름뿐 아니라 라이브러리 버전·평가 프롬프트·Judge 모델까지 고정**해야 한다.

### 8.3 LLM-as-a-Judge: 생성형 AI로 생성형 AI를 평가한다

LLM-as-a-Judge는 평가자 역할의 LLM에게 **평가 대상 응답과 명시적인 채점 기준(rubric)**을 제공해 품질을 판단하게 하는 방식이다. 사람이 모든 답변을 읽기 어려운 상황에서 평가 범위를 넓히는 데 유용하지만, 사람의 판단을 완전히 대체하지는 못한다.

![LLM-as-a-Judge 평가 파이프라인](/diagrams/llm-judge.svg)

**평가 입력 예시**

```json
{
  "question": "설비 A의 압력이 상승한 원인은?",
  "retrieved_context": "최근 밸브 개도율 감소 및 유량 변화 기록",
  "answer": "밸브 개도율 감소로 압력이 상승했을 가능성이 있습니다.",
  "reference_answer": "밸브 개도율 및 유량 변화가 주요 검토 요인",
  "rubric_version": "groundedness-v1"
}
```

**Judge 프롬프트 설계 예시**

```text
역할: 검색 근거에 대한 답변의 충실성을 평가하는 심사자.

평가 기준:
5 = 모든 핵심 주장이 근거로 뒷받침됨
4 = 핵심 주장은 뒷받침되나 사소한 과장 있음
3 = 일부 주장은 뒷받침되지만 중요한 추론이 섞임
2 = 핵심 주장 상당수가 근거로 확인되지 않음
1 = 근거와 모순되거나 근거가 거의 없음

규칙:
- 질문, 검색 컨텍스트, 답변만 사용한다.
- 유창한 문체에 가산점을 주지 않는다.
- 근거가 부족하면 높은 점수를 주지 않는다.
- 점수와 근거가 되는 문장을 JSON으로 반환한다.
```

```json
{
  "score": 4,
  "reason": "밸브 개도율 감소는 컨텍스트에 있지만, 압력 상승의 직접적인 인과관계는 추가 검증이 필요합니다.",
  "unsupported_claims": ["밸브 개도율 감소가 압력 상승의 원인"]
}
```

이 예시는 **평가 형식을 보여주는 가상의 출력**이다. 실제 평가 실행 결과나 특정 Judge 모델의 점수가 아니다.

### 8.4 Judge를 믿어도 될까? — 편향과 캘리브레이션

LLM Judge에는 다음과 같은 오류가 발생할 수 있다.

- **Position bias:** 두 답변을 비교할 때 먼저 제시된 답변을 선호한다.
- **Verbosity bias:** 내용이 더 정확하지 않아도 긴 답변을 높게 평가한다.
- **Self-preference bias:** 평가 모델과 유사한 모델의 문체·출력을 선호할 수 있다.
- **Prompt sensitivity:** 채점 문구나 척도가 바뀌면 점수가 달라질 수 있다.
- **Domain mismatch:** 제조·의료·법률처럼 전문성이 필요한 영역에서 잘못된 판단을 할 수 있다.

따라서 운영용 Judge는 다음과 같이 검증한다.

1. **골든셋 구축:** 도메인 전문가가 평가한 정상·오류·경계 사례를 포함한다.
2. **사람과 비교:** 정확 일치율, 가중 Cohen's κ, 순위 상관 등 평가 척도에 맞는 일치도를 확인한다.
3. **순서 바꾸기:** Pairwise 평가에서는 A/B 순서를 교환해 결과 안정성을 확인한다.
4. **재현성 확인:** 모델·프롬프트·루브릭 버전을 기록하고 반복 평가 분산을 확인한다.
5. **경계 사례 재검토:** 낮은 확신도, 모델 간 불일치, 고위험 답변은 사람이 검토한다.

::: warning 평가 점수는 절대적인 진실이 아니다
Judge가 4/5점을 주었다고 해서 답변이 **80% 정확하다**는 뜻은 아니다. 1~5점은 정의한 루브릭의 **서열형 등급**이며, 검증 없이 확률이나 정확도로 해석하면 안 된다.
:::

### 8.5 Agent Evaluation: 답변 품질보다 작업 성공이 중요할 때

Agent는 중간 과정에서 도구를 호출하고 상태를 변경하므로, RAG 답변 평가만으로 충분하지 않다.

| 평가 계층 | 대표 지표 | 확인할 실패 |
|---|---|---|
| Goal | **Task Success Rate** | 사용자 목표를 실제로 달성하지 못함 |
| Tool | **Tool Selection / Argument Accuracy** | 잘못된 도구·파라미터 선택 |
| Trajectory | **Step Validity / Policy Compliance** | 불필요한 반복, 정책 위반 |
| Reliability | **Timeout / Recovery Rate** | 도구 오류 후 복구 실패 |
| Efficiency | **Latency / Tokens / Cost per Success** | 성공했지만 과도한 비용 발생 |

**Task Success Rate = 성공적으로 완료한 작업 수 / 전체 평가 작업 수**로 정의할 수 있다. 다만 무엇을 '성공'으로 볼지는 도메인별로 명확하게 정해야 한다. 예를 들어 조회형 Agent는 정답 제공이 성공일 수 있지만, 업무 실행형 Agent는 **실제 상태 변경의 정확성과 권한 준수**까지 검증해야 한다.

### 8.6 운영 평가 파이프라인 제안

```text
Versioned Evaluation Dataset
       ↓
Run candidate RAG / Agent
       ↓
Deterministic checks (schema, citation, tool policy)
       ↓
Retrieval metrics + LLM-as-a-Judge
       ↓
Human review on sampled / disputed cases
       ↓
Compare to baseline + release gate
       ↓
Production tracing + drift monitoring
```

배포 게이트는 **평균 Judge 점수 하나**로 만들기보다, 필수 정책 위반 0건, 주요 골든셋의 회귀 여부, p95 지연시간, 성공당 비용 등 **여러 조건**을 함께 적용하는 편이 안전하다. 점수 기준은 실제 트래픽과 비즈니스 위험을 고려해 설정해야 한다.

### Further reading: Evaluation

- [RAGAS — Metrics](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/)
- [LangSmith — Evaluation Concepts](https://docs.langchain.com/langsmith/evaluation-concepts)
- [MT-Bench / Chatbot Arena — LLM-as-a-Judge](https://arxiv.org/abs/2306.05685)
- [G-Eval — NLG Evaluation using GPT-4](https://arxiv.org/abs/2303.16634)

## 9. 시스템 설계의 트레이드오프

> **Quality × Reliability × Latency × Cost**
>
> 네 요소를 동시에 무한히 최적화할 수는 없다.

큰 모델은 품질을 높일 가능성이 있지만 비용·지연이 증가할 수 있다. 검색 Top-K를 늘리면 재현율이 개선될 수 있지만 불필요한 문서가 섞이고 컨텍스트 비용이 늘 수 있다. 따라서 모델이나 프레임워크를 먼저 선택하기보다 **사용자 경험과 운영 제약**을 먼저 정의하는 편이 좋다.

### 실무에 적용할 네 가지 원칙

1. **검증 가능한 변경:** 코드·데이터·모델·프롬프트·인덱스를 릴리스 단위로 식별한다.
2. **안전한 배포:** 오프라인 평가, 점진적 노출, 롤백 기준을 둔다.
3. **원인 추적:** 결과 점수뿐 아니라 실행 경로를 관찰한다.
4. **목적에 맞는 복잡도:** 작은 서비스에 과도한 플랫폼을 강요하지 않는다.

## 10. 다음 학습: MLflow · Feast · Kubeflow

다음 주에는 다음 연결 고리를 더 구체적으로 공부한다.

| 도구 | 주요 학습 질문 |
|---|---|
| **MLflow** | 실험 실행과 모델 아티팩트를 어떻게 추적·관리하는가? |
| **Feast** | 학습·서빙 피처의 정의와 시점 정합성을 어떻게 관리하는가? |
| **Kubeflow** | Kubernetes 환경에서 ML 워크플로를 어떻게 구성하는가? |

이번 주의 Kubernetes·CI/CD 환경 구성은 후속 실습의 기반이므로, **학습 개념과 실제 구축·검증 결과를 구분해** 이어서 기록할 예정이다.

---

### Takeaway

**운영 가능한 AI는 모델 파일이 아니라, 변경을 추적하고 검증하며 되돌릴 수 있는 시스템이다.**

### Further reading

- [Google — Rules of Machine Learning](https://developers.google.com/machine-learning/guides/rules-of-ml)
- [Google — Hidden Technical Debt in Machine Learning Systems](https://papers.nips.cc/paper/5656-hidden-technical-debt-in-machine-learning-systems)
- [MLflow Documentation](https://mlflow.org/docs/latest/index.html)
- [Feast Documentation](https://docs.feast.dev/)
- [Kubeflow Documentation](https://www.kubeflow.org/docs/)
- [VitePress Documentation](https://vitepress.dev/)
