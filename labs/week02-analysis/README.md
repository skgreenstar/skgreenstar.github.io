# Week 02 · 데이터와 선택 근거 시각화

기존 학습 스크립트의 seed 42 데이터 생성 함수를 사용해 피처·목표 관계를 그린다. 모델 비교 그림은 이미 기록한 검증 RMSE를 시각화하며 모델을 새로 학습하지 않는다.

```bash
python -m pip install -r labs/week02-analysis/requirements.txt
python labs/week02-analysis/render_analysis.py
```

생성 파일:

- docs/public/images/week02-feature-quality.svg / png: 세 피처와 합성 품질의 관계. 1,000행의 구간별 평균과 125행의 표본 산점도.
- docs/public/images/week02-model-comparison.svg / png: 기존 검증 비교표의 RMSE.
- analysis_summary.json: 원본 생성 코드 해시·행 수·결측·상관계수·범위.
- validation_comparison.csv: 모델 비교 그림의 원본 수치.

정적 예제 데이터에 대한 탐색이며, 실제 공장 측정값·인과 효과·새로운 모델 학습 결과를 뜻하지 않는다.
