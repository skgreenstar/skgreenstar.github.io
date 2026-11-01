import { defineConfig } from 'vitepress'

export default defineConfig({
  lang: 'ko-KR',
  title: 'Heemin',
  description: 'AI Engineering · MLOps · LLMOps · RAG · Agent',
  cleanUrls: true,
  appearance: false,
  lastUpdated: true,
  head: [['meta', { name: 'theme-color', content: '#ffffff' }]],
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
          { text: '04 · MLflow 학습·등록·재로딩', link: '/ml-platform/mlflow-model-lifecycle' },
          { text: '05 · Feast·KFP 연결 설계', link: '/ml-platform/model-pipeline' },
          { text: '06 · 운영 자동화', link: '/ml-platform/week-04' },
          { text: '07 · 리소스 관리와 성능 실험', link: '/ml-platform/week-05' },
          { text: '08 · KServe와 vLLM', link: '/ml-platform/week-06' }
        ]},
        { text: '심화 · Evaluation', items: [
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
