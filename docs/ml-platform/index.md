# ML Platform Engineering

모델을 학습시키는 단계부터 운영 환경에서 변경을 검증하는 과정까지. **어떤 문제가 생기고, 무엇을 확인해야 하는지**를 순서대로 정리합니다.

## 1주차 · ML 시스템의 기반

**[1주차 학습 정리 · ML Lifecycle에서 Kubernetes CI/CD까지](/ml-platform/study-week-01)**  
CH1~3 핵심 개념을 연결하고 GitLab CI/CD 배포 예제를 추가로 살펴봅니다.

### [01. 모델을 만들고 나서 시작되는 일들](/ml-platform/week-01)
ML Lifecycle, 재현성, 시계열 검증과 학습·서빙 일치성.

### [02. 모델 학습에 CI/CD만 적용하면 충분할까?](/ml-platform/week-02)
MLOps, CI/CD/CT, 데이터 계약과 릴리스 게이트.

### [03. ML 플랫폼을 설계할 때 먼저 정할 것들](/ml-platform/week-03)
플랫폼 책임 경계, 컨테이너와 Kubernetes, 학습 아티팩트 서빙.

## 2주차 · 실험 추적에서 모델 운영까지

**[2주차 학습 정리 · MLflow·Feast·KFP와 운영 검증](/ml-platform/study-week-02)**  
CH4~5의 실험 추적·피처 관리·파이프라인과 kind 운영 실습을 연결합니다.

### [MLflow · 학습에서 모델 등록과 재로딩까지](/ml-platform/mlflow-model-lifecycle)
동일 데이터로 세 모델 비교, 검증 기준 선택, 등록 모델 예측 일치 검증.

### [Feast·KFP · 같은 피처와 같은 모델로 추론하기](/ml-platform/model-pipeline)
MLflow의 데이터·입력 계약·고정 모델 버전을 이어받는 연결 설계.

### [04. 컨테이너가 실행 중이면 서비스도 정상일까?](/ml-platform/week-04)
Startup·Readiness·Liveness Probe, 배포 전략과 롤백.

### [05. 리소스 설정은 성능과 안정성을 어떻게 바꿀까?](/ml-platform/week-05)
Requests/Limits·QoS, 로컬 측정 기록과 성능·가용성 실험.

### [06. KServe와 vLLM으로 모델을 어떻게 운영할까?](/ml-platform/week-06)
모델 서빙의 개념, KServe·vLLM 역할과 실무 운영 지표.

## 심화 · Evaluation

### [MAPE는 낮은데 R²는 왜 낮을까?](/ml-platform/industrial-evaluation)
산업 AI 회귀 지표, 기준 모델, 시계열·운전 구간별 평가.

### [RAG와 Agent의 품질은 어떻게 평가할까?](/ml-platform/evaluation-and-operations)
Retrieval·Generation·Agent 평가, LLM-as-a-Judge, 배포 승인 기준.
