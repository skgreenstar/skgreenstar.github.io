---
title: "19 · 디스크와 Pod가 사라지면 데이터를 어떻게 복구할까?"
outline: deep
prev:
  text: '18 · StatefulSet'
  link: '/ml-platform/week04-statefulset'
next:
  text: '4주차 · 학습 정리'
  link: '/ml-platform/study-week-04'
---

# 19 · 디스크와 Pod가 사라지면 데이터를 어떻게 복구할까?

교재 범위: CH9.3 · Migrating and Recovering Disks / CH9.4 · Generic Ephemeral Volumes.

**질문:** Pod와 PVC를 삭제했을 때 디스크는 정말 남아 있을까? 그리고 데이터가 남아 있어도 어떻게 안전하게 새 PVC에 다시 연결할 수 있을까?

## 1. 네 가지 수명을 따로 구분한다

~~~text
Application container  ─ restart / replacement
       |
Pod                     ─ delete / recreate
       |
PVC                     ─ retain / delete
       |
PV + Storage backend    ─ reclaimPolicy + provider-specific lifecycle
~~~

**Pod를 삭제했다 = PVC가 삭제됐다 = 실제 디스크가 삭제됐다**는 등식은 성립하지 않는다. 반대로 PVC를 삭제해도 데이터가 항상 안전하게 유지되는 것도 아니다. 저장소 정책에 의해 실제 디스크가 제거될 수 있다.

## 2. reclaimPolicy는 어디에 적용될까?

| 정책 | PVC가 해제된 뒤 PV/실제 볼륨 처리 |
|---|---|
| Delete | 스토리지 제공자에 연결된 외부 볼륨까지 삭제될 수 있음 |
| Retain | PV와 데이터를 수동 회수·재연결하도록 보존 |
| Recycle | 현대 Kubernetes 운영에서는 사용하지 않는 구형 방식 |

동적 PV는 일반적으로 StorageClass의 reclaimPolicy 영향을 받는다. 이를 바꾸려면 실제 PV 정책도 확인해야 한다. **StorageClass 설정을 변경했다고 기존 PV 정책까지 자동 갱신된다고 가정하지 않는다.**

~~~bash
kubectl get storageclass
kubectl get pv -o custom-columns=NAME:.metadata.name,POLICY:.spec.persistentVolumeReclaimPolicy,STATUS:.status.phase,CLAIM:.spec.claimRef.name
kubectl -n week04 get pvc
kubectl describe pv <PV_NAME>
~~~

## 3. Retain 복구의 핵심은 데이터 훼손을 막는 것이다

대표적인 복구 시나리오는 기존 PVC와 Pod를 제거한 뒤, Retain 정책의 PV에 남아 있는 데이터를 새 PVC로 연결하는 것이다. 일반적인 흐름은 다음과 같다.

1. 실제 데이터의 백업과 PV 속성을 확인한다.
2. 데이터 쓰기를 멈추거나 애플리케이션을 안전하게 종료한다.
3. 기존 PVC가 삭제돼도 PV와 backing disk가 남는지 검증한다.
4. PV 상태가 Released로 바뀌었다면 이전 claimRef 등 재바인딩 조건을 확인한다.
5. 새 PVC의 volumeName, storageClassName, capacity, accessModes를 기존 PV와 일치시키도록 설계한다.
6. 새 Pod에서 파일 무결성과 읽기/쓰기를 검증한다.
7. 애플리케이션을 재기동하고 애플리케이션 수준 정합성을 확인한다.

~~~yaml
# 데이터 복구 실습용 템플릿 (즉시 적용하지 말 것)
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: restored-data
  namespace: week04
spec:
  storageClassName: ""
  volumeName: <EXISTING_PV_NAME>
  accessModes: ["ReadWriteOnce"]
  resources:
    requests:
      storage: 1Gi
~~~

이 예시는 **기존 PV를 정확히 알고 사전 정리한 경우에만** 적용 가능하다. 단순히 PVC 이름만 같게 만들어도 원래 데이터가 자동 복구되는 것은 아니다. 드라이버별 attach 제한과 volume node affinity, PV claimRef, 실제 disk 존재 여부도 확인해야 한다.

## 4. StatefulSet에서 특히 조심할 것

StatefulSet의 volumeClaimTemplates로 생성된 PVC는 StatefulSet이나 Pod 삭제만으로 자동으로 없어지지 않는 것이 일반적인 기본 동작이다. 하지만 PVC retention policy를 명시적으로 변경하거나 별도 삭제 명령을 수행하면 결과가 달라진다. 상태 저장 워크로드의 정리와 데이터 폐기는 별도 승인·백업 절차를 두어야 한다.

~~~bash
kubectl -n week04 get statefulset stateful-demo -o yaml
kubectl -n week04 get pvc -o wide
kubectl -n week04 get pods -o wide
~~~

Pod가 다른 Node에 재스케줄되더라도 PV의 zone/node affinity와 충돌하면 Pending 또는 Mount 실패가 발생할 수 있다. CH8의 스케줄링과 CH9의 상태 저장을 함께 다루는 이유다.

## 5. emptyDir와 Generic Ephemeral Volume의 차이

| 비교 | emptyDir | Generic Ephemeral Volume |
|---|---|---|
| 생성 | Pod의 volume spec | Pod의 volumeClaimTemplate |
| 저장 능력 | 보통 Node 로컬 임시 공간, memory medium 가능 | 지원 CSI/StorageClass 활용 가능 |
| 수명 | Pod와 함께 제거 | 해당 Pod와 연계된 ephemeral PVC 삭제 |
| 특징 | 간단하고 빠른 scratch | StorageClass 기능, 크기·성능·스냅샷 지원 가능 |
| 제한 | Node 공간 부족·Pod 삭제 시 유실 | 드라이버/스토리지 프로비저닝 지원 필요 |

### Generic Ephemeral Volume 예시

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: ephemeral-train-demo
  namespace: week04
spec:
  containers:
  - name: trainer
    image: busybox:1.36
    command: ["sh", "-c", "echo checkpoint > /scratch/checkpoint; sleep 3600"]
    volumeMounts:
    - name: scratch
      mountPath: /scratch
  volumes:
  - name: scratch
    ephemeral:
      volumeClaimTemplate:
        spec:
          accessModes: ["ReadWriteOnce"]
          resources:
            requests:
              storage: 1Gi
~~~

클러스터의 기본 StorageClass와 CSI 기능에 따라 예제 Pod가 Pending에 머물 수 있다. 임시 볼륨을 모델 최종 가중치 저장소로 사용하면 Pod 제거 시 가중치를 잃으므로, 중요한 아티팩트는 별도의 영속 저장소에 업로드해야 한다.

## 6. MLOps에서 선택할 저장 정책

| 데이터 | 적합한 접근 | 복구 관점 |
|---|---|---|
| 학습 중 임시 캐시 | emptyDir / generic ephemeral | 재생성 가능해야 함 |
| KFP 실행 산출물 | object storage의 버전별 artifact | Run/URI/Checksum 추적 |
| MLflow 메타데이터 DB | 영속 스토리지와 백업 | 스냅샷·복원·무결성 검증 |
| 모델 레지스트리 아티팩트 | 버전 지정된 영속 저장소 | 모델 버전·참조 경로 일치 |
| Stateful DB 복제본 | 독립 PVC + 애플리케이션 복제 | 디스크 복구와 DB 복구 구별 |

## 7. 장애 실험 기록 양식

실제 실습할 때 아래 정보를 남기면 성공/실패를 검증할 수 있다.

| 단계 | 측정할 항목 | 실제 결과 |
|---|---|---|
| 최초 기동 | Pod/PVC/PV 이름, volumeBindingMode | 미실행 |
| 파일 기록 | checksum 및 timestamp | 미실행 |
| Pod 삭제/재생성 | PVC 재연결 여부, checksum 비교 | 미실행 |
| PVC 삭제 | PV Phase, reclaimPolicy, backing storage | 미실행 |
| 재바인딩 | 새 PVC Bound, 파일 checksum 비교 | 미실행 |
| 임시 볼륨 삭제 | Pod/PVC 자원 정리 여부 | 미실행 |

**결론:** 영속 데이터의 핵심은 단순히 PVC를 붙이는 게 아니라 **어떤 객체가 삭제되어도 데이터가 남아야 하는지, 누가 복구 책임을 지는지**를 명확하게 정의하는 것이다.

[4주차 학습 정리](/ml-platform/study-week-04)

참고: [PV Reclaiming](https://kubernetes.io/docs/concepts/storage/persistent-volumes/#reclaiming) · [Generic Ephemeral Volumes](https://kubernetes.io/docs/concepts/storage/ephemeral-volumes/#generic-ephemeral-volumes) · [StatefulSet](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/)
