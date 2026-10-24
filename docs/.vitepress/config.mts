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
      { text: 'ML Platform Study', link: '/ml-platform/week-01' },
      { text: 'About', link: '/about' },
      { text: 'GitHub ↗', link: 'https://github.com/skgreenstar' }
    ],
    sidebar: {
      '/ml-platform/': [
        { text: 'ML Platform Engineering', items: [
          { text: 'Overview', link: '/ml-platform/' },
          { text: '01 · Beyond Model Accuracy', link: '/ml-platform/week-01' },
          { text: '02 · MLflow / Feast / Kubeflow (예정)', link: '/ml-platform/' }
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
