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

**[2주차 학습 정리 · MLflow·Feast·KFP와 결과 검증](/ml-platform/study-week-02)**  
CH4~5를 환경 → 모델 → 피처 → 파이프라인 → 결과 검증 순서로 연결합니다.

### [04. 실행 환경 · Kubernetes에서 도구를 연결하기](/ml-platform/week02-environment)
PC·Pod·Service의 실행 위치, 메타데이터·아티팩트·저장 경로.

### [05. MLflow · 학습에서 모델 등록과 재로딩까지](/ml-platform/mlflow-model-lifecycle)
실험 추적·EDA·후보 비교·고정 버전 등록과 실제 kind 실행 기록.

### [06. Feast · 같은 정의로 과거와 최신 피처 조회하기](/ml-platform/model-pipeline)
피처 계약, Point-in-time join, apply와 materialize의 차이.

### [07. KFP · 피처 조회부터 배치 추론까지 연결하기](/ml-platform/kfp-batch-inference)
컴포넌트·DAG·파라미터·Dataset과 단계별 검증.

### [08. 결과 검증 · 성공한 실행을 재현 가능한 결과로 만들기](/ml-platform/week02-verification)
결과 스키마·입력 해시·모델 버전·예측 비교와 추적성.

## 심화 · 운영과 평가

선택한 모델과 파이프라인을 서비스로 이어가려면 준비 상태·자원 제약·서빙 방식·평가 기준을 함께 살펴봐야 합니다. 아래 글은 이 운영 과정을 주제별로 확장합니다.

### [컨테이너가 실행 중이면 서비스도 정상일까?](/ml-platform/week-04)
Probe·배포 전략·롤백의 개념과 실제 관찰.

### [리소스 설정은 성능과 안정성을 어떻게 바꿀까?](/ml-platform/week-05)
Requests/Limits·CPU throttling·메모리 OOM·QoS.

### [KServe와 vLLM으로 모델을 어떻게 운영할까?](/ml-platform/week-06)
모델 서빙과 GPU·토큰 생성의 개념 확장.

### [MAPE는 낮은데 R²는 왜 낮을까?](/ml-platform/industrial-evaluation)
산업 AI 회귀 지표, 기준 모델, 시계열·운전 구간별 평가.

### [RAG와 Agent의 품질은 어떻게 평가할까?](/ml-platform/evaluation-and-operations)
Retrieval·Generation·Agent 평가, LLM-as-a-Judge, 배포 승인 기준.


## 3주차 · AI 추론 서비스 확장과 트래픽 진단

**[3주차 학습 정리 · CH6~7](/ml-platform/study-week-03)**  
모델을 제공하는 것에서 한 걸음 더 나아가, CPU·대기 병목과 Ready 엔드포인트를 분리하여 확장과 트래픽 경로를 분석합니다.

### [09. 추론이 느려질 때 Pod부터 늘려야 할까?](/ml-platform/week03-autoscaling)
HPA·CPU requests·부하 특성·콜드 스타트의 관계와 재현 실험.

### [10. 요청은 어느 Pod까지 도달하는가?](/ml-platform/week03-traffic)
Service·DNS·EndpointSlice·Ingress/Gateway API와 Readiness 장애 분석.

### [11. BentoML 모델 서빙](/ml-platform/week03-bentoml-serving)
추론 API 정의, 모델 패키징, MLflow 모델 아티팩트와 Kubernetes 연결 설계.

### [12. 데이터와 모델 드리프트](/ml-platform/week03-model-serving-drift)
Data Drift·Prediction Drift·Concept Drift·Model Drift를 구분하고 Evidently 기반 모니터링을 설계한다.

## 4주차 · Node 배치와 상태 저장

**[4주차 학습 정리 · CH8~9 Node 배치와 상태 저장](/ml-platform/study-week-04)**  
KFP 데이터 전달, 품질 승인, 스토리지·스케줄링을 하나의 운영 흐름으로 연결합니다.

### [13. KFP에서 데이터는 어느 Pod를 거쳐 이동할까?](/ml-platform/week04-artifacts)
Parameter와 Artifact, 스냅샷·캐시, 데이터 전달 계약.

### [14. 학습이 끝났다는 사실만으로 모델을 등록할 수 있을까?](/ml-platform/week04-training-validation)
기준 모델과 비교, 품질 게이트, 미승인과 실행 오류 구분.

### [15. 아티팩트 저장소와 PVC 중 무엇을 선택해야 할까?](/ml-platform/week04-storage)
객체 저장소와 볼륨, 접근 모드와 실패 원인.

### [16. 학습 Pod가 Pending이라면 모델보다 무엇을 먼저 볼까?](/ml-platform/week04-scheduling)
Scheduler·Affinity·Taint, PVC와 StatefulSet 운영.

### [17. Pod는 왜 한 Node에 몰리고, 어떻게 분산할까?](/ml-platform/week04-placement)
CH8. Scheduler Filter/Score, Node Affinity, Taint, Pod Affinity/Anti-Affinity, Topology Spread, FailedScheduling 실습 설계.

### [18. StatefulSet은 왜 Pod마다 별도 PVC를 만들까?](/ml-platform/week04-statefulset)
CH9.1~9.2. PV/PVC/StorageClass, Pod identity, Headless Service, volumeClaimTemplates와 데이터 보존.

### [19. 디스크와 Pod가 사라지면 데이터를 어떻게 복구할까?](/ml-platform/week04-recovery)
CH9.3~9.4. reclaimPolicy, Retain 복구, emptyDir, Generic Ephemeral Volume.

### [20. Scheduler와 StatefulSet을 끝까지 검증하는 실습](/ml-platform/week04-practical-lab)
Node Affinity와 Pod Anti-Affinity로 Pending을 재현하고 StatefulSet PVC의 파일 체크섬을 비교하는 통합 실습 설계.
