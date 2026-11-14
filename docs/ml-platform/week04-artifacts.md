---
title: "13 · KFP에서 데이터는 어느 Pod를 거쳐 이동할까?"
outline: deep
prev:
  text: '4주차 · 학습 정리'
  link: '/ml-platform/study-week-04'
next:
  text: '14 · 학습과 검증'
  link: '/ml-platform/week04-training-validation'
---

# 13 · KFP에서 데이터는 어느 Pod를 거쳐 이동할까?

Python 함수처럼 보이는 KFP Pipeline은 클러스터에서 별도 Pod의 작업들로 실행된다. 프로세스의 메모리 변수를 공유하지 않으므로 단계마다 **입출력 계약**을 정의해야 한다.

## 1. Parameter와 Artifact

| 구분 | Parameter | Artifact |
|---|---|---|
| 내용 | 숫자·문자열·불리언 | Dataset·Model·Metrics·HTML |
| 사용 | 작은 제어 값과 결과 | 파일·대용량 데이터·모델 |
| 표현 | 직렬화 값 | URI·메타데이터·파일 |
| 위험 | 큰 값으로 메타데이터 부담 | 다운로드·업로드·보존 비용 |

Artifact의 path는 컨테이너 안의 작업 경로이고 uri는 저장소의 아티팩트 참조다. 실제 전송은 KFP 실행 백엔드의 설정에 좌우된다.

![Artifact 데이터 전달](/images/week04-artifact-flow.svg)

*개념도: 경로 참조와 데이터 바이트 이동을 구분한다.*

## 2. KFP 2.x에서 Dataset을 전달하는 최소 예제

**컴파일용 예제이며 실행 결과는 아니다.**

~~~python
from kfp import compiler, dsl
from kfp.dsl import Dataset, Input, Output, Metrics

@dsl.component(base_image="python:3.11-slim")
def make_dataset(n: int, data: Output[Dataset]):
    from pathlib import Path
    path = Path(data.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x,y\n" + "".join(f"{i},{i*2}\n" for i in range(n)))
    data.metadata["rows"] = n
    data.metadata["schema_version"] = "v1"

@dsl.component(base_image="python:3.11-slim")
def inspect_dataset(data: Input[Dataset], metrics: Output[Metrics]) -> int:
    from pathlib import Path
    rows = len(Path(data.path).read_text().splitlines()) - 1
    metrics.log_metric("rows", rows)
    if rows <= 0:
        raise ValueError("Empty dataset")
    return rows

@dsl.pipeline(name="week04-data-contract")
def pipeline(n: int = 10):
    produced = make_dataset(n=n)
    inspect_dataset(data=produced.outputs["data"])

if __name__ == "__main__":
    compiler.Compiler().compile(pipeline, "week04-artifacts.yaml")
~~~

컴파일된 YAML은 실행 명세다. 실제 KFP Run에는 백엔드, 객체 저장소, 서비스 계정과 이미지 접근 권한이 필요하다.

## 3. 타입이 같아도 내용은 검증해야 한다

KFP Dataset 타입이 컬럼·값 범위·레이블 분포를 자동 검증하는 것은 아니다. 데이터 준비 단계에서 스키마 버전, 체크섬, 행 수, 생성 시점과 데이터 스냅샷을 검증한다.

1. 입력 스냅샷이 고정됐는가?
2. CSV가 비었거나 컬럼이 달라졌다면 실패하는가?
3. Train과 validation의 시간·사용자·그룹 경계를 지켰는가?
4. 생산자·소비자 컴포넌트의 스키마 계약이 같은가?

## 4. 캐시와 재현성의 차이

KFP 캐시는 반복 계산을 줄이지만 외부 URL이 동일한 데이터인지 검증하지는 않는다. 원본이 변할 수 있다면 snapshot ID나 checksum을 입력으로 넘기고, 필요하면 해당 수집 단계의 캐시를 비활성화한다. 이미지 버전도 가변 태그보다 digest 고정을 권장한다.

## 5. 장애가 날 때 확인할 것

| 증상 | 확인 근거 |
|---|---|
| 입력 파일 없음 | 선행 단계 결과·아티팩트 URI·저장소 접근 |
| 내용이 달라짐 | checksum, schema, producer 로그 |
| 재실행만 이상함 | 캐시 재사용 여부·입력 스냅샷 |
| 학습 결과 추적 어려움 | Run ID·데이터 버전·MLflow 연결 |

**결론:** Artifact는 파일 전달과 동시에 어떤 실행이 어떤 데이터를 생산했는지 증명하기 위한 추적 단위다.

[4주차 학습 정리](/ml-platform/study-week-04)

참고: [KFP Parameters](https://www.kubeflow.org/docs/components/pipelines/user-guides/data-handling/parameters/) · [KFP Artifacts](https://www.kubeflow.org/docs/components/pipelines/user-guides/data-handling/artifacts/)
