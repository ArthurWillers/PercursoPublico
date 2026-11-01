// https://nuxt.com/docs/api/configuration/nuxt-config
import manifest from './public/data/manifest.json'

const nodeEnvironment = globalThis as typeof globalThis & { process?: { env?: Record<string, string | undefined> } }

export default defineNuxtConfig({
  modules: [
    '@nuxt/eslint',
    '@nuxt/ui'
  ],

  $production: {
    devtools: {
      enabled: false
    },
    routeRules: {
      '/**': { prerender: true }
    },
    nitro: {
      // Arquivos grandes são compactados diretamente pelo pipeline após generate.
      // Evita duplicar mais de 6 GB de JSON bruto no disco do Actions.
      ignore: ['**/data/expenses/**', '**/data/members/**', '**/data/summary-*.json', '**/data/suppliers-*.json', '**/data/elections-*.json'],
      prerender: {
        crawlLinks: false,
        concurrency: 4,
        routes: [
          '/',
          '/gastos',
          '/eleicoes',
          '/fontes',
          ...manifest.profileIds.map(id => `/gastos/${id.replace(':', '-')}`)
        ]
      }
    }
  },

  devtools: {
    enabled: true
  },

  app: {
    baseURL: nodeEnvironment.process?.env?.NUXT_APP_BASE_URL || '/'
  },

  css: ['~/assets/css/main.css'],

  compatibilityDate: '2026-06-30',

  typescript: {
    strict: true
  },

  eslint: {
    config: {
      stylistic: {
        commaDangle: 'never',
        braceStyle: '1tbs'
      }
    }
  },

  icon: {
    mode: 'svg'
  }
})
