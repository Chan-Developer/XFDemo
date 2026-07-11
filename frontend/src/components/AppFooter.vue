<script setup>
const currentYear = new Date().getFullYear()
</script>

<template>
  <footer class="footer">
    <div class="footer__container container">
      <div class="footer__content">
        <div class="footer__brand">
          <div class="footer__logo">
            <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M12 2C8.5 2 6 5.5 6 9c0 4.5 6 11 6 11s6-6.5 6-11c0-3.5-2.5-7-6-7z" 
                    fill="currentColor" opacity="0.9"/>
              <circle cx="12" cy="9" r="2.5" fill="white"/>
            </svg>
            <span>消防智检</span>
          </div>
          <p class="footer__desc">
            AI驱动的消防安全智能检测系统，助力消防设施合规管理
          </p>
        </div>
        
        <div class="footer__links">
          <div class="footer__links-group">
            <h4>产品</h4>
            <router-link to="/inspect">智能检测</router-link>
            <router-link to="/dataset">&#25968;&#25454;&#38598;</router-link>
            <router-link to="/about">了解更多</router-link>
          </div>
          <div class="footer__links-group">
            <h4>支持</h4>
            <a href="#">使用文档</a>
            <a href="#">常见问题</a>
          </div>
        </div>
      </div>
      
      <div class="footer__bottom">
        <p>&copy; {{ currentYear }} 消防智检. All rights reserved.</p>
        <p class="footer__tech">Powered by AI Vision-Language Model</p>
      </div>
    </div>
  </footer>
</template>

<style scoped>
.footer {
  background: var(--bg-secondary);
  padding: var(--spacing-3xl) 0 var(--spacing-xl);
  margin-top: var(--spacing-4xl);
}

.footer__content {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--spacing-2xl);
  padding-bottom: var(--spacing-2xl);
  border-bottom: 1px solid var(--color-gray-200);
}

@media (min-width: 768px) {
  .footer__content {
    grid-template-columns: 2fr 1fr;
  }
}

.footer__brand {
  max-width: 320px;
}

.footer__logo {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-weight: 600;
  font-size: var(--font-size-lg);
  color: var(--text-primary);
  margin-bottom: var(--spacing-md);
}

.footer__logo svg {
  width: 28px;
  height: 28px;
  color: var(--color-primary);
}

.footer__desc {
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
  line-height: 1.7;
}

.footer__links {
  display: flex;
  gap: var(--spacing-3xl);
}

.footer__links-group h4 {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--spacing-md);
}

.footer__links-group a {
  display: block;
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-sm);
  transition: color var(--transition-fast);
}

.footer__links-group a:hover {
  color: var(--color-primary);
}

.footer__bottom {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-xs);
  padding-top: var(--spacing-xl);
  text-align: center;
}

.footer__bottom p {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.footer__tech {
  font-size: var(--font-size-xs) !important;
}

@media (min-width: 768px) {
  .footer__bottom {
    flex-direction: row;
    justify-content: space-between;
  }
}
</style>
