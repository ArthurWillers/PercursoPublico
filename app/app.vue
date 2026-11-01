<script setup lang="ts">
useHead({
  meta: [
    { name: 'viewport', content: 'width=device-width, initial-scale=1' }
  ],
  link: [
    { rel: 'icon', href: '/favicon.ico' }
  ],
  htmlAttrs: {
    lang: 'pt-BR'
  }
})
</script>

<template>
  <UApp>
    <div class="site-shell">
      <header class="site-header">
        <NuxtLink
          to="/"
          class="brand"
          aria-label="Parlamentares — início"
        >
          <span class="brand-mark"><UIcon
            name="i-lucide-landmark"
            aria-hidden="true"
          /></span>
          <span class="brand-name">Parlamentares</span>
          <span
            class="brand-divider"
            aria-hidden="true"
          />
          <span class="brand-detail">Cota em foco</span>
        </NuxtLink>

        <nav
          class="main-nav"
          aria-label="Navegação principal"
        >
          <NuxtLink to="/">Visão geral</NuxtLink>
          <NuxtLink :to="{ path: '/gastos' }">Parlamentares</NuxtLink>
          <NuxtLink :to="{ path: '/gastos', query: { visao: 'fornecedores' } }">Fornecedores</NuxtLink>
          <NuxtLink to="/eleicoes">Eleições (TSE)</NuxtLink>
          <NuxtLink to="/fontes">Fontes e método</NuxtLink>
        </nav>
      </header>

      <UMain class="site-main">
        <NuxtPage />
      </UMain>

      <footer class="site-footer">
        <NuxtLink
          to="/"
          class="footer-brand"
        >Parlamentares</NuxtLink>
        <p>Despesas públicas com fonte, período e cobertura à vista.</p>
        <NuxtLink to="/fontes">Fontes e metodologia</NuxtLink>
        <a href="/#page-title">Voltar ao início <UIcon
          name="i-lucide-arrow-up"
          aria-hidden="true"
        /></a>
      </footer>
    </div>
  </UApp>
</template>
