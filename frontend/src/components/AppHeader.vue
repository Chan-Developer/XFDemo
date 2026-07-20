<script setup>
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const isScrolled = ref(false)
const moreOpen = ref(false)

const handleScroll = () => {
  isScrolled.value = window.scrollY > 20
}

onMounted(() => {
  window.addEventListener('scroll', handleScroll)
})

onUnmounted(() => {
  window.removeEventListener('scroll', handleScroll)
})

const primaryItems = [
  { path: '/', label: '首页' },
  { path: '/inspect', label: '智能检测' },
  { path: '/pipes-counting', label: '型材计数' },
  { path: '/history', label: '检测历史' },
  { path: '/dataset', label: '数据集' }
]

const secondaryItems = [
  { path: '/regulations', label: '法规库' },
  { path: '/multimodal-search', label: '多模态检索' },
  { path: '/knowledge-graph', label: '知识图谱' },
  { path: '/about', label: '关于' }
]

const isSecondaryActive = computed(() => secondaryItems.some((item) => item.path === route.path))

const toggleMore = () => {
  moreOpen.value = !moreOpen.value
}

const closeMore = () => {
  moreOpen.value = false
}
</script>

<template>
  <header class="header" :class="{ 'header--scrolled': isScrolled }">
    <div class="header__container container">
      <router-link to="/" class="header__logo" aria-label="消防智检">
        <div class="header__logo-icon">
          <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2C8.5 2 6 5.5 6 9c0 4.5 6 11 6 11s6-6.5 6-11c0-3.5-2.5-7-6-7z" fill="currentColor" opacity="0.9"/>
            <circle cx="12" cy="9" r="2.5" fill="white"/>
          </svg>
        </div>
        <span class="header__logo-text">消防智检</span>
      </router-link>

      <nav class="header__nav" aria-label="主导航">
        <router-link
          v-for="item in primaryItems"
          :key="item.path"
          :to="item.path"
          class="header__nav-link"
          :class="{ 'header__nav-link--active': route.path === item.path }"
        >
          {{ item.label }}
        </router-link>

        <div
          class="header__more"
          :class="{ 'header__more--active': isSecondaryActive, 'header__more--open': moreOpen }"
          @mouseenter="moreOpen = true"
          @mouseleave="moreOpen = false"
        >
          <button
            class="header__more-button"
            type="button"
            :aria-expanded="moreOpen"
            @click.stop="toggleMore"
          >
            更多
          </button>
          <div class="header__more-menu">
            <router-link
              v-for="item in secondaryItems"
              :key="item.path"
              :to="item.path"
              class="header__more-link"
              :class="{ 'header__more-link--active': route.path === item.path }"
              @click="closeMore"
            >
              {{ item.label }}
            </router-link>
          </div>
        </div>
      </nav>

      <router-link to="/inspect" class="btn btn-primary btn-sm header__cta">
        开始检测
      </router-link>
    </div>
  </header>
</template>

<style scoped>
.header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 1000;
  padding: var(--spacing-md) 0;
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  transition: all var(--transition-base);
}

.header--scrolled {
  background: rgba(255, 255, 255, 0.96);
  box-shadow: var(--shadow-sm);
}

.header__container {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-lg);
}

.header__logo {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  flex: 0 0 auto;
  font-weight: 700;
  font-size: var(--font-size-lg);
}

.header__logo-icon {
  width: 32px;
  height: 32px;
  color: var(--color-primary);
}

.header__logo-icon svg {
  width: 100%;
  height: 100%;
}

.header__logo-text {
  color: var(--text-primary);
  white-space: nowrap;
}

.header__nav {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: clamp(0.8rem, 1.35vw, var(--spacing-xl));
  min-width: 0;
  flex: 1;
}

.header__nav-link,
.header__more-button,
.header__more-link {
  position: relative;
  white-space: nowrap;
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--text-secondary);
  transition: color var(--transition-fast), background var(--transition-fast);
}

.header__nav-link:hover,
.header__more-button:hover,
.header__more-link:hover {
  color: var(--text-primary);
}

.header__nav-link--active,
.header__more--active .header__more-button {
  color: var(--color-primary);
}

.header__nav-link--active::after,
.header__more--active .header__more-button::after {
  content: '';
  position: absolute;
  bottom: -7px;
  left: 50%;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--color-primary);
  transform: translateX(-50%);
}

.header__more {
  position: relative;
}

.header__more-button {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: 0;
  background: transparent;
  cursor: pointer;
  padding: 0;
}

.header__more-button span,
.header__more-button::after {
  content: none !important;
  display: none !important;
}


.header__more::after {
  content: '';
  position: absolute;
  left: -18px;
  right: -22px;
  top: 100%;
  height: 14px;
}

.header__more-menu {
  position: absolute;
  top: calc(100% + 10px);
  right: -22px;
  display: grid;
  min-width: 150px;
  padding: var(--spacing-xs);
  border: 1px solid var(--color-gray-100);
  border-radius: var(--radius-lg);
  background: var(--bg-primary);
  box-shadow: var(--shadow-lg);
  opacity: 0;
  pointer-events: none;
  transform: translateY(-6px);
  transition: opacity var(--transition-fast), transform var(--transition-fast);
}

.header__more--open .header__more-menu,
.header__more:hover .header__more-menu,
.header__more:focus-within .header__more-menu {
  opacity: 1;
  pointer-events: auto;
  transform: translateY(0);
}

.header__more-link {
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
}

.header__more-link--active,
.header__more-link:hover {
  background: var(--color-primary-subtle);
  color: var(--color-primary);
}

.header__cta {
  flex: 0 0 auto;
}

@media (max-width: 1020px) {
  .header__nav {
    justify-content: flex-start;
    overflow-x: auto;
    scrollbar-width: none;
  }

  .header__nav::-webkit-scrollbar {
    display: none;
  }

  .header__cta {
    display: none;
  }
}

@media (max-width: 640px) {
  .header__logo-text {
    display: none;
  }
}
</style>
