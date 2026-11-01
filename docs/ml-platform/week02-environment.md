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

PC에서는 소스를 내려받고 컨테이너 이미지를 빌드·적재하며 kubectl로 작업을 제어한다. MLflow 서버와 학습 코드는 kind 내부에서 실행한다. 이후 Feast 조회도 Job으로, KFP 컴포넌트도 Pod로 실행하는 흐름으로 연결한다.

| 위치 | 역할 | 접근 방법 |
|---|---|---|
| PC | 이미지 빌드·명령 실행·브라우저 확인 | Docker / kind / kubectl |
| week02 네임스페이스 | MLflow 서버·학습 Job·현재 운영 실습 | context와 namespace 명시 |
| MLflow Service | Pod 사이의 Tracking API | http://mlflow:5000 |
| PC 브라우저 | MLflow UI | port-forward 후 127.0.0.1:5050 |
| KFP 설치 영역 | 파이프라인 제어 기능과 작업 실행 | 설치 후 namespace·서비스 주소 확인 |

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

| 종류 | 현재 MLflow 실습 | 도구를 확장할 때의 역할 |
|---|---|---|
| 실행 메타데이터 | 서버 PVC의 SQLite | Run·지표·모델 버전의 조회 근거 |
| 모델·실험 파일 | 서버 PVC + HTTP artifact proxy | 모델·그래프·데이터 계약 |
| 학습 결과 파일 | mlflow-results PVC | 비교표·선택 모델 URI·예측 CSV |
| 피처 정의 | Feast 연결 단계에서 구성 | Registry에 Entity·FeatureView 등록 |
| 피처 값 | Offline / Online Store 연결 단계 | 과거 이력 / 최신 값 조회 |
| 파이프라인 파일 | KFP 연결 단계에서 구성 | 단계 간 Dataset·최종 결과 보관 |

현재 MLflow는 SQLite와 PVC를 사용하는 단일 서버 학습 환경이다. PostgreSQL·S3 호환 스토리지·Redis가 이미 설치된 구성으로 기술하지 않는다. 확장 시에는 저장소 endpoint, bucket, 접근 권한, 보존 정책을 정하고 Job/Pod가 실제로 읽고 쓸 수 있는지 검사한다. S3 호환 저장소의 제품 이름보다 API 호환성과 연결 설정이 핵심이다.

PVC는 네임스페이스에 속한다. KFP 컴포넌트가 다른 네임스페이스에서 실행되면 기존 PVC를 이름만으로 공유할 수 없다. 모델은 MLflow API로, 단계 간 파일은 해당 환경의 아티팩트 저장소로 전달한다.

## 4. 실습에서 확인한 저장·기동 이슈

`mlflow-results`는 처음 Pending이었다가 학습 Pod 생성 후 Bound가 됐다. StorageClass가 `WaitForFirstConsumer`였으므로 소비 Pod의 스케줄링과 연결해 확인했다. Pending이라는 상태만으로 저장소 장애로 판단하지 않는다.

MLflow 서버는 초기 OOMKilled 후 메모리 limit 2Gi와 불필요한 내장 Job 실행기 비활성화를 함께 적용했다. 복구 후 health 200 세 번과 약 355MiB 메모리, 재시작 0을 확인했고 학습 Job도 완료했다. 상세 로그는 [MLflow 실행 기록](/ml-platform/mlflow-model-lifecycle)에 남겼다.

## 5. 교재의 환경 도구와 우리 환경의 대응

교재 보조 도구의 check/up/status/forward는 점검·설치·상태·접속 단계를 묶어주는 편의 기능이다. 우리 환경은 이미 실습 중인 kind 클러스터를 유지하면서 같은 역할을 kubectl과 명시적 YAML로 수행한다. 기존 클러스터를 새 교재 환경으로 초기화할 필요는 없다.

KFP 단독 설치와 전체 Kubeflow 설치는 범위가 다르다. GitOps 배포 동기화에 쓰는 Argo CD와 워크플로 실행에 쓰는 Argo Workflows도 역할이 다르다. 설치되는 구성 요소·버전과 실행 namespace를 확인한 후 연결한다.
