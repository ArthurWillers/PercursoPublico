export default defineNuxtRouteMiddleware((to) => {
  to.meta.colorMode = 'light'
})
