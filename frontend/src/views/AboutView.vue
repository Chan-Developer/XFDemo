<script setup>
const capabilities = [
  {
    category: '外部环境与标识',
    items: ['周边环境遮挡', '指示标识缺失/模糊', '消火栓箱体破损']
  },
  {
    category: '箱体结构',
    items: ['玻璃破损/缺失', '锁具异常', '箱内环境问题']
  },
  {
    category: '内部组件',
    items: ['消防水带缺失/老化', '水枪缺失/损坏', '阀门手轮缺失/损坏', '接口组件异常']
  },
  {
    category: '安装与功能',
    items: ['供水系统异常', '出水口规格不符', '设备功能失效']
  }
]

const techStack = [
  { name: 'AI引擎', desc: ' 视觉语言模型' },
  { name: '后端服务', desc: 'Flask RESTful API' },
  { name: '推理框架', desc: 'vLLM 高性能推理' },
  { name: '前端界面', desc: 'Vue 3 + Vite' }
]
</script>

<template>
  <div class="about">
    <div class="about__container container container-narrow">
      <!-- Hero -->
      <header class="about__header">
        <h1 class="about__title">关于系统</h1>
        <p class="about__subtitle">
          融合先进AI技术与消防专业知识的智能检测平台
        </p>
      </header>
      
      <!-- Introduction -->
      <section class="about__section">
        <h2 class="about__section-title">系统简介</h2>
        <div class="about__intro card">
          <p>
            消防安全智能检测系统是基于大型视觉语言模型（VLM）构建的专业消防设施合规性检测平台。
            系统扮演消防安全检查专家角色，能够对室内消火栓等消防设施进行智能化识别与合规性分析，
            自动生成包含隐患定位、严重程度、规范依据的专业检测报告。
          </p>
        </div>
      </section>
      
      <!-- Capabilities -->
      <section class="about__section">
        <h2 class="about__section-title">检测能力</h2>
        <div class="about__capabilities">
          <div 
            v-for="(cap, index) in capabilities" 
            :key="index" 
            class="about__capability card"
          >
            <h3 class="about__capability-title">
              <span class="about__capability-number">{{ index + 1 }}</span>
              {{ cap.category }}
            </h3>
            <ul class="about__capability-list">
              <li v-for="item in cap.items" :key="item">{{ item }}</li>
            </ul>
          </div>
        </div>
      </section>
      
      <!-- Tech Stack -->
      <section class="about__section">
        <h2 class="about__section-title">技术架构</h2>
        <div class="about__tech">
          <div 
            v-for="tech in techStack" 
            :key="tech.name" 
            class="about__tech-item"
          >
            <span class="about__tech-name">{{ tech.name }}</span>
            <span class="about__tech-desc">{{ tech.desc }}</span>
          </div>
        </div>
      </section>
      
      <!-- CTA -->
      <section class="about__cta">
        <router-link to="/inspect" class="btn btn-primary btn-lg">
          立即体验
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
            <path d="M5 12h14M12 5l7 7-7 7" stroke="currentColor" stroke-width="2" 
                  stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </router-link>
      </section>
    </div>
  </div>
</template>

<style scoped>
.about {
  padding: calc(80px + var(--spacing-3xl)) 0 var(--spacing-3xl);
  min-height: 100vh;
}

.about__header {
  text-align: center;
  margin-bottom: var(--spacing-3xl);
}

.about__title {
  font-size: var(--font-size-4xl);
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: var(--spacing-md);
}

.about__subtitle {
  font-size: var(--font-size-xl);
  color: var(--text-secondary);
}

.about__section {
  margin-bottom: var(--spacing-3xl);
}

.about__section-title {
  font-size: var(--font-size-2xl);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-xl);
  padding-left: var(--spacing-md);
  border-left: 3px solid var(--color-primary);
}

.about__intro {
  padding: var(--spacing-xl);
}

.about__intro p {
  font-size: var(--font-size-lg);
  line-height: 1.8;
  color: var(--text-secondary);
}

.about__capabilities {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: var(--spacing-lg);
}

.about__capability {
  padding: var(--spacing-xl);
}

.about__capability-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-md);
}

.about__capability-number {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  background: var(--color-primary-subtle);
  color: var(--color-primary);
  font-size: var(--font-size-sm);
  font-weight: 600;
  border-radius: var(--radius-full);
}

.about__capability-list {
  list-style: none;
}

.about__capability-list li {
  position: relative;
  padding-left: var(--spacing-lg);
  margin-bottom: var(--spacing-sm);
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.about__capability-list li::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-gray-300);
}

.about__tech {
  background: var(--bg-secondary);
  border-radius: var(--radius-xl);
  overflow: hidden;
}

.about__tech-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-lg) var(--spacing-xl);
  border-bottom: 1px solid var(--color-gray-200);
}

.about__tech-item:last-child {
  border-bottom: none;
}

.about__tech-name {
  font-weight: 600;
  color: var(--text-primary);
}

.about__tech-desc {
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
}

.about__cta {
  text-align: center;
  padding-top: var(--spacing-xl);
}

@media (max-width: 640px) {
  .about__tech-item {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-xs);
  }
}
</style>
