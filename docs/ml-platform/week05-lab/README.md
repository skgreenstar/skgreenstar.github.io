# 5주차 실습: Job 재시도와 DB 멱등성

## 질문
모델 학습 Job이 외부 DB에 결과를 저장하고, 성공 응답 전에 비정상 종료하면 다음 실행이 결과를 중복 저장할까?

## 실행 환경
- Python 3.13.5, SQLite (Python 표준 라이브러리)
- Docker / kind / kubectl이 없는 로컬 실행 환경에서 실제 subprocess 두 번을 실행
- **Kubernetes Job Controller에서 재시도한 결과가 아니라 Job 재시도 상황을 로컬에서 재현한 실험**이다

## 실행
```bash
python demo.py
```

## 절차
1. 동일한 job_id `retrain-2026w05`로 INSERT 후 COMMIT.
2. 첫 번째 프로세스는 COMMIT 직후 `os._exit(17)`로 강제 종료한다.
3. 두 번째 프로세스를 동일한 job_id로 실행한다 (종료 코드 0).
4. 일반 INSERT와 `UNIQUE(job_id)` + `ON CONFLICT DO NOTHING`의 결과 행 수를 비교한다.
5. 실제 출력은 [results.json](./results.json)에 저장했다.

## 실제 측정
| 방법 | 1차 exit code | 재시도 exit code | 동일 job_id 결과 건수 |
|---|---:|---:|---:|
| 일반 INSERT | 17 | 0 | **2** |
| 멱등 처리 | 17 | 0 | **1** |

단일 실행 후 다시 동일 시나리오를 실행했고 두 번 모두 assertion을 통과했다.

## 해석과 한계
재시도 자체는 외부 부수효과의 정확히 한 번 실행을 보장하지 않는다. DB UNIQUE 제약이 **이 예시의 결과 기록 중복**을 차단한 것이지, 학습 연산이나 다른 외부 시스템 호출까지 정확히 한 번 수행됐다는 뜻은 아니다.

실제 Kubernetes에서는 Job `backoffLimit`, `restartPolicy`, CronJob 중복 스케줄과 병렬 실행, Pod 삭제 타이밍을 함께 검증해야 한다. 이 실험에서는 그런 Kubernetes 동작을 측정하지 않았다.
