---
title: "17 · StatefulSet과 상태 저장"
outline: deep
prev:
  text: '16 · PV·PVC·StorageClass'
  link: '/ml-platform/week04-persistent-storage'
next:
  text: '18 · 디스크 복구와 Ephemeral Volume'
  link: '/ml-platform/week04-volume-recovery'
---


# 17 · StatefulSet과 상태 저장

교재 범위: *Machine Learning Platform Engineering* CH9.1~9.2 · Volumes, Persistent Volumes, Claims, Storage Classes, StatefulSet.

**질문:** Pod를 삭제해도 데이터를 유지하려면 무엇이 필요하고, Redis·MariaDB처럼 각 복제본이 다른 상태를 갖는 애플리케이션을 왜 Deployment만으로 구성하기 어려울까?

## 1. Pod 수명과 데이터 수명을 분리한다

~~~text
                 Kubernetes control plane
                           |
          StatefulSet controller → StatefulSet db
                           |
           ┌───────────────┴───────────────┐
       Pod db-0                         Pod db-1
          |                                |
      PVC data-db-0                   PVC data-db-1
          |                                |
         PV 0                             PV 1
          |                                |
      Storage backend                 Storage backend
~~~

Deployment와 StatefulSet 모두 PVC를 마운트할 수 있다. **차이는 StatefulSet이 각 ordinal Pod에 연결되는 안정적인 이름과 volumeClaimTemplates를 제공한다는 것**이다.

## 2. 볼륨 유형과 수명

| 저장 형태 | 생존 범위 | 추천 용도 |
|---|---|---|
| container writable layer | 컨테이너 재생성 때 잃을 수 있음 | 장기 데이터 저장 금지 |
| emptyDir | 동일 Pod의 컨테이너 재시작 동안 유지; Pod 제거 시 삭제 | 임시 캐시, scratch |
| ConfigMap volume | 설정 값의 파일화 | 설정 주입, 비밀 저장 용도 아님 |
| PVC/PV | Pod 수명과 분리된 영속 저장 | DB 데이터, 모델/메타데이터 |
| generic ephemeral volume | PVC처럼 드라이버 기능을 사용하되 Pod 수명과 함께 생성·삭제 | 임시 대용량 scratch |

노션의 emptyDir 설명 중 'Node 수명'보다 더 정확한 구분은 **Pod에 종속되는 데이터 수명**이다. Pod가 동일 Node에서 컨테이너만 재시작할 때는 유지되지만, Pod 자체가 교체되면 사라진다.

## 3. PV / PVC / StorageClass를 이해하기

- PersistentVolume(PV): 클러스터가 제공하는 저장소 리소스.
- PersistentVolumeClaim(PVC): 워크로드가 요청하는 용량·접근 모드.
- StorageClass: 프로비저닝 드라이버, reclaimPolicy, volumeBindingMode 등.
- CSI: 실제 저장 장치를 attach/mount/provision하는 표준 플러그인 인터페이스.

**접근 모드의 오해:** ReadWriteOnce(RWO)는 한 Node에 읽기·쓰기 마운트를 허용하는 방식이지 Pod 하나만 사용한다는 의미는 아니다. ReadWriteOncePod(RWOP)가 지원되는 환경에서는 단일 Pod 접근을 보장하도록 설정할 수 있다. RWX는 지원 드라이버에서 여러 Node 접근을 허용한다.

~~~yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: week04-shared-data
  namespace: week04
spec:
  accessModes:
  - ReadWriteOnce
  resources:
    requests:
      storage: 2Gi
~~~

기본 StorageClass가 없다면 명시적인 storageClassName 또는 사전 프로비저닝된 PV가 필요하다.

## 4. StatefulSet의 세 가지 핵심 속성

1. **안정적인 Pod 이름:** db-0, db-1처럼 ordinal에 따라 식별.
2. **안정적인 DNS 이름:** Headless Service와 결합해 db-0.db-headless.namespace.svc.cluster.local 같은 식별자 제공.
3. **각 Pod의 독립 PVC:** volumeClaimTemplates로 data-db-0, data-db-1 생성.

기본 OrderedReady 정책은 순차적인 생성·업데이트에 도움을 주지만, 이것만으로 leader election이나 데이터 복제가 완성되지 않는다. Redis/MariaDB의 리더 선출·복제·백업은 애플리케이션과 운영 계층에서 별도로 구현해야 한다.

## 5. StatefulSet 매니페스트와 운영 구조

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: demo-headless
  namespace: week04
spec:
  clusterIP: None
  selector:
    app: stateful-demo
  ports:
  - port: 80
    name: http
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: stateful-demo
  namespace: week04
spec:
  serviceName: demo-headless
  replicas: 2
  selector:
    matchLabels:
      app: stateful-demo
  template:
    metadata:
      labels:
        app: stateful-demo
    spec:
      containers:
      - name: app
        image: busybox:1.36
        command: ["sh", "-c", "while true; do date >> /data/events.log; sleep 15; done"]
        volumeMounts:
        - name: data
          mountPath: /data
  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 1Gi
~~~

~~~bash
kubectl create ns week04 --dry-run=client -o yaml | kubectl apply -f -
kubectl get storageclass
kubectl apply -f stateful-demo.yaml
kubectl -n week04 get pods,pvc -o wide
kubectl -n week04 exec stateful-demo-0 -- tail /data/events.log
kubectl -n week04 delete pod stateful-demo-0
kubectl -n week04 rollout status sts/stateful-demo
kubectl -n week04 exec stateful-demo-0 -- tail /data/events.log
~~~

확인 목적은 Pod 교체 전후에 같은 PVC가 다시 사용되는지, 파일이 남아 있는지를 관찰하는 것이다. 

## 6. StatefulSet과 Deployment를 혼동하지 않기

| 기준 | Deployment | StatefulSet |
|---|---|---|
| Pod 식별성 | 대체 가능한 replica | ordinal 기반 식별 |
| 스케일 | 일반적으로 동일 사양 replica | identity를 가진 replica |
| PVC | Pod spec에 정적 PVC 참조 가능 | volumeClaimTemplates로 개별 PVC 자동 생성 |
| 기동/업데이트 순서 | 롤링 전략 중심 | OrderedReady / Parallel 등 |
| 데이터 복제 | 애플리케이션 책임 | 역시 애플리케이션 책임 |

KFP Training Job은 보통 유한 실행 작업이고, MLflow tracking DB 등은 별도 상태 관리가 필요하다. 모든 MLOps 컴포넌트를 StatefulSet으로 만드는 것은 올바른 일반 규칙이 아니다.

## 7. 상태 저장이 곧 고가용성은 아니다

StatefulSet 3 replicas가 있어도 셋이 같은 zone에 놓이면 zone 장애에 취약하다. 또한 각 Pod의 영속 디스크가 독립적이라고 해서 DB 데이터가 자동으로 복제되는 것은 아니다. CH8의 topology spread와 CH9의 볼륨 특성을 함께 검토해야 한다.

**정리:** StatefulSet은 **안정적인 Pod 정체성 + 개별 영속 볼륨 연결**을 관리한다. DB의 복제, 일관성, 리더 선출은 별도의 문제다.

[4주차 학습 정리](/ml-platform/study-week-04)

참고: [StatefulSet](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/) · [Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/) · [Storage Classes](https://kubernetes.io/docs/concepts/storage/storage-classes/)
