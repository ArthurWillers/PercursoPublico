<script setup lang="ts">
import { pt_br } from '@nuxt/ui/locale'

const { brand } = useAppConfig()
const route = useRoute()
const baseURL = useRuntimeConfig().app.baseURL
const navigation = [
  { label: 'Pessoas', path: '/pessoas', icon: 'i-lucide-user-round-search' },
  { label: 'Visão geral', path: '/', icon: 'i-lucide-chart-no-axes-combined' },
  { label: 'Parlamentares', path: '/gastos', icon: 'i-lucide-users-round' },
  { label: 'Fornecedores', path: '/gastos', query: { visao: 'fornecedores' }, icon: 'i-lucide-building-2' },
  { label: 'Eleições', path: '/eleicoes', icon: 'i-lucide-vote' },
  { label: 'Fontes e método', path: '/fontes', icon: 'i-lucide-book-open' }
]
function isActive(item: typeof navigation[number]) {
  if (item.path === '/gastos') return route.path.startsWith('/gastos') && (route.query.visao === 'fornecedores') === Boolean(item.query)
  return route.path === item.path
}
useSeoMeta({ ogSiteName: brand.name })

useHead({
  titleTemplate: title => title ? `${title} | ${brand.name}` : brand.name,
  meta: [
    { name: 'viewport', content: 'width=device-width, initial-scale=1' },
    { name: 'application-name', content: brand.name }
  ],
  link: [
    { rel: 'icon', href: `${baseURL.replace(/\/+$/, '')}/favicon.ico` }
  ],
  htmlAttrs: {
    lang: 'pt-BR'
  }
})
</script>

<template>
  <UApp :locale="pt_br">
    <div
      id="top"
      class="site-shell"
    >
      <a
        class="skip-link"
        href="#main-content"
      >Pular para o conteúdo</a>
      <header class="site-header">
        <NuxtLink
          to="/"
          class="brand"
          :aria-label="`${brand.name} — início`"
        >
          <span class="brand-mark"><UIcon
            name="i-lucide-landmark"
            aria-hidden="true"
          /></span>
          <span class="brand-name">{{ brand.name }}</span>
          <span
            class="brand-divider"
            aria-hidden="true"
          />
          <span class="brand-detail">{{ brand.tagline }}</span>
        </NuxtLink>

        <nav
          class="main-nav"
          aria-label="Navegação principal"
        >
          <NuxtLink
            v-for="item in navigation"
            :key="item.label"
            :to="{ path: item.path, query: item.query }"
            :class="{ 'is-active': isActive(item) }"
            :aria-current="isActive(item) ? 'page' : undefined"
          >
            <UIcon
              :name="item.icon"
              aria-hidden="true"
            />
            {{ item.label }}
          </NuxtLink>
        </nav>
      </header>

      <UMain
        id="main-content"
        class="site-main"
        tabindex="-1"
      >
        <NuxtPage />
      </UMain>

      <footer class="site-footer">
        <NuxtLink
          to="/"
          class="footer-brand"
        >{{ brand.name }}</NuxtLink>
        <p>{{ brand.tagline }}</p>
        <NuxtLink to="/fontes">Fontes e metodologia</NuxtLink>
        <a href="#top">Voltar ao início <UIcon
          name="i-lucide-arrow-up"
          aria-hidden="true"
        /></a>
      </footer>
    </div>
  </UApp>
</template>
