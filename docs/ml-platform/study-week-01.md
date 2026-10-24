---
title: "Week 01 · ML Lifecycle에서 Kubernetes CI/CD까지"
description: "ML Lifecycle, MLOps, Kubernetes와 GitLab CI/CD를 연결하는 1주차 학습 정리"
date: 2026-10-25
outline: deep
---

# Week 01 · ML Lifecycle에서 Kubernetes CI/CD까지

**학습 범위:** CH1–3 · ML Lifecycle, MLOps 기초, Kubernetes CI/CD(GitLab)  
**스터디 일정:** 2026.10.18 · Machine Learning Platform Engineering Study

> CH1~3의 주요 주제를 바탕으로 ML Lifecycle, MLOps, Kubernetes CI/CD가 어떻게 이어지는지 정리했다. GitLab 파이프라인은 추가 조사한 **학습용 예시**이며, 실제 클러스터에서 실행·검증한 결과는 아니다.

## 1. 이번 주차에서 답하고 싶은 질문

| 주제 | 핵심 질문 | 상세 글 |
|---|---|---|
| ML Lifecycle | 모델을 만든 뒤 어떤 정보와 품질을 관리해야 하는가? | [01. 모델을 만들고 나서 시작되는 일들](/ml-platform/week-01) |
| MLOps | 코드뿐 아니라 데이터·모델 변경은 어떻게 검증하는가? | [02. 모델 학습에 CI/CD만 적용하면 충분할까?](/ml-platform/week-02) |
| Kubernetes | 모델을 어떤 단위로 패키징하고 안정적으로 실행하는가? | [03. ML 플랫폼을 설계할 때 먼저 정할 것들](/ml-platform/week-03) |

![ML 변경 관리와 릴리스 승인 흐름](/diagrams/ml-release-gates.svg)

## 2. 세 장을 하나의 흐름으로 연결하면

ML Lifecycle은 **무엇을 관리해야 하는지**, MLOps는 **변경을 어떤 기준으로 검증할지**, Kubernetes와 CI/CD는 **승인된 산출물을 어떻게 실행 환경에 전달할지**에 답한다.

1. 학습 데이터·피처 정의·모델·평가셋의 버전을 연결한다.
2. CI에서 코드 테스트와 데이터 계약을 검증한다.
3. CT가 필요하다면 후보 모델을 학습하고 기준 모델과 비교한다.
4. 승인된 이미지와 모델 아티팩트를 배포한다.
5. 운영에서 지연·오류·품질 변화를 관측하고 필요하면 롤백한다.

**CI 통과가 모델 품질 통과를 뜻하지 않고, Kubernetes의 Pod가 정상이라는 사실이 예측 정확도를 보장하지도 않는다.** 이 두 경계를 분리하는 것이 핵심이다.

## 3. 추가 학습 · GitLab CI/CD와 Kubernetes

기존 [MLOps 글](/ml-platform/week-02)은 GitHub Actions로 최소 데이터 검증을 설명했다. 1주차의 Kubernetes CI/CD 범위에 맞춰 **GitLab CI 파이프라인에서 무엇을 어디까지 자동화하는지**도 비교했다.

| 단계 | GitLab CI에서 하는 일 | 모델 플랫폼에서 추가로 필요한 판단 |
|---|---|---|
| Validate | 코드 테스트·입력 스키마 검증 | 피처 시점 정합성, 데이터 누수 |
| Build | 컨테이너 이미지 생성·레지스트리 푸시 | 모델 아티팩트와 이미지의 버전 호환성 |
| Evaluate (확장 단계) | 현재 예제에는 미구현 | 기준 모델 대비 회귀 여부와 업무 제약 |
| Deploy | 승인된 이미지의 Kubernetes 배포 | 롤백 조건, 리소스·보안·관측 정책 |

### GitLab CI 최소 구조 · 데이터 검증, 이미지 빌드, 수동 배포

아래 YAML은 **기존 Kubernetes Deployment가 준비되어 있고**, GitLab Container Registry를 사용할 수 있으며, Runner에서 Docker-in-Docker와 `kubectl` 실행이 가능하도록 구성한 환경을 전제로 한다. Kubernetes 인증 정보는 CI 변수로 주입해야 한다.

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
    name: bitnami/kubectl:1.31
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

**실행 전 준비할 것:** `validate_data.py`와 `train.csv`, `train.py`, `Dockerfile`, `ml-serving` Deployment, 레지스트리 접근 권한, `KUBE_CONTEXT`가 필요하다. Docker-in-Docker의 TLS 및 Runner 설정과 클러스터 접근 방식은 설치 환경에 따라 달라진다. 예시의 `kubectl` 이미지는 실제 사용 전 태그 가용성과 조직 정책을 확인해야 한다.

이 파이프라인은 **데이터 검증 → 모델 아티팩트 생성·이미지 빌드 → 수동 승인 배포**만 보여준다. CT·모델 평가 게이트는 구현하지 않았으며, 실서비스라면 배포 전에 평가 Job과 보안 검증을 추가해야 한다. 또한 GitOps를 선택한다면 `kubectl set image` 대신 선언형 배포 설정을 변경하고 동기화하는 방식이 더 적절할 수 있다.

## 4. 실무에 적용할 때 생각할 점

산업 시계열에서는 시간 분할을 했더라도 미래값이 파생 피처에 섞이거나, 학습 시점과 서빙 시점의 전처리가 달라질 수 있다. 따라서 **데이터 계약과 시점 정합성 검증을 분리**하는 편이 좋다.

RAG·Agent 시스템에서도 원리는 비슷하다. 코드 테스트가 통과하더라도 검색 품질이나 답변의 근거 충실성이 나빠질 수 있으므로, 서비스에 맞는 별도의 평가 게이트가 필요하다.

## 5. 정리

- **Lifecycle:** 데이터·모델·평가·운영의 연결을 추적한다.
- **MLOps:** 변경을 반복 가능하게 검증하고 승인한다.
- **Kubernetes CI/CD:** 검증된 산출물을 배포하고 상태를 관측한다.
- **주의:** 배포 자동화와 모델 품질 보증은 서로 다른 책임이다.

### 관련 심화 글

- [산업 AI 회귀 평가 — MAPE와 R²](/ml-platform/industrial-evaluation)
- [RAG·Agent 품질 평가](/ml-platform/evaluation-and-operations)

### 참고 자료

- [GitLab CI/CD 공식 문서](https://docs.gitlab.com/ci/)
- [GitLab Docker-in-Docker](https://docs.gitlab.com/ci/docker/using_docker-in-docker/)
- [Kubernetes Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
