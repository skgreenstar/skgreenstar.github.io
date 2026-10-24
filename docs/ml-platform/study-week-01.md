---
title: "Week 01 · ML Lifecycle에서 Kubernetes CI/CD까지"
description: "ML Lifecycle, MLOps, Kubernetes와 GitLab CI/CD를 연결하는 1주차 학습 정리"
date: 2026-10-25
outline: deep
---

# Week 01 · ML Lifecycle에서 Kubernetes CI/CD까지

**학습 범위:** CH1–3 · ML Lifecycle, MLOps 기초, Kubernetes CI/CD(GitLab)  
**스터디 일정:** 2026.10.18 · Machine Learning Platform Engineering Study

모델을 학습시키는 것과 그 모델을 안정적으로 운영하는 것은 다른 문제다. 이번 범위에서 가장 중요하게 본 부분은 **데이터와 모델의 변경 이력을 관리하고, 검증된 결과만 서비스에 반영하는 흐름**이다. ML Lifecycle에서 출발해 MLOps의 검증 절차를 거쳐 Kubernetes 배포까지 연결해 보았다.

## 1. 모델 개발과 운영 사이에 필요한 것들

| 주제 | 핵심 질문 | 상세 글 |
|---|---|---|
| ML Lifecycle | 모델을 만든 뒤 어떤 정보와 품질을 관리해야 하는가? | [01. 모델을 만들고 나서 시작되는 일들](/ml-platform/week-01) |
| MLOps | 코드뿐 아니라 데이터·모델 변경은 어떻게 검증하는가? | [02. 모델 학습에 CI/CD만 적용하면 충분할까?](/ml-platform/week-02) |
| Kubernetes | 모델을 어떤 단위로 패키징하고 안정적으로 실행하는가? | [03. ML 플랫폼을 설계할 때 먼저 정할 것들](/ml-platform/week-03) |

![ML 변경 관리와 릴리스 승인 흐름](/diagrams/ml-release-gates.svg)

교재 범위를 따라 추가로 확인한 주제도 있다. **ML Engineer에게 필요한 역량**은 [Lifecycle 글](/ml-platform/week-01)에서, **MLOps 성숙도 Level 0~2**는 [MLOps 글](/ml-platform/week-02)에서, **플랫폼 직접 구축과 관리형 서비스 선택 기준(Build vs. Buy)**은 [플랫폼 설계 글](/ml-platform/week-03)에서 정리했다.

## 2. Lifecycle부터 배포까지 연결하기

ML Lifecycle은 **무엇을 관리해야 하는지**, MLOps는 **변경을 어떤 기준으로 검증할지**, Kubernetes와 CI/CD는 **승인된 산출물을 어떻게 실행 환경에 전달할지**에 답한다.

1. 학습 데이터·피처 정의·모델·평가셋의 버전을 연결한다.
2. CI에서 코드 테스트와 데이터 계약을 검증한다.
3. CT가 필요하다면 후보 모델을 학습하고 기준 모델과 비교한다.
4. 승인된 이미지와 모델 아티팩트를 배포한다.
5. 운영에서 지연·오류·품질 변화를 관측하고 필요하면 롤백한다.

**CI 통과가 모델 품질 통과를 뜻하지 않고, Kubernetes의 Pod가 정상이라는 사실이 예측 정확도를 보장하지도 않는다.** 이 두 경계를 분리하는 것이 핵심이다.

### 한 번의 모델 변경을 끝까지 추적하려면

![ML 플랫폼의 데이터 계보, 평가, 배포와 운영 흐름](/diagrams/ml-platform-end-to-end.svg)

예를 들어 설비 온도로 품질을 예측하는 모델을 업데이트한다고 가정하자. **데이터를 다시 모았다는 사실만으로 모델을 다시 배포할 수는 없다.** 수집된 데이터가 어떤 전처리·피처 정의를 거쳤고, 어떤 평가를 통과했으며, 현재 어떤 이미지에서 실행 중인지 연결되어야 한다.

| 연결 지점 | 남겨야 할 근거 | 확인할 실패 조건 |
|---|---|---|
| 원천 데이터 → 학습셋 | 원천 버전, 수집 시각, 정제 규칙, 데이터셋 ID | 중복·결측·미래 정보 유입 |
| 학습셋 → 모델 | 코드 커밋, 피처 정의, 학습 설정, 실행 ID | 재현 불가, 학습·서빙 피처 차이 |
| 모델 → 평가 | 고정 평가셋, 기준 모델, 구간별 성능 | 평균 지표만 개선되고 중요 구간에서 악화 |
| 평가 → 배포 | 승인 기록, 모델 버전, 이미지 digest, 배포 설정 | 승인하지 않은 모델 또는 호환되지 않는 이미지 |
| 배포 → 운영 | 릴리스 ID, 오류율·지연·데이터 분포, 라벨 기반 품질 | Pod는 정상이지만 예측 성능 저하 |

모델 성능 저하를 발견했을 때 바로 재학습부터 시작하지 않고, **어느 연결 지점에서 변경이 발생했는지 역추적**할 수 있어야 한다. 이때 MLflow·Feast·Kubeflow 같은 도구는 각 문제를 해결하는 선택지이며, 도구 도입 자체가 목적은 아니다.

## 3. GitLab CI/CD로 연결하는 Kubernetes 배포

[MLOps의 변경 관리](/ml-platform/week-02)를 CI 파이프라인에 적용하면 어디까지 자동화할 수 있을까? GitLab CI를 기준으로 데이터 검증, 이미지 빌드, Kubernetes 배포를 나눠 보았다. 중요한 것은 자동화 범위 자체보다 **각 단계가 실패했을 때 다음 단계로 넘어가지 않도록 하는 것**이다.

| 단계 | GitLab CI에서 하는 일 | 모델 플랫폼에서 추가로 필요한 판단 |
|---|---|---|
| Validate | 필수 컬럼·결측치 검증 | 타입·값 범위·시점 정합성은 별도 검증 |
| Build | 컨테이너 이미지 생성·레지스트리 푸시 | 모델 아티팩트와 이미지의 버전 호환성 |
| Evaluate (확장 단계) | 현재 예제에는 미구현 | 기준 모델 대비 회귀 여부와 업무 제약 |
| Deploy | 수동 승인 후 Kubernetes 이미지 교체 | 롤백 조건, 리소스·보안·관측 정책 |

### GitLab CI 최소 구조 · 데이터 검증, 이미지 빌드, 수동 배포

아래는 단계를 이해하기 위한 최소 구성이다. 이미지 빌드에는 Docker-in-Docker가 가능한 Runner가 필요하고, 배포 Job에는 클러스터 접근 권한이 필요하다. 실제 파이프라인에서는 Runner 권한과 비밀정보 관리부터 확인해야 한다.

```yaml [.gitlab-ci.yml]
stages:
  - validate
  - build
  - deploy

variables:
  IMAGE_TAG: "$CI_REGISTRY_IMAGE:$CI_COMMIT_SHA"

validate:
  stage: validate
  image: python:3.12-slim
  script:
    - python -m pip install pandas
    - python validate_data.py

build:
  stage: build
  image: docker:27-cli
  services:
    - name: docker:27-dind
      alias: docker
  variables:
    DOCKER_HOST: tcp://docker:2376
    DOCKER_TLS_CERTDIR: "/certs"
    DOCKER_TLS_VERIFY: "1"
    DOCKER_CERT_PATH: "$DOCKER_TLS_CERTDIR/client"
  before_script:
    - apk add --no-cache python3 py3-pip
    - python3 -m venv /tmp/model-env
    - /tmp/model-env/bin/pip install numpy scikit-learn
    - /tmp/model-env/bin/python train.py
  script:
    - echo "$CI_REGISTRY_PASSWORD" | docker login "$CI_REGISTRY" -u "$CI_REGISTRY_USER" --password-stdin
    - docker build -t "$IMAGE_TAG" .
    - docker push "$IMAGE_TAG"

deploy:
  stage: deploy
  image:
    name: registry.example.com/ci/kubectl:1.31
    entrypoint: [""]
  rules:
    - if: '$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH'
      when: manual
    - when: never
  script:
    - kubectl config use-context "$KUBE_CONTEXT"
    - kubectl set image deployment/ml-serving api="$IMAGE_TAG"
    - kubectl rollout status deployment/ml-serving --timeout=180s
```

**구성 전 확인 사항:** `validate_data.py`, `train.csv`, `train.py`, `Dockerfile`과 기존 `ml-serving` Deployment가 필요하다. Docker-in-Docker용 Runner 설정, 레지스트리 인증, GitLab Agent 기반 Kubernetes 접근 및 `KUBE_CONTEXT` 설정도 환경에 맞게 준비해야 한다. `registry.example.com/ci/kubectl:1.31`은 조직에서 준비한 kubectl 실행 이미지의 자리표시자다. 실제 사용 가능한 이미지로 교체하고 CLI 호환성을 확인해야 한다.

여기서 **모델 아티팩트 생성은 예제의 빌드 과정**이지, 새로운 운영 데이터에 대한 CT 파이프라인은 아니다. 별도의 모델 평가·승인 절차 없이 운영에 반영하면 안 된다. 또한 위 방식은 명령형 배포이므로 GitOps를 도입했다면 `kubectl set image` 대신 Git에 선언된 이미지 태그를 변경하고 동기화하는 편이 일관적이다.

## 4. 운영 환경에서는 무엇을 더 검증해야 할까?

산업 시계열에서는 시간 분할을 했더라도 미래값이 파생 피처에 섞이거나, 학습 시점과 서빙 시점의 전처리가 달라질 수 있다. 따라서 **데이터 계약과 시점 정합성 검증을 분리**하는 편이 좋다.

RAG·Agent 시스템에서도 원리는 비슷하다. 코드 테스트가 통과하더라도 검색 품질이나 답변의 근거 충실성이 나빠질 수 있으므로, 서비스에 맞는 별도의 평가 게이트가 필요하다.

## 5. 이번 주차에서 정리한 기준

- **Lifecycle:** 데이터·모델·평가·운영의 연결을 추적한다.
- **MLOps:** 변경을 반복 가능하게 검증하고 승인한다.
- **Kubernetes CI/CD:** 검증된 산출물을 배포하고 상태를 관측한다.
- **주의:** 배포 자동화와 모델 품질 보증은 서로 다른 책임이다.

### 관련 심화 글

- [산업 AI 회귀 평가 — MAPE와 R²](/ml-platform/industrial-evaluation)
- [RAG·Agent 품질 평가](/ml-platform/evaluation-and-operations)

### 참고 자료

- [Machine Learning Platform Engineering · 공식 목차](https://www.manning.com/preview/machine-learning-platform-engineering/chapter-1)
- [GitLab CI/CD 공식 문서](https://docs.gitlab.com/ci/)
- [GitLab Docker-in-Docker](https://docs.gitlab.com/ci/docker/using_docker-in-docker/)
- [Kubernetes Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
