<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const isScrolled = ref(false)

const handleScroll = () => {
  isScrolled.value = window.scrollY > 20
}

onMounted(() => {
  window.addEventListener('scroll', handleScroll)
})

onUnmounted(() => {
  window.removeEventListener('scroll', handleScroll)
})

const navItems = [
  { path: '/', label: '首页' },
  { path: '/inspect', label: '智能检测' },
  { path: '/history', label: '\u68c0\u6d4b\u5386\u53f2' },
  { path: '/dataset', label: '\u6570\u636e\u96c6' },
  { path: '/knowledge-graph', label: '\u77e5\u8bc6\u56fe\u8c31' },
  { path: '/about', label: '关于' }
]
</script>

<template>
  <header class="header" :class="{ 'header--scrolled': isScrolled }">
    <div class="header__container container">
      <router-link to="/" class="header__logo">
        <div class="header__logo-icon">
          <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2C8.5 2 6 5.5 6 9c0 4.5 6 11 6 11s6-6.5 6-11c0-3.5-2.5-7-6-7z" 
                  fill="currentColor" opacity="0.9"/>
            <circle cx="12" cy="9" r="2.5" fill="white"/>
          </svg>
        </div>
        <span class="header__logo-text">消防智检</span>
      </router-link>
      
      <nav class="header__nav">
        <router-link
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="header__nav-link"
          :class="{ 'header__nav-link--active': route.path === item.path }"
        >
          {{ item.label }}
        </router-link>
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
  transition: all var(--transition-base);
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
}

.header--scrolled {
  background: rgba(255, 255, 255, 0.95);
  box-shadow: var(--shadow-sm);
}

.header__container {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header__logo {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-weight: 600;
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
}

.header__nav {
  display: flex;
  align-items: center;
  gap: var(--spacing-lg);
}

.header__nav-link {
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--text-secondary);
  transition: color var(--transition-fast);
  position: relative;
}

.header__nav-link:hover {
  color: var(--text-primary);
}

.header__nav-link--active {
  color: var(--color-primary);
}

.header__nav-link--active::after {
  content: '';
  position: absolute;
  bottom: -4px;
  left: 50%;
  transform: translateX(-50%);
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--color-primary);
}

.header__cta {
  display: none;
}

@media (min-width: 768px) {
  .header__cta {
    display: inline-flex;
  }
}

@media (max-width: 640px) {
  .header__container {
    gap: var(--spacing-md);
  }

  .header__logo-text {
    display: none;
  }

  .header__nav {
    flex: 1;
    gap: var(--spacing-md);
    overflow-x: auto;
    scrollbar-width: none;
  }

  .header__nav::-webkit-scrollbar {
    display: none;
  }

  .header__nav-link {
    flex: 0 0 auto;
  }
}
</style>
