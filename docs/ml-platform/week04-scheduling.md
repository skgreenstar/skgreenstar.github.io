---
title: "16 · 학습 Pod가 Pending이라면 모델보다 무엇을 먼저 볼까?"
outline: deep
prev:
  text: '15 · PVC와 저장 전략'
  link: '/ml-platform/week04-storage'
next:
  text: '4주차 · 학습 정리'
  link: '/ml-platform/study-week-04'
---

# 16 · 학습 Pod가 Pending이라면 모델보다 무엇을 먼저 볼까?

KFP 작업이 생성됐어도 Pod가 스케줄링되지 않으면 학습 코드는 시작조차 하지 못한다. Pod Pending을 모델 코드 문제로 판단하기 전에 Scheduler 이벤트와 자원·볼륨 조건을 분리해야 한다.

## 1. Scheduler의 Filter와 Score

~~~text
KFP → Pod 생성 → API Server → Scheduler
                                  |
                        Filter: 배치 가능한 Node?
                                  |
                        Score: 어느 Node가 적합?
                                  |
                       Bind: Pod.spec.nodeName
                                  |
                      Kubelet → 이미지/볼륨/컨테이너
~~~

Filter는 리소스, 필수 노드 조건, Taint·Toleration, 볼륨 제약을 검토한다. Score는 적합한 후보 노드에 우선순위를 매긴다. **점수가 높은 노드를 선택하는 과정은 필수 조건 불일치를 해결하지 않는다.**

## 2. 노드 조건의 차이

| 기능 | 목적 | 필수/선호 |
|---|---|---|
| nodeSelector | 특정 레이블에 정확히 맞는 노드 | 필수 |
| nodeAffinity | 여러 레이블을 조합한 노드 선택 | required / preferred |
| podAffinity | 다른 Pod와 같은 토폴로지에 배치 | required / preferred |
| podAntiAffinity | 다른 Pod와 분리 배치 | required / preferred |
| topologySpreadConstraints | 노드·존의 배치 편차 관리 | DoNotSchedule / ScheduleAnyway |
| Taint/Toleration | 노드의 배치 거부와 파드의 예외 허용 | NoSchedule / NoExecute 등 |

Toleration은 노드 진입을 허용하는 조건이지 그 노드로 반드시 가게 하는 조건이 아니다. GPU 노드에 배치하려면 노드 affinity 등 선택 제약을 함께 고려한다. requiredDuringSchedulingIgnoredDuringExecution은 **배치 시점 조건**으로, 이미 실행 중인 Pod를 조건 변화만으로 자동 퇴거시키지 않는다.

## 3. 실습용 Node Affinity 매니페스트

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: week04-scheduler-demo
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
          - key: disktype
            operator: In
            values: ["ssd"]
  containers:
  - name: sample
    image: nginx:alpine
    resources:
      requests:
        cpu: 100m
        memory: 128Mi
~~~

이 예시는 workload=ml 레이블을 가진 노드가 없으면 Pending이 된다. 기존 kind 노드에 임의의 레이블이 있다고 가정하지 않는다.

~~~bash
kubectl create namespace week04 --dry-run=client -o yaml | kubectl apply -f -
kubectl get nodes --show-labels
kubectl -n week04 describe pod week04-scheduler-demo
kubectl -n week04 get events --sort-by=.lastTimestamp
~~~

## 4. Pod Pending 진단

| 이벤트/상태 | 가능한 원인 | 먼저 볼 항목 |
|---|---|---|
| Insufficient cpu/memory | requests 대비 노드 용량 부족 | kubectl describe node |
| didn't match node affinity/selector | 필수 레이블 불일치 | 노드 labels / Pod affinity |
| untolerated taint | Toleration 없음 | 노드 Taint |
| unbound immediate PersistentVolumeClaims | PVC 미바인딩 | PVC/StorageClass/CSI 이벤트 |
| PodScheduled=True, ContainerCreating | 이미지·마운트·컨테이너 시작 | kubelet 이벤트·이미지 접근 |

HPA가 replica 수를 늘려도 Scheduler가 할당할 수 없는 Pod는 Ready가 되지 않는다. 따라서 3주차의 HPA 실험과 4주차 스케줄링은 연결된 문제다.

## 5. StatefulSet과 KFP Job은 다르다

KFP의 학습 컴포넌트는 일반적으로 Run 단위의 유한 작업이다. 반면 StatefulSet은 안정적인 네트워크 식별성과 지속 볼륨이 필요한 상태 저장 애플리케이션에 적합하다. MLflow DB나 메시지 브로커를 상태 저장 방식으로 운영할 수 있지만 모든 학습 작업을 StatefulSet으로 바꾸는 것이 정답은 아니다. 상태 저장 컴포넌트에는 백업, 복구, StorageClass, 노드 토폴로지 정책을 별도로 마련한다.

## 6. 이번 주의 운영 결론

모델 오류, Pod 스케줄링 실패, PVC 바인딩 실패, ContainerCreating 장애는 발생 지점과 담당 컴포넌트가 다르다. **학습 파이프라인의 실패를 애플리케이션 예외와 인프라 이벤트로 분리해서 진단**해야 한다.

[4주차 학습 정리](/ml-platform/study-week-04)

참고: [Kubernetes Scheduler](https://kubernetes.io/docs/concepts/scheduling-eviction/kube-scheduler/) · [Node Affinity](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/) · [Taints](https://kubernetes.io/docs/concepts/scheduling-eviction/taint-and-toleration/) · [StatefulSet](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/)
