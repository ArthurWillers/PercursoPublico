export default defineAppConfig({
  brand: {
    name: 'Percurso Público',
    tagline: 'Pessoas, mandatos e eleições.'
  },
  ui: {
    colors: {
      primary: 'teal',
      neutral: 'slate'
    },
    modal: {
      slots: {
        wrapper: 'min-w-0 pe-12',
        title: 'text-xl'
      }
    }
  }
})
