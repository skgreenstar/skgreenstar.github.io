---
title: "Week 02 · 실험 추적에서 모델 운영까지"
description: "MLflow·Feast·KFP와 kind 운영 실습을 연결하는 2주차 학습 정리"
outline: deep
prev:
  text: '1주차 · ML 시스템의 기반'
  link: '/ml-platform/study-week-01'
next:
  text: 'MLflow · 모델 학습과 재로딩'
  link: '/ml-platform/mlflow-model-lifecycle'
---

# Week 02 · 실험 추적에서 모델 운영까지

**교재 범위:** CH4 · MLflow와 Feast / CH5 · Kubeflow Pipelines  
**확장 실습:** kind의 Probe·배포 전략·CPU·메모리·QoS, KServe·vLLM 개념

모델을 선택할 근거를 MLflow에 남기고, 동일한 피처와 등록 모델을 Feast·KFP로 연결한다. 여기에 직접 실행한 Kubernetes 운영 실습을 더해 **어떤 모델을 어떤 자원으로 실행하고, 장애가 나면 어떻게 복구하는가**까지 학습 범위를 확장한다.

## 1. 교재 학습과 모델 파이프라인

| 단계 | 핵심 질문 | 연결 글 |
|---|---|
| MLflow · CH4 | 어떤 데이터·설정으로 선택한 모델을 다시 사용할 수 있는가? | [학습·실험 비교·모델 등록·재로딩](/ml-platform/mlflow-model-lifecycle) |
| Feast · CH4 | 예측 시각에 사용할 수 있던 피처를 같은 정의로 조회하는가? | [피처 계약과 Offline·Online 조회](/ml-platform/model-pipeline) |
| KFP · CH5 | 고정 모델과 피처로 배치 추론을 반복 실행하는가? | [컴포넌트와 결과 검증 설계](/ml-platform/model-pipeline) |

MLflow 실행 코드는 합성 제조 품질 데이터와 세 모델을 사용한다. 검증 RMSE로 모델을 선택하고, 등록한 고정 버전을 재로딩해 예측값 일치를 검사한다. 데이터 CSV·피처 계약·선택 모델 URI를 후속 Feast·KFP의 입력으로 재사용한다.

## 2. kind에서 완료한 운영 실습

| 실습 | 실행 결과 |
|---|---|
| Readiness 장애·복구 | healthz=200, readyz=503 / Ready 1→0→1 / EndpointSlice ready true→false→true / 재시작 0 |
| Liveness 장애 | HTTP 503 → Killing → 동일 Pod 재시작 1회 → Ready 복구 |
| RollingUpdate | 새 Pod Ready 후 기존 Pod Terminating / LAB_VERSION=v2 / revision 2 |
| Rollback | revision 1 템플릿 복원 / LAB_VERSION 제거 / 새 Pod Ready / revision 3 |
| Recreate | 기존 Pod 종료 상태 이후 신규 Pod 생성·Ready / LAB_VERSION=recreate |
| CPU limit 100m | 10.006초 동안 CPU 1.001782초 사용 / 제어 주기 100개에서 throttling |
| Memory limit 64Mi | 160Mi 할당 시도 → OOMKilled / exitCode=137 / 재시작 0 |
| QoS 등급 | Guaranteed·Burstable·BestEffort 세 구성의 실제 등급 확인 |

이 기록은 개인 PC에서 실행한 터미널 출력에 근거한다. 배포 전략은 Pod 교체 순서, 자원 실습은 quota·OOM 종료·QoS 등급을 검증했다. 요청 가용성 비교와 노드 압박 시 eviction 실험은 별도의 검증 범위다.

## 3. 상세 글

### [04. 컨테이너가 실행 중이면 서비스도 정상일까?](/ml-platform/week-04)
Probe·RollingUpdate·Recreate·롤백의 명령, 로그, 결과 해석.

### [05. 리소스 설정은 성능과 안정성을 어떻게 바꿀까?](/ml-platform/week-05)
CPU cgroup 통계, OOMKilled, QoS 세 등급과 로컬 API 기준선.

### [06. KServe와 vLLM으로 모델을 어떻게 운영할까?](/ml-platform/week-06)
모델 서빙의 개념과 책임 경계, GPU 메모리·초기화·스트리밍 운영 지표.

## 4. 실행 환경과 재현 코드

| 항목 | 구성 |
|---|---|
| Docker | Linux / aarch64 |
| kind 클러스터 / 컨텍스트 | mlops-lab / kind-mlops-lab |
| 노드 | mlops-lab-control-plane, Kubernetes v1.37.0 |
| 런타임 / 네임스페이스 | containerd 2.3.4 / week02 |

- [MLflow 학습·등록 코드](https://github.com/skgreenstar/skgreenstar.github.io/tree/main/labs/week02-mlflow)
- [Kubernetes 기초 실습 YAML](https://github.com/skgreenstar/skgreenstar.github.io/tree/main/docs/ml-platform/week-02-lab)
- [후속 부하 실험 코드](https://github.com/skgreenstar/skgreenstar.github.io/tree/main/docs/ml-platform/week-02-advanced)

## 5. 이번 주에 정리한 기준

모델 품질은 고정된 데이터·피처·모델 버전과 연결해 비교한다. 운영 상태는 별도로 검증한다. 프로세스가 살아 있는 상태와 트래픽을 받을 준비가 된 상태는 달랐고, CPU 제한은 throttling으로, 메모리 제한은 OOM 종료로 나타났다. 배포·롤백에서는 선택한 설정과 Pod 교체 순서가 연결됐다.

앞으로는 동일 모델 버전을 이 운영 실습의 실행 대상으로 사용한다. MLflow의 선택 근거, Feast의 피처 계약, KFP의 단계별 산출물이 맞물려야 모델 품질과 운영 결과를 하나의 계보로 추적할 수 있다.

### 참고 자료

- [교재 CH4](https://livebook.manning.com/learn/machine-learning-platform-engineering/chapter-4)
- [교재 CH5](https://livebook.manning.com/learn/machine-learning-platform-engineering/chapter-5)
- [Kubernetes Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)
- [Kubernetes Deployment](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Kubernetes 자원 관리](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)
