---
title: "06. Feast · 같은 정의로 과거와 최신 피처 조회하기"
outline: deep
prev:
  text: '05 · MLflow'
  link: '/ml-platform/mlflow-model-lifecycle'
next:
  text: '07 · KFP'
  link: '/ml-platform/kfp-batch-inference'
---

# 06. Feast · 같은 정의로 과거와 최신 피처 조회하기

**CH4 · 피처 스토어.** MLflow가 모델과 실험의 근거를 관리한다면, Feast는 학습과 추론이 사용할 피처 정의와 조회 경로를 관리한다. 이 장은 기존 제조 품질 데이터에 연결할 피처 정의와 조회·검증 순서를 정리한다.

## 1. 피처 스토어를 쓰는 이유

학습에서는 CSV의 온도·압력·속도를 사용하고 추론에서는 별도 코드로 컬럼을 재구성하면 이름·자료형·시점이 어긋날 수 있다. 공통 정의를 사용하면 어떤 설비의 어느 시점 값을 읽는지 명시할 수 있다. Feast 자체가 원천 센서의 오류나 모든 데이터 누수를 자동 해결해 주지는 않는다.

![Feast의 정의 등록과 Offline·Online 값 전달 경로](/images/week02-feast.svg)

| 개념 | 의미 | 우리 데이터의 대응 |
|---|---|---|
| Entity | 피처를 찾는 업무 식별자 | equipment_id |
| DataSource | 원본 위치·형식·시각 컬럼 | CSV를 변환한 이력 파일, event_timestamp |
| FeatureView | Entity·피처 스키마·TTL을 묶은 정의 | temperature, pressure, speed |
| FeatureService | 함께 사용할 피처 묶음 | 제조 품질 모델 입력 계약 |
| Registry | 피처 정의의 메타데이터 | 정의·스키마·연결 정보 |
| Offline Store | 시각별 피처 이력 | 학습·과거 배치용 조회 |
| Online Store | Entity별 최신 피처 | 실시간 추론용 조회 |

`quality`는 학습 목표이므로 입력 피처 묶음에서 제외한다. MLflow에 기록한 signature·피처 순서와 Feast 조회 결과가 일치하도록 한다. 현재 데이터는 수치 피처이므로 교재의 one-hot 컬럼 목록을 그대로 복사하기보다 이름·순서·자료형 계약을 유지하는 목적에 맞춘다.

## 2. 과거 시점 조회와 데이터 누수

학습용 Entity 표에는 `equipment_id`와 **예측 기준 시각**이 필요하다. Historical 조회는 동일 Entity에서 기준 시각 이하이면서 TTL 범위에 있는 최신 관측을 연결한다. 우리 데이터의 `event_timestamp`와 `prediction_timestamp`는 역할이 다르므로 조회용 시각 컬럼으로 명시적으로 대응한다.

![예측 시점 이전 피처를 선택하는 point-in-time join 예시](/images/week02-time.svg)

예측이 00:05라면 00:10의 온도 88을 사용하면 안 된다. 00:00의 72가 유효 기간 안에 있다면 그것을 선택한다. 유효한 과거 값이 없을 때 결측값을 어떻게 처리할지도 계약에 포함한다. TTL은 피처 신선도 정책이며 누락을 무조건 0으로 바꾸라는 뜻이 아니다.

또한 관측 시각이 과거여도 데이터가 실제 시스템에 늦게 도착했다면 당시 사용 가능하지 않았을 수 있다. 엄격한 재현에는 수집·가용 시각과 backfill 정책까지 확인한다.

## 3. apply와 materialize를 구분하기

| 작업 | 바뀌는 대상 | 확인할 것 |
|---|---|---|
| apply | Registry의 정의 | Entity 키·피처 스키마·TTL·소스 |
| Historical 조회 | 지정 시점의 조회 결과 | 미래 값 제외·행 수·키 중복·결측 |
| materialize | Offline에서 Online으로 적재된 값 | 시간 구간·대상 Entity·최신 시각 |
| Online 조회 | Entity별 최신 값 응답 | 값 존재·신선도·자료형 |

apply 성공만으로 Redis 등에 값이 들어간 것은 아니다. materialization 후 알려진 Entity를 조회해 `None` 여부와 실제 값을 확인한다. Online 조회는 과거 시점을 재현하는 Historical 조회를 대체하지 않는다. 과거 배치 검증에는 Historical 경로를 사용한다.

## 4. 기존 MLflow 실습과 연결하는 실행 순서

1. MLflow 산출물의 원본 CSV·`dataset_contract.json`을 읽고 SHA-256과 필수 컬럼을 확인한다.
2. UTC 시각·Entity 키·수치 자료형을 정리하고 Offline 소스와 피처 정의를 준비한다.
3. kind 안의 Feast 조회 Job에서 정의를 적용하고 최종 평가 대상 Entity·예측 시각으로 Historical 피처를 조회한다.
4. 원본에서 같은 규칙으로 찾은 값과 대조한다. 미래 데이터 제외, 행 수 보존, Entity·시각 중복 정책을 확인한다.
5. 지정 구간을 materialize한 후 같은 Entity의 Online 최신 값과 기준 시각을 확인한다.
6. 피처 조회 산출물을 MLflow의 고정 모델 URI와 함께 다음 KFP 단계의 입력으로 넘긴다.

첫 MLflow 학습은 CSV를 직접 사용했다. Feast를 도입했다는 사실만으로 기존 학습이 Feast 기반이었다고 바꾸어 쓰지 않는다. 다음 학습부터 Historical 조회 결과를 사용하고, FeatureService 이름·정의 버전 또는 해시·실제 피처 목록을 Run에 기록하면 학습 입력의 계보까지 이어진다.

::: tip 실습 화면 ② · Feast 조회 결과
Feast Job을 실행한 뒤 한 화면에 **Entity·예측 기준 시각·Historical 피처 값**, 그리고 **동일 Entity의 Online 최신 값과 관측 시각**을 표시해 캡처한다. 미래 값이 제외된 예시 한 행과 결측 검사 결과를 함께 보이면 조회 의미가 드러난다. 캡처 후 이 안내를 실제 화면과 짧은 해석으로 교체한다.
:::

## 5. 다음 장으로 넘기는 계약

피처 Dataset은 Entity·예측 시각을 보존하고 입력 피처만 모델에 전달한다. 컬럼 누락·중복·허용하지 않은 결측이 있으면 추론을 시작하기 전에 실패시킨다. 고정 모델 URI와 피처 정의 식별자를 KFP 실행 파라미터에 함께 기록한다.

참고: [Feast 공식 문서](https://docs.feast.dev/)
