---
title: "16 · PVC와 StorageClass가 데이터 수명을 어떻게 결정할까?"
outline: deep
prev: { text: '15 · Pending 진단', link: '/ml-platform/week04-storage' }
next: { text: '17 · StatefulSet', link: '/ml-platform/week04-placement' }
---

# 16 · PVC와 StorageClass가 데이터 수명을 어떻게 결정할까?

CH9.1 Volumes, Persistent Volumes, Claims and StorageClasses

Pod에 파일을 기록했다는 것과 Pod가 교체된 뒤에도 파일을 읽을 수 있다는 것은 다르다. **어디에 저장했는지, 저장소가 누구의 수명주기를 따르는지**를 먼저 알아야 한다.

## 1. 컨테이너와 볼륨의 수명

~~~text
container writable layer → 컨테이너 교체에 취약
emptyDir                 → 동일 Pod의 컨테이너 재시작 동안 유지
                           Pod 삭제 시 제거
PVC → PV → Disk          → Pod 수명과 별도 관리
Object Storage           → Pod 외부의 버전된 데이터/모델 아티팩트
~~~

| 저장소 | 주요 용도 | 주의 |
|---|---|---|
| emptyDir | 임시 데이터·컨테이너 간 파일 공유 | Pod 제거 시 삭제 |
| ConfigMap | 설정 파일 주입 | 상태 데이터 저장용이 아님 |
| Secret | 비밀 설정 주입 | 권한·회전 필요 |
| PVC | 데이터베이스·모델 캐시 | 바인딩, 접근 모드, Zone |
| Generic Ephemeral | StorageClass로 만드는 일시적 볼륨 | Pod 수명과 함께 정리 |

## 2. PV / PVC / StorageClass

~~~text
Pod volumeMount
      |
      v
PVC (저장소 요청)
      |
      v
PV (클러스터 저장소)
      |
      v
CSI Driver / Disk
~~~

PV는 클러스터에서 제공하는 영속 볼륨 리소스, PVC는 용량·접근 모드 등에 대한 워크로드의 요청이다. StorageClass는 동적 프로비저닝 정책을 제공하며 CSI는 실제 스토리지 제공자를 연결한다.

~~~yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: mlflow-data
  namespace: week04
spec:
  accessModes:
  - ReadWriteOnce
  resources:
    requests:
      storage: 2Gi
~~~

기본 StorageClass가 없다면 PVC가 Pending일 수 있으므로 실제 클러스터의 StorageClass를 먼저 확인한다.

## 3. 접근 모드의 오해

| Mode | 의미 | 오해하지 말 것 |
|---|---|---|
| RWO | 한 Node에서 Read/Write 마운트 | Pod 하나만이라는 뜻은 아님 |
| RWOP | 지원 환경에서 단일 Pod 접근 | CSI 드라이버 조건 확인 |
| RWX | 여러 Node의 Read/Write | 드라이버가 지원해야 함 |
| ROX | 여러 Node의 ReadOnly | 쓰기 공유 아님 |

동일한 RWO PVC를 여러 Node의 학습 Job이 사용하려 하면 Multi-Attach 제한이 발생할 수 있다.

## 4. Binding의 시간: Immediate vs WaitForFirstConsumer

**Immediate**는 PVC 요청 이후 즉시 프로비저닝·바인딩할 수 있다. 반면 **WaitForFirstConsumer**는 첫 Pod의 리소스·배치 조건과 볼륨 토폴로지를 함께 고려할 수 있도록 바인딩을 늦춘다.

이 차이는 Scheduler의 Node Affinity와 맞물린다. 이미 특정 Zone에 있는 PV를 Pod가 다른 Zone에서 사용하도록 강제하면 Pod가 Pending될 수 있다.

## 5. ReclaimPolicy는 데이터 보존 약속이 아니다

| 설정 | PVC 해제 후 |
|---|---|
| Delete | 연결된 PV와 실제 볼륨이 삭제될 수 있음 |
| Retain | 수동 복구·재연결을 위해 저장소 유지 |

동적 PV는 StorageClass의 reclaimPolicy가 반영되지만, 나중에 StorageClass를 바꾼다고 기존 PV 값까지 자동으로 바뀌는 것은 아니다. 실제 PV의 spec을 확인해야 한다.

~~~bash
kubectl get storageclass -o wide
kubectl -n week04 get pvc
kubectl -n week04 describe pvc mlflow-data
kubectl get pv -o wide
~~~

## 6. Single-Pod Stateful Workload: Recreate 전략

한 DB Pod가 RWO PVC를 사용한다면 RollingUpdate 중 old/new Pod의 볼륨 사용이 겹칠 수 있다. Deployment의 Recreate 전략은 old Pod를 먼저 제거한 뒤 new Pod를 생성하도록 해 겹침을 줄인다.

~~~yaml
spec:
  strategy:
    type: Recreate
~~~

대신 일시적인 중단이 발생할 수 있다. Recreate는 무중단 보장도 백업도 아니다.

## 7. MLOps 적용

- Preprocessing scratch: emptyDir 또는 ephemeral.
- 반복 사용 데이터 캐시: PVC, 필요 시 shared storage.
- MLflow backend DB: PVC와 별도의 DB 백업·복원.
- KFP artifact: 실행 ID와 데이터/모델 URI를 추적할 수 있는 영속 저장소.
- 배포 가중치: 불변 모델 버전과 체크섬으로 검증.

**결론:** PVC가 있다고 복구가 완성되는 것이 아니다. 접근 모드, Binding, PV 보존 정책과 백업 전략까지 연결해야 한다.

[4주차 학습 정리](/ml-platform/study-week-04)

참고: [Volumes](https://kubernetes.io/docs/concepts/storage/volumes/) · [PersistentVolumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/) · [StorageClass](https://kubernetes.io/docs/concepts/storage/storage-classes/)
