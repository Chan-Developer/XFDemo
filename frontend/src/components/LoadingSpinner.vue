<script setup>
defineProps({
  size: {
    type: String,
    default: 'md',
    validator: (v) => ['sm', 'md', 'lg'].includes(v)
  },
  text: {
    type: String,
    default: ''
  }
})
</script>

<template>
  <div class="spinner" :class="`spinner--${size}`">
    <div class="spinner__ring">
      <div class="spinner__ring-inner"></div>
    </div>
    <p v-if="text" class="spinner__text">{{ text }}</p>
  </div>
</template>

<style scoped>
.spinner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-md);
}

.spinner__ring {
  position: relative;
  border-radius: 50%;
  background: conic-gradient(
    from 0deg,
    transparent 0deg,
    var(--color-primary) 60deg,
    transparent 120deg
  );
  animation: spin 1s linear infinite;
}

.spinner--sm .spinner__ring {
  width: 24px;
  height: 24px;
  padding: 3px;
}

.spinner--md .spinner__ring {
  width: 40px;
  height: 40px;
  padding: 4px;
}

.spinner--lg .spinner__ring {
  width: 56px;
  height: 56px;
  padding: 5px;
}

.spinner__ring-inner {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  background: var(--bg-primary);
}

.spinner__text {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  animation: pulse 2s ease-in-out infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
