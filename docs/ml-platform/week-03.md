---
title: "ML 플랫폼을 설계할 때 먼저 정할 것들"
description: "Kubernetes 기반 ML 플랫폼의 책임 경계, 배포 흐름, 운영 복잡도"
date: 2026-10-25
outline: deep
---

# ML 플랫폼을 설계할 때 먼저 정할 것들

ML 플랫폼 아키텍처를 그리면 Kubernetes, Registry, Pipeline, Monitoring 같은 구성 요소가 먼저 눈에 들어온다. 하지만 도구를 연결하기 전에 답해야 할 질문이 있다. **누가 무엇을 책임지고, 어떤 변경을 안전하게 배포할 것인가?**

플랫폼은 기술 스택을 많이 쌓는 일이 아니라 반복되는 운영 문제를 공통 기능으로 해결하는 일에 가깝다.

## 1. 플랫폼의 책임 경계

플랫폼이 모든 모델의 특성을 알아야 할 필요는 없다. 대신 팀마다 반복해서 구현하는 부분을 표준화할 수 있다.

| 플랫폼이 공통으로 제공할 영역 | 모델·서비스 팀이 결정할 영역 |
|---|---|
| 실행 환경, 인증·권한, 로그 | 문제 정의와 데이터 의미 |
| 아티팩트 저장과 버전 추적 | 피처와 모델 선택 |
| 배포 자동화, 롤백 절차 | 평가셋과 업무별 성공 기준 |
| 자원 할당과 비용 관측 | 추론 품질 개선 |

공통화 범위를 넓히면 편리해지지만, 추상화가 깊어질수록 장애 원인을 찾기 어려워질 수 있다. 플랫폼이 제공할 **최소한의 공통 계약**부터 정하는 편이 안전하다.

## 2. Kubernetes는 무엇을 해결하고, 무엇을 해결하지 못할까?

Kubernetes는 컨테이너 실행, 스케일링, 장애 복구, 배포 전략을 지원한다. 그러나 학습 데이터의 품질이나 모델의 정확도를 검증해 주지는 않는다.

따라서 클러스터 구축과 ML 플랫폼 구축을 같은 일로 보지 않아야 한다.

- **실행:** 학습 Job과 추론 Deployment의 자원 요구사항은 다르다.
- **저장:** 모델 아티팩트와 데이터셋은 컨테이너 이미지와 별도 수명주기를 가진다.
- **배포:** 새 이미지가 정상 실행되어도 모델 품질은 별도로 검증해야 한다.
- **관측:** Pod 상태뿐 아니라 예측 결과와 업무 성공률까지 연결해야 한다.

## 3. 배포 흐름을 설계할 때

```text
Git change
   ↓
CI: test / build / scan
   ↓
Image Registry + Model Registry
   ↓
Staging: integration + evaluation
   ↓
Release approval
   ↓
GitOps desired state
   ↓
Kubernetes serving
   ↓
Tracing / metrics / rollback
```

GitOps는 Git에 기록된 원하는 상태와 실제 클러스터 상태를 비교하고 차이를 조정하는 방식이다. 다만 **GitOps가 모델 품질을 평가하는 것은 아니다.** 모델의 승인 여부는 별도의 평가·릴리스 정책으로 관리해야 한다.

## 4. 도구는 문제에 맞춰 선택한다

| 반복되는 문제 | 고려할 도구·접근 | 추가로 생기는 운영 부담 |
|---|---|---|
| 실험 조건 추적이 어렵다 | MLflow | 저장소·접근 권한·아티팩트 보존 |
| 학습·서빙 피처가 불일치한다 | Feast 등 | 온라인 저장소, 시점 정합성 |
| 파이프라인 의존성이 복잡하다 | Kubeflow Pipelines 등 | 클러스터·워크플로 유지보수 |
| 배포 상태가 일관되지 않다 | Argo CD 등 GitOps | 선언형 설정·권한·동기화 정책 |
| 요청별 실패 원인을 찾기 어렵다 | Metrics + Tracing | 로그 비용, 민감정보 처리 |

도구를 추가하면 기능뿐 아니라 운영 책임도 늘어난다. 작은 규모라면 간단한 CI 작업과 스케줄러만으로도 충분할 수 있다.

## 5. 실제 설계에서 놓치기 쉬운 것

플랫폼 구성도를 그릴 때는 정상 경로보다 **실패했을 때의 경로**를 먼저 확인하는 것이 도움이 된다.

1. 모델 아티팩트를 내려받지 못하면 서비스는 어떻게 동작하는가?
2. 배포 직후 오류율이 올라가면 어떤 기준으로 롤백하는가?
3. 추론 요청에 포함된 민감정보는 어디에 기록되고 언제 삭제되는가?
4. 특정 모델의 자원 사용량이 급증하면 다른 서비스에 영향을 주는가?
5. 모델과 추론 코드의 버전 호환성을 어떻게 검증하는가?

좋은 플랫폼은 구성 요소가 많아서가 아니라, **변경과 실패를 예측 가능한 방식으로 처리할 수 있어서** 가치가 있다.

## 작은 프로젝트로 배포 구조 살펴보기

아키텍처 그림만 보면 각 구성 요소가 추상적으로 느껴질 수 있다. 아래는 **FastAPI 앱을 컨테이너로 패키징하고 Kubernetes에 배포하는 최소 구조**다. 실제 ML 모델 로딩, 인증, 모니터링은 별도로 설계해야 한다.

```text [project structure]
ml-serving/
├── app/
│   └── main.py
├── requirements.txt
├── Dockerfile
└── k8s/
    └── deployment.yaml
```

```python [app/main.py]
from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}
```

```text [requirements.txt]
fastapi>=0.115,<1
uvicorn>=0.30,<1
```

```dockerfile [Dockerfile]
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

```bash [terminal]
docker build -t ml-serving:local .
docker run --rm -p 8080:8080 ml-serving:local
# 별도 터미널에서 확인
curl http://localhost:8080/health
```

```json [expected response]
{
  "status": "ok"
}
```

Kubernetes에서는 이미지를 클러스터가 접근할 수 있는 레지스트리에 푸시해야 한다. `ml-serving:local`은 로컬 Docker 테스트용 이름이다.

```yaml [k8s/deployment.yaml]
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ml-serving
spec:
  replicas: 2
  selector:
    matchLabels:
      app: ml-serving
  template:
    metadata:
      labels:
        app: ml-serving
    spec:
      containers:
        - name: api
          image: registry.example.com/ml-serving:v1
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 3
            periodSeconds: 10
```

```bash [terminal]
# 이미지 주소를 실제 접근 가능한 레지스트리로 바꾼 뒤 실행
kubectl apply -f k8s/deployment.yaml
kubectl rollout status deployment/ml-serving
kubectl get pods -l app=ml-serving
```

이 예시에서 `registry.example.com`은 자리표시자다. 운영 배포에는 이미지 인증, 리소스 제한, 보안 컨텍스트, 종료 처리, Service 및 네트워크 정책이 추가로 필요하다.


---

**이전 글:** [모델 학습에 CI/CD만 적용하면 충분할까?](/ml-platform/week-02)  
**심화 글:** [모델 성능 다음에 확인해야 할 것들 — 평가와 운영 설계](/ml-platform/evaluation-and-operations)

### 참고 자료

- [Kubernetes Documentation](https://kubernetes.io/docs/home/)
- [Argo CD Documentation](https://argo-cd.readthedocs.io/en/stable/)
- [Kubeflow Documentation](https://www.kubeflow.org/docs/)
