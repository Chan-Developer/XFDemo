<script setup>
import { ref, onMounted } from 'vue'
import { checkHealth } from '@/api'

const systemStatus = ref('checking')

const features = [
  {
    icon: `<svg viewBox="0 0 24 24" fill="none"><path d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" stroke="currentColor" stroke-width="1.5"/><path d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" stroke="currentColor" stroke-width="1.5"/></svg>`,
    title: '视觉识别',
    desc: '基于先进的视觉语言模型，精准识别消防设施状态'
  },
  {
    icon: `<svg viewBox="0 0 24 24" fill="none"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" stroke="currentColor" stroke-width="1.5"/></svg>`,
    title: '合规检测',
    desc: '自动对照消防规范标准，输出专业检测报告'
  },
  {
    icon: `<svg viewBox="0 0 24 24" fill="none"><path d="M13 10V3L4 14h7v7l9-11h-7z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
    title: '即时响应',
    desc: '秒级分析响应，高效完成大规模检测任务'
  }
]

onMounted(async () => {
  try {
    const res = await checkHealth()
    systemStatus.value = res.status === 'running' ? 'online' : 'offline'
  } catch {
    systemStatus.value = 'offline'
  }
})
</script>

<template>
  <div class="home">
    <!-- Hero Section -->
    <section class="hero">
      <div class="hero__container container">
        <div class="hero__badge animate-fade-in">
          <span class="hero__badge-dot" :class="`hero__badge-dot--${systemStatus}`"></span>
          <span>{{ systemStatus === 'online' ? '系统运行中' : systemStatus === 'checking' ? '检测中...' : '系统离线' }}</span>
        </div>
        
        <h1 class="hero__title animate-slide-up">
          消防安全<br />
          <span class="hero__title-accent">智能检测系统</span>
        </h1>
        
        <p class="hero__subtitle animate-slide-up">
          基于先进AI视觉语言模型，为消防设施提供智能化合规性检测服务
        </p>
        
        <div class="hero__actions animate-slide-up">
          <router-link to="/inspect" class="btn btn-primary btn-lg">
            开始检测
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <path d="M5 12h14M12 5l7 7-7 7" stroke="currentColor" stroke-width="2" 
                    stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </router-link>
          <router-link to="/about" class="btn btn-secondary btn-lg">
            了解更多
          </router-link>
        </div>
      </div>
      
      <!-- Background Decoration -->
      <div class="hero__bg">
        <div class="hero__bg-circle hero__bg-circle--1"></div>
        <div class="hero__bg-circle hero__bg-circle--2"></div>
      </div>
    </section>
    
    <!-- Features Section -->
    <section class="features">
      <div class="features__container container">
        <div class="features__header">
          <h2 class="features__title">核心能力</h2>
          <p class="features__subtitle">
            融合视觉AI与消防专业知识，实现智能化检测
          </p>
        </div>
        
        <div class="features__grid">
          <div v-for="(feature, index) in features" :key="index" class="feature-card card">
            <div class="feature-card__icon" v-html="feature.icon"></div>
            <h3 class="feature-card__title">{{ feature.title }}</h3>
            <p class="feature-card__desc">{{ feature.desc }}</p>
          </div>
        </div>
      </div>
    </section>
    
    <!-- CTA Section -->
    <section class="cta">
      <div class="cta__container container container-narrow">
        <div class="cta__card">
          <h2 class="cta__title">立即体验智能检测</h2>
          <p class="cta__desc">
            上传消防栓图片，获取专业的合规性检测报告
          </p>
          <router-link to="/inspect" class="btn btn-primary btn-lg">
            开始使用
          </router-link>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
/* Hero */
.hero {
  position: relative;
  min-height: 100vh;
  display: flex;
  align-items: center;
  padding: var(--spacing-4xl) 0;
  overflow: hidden;
}

.hero__container {
  position: relative;
  z-index: 1;
  text-align: center;
  max-width: 800px;
}

.hero__badge {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--bg-secondary);
  border-radius: var(--radius-full);
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-xl);
}

.hero__badge-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-gray-400);
}

.hero__badge-dot--online {
  background: var(--color-success);
  animation: pulse 2s ease-in-out infinite;
}

.hero__badge-dot--offline {
  background: var(--color-error);
}

.hero__badge-dot--checking {
  background: var(--color-warning);
  animation: pulse 1s ease-in-out infinite;
}

.hero__title {
  font-size: var(--font-size-5xl);
  font-weight: 700;
  line-height: 1.1;
  color: var(--text-primary);
  margin-bottom: var(--spacing-lg);
  letter-spacing: -0.02em;
}

.hero__title-accent {
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-primary-light) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.hero__subtitle {
  font-size: var(--font-size-xl);
  color: var(--text-secondary);
  max-width: 560px;
  margin: 0 auto var(--spacing-2xl);
  line-height: 1.6;
}

.hero__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: var(--spacing-md);
}

.hero__bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.hero__bg-circle {
  position: absolute;
  border-radius: 50%;
  opacity: 0.1;
}

.hero__bg-circle--1 {
  width: 600px;
  height: 600px;
  background: var(--color-primary);
  top: -200px;
  right: -200px;
}

.hero__bg-circle--2 {
  width: 400px;
  height: 400px;
  background: var(--color-primary-light);
  bottom: -100px;
  left: -100px;
}

/* Features */
.features {
  padding: var(--spacing-4xl) 0;
  background: var(--bg-secondary);
}

.features__header {
  text-align: center;
  margin-bottom: var(--spacing-3xl);
}

.features__title {
  font-size: var(--font-size-3xl);
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: var(--spacing-md);
}

.features__subtitle {
  font-size: var(--font-size-lg);
  color: var(--text-secondary);
}

.features__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--spacing-xl);
}

.feature-card {
  text-align: center;
  padding: var(--spacing-2xl);
}

.feature-card__icon {
  width: 48px;
  height: 48px;
  margin: 0 auto var(--spacing-lg);
  color: var(--color-primary);
}

.feature-card__icon :deep(svg) {
  width: 100%;
  height: 100%;
}

.feature-card__title {
  font-size: var(--font-size-xl);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-sm);
}

.feature-card__desc {
  font-size: var(--font-size-base);
  color: var(--text-secondary);
  line-height: 1.6;
}

/* CTA */
.cta {
  padding: var(--spacing-4xl) 0;
}

.cta__card {
  text-align: center;
  padding: var(--spacing-3xl);
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-primary-dark) 100%);
  border-radius: var(--radius-2xl);
  color: var(--text-inverse);
}

.cta__title {
  font-size: var(--font-size-3xl);
  font-weight: 700;
  margin-bottom: var(--spacing-md);
}

.cta__desc {
  font-size: var(--font-size-lg);
  opacity: 0.9;
  margin-bottom: var(--spacing-xl);
}

.cta__card .btn {
  background: white;
  color: var(--color-primary);
}

.cta__card .btn:hover {
  background: var(--color-gray-100);
  transform: translateY(-2px);
}

@media (max-width: 768px) {
  .hero {
    min-height: auto;
    padding: calc(80px + var(--spacing-3xl)) 0 var(--spacing-3xl);
  }
  
  .hero__title {
    font-size: var(--font-size-4xl);
  }
  
  .hero__subtitle {
    font-size: var(--font-size-lg);
  }
}
</style>
