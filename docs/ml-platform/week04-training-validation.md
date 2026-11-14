---
title: "14 · 학습이 끝났다는 사실만으로 모델을 등록할 수 있을까?"
outline: deep
prev:
  text: '13 · 데이터 전달'
  link: '/ml-platform/week04-artifacts'
next:
  text: '15 · PVC와 저장 전략'
  link: '/ml-platform/week04-storage'
---

# 14 · 학습이 끝났다는 사실만으로 모델을 등록할 수 있을까?

학습 컴포넌트가 완료됐다는 사실만으로 모델이 유효한 것은 아니다. **학습 완료와 모델 승인을 구분하는 게이트**가 필요하다.

## 1. 단계별 입출력 계약

| 단계 | 입력 | 출력 | 중단 조건 |
|---|---|---|---|
| Prepare | 데이터 스냅샷 | 정제 데이터·스키마 보고 | 필수 컬럼 누락, 빈 데이터 |
| Split | 정제 데이터·분리 정책 | train/validation/test | 시간·그룹 누수 |
| Train | 학습 데이터·파라미터 | 모델·학습 지표 | NaN, 실행 오류 |
| Evaluate | 모델·고정 검증셋 | 예측·평가 지표 | 지표 계산 실패 |
| Quality gate | 후보·기준 모델 지표 | 승인 여부·사유 | 기준 미달은 정상 거절 |
| Register | 승인된 모델 URI | 모델 버전·Run 참조 | 미승인 후보 등록 금지 |

## 2. 기존 모델과 비교할 기준부터 고정하기

회귀 문제에서 과거 값 유지, 평균값 예측, 현재 운영 모델을 기준 모델(B0)로 사용할 수 있다. 비교 지표와 데이터 분할은 후보 모델(M1)과 동일해야 한다.

~~~text
schema_valid == true
sample_count >= 최소 샘플 수
RMSE(M1) <= 0.98 * RMSE(B0)
critical_segment_MAE <= 현업 허용 오차
모두 통과 → 승인
하나라도 미달 → 미승인
~~~

0.98은 2% 이상 개선이라는 **정책 예시**다. 실제 기준은 업무 손실·운전 구간의 위험·측정 오차를 고려해 정해야 한다. 전체 RMSE가 개선돼도 중요한 구간의 오차가 악화되면 보류할 수 있다.

## 3. 정상적인 품질 거절과 시스템 오류 구분

단순하게 임곗값 미달에서 예외를 발생시키면 KFP Run에 실패로 남아 운영 장애와 품질 미승인이 섞일 수 있다. 더 명확한 설계는 게이트가 판정 결과를 반환하고, Pipeline의 조건부 분기로 등록을 제어하는 것이다.

~~~python
from kfp import dsl, compiler
from kfp.dsl import Metrics, Output

@dsl.component(base_image="python:3.11-slim")
def quality_gate(
    candidate_rmse: float,
    baseline_rmse: float,
    metrics: Output[Metrics],
    required_improvement: float = 0.02,
) -> bool:
    import math
    if not all(math.isfinite(x) for x in (candidate_rmse, baseline_rmse)):
        raise ValueError("Invalid metric")
    if baseline_rmse <= 0 or candidate_rmse < 0:
        raise ValueError("Invalid RMSE")
    improvement = (baseline_rmse - candidate_rmse) / baseline_rmse
    approved = improvement >= required_improvement
    metrics.log_metric("candidate_rmse", candidate_rmse)
    metrics.log_metric("baseline_rmse", baseline_rmse)
    metrics.log_metric("improvement", improvement)
    return approved

@dsl.component(base_image="python:3.11-slim")
def record_approval() -> str:
    # 실제 운영에서는 승인된 모델 URI와 Run ID를 Registry에 기록
    return "approved-for-registration"

@dsl.pipeline(name="week04-quality-gate")
def pipeline(candidate_rmse: float = 0.9, baseline_rmse: float = 1.0):
    gate = quality_gate(
        candidate_rmse=candidate_rmse, baseline_rmse=baseline_rmse
    )
    with dsl.If(gate.output == True, name="approved"):
        record_approval()

if __name__ == "__main__":
    compiler.Compiler().compile(pipeline, "week04-quality-gate.yaml")
~~~

위 예제는 등록을 **모사한 컴파일용 설계**다. 실제 MLflow Registry 호출, 인증·모델 URI 검증은 구현되어 있지 않다. 미승인인 경우 조건부 등록 단계가 실행되지 않지만, 품질 미달을 시스템 오류로 기록하지 않는다.

## 4. 실행을 재현하기 위한 메타데이터

~~~yaml
data:
  snapshot_id: "example-snapshot-id"
  sha256: "<실행 후 측정값>"
split_policy: "time-based-v1"
seed: 42
image_digest: "<실제 이미지 digest>"
code_commit: "<실제 Git commit>"
kfp_run_id: "<실제 Run ID>"
mlflow_run_id: "<실제 Run ID>"
validation_policy: "model-gate-v1"
~~~

임의의 체크섬이나 실행 ID를 만들어 쓰지 않는다. 배포 승인을 거쳤는지 추적할 수 있도록 KFP와 MLflow 양쪽에 연결 정보를 남긴다.

## 5. 컴포넌트 이미지와 운영 안정성

경량 컴포넌트는 빠른 학습에 좋다. 하지만 매 실행 때 패키지 설치가 반복되면 외부 저장소 의존성이 생긴다. 재현성에 민감한 Train/Evaluate는 의존성과 아키텍처가 고정된 컨테이너 이미지를 권장한다. Apple Silicon에서는 linux/arm64 지원과 시스템 공유 라이브러리도 확인한다.

## 6. 결과 기록에서 지켜야 할 구분

| 구분 | 검증해야 할 증거 |
|---|---|
| 컴파일 | pipeline YAML 생성 |
| 실행 성공 | KFP Run 및 Pod 완료 로그 |
| 모델 성능 | 후보/기준 지표와 검증 데이터 버전 |
| 품질 승인 | 승인 기준·판정·미승인 사유 |
| Registry | 실제 모델 버전·아티팩트 URI·Run ID |

**결론:** 좋은 파이프라인은 모델을 자동으로 등록하는 것이 아니라, 승인되지 않은 모델이 다음 단계로 넘어가지 못하게 한다.

[4주차 학습 정리](/ml-platform/study-week-04)

참고: [KFP Control Flow](https://www.kubeflow.org/docs/components/pipelines/user-guides/core-functions/control-flow/) · [MLflow Registry](https://mlflow.org/docs/latest/ml/model-registry/)
