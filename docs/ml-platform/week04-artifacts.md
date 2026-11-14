---
title: "13 · Scheduler는 학습 Pod의 Node를 어떻게 선택할까?"
outline: deep
prev: { text: '4주차 학습 정리', link: '/ml-platform/study-week-04' }
next: { text: '14 · Pod 배치 전략', link: '/ml-platform/week04-training-validation' }
---

# 13 · Scheduler는 학습 Pod의 Node를 어떻게 선택할까?

CH8.1 Node Feature Selection

Kubernetes에서 Pod가 생성되는 것과 컨테이너가 실행되는 것은 별개의 사건이다. API Server가 아직 Node에 연결되지 않은 Pod를 저장하면 Scheduler가 실행 가능한 Node를 평가하고, 선정한 Node의 kubelet이 이미지와 볼륨을 준비한다. ML 학습의 CPU·메모리·GPU 요구량은 Scheduler 단계에서 먼저 현실적인 제약으로 드러난다.

## 1. 스케줄링의 실제 순서

~~~text
Job/Deployment → API Server → Pending Pod (nodeName 없음)
                                       |
                               kube-scheduler
                                       |
                          PreFilter → Filter → Score
                                       |
                              Reserve / Permit / Bind
                                       |
                         Pod.spec.nodeName 설정
                                       |
                           kubelet → Container
~~~

Filter는 필수 조건을 통과하는 Node를 남기고, Score는 통과한 Node의 선호도를 평가한다. Scheduler Framework에는 PreScore·PreBind 등 추가 확장 지점이 있다. Filter에 실패한 Pod는 점수 비교 대상이 아니므로 **선호도 가중치를 높여도 필수 조건을 우회할 수 없다.**

| 고려 대상 | 대표 점검 항목 | 실패 시 |
|---|---|---|
| 리소스 | Pod CPU·메모리 requests, Node allocatable | Insufficient cpu/memory |
| Node 속성 | nodeSelector, required nodeAffinity | node affinity/selector mismatch |
| 전용 Node | taint와 toleration | untolerated taint |
| Pod 관계 | Pod affinity/anti-affinity | affinity constraints |
| 영속 볼륨 | VolumeBinding, PV topology | PVC 또는 binding 문제 |

## 2. nodeSelector: 가장 단순한 필수 제약

~~~yaml
spec:
  nodeSelector:
    kubernetes.io/os: linux
    workload: training
~~~

두 레이블을 **모두** 가진 Node만 사용할 수 있다. 범용 Node에 training 전용 레이블을 추가하지 않았다면 Pod는 배치되지 않는다. 다수 Node를 유연하게 묶어야 한다면 nodeAffinity를 이용한다.

## 3. Node Affinity의 논리 연산

~~~yaml
spec:
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
        - matchExpressions:
          - key: disk
            operator: In
            values: [nvme, ssd]
          - key: kubernetes.io/arch
            operator: In
            values: [arm64]
        - matchExpressions:
          - key: disk
            operator: In
            values: [nvme]
          - key: kubernetes.io/arch
            operator: In
            values: [amd64]
      preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 80
        preference:
          matchExpressions:
          - key: zone
            operator: In
            values: [az1]
~~~

하나의 nodeSelectorTerm 안에 여러 matchExpressions를 작성하면 **AND**, 서로 다른 nodeSelectorTerms 사이에는 **OR**가 적용된다. 위 예제는 '(arm64이고 SSD/NVMe) 또는 (amd64이고 NVMe)'를 필수로 요구하면서, az1을 선호한다. 선호 조건은 여러 스코어링 정책 중 하나이므로 weight 80이 무조건 선택을 보장하지는 않는다.

| 연산자 | 의미 |
|---|---|
| In / NotIn | 레이블 값이 집합에 포함 / 미포함 |
| Exists / DoesNotExist | 레이블의 존재 / 부재 |
| Gt / Lt | 정수로 해석 가능한 레이블 값 비교 |

requiredDuringSchedulingIgnoredDuringExecution에서 IgnoredDuringExecution은 스케줄링 **이후 레이블이 달라져도 해당 이유만으로 Pod를 퇴거시키지 않는다**는 의미다. 새로 생성되는 Pod에는 현재 조건이 적용된다.

## 4. Node Affinity와 Taint는 서로 반대 방향의 정책이다

~~~text
Pod → Node Affinity: "나는 GPU Node가 필요해"
Node → Taint:         "GPU를 허용한 Pod만 들어와"
Pod → Toleration:     "그 Taint를 허용해"
~~~

~~~bash
kubectl taint node <WORKER> dedicated=ml:NoSchedule
kubectl describe node <WORKER>
# 실습 Node 정책 복원
kubectl taint node <WORKER> dedicated=ml:NoSchedule-
~~~

~~~yaml
spec:
  tolerations:
  - key: dedicated
    operator: Equal
    value: ml
    effect: NoSchedule
~~~

| Effect | 새 Pod에 대한 의미 | 기존 Pod |
|---|---|---|
| PreferNoSchedule | 가능하면 배치하지 않음 | 유지 |
| NoSchedule | 허용되지 않으면 배치 금지 | 유지 |
| NoExecute | 허용되지 않으면 배치 금지 | 퇴거 대상 |

**Toleration은 해당 Node 배치를 허용할 뿐 선택을 강제하지 않는다.** ML 전용 Node pool에서는 taint와 required affinity를 함께 사용한다. GPU 학습을 실제 실행하려면 GPU device plugin과 스케줄 가능한 accelerator resource가 별도로 필요하다.

## 5. 리소스 배치와 Bin Packing

노드가 세 대 있어도 각 노드에 CPU 1개씩만 남았는데 하나의 학습 Job이 CPU 2개를 요청하면 총 여유 CPU가 3개라는 사실만으로 배치할 수 없다. **Pod 단위 요청을 수용하는 Node가 존재해야 한다.** 이것이 자원 단편화의 대표적인 예다.

CPU 사용률이 낮다는 이유만으로 Pod가 항상 배치 가능한 것도 아니다. Scheduler는 일반적으로 실시간 사용률이 아닌 requests와 allocatable을 기본 자원 판단의 중요한 입력으로 사용한다. NodeResourcesFit의 scoring 전략은 실제 Scheduler 프로필에 따라 달라질 수 있으므로 모든 클러스터가 항상 LeastAllocated라고 해석하지 않는다.

## 6. MLOps에 적용한다면

- CPU preprocessing: 범용 Node, 적절한 requests, 재시도 가능한 Job.
- GPU training: 전용 Node pool, GPU resource, checkpoint, taints와 affinity.
- Inference: 안정적 Node pool, 적절한 Pod 분산, readiness.
- 로컬 kind: Node Label/Taint의 스케줄링 동작을 이해하는 용도. GPU 성능 검증 환경과 구분.

### 명령어 참고

~~~bash
kubectl get nodes -L kubernetes.io/arch,topology.kubernetes.io/zone
kubectl describe node <NODE>
kubectl -n week04 describe pod <POD>
kubectl -n week04 get events --sort-by=.lastTimestamp
~~~

이 명령은 원리를 확인하는 참고 명령이다. 화면 출력이나 가상의 실행 성공 기록은 넣지 않았다.

## 요약

Scheduler는 **Filter로 가능한 Node를 제한하고 Score로 더 적합한 Node를 선택**한다. nodeSelector·required affinity·taint는 배치 가능성을 결정하고 preferred affinity는 후보 내 선호도를 바꾼다.

[4주차 학습 정리](/ml-platform/study-week-04)

참고: [Scheduler Framework](https://kubernetes.io/docs/concepts/scheduling-eviction/scheduling-framework/) · [Node Affinity](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/) · [Taint/Toleration](https://kubernetes.io/docs/concepts/scheduling-eviction/taint-and-toleration/)
