---
title: "11. KServe와 vLLM으로 모델을 어떻게 운영할까?"
description: "KServe와 vLLM의 개념, 역할 구분, 서빙 지표와 Kubernetes 운영 설계"
date: 2026-11-01
outline: deep
prev:
  text: '10. 리소스 설정은 성능과 안정성을 어떻게 바꿀까?'
  link: '/ml-platform/week-05'
next: false
---

# 11. KServe와 vLLM으로 모델을 어떻게 운영할까?

**학습 범위:** 확장 · ML/LLM 모델 서빙  
**핵심 질문:** Kubernetes 운영 설정을 모델 배포·GPU 자원·토큰 생성에 어떻게 적용할까?

## KServe와 vLLM: ML 모델을 서비스로 운영하는 방법

앞서 다룬 Probe, Deployment, Requests/Limits는 웹 애플리케이션뿐 아니라 **ML·LLM 모델 서빙**에도 그대로 중요하다. 다만 모델 서버에는 일반 웹 서비스와 다른 특성이 있다. 모델 파일을 메모리나 GPU에 적재해야 하고, 긴 추론 요청을 처리하며, 응답 지연이 토큰 수와 캐시 상태에 크게 영향을 받는다.

### 1. Model Serving이란?

모델 학습이 끝나면 가중치 파일이나 직렬화된 모델 아티팩트를 얻는다. **Serving은 이 모델을 메모리에 올리고, 요청을 받아 전처리 → 추론 → 후처리 → 응답하는 지속 실행 서비스로 만드는 과정**이다.

```text
Training / Registry
      │ 검증된 모델 버전
      ▼
Model Artifact Storage ── 모델 로딩 ──► Inference Server
                                             ▲
Client → API Gateway → Service / Routing ───┘
                                             │
                                      Prediction / Tokens
                                             │
                                     Logs · Metrics · Traces
```

학습에서는 재현성과 모델 품질이 핵심이라면, 서빙에서는 요청 성공률, 지연시간, 처리량, 자원 사용량, 업데이트 중 가용성이 중요하다. 코드가 정상이더라도 **모델을 다운로드하지 못하면 준비되지 않은 서비스**라는 점이 일반적인 HTTP API와 다르다.

### 2. KServe란 무엇인가?

**KServe는 Kubernetes 위에서 머신러닝 추론 서비스를 배포하고 관리하는 오픈소스 모델 서빙 플랫폼**이다. 기본 Kubernetes에서는 Deployment·Service·HPA·스토리지 연결을 개발자가 조합해야 한다. KServe는 모델 중심의 선언적 리소스를 추가하여 배포·실행 환경·트래픽 관리 등 반복 작업을 표준화한다.

KServe를 이해하려면 두 영역을 구분해야 한다.

| 구분 | 의미 | 실제 역할 |
|---|---|---|
| Control Plane | 어떤 모델을 어떻게 운영할지 결정 | InferenceService 해석, Pod 및 네트워크 리소스 관리 |
| Data Plane | 실제 사용자의 추론 요청 처리 | Predictor, Transformer, 모델 서버 |
| InferenceService | '이 모델을 이 설정으로 제공해줘'라는 선언 | 모델 URI·리소스·런타임 선택 등 |
| ServingRuntime | 어떤 이미지로 모델을 실행할지 정의 | 예: MLServer, Triton 또는 사용자 정의 런타임 |
| LLMInferenceService | 대규모 LLM을 위한 특화 리소스 | GPU 기반 LLM 운영, 라우팅, 분리형 서빙 등 |

**동작 흐름:** 사용자가 InferenceService를 생성하면 KServe Controller가 스펙을 감시하고, 실행 모드에 맞게 Deployment, Service 등의 Kubernetes 리소스를 구성한다. Pod가 모델을 적재한 뒤 준비 상태가 되면 트래픽을 받는다. 사용자는 일반적인 웹 서버 배포 YAML보다 **모델 자체와 서빙 요구사항**에 집중할 수 있다.

```text
사용자: InferenceService 생성
        │
        ▼
Kubernetes API ─────► KServe Controller (Control Plane)
                             │ 원하는 상태 Reconcile
                             ▼
                    Deployment / Service / Gateway
                             │
                             ▼
                   Predictor Pod (Data Plane)
                    모델 다운로드 → 초기화
                             │
                    Readiness → 요청 수신
```

**KServe의 배포 방식:** Standard Mode는 일반적인 Deployment/Service 등 Kubernetes 리소스를 활용해 제어하기 쉽고, Knative Mode는 서버리스 특성 및 scale-to-zero를 활용할 수 있다. LLM은 모델 초기화가 무겁고 GPU 자원 할당이 복잡해 일반적으로 Standard/LLM 전용 구성을 먼저 검토한다. KServe 버전에 따라 CRD 구조와 지원 기능이 달라질 수 있다.

### 3. vLLM이란 무엇이며 왜 쓰는가?

**vLLM은 대규모 언어 모델을 빠르고 효율적으로 추론하기 위한 오픈소스 엔진 및 서버**다. Transformers로 모델을 단순 실행하는 것과 달리, 동시에 들어오는 여러 요청의 GPU 메모리와 연산 스케줄을 효율적으로 관리한다.

LLM 요청은 크게 두 단계로 구성된다.

- **Prefill:** 입력 Prompt 토큰을 한 번에 처리해 Attention 계산과 KV Cache를 만든다. 입력이 길수록 첫 토큰까지 걸리는 시간(TTFT)에 영향을 준다.
- **Decode:** 앞선 토큰과 KV Cache를 참조하며 다음 토큰을 반복적으로 생성한다. 출력 토큰 수와 동시 요청량에 따라 TPOT가 달라진다.

vLLM의 핵심 기술을 동작 원리까지 살펴보자.

| 기술 | 개념 | 효과와 주의점 |
|---|---|---|
| **PagedAttention** | KV Cache를 고정된 블록 단위로 관리하고 논리적 토큰 위치와 실제 메모리 블록을 매핑 | 긴 요청과 다양한 길이의 요청에서 메모리 낭비 감소 |
| **Continuous Batching** | 요청 전체가 끝날 때까지 기다리지 않고, 실행 중인 배치에 요청을 동적으로 넣고 뺌 | GPU 활용과 처리량 향상, 요청별 대기시간은 부하에 따라 달라짐 |
| **KV Cache** | 이전 토큰의 Key/Value 계산 결과를 저장 | 재계산 감소 대신 GPU 메모리 점유 증가 |
| **Tensor Parallelism** | 하나의 모델 연산을 여러 GPU에 분할 | 대규모 모델 실행 가능, GPU 간 통신비용 증가 |
| **OpenAI-compatible API** | 채팅·완성형 요청 등 지원 엔드포인트 제공 | 기존 클라이언트 연결 쉬움, 모든 API 기능의 완전 호환을 의미하지 않음 |

```text
Request A: [Prefill] [Decode] [Decode] [Done]
Request B:            [Prefill] [Decode] [Decode] ...
Request C:                     [Prefill] [Decode] ...
                              ▼
                     Continuous Scheduler
                              ▼
                   GPU Compute + KV Cache Blocks
```

**왜 일반 API보다 메모리 관리가 중요할까?** LLM 서버의 GPU 메모리는 모델 가중치뿐 아니라 KV Cache와 추론 버퍼가 점유한다. 컨텍스트 길이와 동시 요청이 늘면 KV Cache 요구량도 증가한다. 따라서 단순히 'GPU 사용률이 80%'라는 정보만으로 충분하지 않고, 사용 가능한 KV Cache, 대기 요청, 토큰 처리 속도를 함께 봐야 한다.

### 4. KServe와 vLLM의 관계

**KServe가 모델을 어떻게 운영할지 관리한다면, vLLM은 모델 내부의 실제 추론을 실행한다.** 둘은 경쟁 기술이 아니며 함께 사용할 수 있다.

| 책임 | KServe | vLLM |
|---|---|---|
| Kubernetes 배포·상태 조정 | 주 역할 | 자체적으로 수행하지 않음 |
| GPU Pod·라우팅/스케일링 연계 | 담당 또는 주변 컴포넌트 활용 | 서버 내부 요청 스케줄링 담당 |
| 모델 가중치 로딩 | 서빙 아티팩트 경로·런타임 설정 | 실제 엔진 로딩 |
| 토큰 생성 | 모델 서버에 위임 | Prefill / Decode 수행 |
| 관찰 지표 | Pod·서비스·라우팅 상태 | TTFT, TPOT, KV Cache, 토큰 처리량 |

```text
사용자 / RAG Agent
       │
       ▼
API Gateway (Auth / Rate Limit)
       │
       ▼
KServe (배포 정책 / 라우팅 / Scaling)
       │
       ▼
vLLM GPU Pod
       ├─ Model Weights + Tokenizer
       ├─ Prefill / Decode Scheduler
       ├─ KV Cache (PagedAttention)
       └─ OpenAI-compatible Inference API
       │
       ▼
Metrics / Logs / Traces → SLO 검증 및 알림
```

### 5. 실무에서 가장 먼저 봐야 하는 성능 지표

| 지표 | 어떤 문제를 설명하나? | 확인할 원인 |
|---|---|---|
| **TTFT (Time to First Token)** | 첫 응답 토큰이 늦게 옴 | 긴 입력, Prefill 병목, 대기열 |
| **TPOT (Time per Output Token)** | 응답 생성 자체가 느림 | Decode 경합, GPU 메모리·대역폭 |
| **Tokens/s** | 실제 토큰 처리량 | 연산 효율, batching, 동시성 |
| **KV Cache 사용량** | 요청을 얼마나 더 받을 수 있는가 | 긴 Context, 동시 세션 수 |
| **Request Queue** | 이미 처리 용량을 넘었는가 | 실행 중 요청, 대기시간 |
| **OOM / Restarts** | 자원 부족이나 프로세스 장애 | 모델 크기, 캐시 구성, GPU 메모리 |

예를 들어 RAG의 응답이 느린 상황에서 **TTFT만 증가했다면** 검색 결과가 길어져 Prompt가 커졌거나 요청 대기열이 늘었을 수 있다. 반면 **TPOT가 증가한다면** Decode 단계의 동시 실행 경합과 KV Cache 사용량을 먼저 분석하는 편이 합리적이다. 원인 확정은 각 메트릭을 함께 확인해야 한다.

### 6. Kubernetes 운영과 연결되는 핵심 문제

**① Startup Probe: 모델 로딩이 긴 경우**  
대형 모델은 컨테이너가 실행되어도 가중치 다운로드, GPU 메모리 적재, 엔진 준비가 끝나지 않았을 수 있다. Startup Probe의 충분한 실패 허용시간과 Readiness 조건을 설정해야 초기화 중 불필요한 재시작을 방지한다.

**② GPU RollingUpdate: 새 Pod가 Pending인 경우**  
GPU 2개가 있는 클러스터에서 GPU Pod 2개가 이미 실행 중인데 `maxSurge: 1`, `maxUnavailable: 0`으로 업데이트하면 새 Pod가 요구하는 추가 GPU를 확보하지 못해 배포가 진행되지 않을 수 있다. 해결책은 배포용 GPU 여유 확보, Blue/Green 환경, 모델 사전 캐싱, 단계별 트래픽 절체 등이다.

**③ 종료 중 스트리밍 응답이 끊기는 경우**  
LLM 스트리밍 응답은 수 초~수십 초 연결을 유지할 수 있다. Pod가 종료되기 전에 새 요청 수신을 중단하고 기존 요청을 처리하는 draining 전략이 필요하다. `terminationGracePeriodSeconds`만 늘린다고 자동으로 해결되지는 않는다.

**④ Scale-out하면 처리량이 선형 증가할까?**  
그렇지 않을 수 있다. 각 replica마다 가중치와 캐시가 중복되어 GPU 메모리가 소비되고, 새 replica 로딩·네트워크·라우터 병목도 발생하기 때문이다. 성능 평가에서는 입력/출력 토큰 길이 분포를 고정하고 TTFT p95, TPOT p95, Tokens/s, 실패율을 함께 비교해야 한다.

### 7. 실행 및 관찰 예제

GPU가 있는 별도 서버라면 vLLM을 먼저 단독으로 검증한 후 KServe 통합을 진행하는 것이 문제 분리에 유리하다.

```bash
# GPU 및 호환 버전이 준비된 서버에서 실행 (예시)
vllm serve <MODEL_ID> --host 0.0.0.0 --port 8000

# 추론 서버 및 메트릭 확인
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/v1/models
curl -fsS http://localhost:8000/metrics | head
```

아래는 별도 설치된 KServe 클러스터에서 구조를 확인하는 명령이다.

```bash
kubectl get crd | grep -E 'inferenceservice|servingruntime'
kubectl get inferenceservices -A
kubectl get servingruntimes -A
kubectl get deployments,pods,svc -A
```

이는 **실행 가이드**이며 이번 환경에서 vLLM·KServe 또는 GPU 성능을 직접 실행한 결과는 아니다. 설치 방식과 API 스펙은 KServe 버전에 따라 달라지므로 공식 문서를 확인하고 적용한다.

### 8. 설계 판단 정리

일반적인 회귀·분류 모델을 안정적으로 제공하려면 KServe의 기본 InferenceService와 표준 런타임을 우선 검토한다. 고성능 LLM 추론이 목표라면 vLLM 단독 배포로 성능 병목을 먼저 측정한 뒤, **여러 모델·여러 팀의 배포 표준화와 라우팅·운영 거버넌스가 필요할 때** KServe를 결합하는 접근이 실용적이다.

공식 참고: [KServe Architecture](https://kserve.github.io/website/docs/intro), [KServe ServingRuntime](https://kserve.github.io/website/docs/concepts/resources/servingruntime), [KServe LLMInferenceService](https://kserve.github.io/website/docs/concepts/architecture/control-plane-llmisvc), [vLLM Documentation](https://docs.vllm.ai/)

---

[2주차 학습 정리로 돌아가기](/ml-platform/study-week-02)

