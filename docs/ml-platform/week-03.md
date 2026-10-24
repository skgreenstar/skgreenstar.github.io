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

## 2. ML 플랫폼은 직접 구축할까, 관리형 서비스를 사용할까?

플랫폼 구축에서 먼저 정할 것은 제품명이 아니라 **직접 책임질 운영 범위**다. 직접 구축(Build)과 관리형 서비스 활용(Buy)은 양자택일보다 구성 요소별로 결정하는 문제에 가깝다.

| 판단 기준 | 직접 구축·운영 | 관리형 서비스 활용 |
|---|---|---|
| 초기 도입 | 아키텍처·운영 체계 설계에 시간 필요 | 상대적으로 빠르게 시작 가능 |
| 커스터마이징 | 네트워크·보안·워크플로 세밀한 제어 | 서비스가 제공하는 범위 내에서 조정 |
| 운영 책임 | 업그레이드·장애·용량 관리까지 부담 | 인프라 운영 부담 일부 위임 |
| 비용 구조 | 인력·운영비·유휴 자원까지 고려 | 사용량·요금·종속성 함께 고려 |
| 적합한 상황 | 특수한 제약, 높은 제어 요구, 충분한 운영 역량 | 빠른 도입, 표준적인 요구, 작은 플랫폼 팀 |

예를 들어 학습 실행 환경은 Kubernetes에서 운영하되 실험 추적은 관리형 서비스를 선택할 수 있다. 반대로 보안·망 분리 요구가 크면 아티팩트 저장과 배포 경로를 내부에서 관리해야 할 수 있다.

결국 **총소유비용(TCO), 데이터 반출 제약, 장애 대응 책임, 팀의 운영 역량**을 함께 비교해야 한다. 특정 서비스를 도입하는 것만으로 MLOps가 완성되지는 않는다.

## 3. Kubernetes는 무엇을 해결하고, 무엇을 해결하지 못할까?

Kubernetes는 컨테이너 실행, 스케일링, 장애 복구, 배포 전략을 지원한다. 그러나 학습 데이터의 품질이나 모델의 정확도를 검증해 주지는 않는다.

따라서 클러스터 구축과 ML 플랫폼 구축을 같은 일로 보지 않아야 한다.

- **실행:** 학습 Job과 추론 Deployment의 자원 요구사항은 다르다.
- **저장:** 모델 아티팩트와 데이터셋은 컨테이너 이미지와 별도 수명주기를 가진다.
- **배포:** 새 이미지가 정상 실행되어도 모델 품질은 별도로 검증해야 한다.
- **관측:** Pod 상태뿐 아니라 예측 결과와 업무 성공률까지 연결해야 한다.

## 4. 변경을 서비스까지 전달하는 경로

![ML 모델 서빙 구성 요소와 배포 흐름](/diagrams/ml-serving-architecture.svg)

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

## 5. 도구는 문제에 맞춰 선택한다

| 반복되는 문제 | 고려할 도구·접근 | 추가로 생기는 운영 부담 |
|---|---|---|
| 실험 조건 추적이 어렵다 | MLflow | 저장소·접근 권한·아티팩트 보존 |
| 학습·서빙 피처가 불일치한다 | Feast 등 | 온라인 저장소, 시점 정합성 |
| 파이프라인 의존성이 복잡하다 | Kubeflow Pipelines 등 | 클러스터·워크플로 유지보수 |
| 배포 상태가 일관되지 않다 | Argo CD 등 GitOps | 선언형 설정·권한·동기화 정책 |
| 요청별 실패 원인을 찾기 어렵다 | Metrics + Tracing | 로그 비용, 민감정보 처리 |

도구를 추가하면 기능뿐 아니라 운영 책임도 늘어난다. 작은 규모라면 간단한 CI 작업과 스케줄러만으로도 충분할 수 있다.

### 모델과 이미지의 호환성을 릴리스 단위로 묶기

모델 버전만 되돌려도 추론 코드가 새로운 입력 스키마를 요구한다면 롤백은 실패할 수 있다. 따라서 운영에서 되돌릴 단위는 **모델 파일 하나가 아니라 검증된 릴리스 묶음**이어야 한다.

```yaml [release-manifest.yaml]
release_id: quality-predictor-2026-10
model_version: quality-v12
dataset_snapshot: sensor-snapshot-202610
feature_schema_version: features-v3
serving_image: registry.example.com/ml/quality@sha256:<digest>
evaluation_report: eval-quality-v12
deployment_config: serving-config-v5
```

위 값은 릴리스 메타데이터의 구조를 보여주는 예시다. 실제로는 이미지 digest와 모델 체크섬을 확인하고, 스테이징 환경에서 해당 조합을 테스트한 뒤 승인한다. 장애가 발생하면 **마지막으로 승인된 조합 전체**를 기준으로 복구한다.

## 6. 정상 동작보다 먼저 점검할 실패 경로

플랫폼 구성도를 그릴 때는 정상 경로보다 **실패했을 때의 경로**를 먼저 확인하는 것이 도움이 된다.

1. 모델 아티팩트를 내려받지 못하면 서비스는 어떻게 동작하는가?
2. 배포 직후 오류율이 올라가면 어떤 기준으로 롤백하는가?
3. 추론 요청에 포함된 민감정보는 어디에 기록되고 언제 삭제되는가?
4. 특정 모델의 자원 사용량이 급증하면 다른 서비스에 영향을 주는가?
5. 모델과 추론 코드의 버전 호환성을 어떻게 검증하는가?

좋은 플랫폼은 구성 요소가 많아서가 아니라, **변경과 실패를 예측 가능한 방식으로 처리할 수 있어서** 가치가 있다.

### 산업 AI에서 모델 서빙과 제어를 구분하는 이유

제조 현장의 예측 모델은 **예측 결과를 보여주는 서비스**와 **설비 운전을 실제로 변경하는 제어 시스템**을 구분해야 한다. 모델의 예측값이 바로 제어 명령으로 이어지면, 예측 오차뿐 아니라 지연시간·센서 이상·물리적 제약 위반이 안전 문제로 확대될 수 있다.

따라서 플랫폼 아키텍처에는 모델 앞뒤의 책임 경계를 표시하는 편이 좋다.

```text [industrial-ai-flow]
Sensor / Historian
       |
Data validation + timestamp alignment
       |
Feature pipeline -> Versioned model
       |
Prediction + uncertainty / quality checks
       |
Business rules + operating constraints
       |
Operator review or approved control system
```

이 흐름은 개념적 구성이며, 실제 설비 제어는 별도의 안전 계층과 현장 승인 절차가 필요하다. **예측 API가 정상 응답한다는 사실은 제어에 사용해도 안전하다는 뜻이 아니다.**

## 7. 학습한 모델을 서빙하는 최소 구현

아키텍처 그림만 보면 각 구성 요소가 추상적으로 느껴질 수 있다. 아래는 **작은 예측 모델을 FastAPI로 서빙하고 Kubernetes에 배포하는 최소 구조**다. 학습·모델 로딩과 서빙을 구분하되, 인증과 모니터링 등 운영 기능은 별도로 설계해야 한다.

```text [project structure]
ml-serving/
├── app/
│   ├── main.py
│   └── model.json       # train.py 실행 시 생성
├── train.py
├── requirements.txt
├── Dockerfile
└── k8s/
    └── deployment.yaml
```

```python [app/main.py]
from pathlib import Path
import json
from fastapi import FastAPI
from pydantic import BaseModel

MODEL = json.loads((Path(__file__).parent / "model.json").read_text())
app = FastAPI()

class PredictRequest(BaseModel):
    temperature: float

@app.get("/health")
def health():
    return {"status": "ok", "model_version": MODEL["version"]}

@app.post("/predict")
def predict(request: PredictRequest):
    prediction = MODEL["weight"] * request.temperature + MODEL["bias"]
    return {"prediction": round(prediction, 3), "model_version": MODEL["version"]}
```

### 1단계 · 모델을 학습하고 아티팩트를 생성한다

아래는 합성 데이터로 선형 회귀 모델을 학습한 뒤, **추론에 필요한 계수와 버전만 JSON으로 저장**하는 최소 예시다. 실제 제조 데이터를 사용한 실험 결과는 아니다.

```python [train.py]
from pathlib import Path
import json
import numpy as np
from sklearn.linear_model import LinearRegression

x = np.array([0., 10., 20., 30.]).reshape(-1, 1)
y = np.array([2., 9.5, 17., 24.5])

model = LinearRegression().fit(x, y)
artifact = {
    "version": "demo-linear-v1",
    "weight": round(float(model.coef_[0]), 6),
    "bias": round(float(model.intercept_), 6),
}
Path("app/model.json").write_text(json.dumps(artifact, indent=2))
print(artifact)
```

```bash [terminal]
python -m pip install numpy scikit-learn
python train.py
```

```json [app/model.json]
{
  "version": "demo-linear-v1",
  "weight": 0.75,
  "bias": 2.0
}
```

이 데이터에서는 선형 관계가 정확하므로 위 계수가 나온다. 예제의 JSON은 **모델 아티팩트의 단순화된 표현**이다. 복잡한 모델이라면 검증된 직렬화 형식과 아티팩트 저장소, 체크섬 및 로딩 정책을 사용한다.

### 2단계 · API와 이미지를 준비한다

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
# train.py를 먼저 실행해 app/model.json을 생성한다.
docker build -t ml-serving:local .
docker run --rm -p 8080:8080 ml-serving:local
# 별도 터미널에서 확인
curl http://localhost:8080/health
curl -X POST http://localhost:8080/predict \
  -H "Content-Type: application/json" \
  -d '{"temperature": 20}'
```

```json [expected response]
{
  "prediction": 17.0,
  "model_version": "demo-linear-v1"
}
```

### 3단계 · 컨테이너와 추론 API를 확인한다

위 JSON은 `/predict` 호출의 예상 응답이다. `/health`는 `status`와 `model_version`을 반환한다.

### 4단계 · Kubernetes에 배포한다

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
          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              cpu: "500m"
              memory: "256Mi"
          readinessProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 3
            periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: ml-serving
spec:
  selector:
    app: ml-serving
  ports:
    - port: 80
      targetPort: 8080
  type: ClusterIP
```

`Service`는 Pod가 교체되어도 클러스터 내부에서 `ml-serving`이라는 이름으로 접근할 수 있게 한다. `ClusterIP`는 외부 인터넷에 서비스를 공개하지 않는다.

```bash [terminal]
# 아래 registry.example.com은 예시 주소다. 실제 레지스트리로 교체한다.
docker tag ml-serving:local registry.example.com/ml-serving:v1
docker push registry.example.com/ml-serving:v1
# Deployment의 image 주소도 같은 레지스트리 이미지로 설정한다.
kubectl apply -f k8s/deployment.yaml
kubectl rollout status deployment/ml-serving
kubectl get pods -l app=ml-serving
kubectl port-forward service/ml-serving 8081:80
# 다른 터미널: curl http://localhost:8081/health
```

이 예시에서 `registry.example.com`은 자리표시자다. 레지스트리 로그인과 이미지 Pull 권한이 사전에 필요하다. 위 YAML은 Service와 자원 요청·제한을 포함하지만, 실제 운영에는 보안 컨텍스트, 종료 처리, 네트워크 정책, 모델 아티팩트 무결성 검증 등을 추가로 검토해야 한다. `readinessProbe`는 요청 수신 가능 여부를 판단하며, `startupProbe`나 `livenessProbe`는 초기화 시간과 재시작 정책에 따라 선택한다.


---

**이전 글:** [모델 학습에 CI/CD만 적용하면 충분할까?](/ml-platform/week-02)  
**심화 글:** [산업 AI 회귀 평가](/ml-platform/industrial-evaluation) · [RAG·Agent 평가](/ml-platform/evaluation-and-operations)

### 참고 자료

- [Kubernetes Documentation](https://kubernetes.io/docs/home/)
- [Argo CD Documentation](https://argo-cd.readthedocs.io/en/stable/)
- [Kubeflow Documentation](https://www.kubeflow.org/docs/)
