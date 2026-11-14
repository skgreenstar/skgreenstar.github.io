---
title: "17 · Pod는 왜 한 Node에 몰리고, 어떻게 분산할까?"
outline: deep
prev:
  text: '16 · Scheduler와 상태 저장'
  link: '/ml-platform/week04-scheduling'
next:
  text: '18 · StatefulSet'
  link: '/ml-platform/week04-statefulset'
---

# 17 · Pod는 왜 한 Node에 몰리고, 어떻게 분산할까?

교재 범위: *Machine Learning Platform Engineering* CH8.1~8.3 · Node Feature Selection, Placing Pods, Debugging Placement Problems.

**질문:** CPU·GPU Node가 섞인 클러스터에서 학습 Pod가 특정 Node에 몰리거나, 서로 다른 zone에 있어야 할 추론 Pod가 한곳에 배치되면 어떻게 제어할 수 있을까?

## 1. Scheduler의 Filter와 Score를 구분해야 한다

~~~text
API Server → unscheduled Pod → kube-scheduler
                                  |
                     Filter: NodeResourcesFit,
                     NodeAffinity, TaintToleration,
                     VolumeBinding, PodTopologySpread ...
                                  |
                      feasible Node candidates
                                  |
                     Score: NodeResourcesFit,
                     preferred affinity,
                     PodTopologySpread ...
                                  |
                           Bind → kubelet
~~~

Node에 Pod가 배치되는 것은 단순히 CPU가 남아 있기 때문만은 아니다. **Filter를 통과한 Node만 Score의 대상**이다. 필수 규칙이 맞지 않으면 선호 규칙의 점수가 아무리 높아도 배치되지 않는다. 실제 스케줄러 플러그인과 가중치는 Kubernetes 버전과 Scheduler 설정에 따라 달라진다.

## 2. Node selector와 affinity의 논리식

| 규칙 | 의미 | 사용 예 |
|---|---|---|
| nodeSelector | 모든 key=value의 AND | workload=training, arch=arm64 |
| required nodeAffinity | 필수 조건 | GPU 노드만 |
| preferred nodeAffinity | 점수에 반영되는 선호 | SSD 노드를 더 선호 |
| NodeAffinity NotIn | 선택 대상 제외 | spot이 아닌 Node |
| tolerations | Node Taint를 허용 | dedicated=gpu:NoSchedule 허용 |

하나의 nodeSelectorTerm 내부 matchExpressions는 AND로, 여러 nodeSelectorTerms는 OR로 연결된다. **nodeSelector와 required nodeAffinity는 모두 만족해야 한다.**

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: affinity-demo
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
          - key: kubernetes.io/os
            operator: In
            values: ["linux"]
      preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 80
        preference:
          matchExpressions:
          - key: disktype
            operator: In
            values: ["ssd"]
  containers:
  - name: demo
    image: busybox:1.36
    command: ["sh", "-c", "sleep 3600"]
    resources:
      requests:
        cpu: 100m
        memory: 64Mi
~~~

## 3. Taints와 Tolerations는 Pod의 선호가 아니다

Node에서 dedicated=gpu:NoSchedule을 부여하면 이를 허용하지 않는 Pod는 새로 배치되지 않는다. Toleration을 추가해도 **그 Node로 가도록 강제하지 않는다.** GPU 학습과 일반 API를 분리하려면 Taint/Toleration과 필수 Node affinity를 함께 사용한다.

| Taint Effect | 새 Pod | 기존 Pod |
|---|---|---|
| PreferNoSchedule | 가능한 피함 | 유지 |
| NoSchedule | 미허용 Pod 배치 금지 | 유지 |
| NoExecute | 미허용 Pod 배치 금지 | 미허용 Pod 퇴거 대상 |

~~~bash
kubectl get nodes --show-labels
kubectl taint node <WORKER_NODE_NAME> dedicated=gpu:NoSchedule
kubectl describe node <WORKER_NODE_NAME> | grep -i taint
# 확인 후 되돌리기
kubectl taint node <WORKER_NODE_NAME> dedicated=gpu:NoSchedule-
~~~

GPU가 없는 kind 환경에서는 GPU 할당 자체를 재현했다고 쓰지 않는다. Taint 동작만 모사할 수 있다.

## 4. Pod Affinity와 Anti-Affinity: 서로 모으거나 떨어뜨리기

Pod Affinity는 다른 Pod의 레이블을 기준으로 같은 topology domain에 배치한다. 반면 Anti-Affinity는 같은 도메인에 함께 놓이지 않도록 한다. topologyKey가 kubernetes.io/hostname이면 **Node**, topology.kubernetes.io/zone이면 **zone** 수준으로 조건을 해석한다.

~~~yaml
affinity:
  podAntiAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
    - labelSelector:
        matchLabels:
          app: infer-api
      topologyKey: kubernetes.io/hostname
~~~

이 항목은 Pod spec의 부분 예제다. Pod 3개를 서로 다른 Node에 놓도록 강제했는데 가능한 Node가 2개뿐이라면, 세 번째 Pod는 Pending일 수 있다. 따라서 강제 규칙은 고가용성에 유리한 동시에 리소스 유연성을 낮춘다.

## 5. TopologySpreadConstraints: 최대 편차를 제어한다

~~~yaml
topologySpreadConstraints:
- maxSkew: 1
  topologyKey: topology.kubernetes.io/zone
  whenUnsatisfiable: DoNotSchedule
  labelSelector:
    matchLabels:
      app: infer-api
~~~

maxSkew는 스케줄 대상 topology domain 사이에 허용할 Pod 수 편차를 정의한다. 다만 eligible domain, nodeAffinityPolicy, nodeTaintsPolicy, minDomains의 영향을 받을 수 있어 단순한 전체 노드 수의 평균으로 계산하지 않는다.

- DoNotSchedule: 조건이 충족되지 않으면 배치하지 않는다.
- ScheduleAnyway: 가능한 한 균형을 맞추되 불균형 자체로 배치를 금지하지 않는다.

**운영 선택:** 장애 도메인 분산이 필수이면 hard constraint, 일시적인 capacity 부족에도 가동성을 유지해야 하면 soft constraint를 고려한다.

## 6. CH8.3 · 의도적으로 Pending 만들기

실습에서 soft 규칙만 사용하면 조건이 지켜지지 않았는지 판단하기 어렵다. 노션 자료가 제안하듯 **required로 먼저 검증 후 preferred로 완화**하는 순서가 좋다.

~~~bash
kind get clusters
kubectl create ns week04 --dry-run=client -o yaml | kubectl apply -f -
kubectl get nodes -L workload,disktype,topology.kubernetes.io/zone
kubectl apply -f affinity-demo.yaml
kubectl -n week04 get pods -o wide
kubectl -n week04 describe pod affinity-demo
kubectl -n week04 get events --sort-by=.lastTimestamp
~~~

| 시나리오 | 의도한 관찰 | 진단 근거 |
|---|---|---|
| workload=ml Node가 없음 | Pending | didn't match node affinity/selector |
| 레이블 부여 후 재평가 | Scheduled 가능 | Pod.spec.nodeName |
| 전용 Node에 taint 추가 | Toleration 없으면 Pending 가능 | untolerated taint |
| 필수 Pod Anti-Affinity + Node 부족 | 일부 replicas Pending | affinity mismatch |
| preferred로 완화 | 다른 Node에도 배치 가능 | Pod 위치 비교 |

이 표는 **기대 결과**다. 실제 실행 로그와 구분하며, 장애 재현 후 실습 Pod·Taint·Label을 되돌린다.

## 7. MLOps 관점에서의 배치 정책

- GPU Training: GPU Node affinity, 전용 Taint/Toleration, GPU device plugin, checkpoints.
- CPU Preprocessing: 저비용 Node pool, 작업 재시도, scratch 용량.
- Model Serving: Pod topology spread, readiness, PDB, Service endpoint 확인.
- State Store: 볼륨의 zone affinity와 Pod nodeAffinity가 충돌하지 않는지 점검.

스케줄링이 되는지와 성능이 나오는지는 별개다. 3주차 HPA에서 Desired replicas만 보고 가용 용량을 판단하지 않았던 이유와 연결된다.

**정리:** Scheduler 정책은 선호하는 Node를 선택하는 기술인 동시에 장애를 어디까지 허용할지 결정하는 운영 정책이다.

[4주차 학습 정리](/ml-platform/study-week-04)

참고: [Scheduling Framework](https://kubernetes.io/docs/concepts/scheduling-eviction/scheduling-framework/) · [Assign Pods to Nodes](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/) · [Topology Spread](https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints/)
