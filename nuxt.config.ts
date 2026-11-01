// https://nuxt.com/docs/api/configuration/nuxt-config
import { readFileSync } from 'node:fs'
import manifest from './schemas/manifest.empty.json' with { type: 'json' }

interface ManifestReference {
  profileIds?: string[]
}

const nodeEnvironment = globalThis as typeof globalThis & {
  process?: {
    env?: Record<string, string | undefined>
  }
}

function resolveProfileIds(): string[] {
  try {
    const loaded: ManifestReference = JSON.parse(readFileSync(new URL('./public/data/manifest.json', import.meta.url), 'utf8'))
    if (loaded && Array.isArray(loaded.profileIds)) {
      return loaded.profileIds
    }
  } catch {
    // Arquivo ainda não gerado ou em ambiente sem dados
  }
  return manifest.profileIds || []
}

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
      ignore: ['**/data/people/**', '**/data/people.json', '**/data/expenses/**', '**/data/members/**', '**/data/summary-*.json', '**/data/suppliers-*.json', '**/data/elections-*.json'],
      prerender: {
        crawlLinks: false,
        concurrency: 4,
        routes: [
          '/',
          '/gastos',
          '/pessoas',
          '/eleicoes',
          '/fontes',
          ...resolveProfileIds().map(id => `/gastos/${id.replace(':', '-')}`)
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

  colorMode: {
    preference: 'light',
    fallback: 'light'
  },

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
    mode: 'svg',
    // A hospedagem estática não oferece o endpoint de ícones do Nuxt.
    clientBundle: {
      scan: true
    }
  }
})
