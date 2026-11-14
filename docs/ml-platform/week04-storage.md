---
title: "15 · 아티팩트 저장소와 PVC 중 무엇을 선택해야 할까?"
outline: deep
prev:
  text: '14 · 학습과 검증'
  link: '/ml-platform/week04-training-validation'
next:
  text: '16 · Scheduler'
  link: '/ml-platform/week04-scheduling'
---

# 15 · 아티팩트 저장소와 PVC 중 무엇을 선택해야 할까?

데이터를 KFP 단계 사이에 전달한다고 반드시 공유 PVC가 필요한 것은 아니다. 객체 저장소·볼륨·임시 디스크는 데이터의 수명과 접근 패턴에 따라 나눠야 한다.

## 1. 세 저장 방식의 책임

| 방식 | 강점 | 주의할 점 |
|---|---|---|
| KFP Artifact + 객체 저장소 | 실행별 결과 추적·Pod 간 전달·영속화 | 전송 및 저장 비용, 접근 권한 |
| PVC | 동일 클러스터에서 큰 파일 반복 접근 | 접근 모드·스토리지 토폴로지·정리 |
| ephemeral storage | 임시 파일·짧은 작업 공간 | Pod 종료 시 데이터 소실 |

KFP 아티팩트는 추적의 단위이고 PVC는 파일시스템 접근 방식이다. 이 둘은 대체 관계라기보다 필요하면 함께 사용하는 구조다.

## 2. PV, PVC, StorageClass

- PV는 클러스터에서 제공하는 볼륨 리소스이고 PVC는 Pod 측의 스토리지 요청이다.
- StorageClass는 동적 프로비저닝과 바인딩 정책을 정의한다.
- ReadWriteOnce(RWO)는 한 노드에 읽기/쓰기 마운트를 허용하는 접근 모드다. 반드시 Pod 하나만 쓴다는 의미는 아니다.
- ReadWriteMany(RWX)는 지원되는 드라이버에서 다중 노드 접근을 허용한다.
- WaitForFirstConsumer는 첫 소비 Pod의 스케줄링 조건을 고려해 바인딩·프로비저닝을 지연할 수 있다.

~~~yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: week04-cache
  namespace: week04
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 2Gi
~~~

이 PVC는 예시다. 실제로 사용할 StorageClass와 클러스터의 기본값이 있는지 먼저 확인해야 한다.

## 3. 대용량 데이터에서 발생할 수 있는 병목

~~~text
데이터 수집 → Object storage (불변 원본 스냅샷)
                               |
                     Prepare / Validate
                               |
                     반복 학습용 캐시 PVC
                               |
                        Train / Evaluate
                               |
                      Model Artifact 업로드
~~~

원본 데이터는 불변 스냅샷으로 보관하고, 중간 계산 결과는 재생성 가능하다면 별도로 보존 기한을 정한다. 큰 Dataset을 매번 다운로드/업로드하는 비용과 PVC 사용 시 노드 바인딩·동시성을 비교한다.

## 4. PVC를 사용할 때 실패하는 이유

| 증상 | 점검 순서 |
|---|---|
| PVC Pending | StorageClass, 용량, 프로비저너 이벤트 |
| Pod Pending | PVC 바인딩 상태, nodeAffinity, topology |
| mount 실패 | CSI 드라이버, 접근 모드, 권한, 노드 이벤트 |
| 저장 공간 부족 | PVC 사용량, ephemeral storage, log |
| 재시도 결과가 이상함 | 이전 실행 중간 파일 오염, 실행별 경로 분리 |

~~~bash
kubectl get storageclass
kubectl -n week04 get pvc
kubectl -n week04 describe pvc week04-cache
kubectl -n week04 get pods -o wide
kubectl -n week04 get events --sort-by=.lastTimestamp
~~~

## 5. 운영 판단 기준

- 모델 버전과 연계해 오래 보존할 파일 → 객체 저장소 Artifact.
- 여러 단계가 자주 읽고 쓰는 대형 파일 → PVC 검토.
- 실패 시 바로 다시 계산할 작은 파일 → 임시 스토리지.
- 서로 다른 클러스터·리전에 접근할 데이터 → 원격 불변 데이터셋 URI 검토.

**결론:** 스토리지 선택은 속도 하나가 아니라 재현성·비용·격리·동시성·Pod 배치 조건을 함께 최적화하는 결정이다.

[4주차 학습 정리](/ml-platform/study-week-04)

참고: [Kubernetes PV](https://kubernetes.io/docs/concepts/storage/persistent-volumes/) · [StorageClass](https://kubernetes.io/docs/concepts/storage/storage-classes/)
