import { defineConfig } from 'vitepress'

export default defineConfig({
  lang: 'ko-KR',
  title: 'Heemin',
  description: 'AI Engineering · MLOps · LLMOps · RAG · Agent',
  cleanUrls: true,
  appearance: false,
  lastUpdated: true,
  head: [['meta', { name: 'theme-color', content: '#ffffff' }]],
  markdown: { math: true },
  themeConfig: {
    logo: '/logo.svg',
    siteTitle: 'Heemin / Engineering',
    nav: [
      { text: 'Home', link: '/' },
      { text: 'Writing', link: '/writing/' },
      { text: 'ML Platform', link: '/ml-platform/' },
      { text: 'About', link: '/about' },
      { text: 'GitHub ↗', link: 'https://github.com/skgreenstar' }
    ],
    sidebar: {
      '/ml-platform/': [
        { text: 'ML Platform Engineering', items: [
          { text: 'Overview', link: '/ml-platform/' }
        ]},
        { text: '1주차 · ML 시스템의 기반', items: [
          { text: '학습 정리 · CH1~3', link: '/ml-platform/study-week-01' },
          { text: '01 · ML Lifecycle', link: '/ml-platform/week-01' },
          { text: '02 · MLOps', link: '/ml-platform/week-02' },
          { text: '03 · Platform Architecture', link: '/ml-platform/week-03' }
        ]},
        { text: '2주차 · 실험 추적에서 모델 운영까지', items: [
          { text: '학습 정리 · CH4~5', link: '/ml-platform/study-week-02' },
          { text: '04 · 실행 환경', link: '/ml-platform/week02-environment' },
          { text: '05 · MLflow 실험·모델 관리', link: '/ml-platform/mlflow-model-lifecycle' },
          { text: '06 · Feast 피처 관리', link: '/ml-platform/model-pipeline' },
          { text: '07 · KFP 배치 추론', link: '/ml-platform/kfp-batch-inference' },
          { text: '08 · 결과 검증', link: '/ml-platform/week02-verification' }
        ]},
        { text: '3주차 · AI 추론 서비스 확장과 트래픽', items: [
          { text: '학습 정리 · CH6~7', link: '/ml-platform/study-week-03' },
          { text: '09 · HPA와 추론 부하', link: '/ml-platform/week03-autoscaling' },
          { text: '10 · Service와 요청 경로', link: '/ml-platform/week03-traffic' },
          { text: '11 · BentoML 모델 서빙', link: '/ml-platform/week03-bentoml-serving' },
          { text: '12 · 데이터와 모델 드리프트', link: '/ml-platform/week03-model-serving-drift' }
        ]},
        { text: '심화 · 운영과 평가', items: [
          { text: '운영 자동화', link: '/ml-platform/week-04' },
          { text: '리소스 관리', link: '/ml-platform/week-05' },
          { text: 'KServe와 vLLM', link: '/ml-platform/week-06' },
          { text: '산업 AI 회귀 평가', link: '/ml-platform/industrial-evaluation' },
          { text: 'RAG / Agent 평가', link: '/ml-platform/evaluation-and-operations' }
        ]}
      ],
      '/writing/': [
        { text: 'Technical Writing', items: [
          { text: 'All articles', link: '/writing/' },
          { text: 'ML Platform Engineering', link: '/ml-platform/week-01' }
        ]}
      ]
    },
    outline: { level: [2, 3], label: '이 페이지에서' },
    docFooter: { prev: '이전 글', next: '다음 글' },
    search: { provider: 'local', options: { translations: {
      button: { buttonText: '검색', buttonAriaLabel: '검색' },
      modal: { noResultsText: '검색 결과가 없습니다', resetButtonTitle: '검색 초기화', footer: { selectText: '선택', navigateText: '이동', closeText: '닫기' } }
    }}},
    socialLinks: [{ icon: 'github', link: 'https://github.com/skgreenstar' }],
    footer: { message: 'Built with VitePress · Engineering notes', copyright: '© 2026 Heemin' },
    editLink: { pattern: 'https://github.com/skgreenstar/skgreenstar.github.io/edit/main/docs/:path', text: '이 페이지 개선하기' }
  }
})

