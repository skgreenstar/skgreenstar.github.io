---
title: "04. 실행 환경 · Kubernetes에서 도구를 연결하기"
outline: deep
prev:
  text: '2주차 · 학습 정리'
  link: '/ml-platform/study-week-02'
next:
  text: '05 · MLflow'
  link: '/ml-platform/mlflow-model-lifecycle'
---

# 04. 실행 환경 · Kubernetes에서 도구를 연결하기

**CH4~5 · 도구를 설치하기 전에 실행 위치와 저장 경로부터 구분한다.**

## 1. PC와 클러스터가 담당하는 일

PC에서는 소스를 내려받고 컨테이너 이미지를 빌드·적재하며 kubectl로 작업을 제어한다. MLflow 서버와 학습 Job은 kind에서 실행했다. Feast 조회·등록 모델 예측 비교와 KFP 컴포넌트의 파일 입출력은 별도 자동 검증 환경에서 확인했다. 클러스터에 연결할 때는 Feast를 Job으로, KFP 컴포넌트를 각각의 Pod로 실행하는 구조를 사용한다.

| 위치 | 역할 | 접근 방법 |
|---|---|---|
| PC | 이미지 빌드·명령 실행·브라우저 확인 | Docker / kind / kubectl |
| week02 네임스페이스 | MLflow 서버·학습 Job·현재 운영 실습 | context와 namespace 명시 |
| MLflow Service | Pod 사이의 Tracking API | http://mlflow:5000 |
| PC 브라우저 | MLflow UI | port-forward 후 127.0.0.1:5050 |
| KFP 연결 구조 | 파이프라인 제어 기능과 컴포넌트 Pod | 실행 namespace·서비스 주소·MinIO 연결 |

`localhost`는 각 프로세스가 있는 환경 자신을 가리킨다. 학습 Pod가 PC의 포트 포워딩 주소로 서버를 찾게 하지 않는다. 다른 네임스페이스에서는 `mlflow.week02.svc.cluster.local:5000`처럼 서비스 주소를 명시한다.

## 2. 현재 확인한 구성

Docker Linux/aarch64, kind 클러스터 `mlops-lab`, kubectl context `kind-mlops-lab`, Ready 노드 1대에서 실습했다. 노드 Kubernetes 버전은 v1.37.0이다. 교재 환경과 버전이 같다고 가정하지 않고 실제 설치 버전을 기록한다.

```bash
k() { kubectl --context kind-mlops-lab -n week02 "$@"; }
kubectl --context kind-mlops-lab get nodes
k get deployment,service,job,pvc
```

MLflow Deployment는 서버 프로세스를 유지하고 Job은 학습을 한 번 실행한다. Job의 Complete는 종료 코드에 따른 작업 성공이며, 서버 Running은 프로세스 상태다. 서버 응답은 readiness와 `/health`, 학습 결과는 로그·산출물로 따로 확인한다.

## 3. 메타데이터와 파일 저장을 구분하기

| 종류 | 저장 위치·구성 | 역할 |
|---|---|---|
| 실행 메타데이터 | 서버 PVC의 SQLite | Run·지표·모델 버전의 조회 근거 |
| 모델·실험 파일 | 서버 PVC + HTTP artifact proxy | 모델·그래프·데이터 계약 |
| 학습 결과 파일 | mlflow-results PVC | 비교표·선택 모델 URI·예측 CSV |
| 피처 정의 | Feast Registry | Entity·FeatureView 메타데이터 |
| 피처 값 | Offline 이력 / Redis Online Store | 과거 기준 시각 / Entity별 최신 값 조회 |
| 파이프라인 파일 | MinIO · 클러스터 연결 설계 | 단계 간 Dataset·최종 결과 보관 |

현재 MLflow는 SQLite와 PVC를 사용하는 단일 서버 학습 환경이다. 후속 KFP 실습의 파일 저장소는 kind 안의 **MinIO**, Feast Online Store는 **Redis**로 구성한다. MinIO의 내부 Service 주소·bucket·접근 권한·보존 정책을 정하고 컴포넌트 Pod가 실제로 읽고 쓸 수 있는지 검사한다. 기존 MLflow 아티팩트는 현재 PVC에 유지하고, MinIO 설치·연결 결과는 실행 후 확인한다.

PVC는 네임스페이스에 속한다. KFP 컴포넌트가 다른 네임스페이스에서 실행되면 기존 PVC를 이름만으로 공유할 수 없다. 모델은 MLflow API로, 단계 간 파일은 MinIO 아티팩트 저장소로 전달한다.

## 4. 실습에서 확인한 저장·기동 이슈

`mlflow-results`는 처음 Pending이었다가 학습 Pod 생성 후 Bound가 됐다. StorageClass가 `WaitForFirstConsumer`였으므로 소비 Pod의 스케줄링과 연결해 확인했다. Pending이라는 상태만으로 저장소 장애로 판단하지 않는다.

MLflow 서버는 초기 OOMKilled를 확인한 뒤 기동 설정을 보완해 학습 Job을 완료했다. 설정 변경과 복구 후 관측은 [MLflow의 OOM 복구 기록](/ml-platform/mlflow-model-lifecycle)에 정리했다.

## 5. KFP와 Kubeflow의 설치 범위

Kubeflow Pipelines(KFP)는 작업의 순서·입출력·실행 이력을 관리하는 Kubeflow의 구성 요소다. 이 글에서 다루는 범위는 MLflow와 Feast를 연결하는 파이프라인이며, 노트북·인증 등 여러 기능을 함께 제공하는 전체 Kubeflow 플랫폼의 설치와는 구분한다.

참조하는 KFP standalone 구성에서는 Argo Workflows가 워크플로 실행을 담당하고, 각 컴포넌트는 Kubernetes Pod로 실행된다. 파이프라인의 작업 상태는 KFP에서 확인하고, 개별 Pod의 스케줄링·컨테이너 상태·이벤트는 kubectl로 확인한다.
