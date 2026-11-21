---
title: "22 · 구성과 Secret의 운영 경계"
outline: deep
prev:
  text: '21 · GitOps와 모델 승격'
  link: '/ml-platform/week05-gitops'
next:
  text: 'ML Platform 개요'
  link: '/ml-platform/'
---

# 22 · Namespace와 Secret만 분리하면 안전할까?

CH11 GitOps: Configuration as Code · Namespace / ConfigMap / Secret

## 1. 분리해야 할 것은 이름만이 아니다

Namespace는 리소스를 구분하는 논리적 범위다. 그러나 Namespace를 분리한다고 네트워크 트래픽과 클러스터 관리 권한까지 자동 격리되지는 않는다.

| 구분 | 역할 | 추가 제어 |
|---|---|---|
| Namespace | 리소스 이름·운영 공간 | RBAC, ResourceQuota |
| ConfigMap | 비민감 설정 | 배포 버전 관리 |
| Secret | 자격증명 등의 API 객체 | RBAC, etcd 암호화, 회전 |
| NetworkPolicy | 트래픽 제한 | 지원 CNI 확인 |
| Cluster 분리 | 강한 운영·장애 경계 | 관리 비용·인프라 분리 |

개발과 운영이 같은 클러스터일 때 실수로 운영 리소스를 수정하지 않도록 context와 namespace를 명시하고, prod 변경은 별도 승인 경로를 사용한다. 보안·규제·장애 범위가 다르면 별도 클러스터도 고려한다.

## 2. 구성 주입의 경계

~~~mermaid
flowchart LR
    A["GitOps Repo"] --> B["ConfigMap / Deployment"]
    C["Secret Manager"] --> D["Secret sync / CSI"]
    B --> E["Pod"]
    D --> E
    E --> F["Training / Inference"]
    G["RBAC / Admission Policy"] --> E
~~~

ConfigMap과 Secret을 환경변수로 주입하면 업데이트가 기존 프로세스에 자동 반영되지 않는다. 볼륨으로 마운트한 값은 조건에 따라 갱신될 수 있으나 `subPath` 마운트에는 자동 업데이트가 반영되지 않는다. 애플리케이션 재로딩 또는 롤아웃 전략을 결정해야 한다.

## 보안 아키텍처 · 설정·권한·네트워크를 따로 설계

~~~mermaid
flowchart TB
  USER["개발자 / CI"] --> POLICY["PR 승인·Policy as Code"]
  POLICY --> GIT[("Git · 비민감 설정/참조")]
  GIT --> OP["GitOps Controller"]
  KEY[("Secret Manager / KMS")] --> SYNC["Secret Sync / CSI"]
  subgraph CLUSTER["Kubernetes Cluster"]
    subgraph DEV["Namespace: mlops-dev"]
      DCFG["Dev ConfigMap"]
      DWORK["Dev Workload"]
      DCFG --> DWORK
    end
    subgraph PROD["Namespace: mlops-prod"]
      PCFG["Prod ConfigMap"]
      PSEC["Prod Secret"]
      PWORK["Prod Inference"]
      PCFG --> PWORK
      PSEC --> PWORK
    end
    RBAC["RBAC / Admission"]
    NET["NetworkPolicy · CNI 지원 필요"]
  end
  OP --> DCFG
  OP --> PCFG
  SYNC --> PSEC
  RBAC --> PWORK
  NET --> PWORK
~~~

Namespace 분리는 네트워크·보안 경계를 자동 형성하지 않는다. 동일 클러스터의 관리자 권한은 Namespace를 넘어 작동할 수 있으므로 신뢰 수준이 다르면 클러스터·계정 분리까지 검토한다.

### Secret 회전 시 설정 반영 경로

~~~mermaid
sequenceDiagram
  participant M as Secret Manager
  participant S as Secret Sync
  participant K as K8s Secret / Volume
  participant P as Application Pod
  M->>S: 새 버전 발행
  S->>K: Secret 동기화
  alt 환경 변수 주입
    Note over P: 기존 프로세스의 값은 자동 변경되지 않음
    K-->>P: 명시적 rollout/restart 필요
  else 일반 Secret 볼륨 마운트
    K-->>P: 전파 지연 후 파일 갱신 가능
    Note over P: 앱에서 다시 읽거나 재시작해야 사용
  end
  Note over K,P: subPath 마운트는 자동 갱신되지 않음
~~~


## 3. 설정 예제

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: trainer-config
  namespace: mlops-dev
data:
  LOG_LEVEL: "INFO"
  MODEL_NAME: "price-model"
---
apiVersion: v1
kind: Secret
metadata:
  name: mlflow-credentials
  namespace: mlops-dev
type: Opaque
stringData:
  MLFLOW_TRACKING_TOKEN: "REPLACE_ME"
~~~

이 Secret 예시는 로컬 학습용 형태다. 실제 토큰을 Git에 평문으로 커밋하지 않는다. Kubernetes Secret은 기본적으로 단지 base64 인코딩된 데이터를 저장하므로 **Secret이라는 이름만으로 충분한 암호화·접근 통제가 제공되지 않는다.**

운영에서는 외부 Secret Manager + CSI/동기화, SOPS 암호화 GitOps, Sealed Secrets 등 중 조직의 키 관리·회전·감사 요구에 맞는 방법을 택한다.

## 4. 배포 실수 방지 체크

~~~bash
kubectl config current-context
kubectl config get-contexts
kubectl auth can-i create deployments -n mlops-prod
kubectl get resourcequota -n mlops-prod
kubectl get networkpolicy -n mlops-prod
kubectl diff -f deployment.yaml -n mlops-dev
~~~

- `kubectl` 기본 namespace를 믿지 않고 대상 환경을 명시한다.
- prod write 권한은 최소 인원과 CI/GitOps ServiceAccount에만 부여한다.
- `kubectl diff`, Policy-as-Code, PR 리뷰를 통과한 설정만 반영한다.
- Secret의 내용이 터미널 로그·CI 로그·에러 메시지에 노출되지 않도록 한다.
- 데이터 백업, 모델 파일, 메타데이터 DB의 자격증명과 권한을 구분한다.

## 5. Immutable ConfigMap/Secret

`immutable: true`는 기존 객체의 `data` 변경을 막는다. 변경하려면 새 이름으로 교체하는 패턴이 안전하며, 객체 삭제·재생성의 영향은 의존 Pod와 배포 정책을 고려해야 한다. Immutable은 권한 없는 읽기를 막는 보안 기능이 아니다.

## 6. Namespace와 Cluster 분리 기준

| 상황 | 우선 고려 |
|---|---|
| 개인 로컬 kind 실습 | Namespace 구분 |
| 동일 신뢰 수준의 dev/test | Namespace + RBAC/Quota |
| 보안 통제가 다른 prod | 별도 Cluster 검토 |
| GPU 고비용 워크로드 | Quota·NodePool·권한 분리 |
| 민감 데이터/규제 분리 | Cluster·계정·네트워크·키 분리 |

보안 경계는 조직 환경에 따라 달라진다. Namespace는 관리 편의를 주지만 모든 위험을 격리하는 단위로 간주하지 않는다.

## 7. 결론

**ConfigMap은 구성, Secret은 민감정보 객체, Namespace는 논리적 운영 범위다.** 안전한 ML 플랫폼은 세 기능에 RBAC·네트워크·키 관리·승인 정책을 더해 완성한다.

[5주차 학습 정리](/ml-platform/study-week-05)

참고: [Namespaces](https://kubernetes.io/docs/concepts/overview/working-with-objects/namespaces/) · [ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/) · [Secrets](https://kubernetes.io/docs/concepts/configuration/secret/) · [RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)
