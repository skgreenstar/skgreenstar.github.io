---
title: "20 · Scheduler와 StatefulSet을 끝까지 검증하는 실습"
outline: deep
prev:
  text: '19 · 디스크 복구'
  link: '/ml-platform/week04-recovery'
next:
  text: '4주차 · 학습 정리'
  link: '/ml-platform/study-week-04'
---

# 20 · Scheduler와 StatefulSet을 끝까지 검증하는 실습

이번 페이지의 목적은 기능을 무작정 적용하는 것이 아니라 **가설을 세우고, 실패를 의도적으로 만들고, Kubernetes의 근거로 설명하는 것**이다.

실습 환경: Mac Apple Silicon + kind + kubectl. 기존 1~3주차와 같은 로컬 환경을 사용한다. 아래 절차는 **검증 설계**이며 실제 클러스터 결과를 확보했다는 의미가 아니다.

## 1. 세 가지 질문

1. Node를 선택하는 필수 조건과 선호 조건이 충돌하면 어떤 조건이 우선될까?
2. replica를 늘리면 언제나 고가용성이 올라갈까?
3. StatefulSet Pod를 지웠다가 다시 만들어도 파일이 유지될까?

각 질문에 대해 **준비 → 조작 → Kubernetes 이벤트 → 해석 → 되돌리기** 순서로 관찰한다.

## 2. 실험에 앞서 Node 조건 확인

~~~bash
kind get clusters
kubectl config current-context
kubectl get nodes -o wide
kubectl get nodes -L kubernetes.io/arch,topology.kubernetes.io/zone
kubectl get sc
kubectl create namespace week04 --dry-run=client -o yaml | kubectl apply -f -
~~~

여기서 필요한 점검 사항:
- 실습할 worker Node가 최소 2개인지 확인한다. 하나뿐이면 anti-affinity 실험의 비교가 제한된다.
- 기본 StorageClass가 있는지 확인한다. kind의 local-path 계열 볼륨은 실제 클라우드 EBS/EFS와 복구 특성이 다르다.
- 강제적인 taint는 운영 클러스터가 아닌 로컬 테스트 Node에만 부여한다.

## 3. 실험 A · required와 preferred

**가설 A1:** 모든 worker에 workload=ml 레이블이 없다면, 필수 nodeAffinity가 있는 Pod는 Pending이어야 한다.

~~~yaml
# scheduling-demo.yaml
apiVersion: v1
kind: Pod
metadata:
  name: scheduling-demo
  namespace: week04
spec:
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
        - matchExpressions:
          - key: workload
            operator: In
            values: ["ml"]
      preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        preference:
          matchExpressions:
          - key: speed
            operator: In
            values: ["fast"]
  containers:
  - name: worker
    image: busybox:1.36
    command: ["sh", "-c", "sleep 3600"]
    resources:
      requests:
        cpu: "100m"
        memory: "64Mi"
~~~

~~~bash
kubectl apply -f scheduling-demo.yaml
kubectl -n week04 get pod scheduling-demo -o wide
kubectl -n week04 describe pod scheduling-demo

# 실제 노드 이름을 먼저 조회
kubectl get nodes
# 하나의 테스트 worker에만 필수 레이블을 부여
kubectl label node <WORKER_NODE_NAME> workload=ml --overwrite
kubectl -n week04 get pod scheduling-demo -o wide
~~~

**해석:** 레이블이 없는 동안 FailedScheduling 이벤트가 나오고, 필수 레이블을 추가한 뒤 Pod가 스케줄되면 required 조건의 효과를 설명할 수 있다. speed=fast 레이블이 없어도 다른 Node 제약과 자원이 맞으면 배치될 수 있다.

주의: Pod가 한 번 Bind된 뒤 preferred 값을 변경해도 기존 Pod가 자동 재배치되지는 않는다. 배치 비교를 하려면 Pod를 다시 생성한다.

## 4. 실험 B · Hard Anti-Affinity와 Replica 증가

**가설 B1:** worker가 2개인데 replica 3개가 같은 Node에 배치되는 것을 금지하면 1개는 Pending일 수 있다.

~~~yaml
# spread-demo.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: spread-demo
  namespace: week04
spec:
  replicas: 3
  selector:
    matchLabels:
      app: spread-demo
  template:
    metadata:
      labels:
        app: spread-demo
    spec:
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
          - labelSelector:
              matchLabels:
                app: spread-demo
            topologyKey: kubernetes.io/hostname
      containers:
      - name: sample
        image: nginx:alpine
        resources:
          requests:
            cpu: 100m
            memory: 64Mi
~~~

~~~bash
kubectl apply -f spread-demo.yaml
kubectl -n week04 get pods -l app=spread-demo -o wide
kubectl -n week04 get events --sort-by=.lastTimestamp
kubectl -n week04 describe deployment spread-demo
~~~

*실험 설계의 한계:* 3개 이상 worker가 있는 기존 클러스터라면 이 가설은 실패할 수 있다. 이때는 replica를 **worker 수 + 1**로 바꾸거나 eligible Node를 2개로 제한해야 한다. 실제 Node 수를 무시한 채 결과를 만들어 넣지 않는다.

## 5. 실험 C · StatefulSet 재시작과 데이터 보존

**가설 C1:** StatefulSet Pod만 삭제하면 volumeClaimTemplates에서 생성한 동일 PVC를 다시 사용하고 파일을 보존한다.

~~~yaml
# stateful-demo.yaml
apiVersion: v1
kind: Service
metadata:
  name: stateful-demo
  namespace: week04
spec:
  clusterIP: None
  selector:
    app: stateful-demo
  ports:
  - name: http
    port: 80
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: stateful-demo
  namespace: week04
spec:
  serviceName: stateful-demo
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
        command: ["sh", "-c", "sleep 36000"]
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
kubectl apply -f stateful-demo.yaml
kubectl -n week04 rollout status sts/stateful-demo --timeout=180s
kubectl -n week04 get pod,pvc,pv -o wide

kubectl -n week04 exec stateful-demo-0 -- sh -c 'echo "week04-stable-data" > /data/proof.txt; sha256sum /data/proof.txt'
kubectl -n week04 delete pod stateful-demo-0
kubectl -n week04 rollout status sts/stateful-demo --timeout=180s
kubectl -n week04 exec stateful-demo-0 -- sh -c 'cat /data/proof.txt; sha256sum /data/proof.txt'
kubectl -n week04 get pvc -o wide
~~~

**반증 가능성:** PVC가 Pending이면 StorageClass/프로비저너부터 점검한다. Pod가 새로 생성됐는데 파일이 유실됐다면 새 PVC를 사용했는지, 실제 volumeMount와 이전 PV가 같은지 확인한다. 볼륨 보존은 데이터베이스 복제·백업이 자동 제공된다는 뜻이 아니다.

## 6. 실험 D · 리소스 문제인지 스토리지 문제인지?

~~~bash
kubectl -n week04 describe pod <PENDING_POD_NAME>
kubectl -n week04 get events --sort-by=.lastTimestamp
kubectl -n week04 get pvc
kubectl get pv
kubectl get storageclass -o wide
kubectl describe node <WORKER_NODE_NAME>
~~~

| Kubernetes 메시지 | 우선 의심하는 계층 | 다음 조사 |
|---|---|---|
| Insufficient cpu | Scheduler NodeResourcesFit | requests·Allocatable |
| didn't match Pod's node affinity/selector | Scheduler NodeAffinity | Node labels, required |
| untolerated taint | Scheduler TaintToleration | Taint와 Toleration |
| unbound immediate PersistentVolumeClaims | PV/StorageClass | PVC 상태, provisioner |
| FailedMount | kubelet·CSI | 볼륨 이벤트, CSI logs |
| ImagePullBackOff | image registry | 이미지 이름·아키텍처·권한 |

**주의:** Pending인 모든 Pod가 스케줄링되지 않은 것은 아니다. PodScheduled=True인데 볼륨 마운트나 이미지 다운로드가 진행되지 않아 Pending일 수 있다. Pod conditions와 Events를 반드시 함께 읽는다.

## 7. 기록 양식: 이 표를 채워야 실습한 글이 된다

| 실험 | 가설 | 실행 명령 | 실제 Pod 상태/이벤트 | 결과 해석 |
|---|---|---|---|---|
| A1 | required mismatch → Pending | describe pod | 미실행 | 추후 기록 |
| A2 | label 부여 → scheduling | label node | 미실행 | 추후 기록 |
| B1 | hard anti-affinity → 일부 Pending | get pods -o wide | 미실행 | 추후 기록 |
| C1 | Pod 교체 후 데이터 유지 | sha256sum | 미실행 | 추후 기록 |
| D1 | PVC 문제 vs Node 문제 분리 | describe pvc / pod | 미실행 | 추후 기록 |

실험의 목적은 모든 예상값이 맞는 모습을 만드는 것이 아니다. 실제 결과가 다르면 조건, 버전, 사용 Node 수를 확인해 **왜 다른지 분석**한다.

## 8. 실험 후 정리

~~~bash
kubectl -n week04 delete deploy spread-demo --ignore-not-found
kubectl -n week04 delete pod scheduling-demo --ignore-not-found
# StatefulSet / PVC는 데이터 보존 확인 뒤에만 삭제
kubectl -n week04 delete sts stateful-demo --ignore-not-found
kubectl -n week04 get pvc
# PVC 삭제는 백업/보존 정책 점검 후 명시적으로 수행
kubectl label node <WORKER_NODE_NAME> workload-
~~~

PVC는 StorageClass의 reclaimPolicy가 Delete이면 삭제 시 backing data가 제거될 수 있다. 따라서 학습용 Pod 정리와 데이터 폐기는 다른 작업으로 다룬다.

## 9. 1~3주차를 실제로 이어 붙이는 법

- 2주차 KFP Job이 Pending이면 모델을 다시 학습시키기 전에 Node affinity, resource requests, PVC 바인딩을 확인한다.
- 3주차 HPA Desired replicas가 늘었는데 Ready replicas가 그대로라면 Scheduler 이벤트와 Pod readiness를 시간 순서로 대조한다.
- MLflow Tracking DB 또는 파일 기반 artifact store의 지속성이 중요하면 StatefulSet/Deployment와 무관하게 PV/PVC·백업·복구 정책을 검토한다.

**이번 주의 최종 판단:** MLOps의 안정성을 결정하는 것은 좋은 모델만이 아니다. 모델을 실행할 Node, 저장소의 수명, 장애 뒤 복구 경로까지 재현 가능하게 정의해야 한다.

[4주차 학습 정리로 돌아가기](/ml-platform/study-week-04)

참고: [Kubernetes Scheduling Framework](https://kubernetes.io/docs/concepts/scheduling-eviction/scheduling-framework/) · [Topology Spread](https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints/) · [StatefulSet](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/) · [PV](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)
