<script setup lang="ts">
const name = ref('')
function findPerson() {
  return navigateTo({ path: '/pessoas', query: { busca: name.value || undefined } })
}
</script>

<template>
  <section
    class="person-search-entry"
    aria-labelledby="find-person-title"
  >
    <div>
      <h2 id="find-person-title">
        Quem você quer consultar?
      </h2><p>Encontre a pessoa para acessar mandatos, gastos e candidaturas em diferentes anos.</p>
    </div>
    <form @submit.prevent="findPerson">
      <UFormField label="Nome da pessoa">
        <UInput
          v-model="name"
          type="search"
          size="xl"
          icon="i-lucide-search"
          placeholder="Nome civil ou nome de urna"
          class="w-full"
        />
      </UFormField>
      <UButton
        type="submit"
        size="xl"
      >
        Buscar pessoa
      </UButton>
    </form>
  </section>
</template>
