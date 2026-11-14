---
title: "15 · Pending과 스케줄링 진단"
outline: deep
prev:
  text: '14 · Pod 배치와 Topology'
  link: '/ml-platform/week04-pod-placement'
next:
  text: '16 · PV·PVC·StorageClass'
  link: '/ml-platform/week04-persistent-storage'
---


# 15 · Pending과 스케줄링 진단

CH8.3 Debugging Placement Problems

Pending은 반드시 Scheduler 문제를 뜻하지 않는다. Node 배치 전에도, Node가 결정되었지만 컨테이너와 볼륨을 준비하는 단계에서도 발생할 수 있다.

## 1. PodScheduled부터 분리한다

~~~text
                  Pod: Pending
                       |
              PodScheduled?
                /            \
             False           True
              |               |
        FailedScheduling    Kubelet / CSI
              |               |
        Node / affinity    FailedMount /
        taints / capacity  ImagePullBackOff
~~~

~~~bash
kubectl -n week04 get pod <POD> -o wide
kubectl -n week04 describe pod <POD>
kubectl -n week04 get pod <POD> -o jsonpath='{.status.conditions}'
kubectl -n week04 get events --sort-by=.lastTimestamp
~~~

상태·이벤트를 읽는 참고 명령어이며 실제 클러스터 실행 로그는 아니다.

## 2. 실패 메시지를 계층별로 해석한다

| 이벤트 | 대표 원인 | 먼저 확인할 대상 |
|---|---|---|
| Insufficient cpu / memory | NodeResourcesFit 필터 | requests, Node allocatable |
| node affinity/selector mismatch | NodeAffinity 필터 | 레이블, required 조건 |
| untolerated taint | TaintToleration 필터 | Node taints, Pod tolerations |
| pod affinity/anti-affinity mismatch | InterPodAffinity | labelSelector, namespace, topologyKey |
| topology spread constraint | PodTopologySpread | 대상 Pod, zone, maxSkew |
| unbound PVC | StorageClass/VolumeBinding | PVC describe, provisioner |
| FailedMount | kubelet/CSI | PV zone, 드라이버, 접근 권한 |
| ImagePullBackOff | 이미지 레지스트리 | 이름, 태그, 인증, 아키텍처 |

## 3. 자원 단편화와 Requests

Node A에 CPU 1500m, Node B에 CPU 1000m가 남아 있을 때 CPU 2000m를 요청하는 하나의 Pod는 배치할 수 없다. 클러스터 전체 여유 CPU는 2500m이지만 **한 Pod가 여러 Node의 CPU를 합쳐 사용할 수는 없기 때문**이다.

실시간 사용률이 낮아도 requests를 기준으로 추가 Pod 배치가 제한될 수 있다. 따라서 CPU를 조사할 때는 top 명령만이 아니라 Node의 Allocated resources를 함께 확인한다.

~~~bash
kubectl describe node <NODE>
kubectl top node
kubectl -n week04 get pod <POD> -o yaml
~~~

## 4. 필수 조건들이 서로 충돌하는 경우

~~~yaml
spec:
  nodeSelector:
    disk: nvme
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
        - matchExpressions:
          - key: zone
            operator: In
            values: [az2]
~~~

이 매니페스트는 NVMe 디스크이면서 az2 Node여야 한다. az1에 NVMe가 아무리 많아도 필수 조건을 통과하지 못한다. Toleration을 추가해도 잘못된 zone 조건은 우회할 수 없다.

## 5. PVC가 Scheduler 장애처럼 보이는 이유

볼륨이 특정 zone에 고정되어 있다면 Pod의 Node Affinity도 그 범위와 양립해야 한다. StorageClass의 WaitForFirstConsumer는 최초 Pod의 배치 제약을 고려해 볼륨을 준비하도록 설계된 정책이다. 반대로 Immediate는 Pod가 결정되기 전에 볼륨의 위치가 정해질 수 있다.

~~~bash
kubectl get storageclass -o wide
kubectl -n week04 get pvc
kubectl -n week04 describe pvc <PVC>
kubectl get pv -o wide
~~~

## 6. ML 학습 작업의 장애 분석 순서

1. PodScheduled와 Events로 Scheduler 이전/이후 단계 분리.
2. CPU/메모리 requests와 Node allocatable 확인.
3. nodeSelector, affinity, taint, topology 제약 검토.
4. PVC Bound와 StorageClass, 볼륨 topology 확인.
5. 이미 스케줄되었다면 이미지 Pull·Mount·컨테이너 시작 단계 점검.
6. 컨테이너가 실행된 다음 모델 학습 로그와 exit code 확인.

KFP Training Job의 Pod가 Pending일 때 학습 코드를 먼저 수정하는 것은 문제 해결의 순서를 거꾸로 잡는 것이다.

## 요약

**Pending은 증상이고 PodScheduled와 Event는 문제의 경계를 알려 주는 근거**다. Scheduler, Kubelet, CSI, 이미지 저장소 문제를 구분해야 적절한 조치를 선택할 수 있다.

[4주차 학습 정리](/ml-platform/study-week-04)

참고: [Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/) · [Kubernetes Scheduler](https://kubernetes.io/docs/concepts/scheduling-eviction/kube-scheduler/)
