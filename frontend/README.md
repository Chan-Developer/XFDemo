# 消防安全智能检测系统 - 前端

基于 Vue 3 + Vite 构建的消防安全智能检测系统前端界面。

## 技术栈

- **Vue 3** - 渐进式 JavaScript 框架
- **Vite** - 下一代前端构建工具
- **Vue Router** - 官方路由管理器
- **Axios** - HTTP 客户端

## 设计理念

- **简约美学** - Apple 风格的极简设计语言
- **消防特色** - 专业的消防红配色体系
- **响应式布局** - 完美适配桌面和移动端
- **流畅动画** - 精心设计的交互动效

## 快速开始

### 安装依赖

```bash
npm install
```

### 启动开发服务器

```bash
npm run dev
```

开发服务器将在 http://localhost:3000 启动

### 构建生产版本

```bash
npm run build
```

## 项目结构

```
frontend/
├── src/
│   ├── api/           # API 接口封装
│   ├── components/    # 通用组件
│   │   ├── AppHeader.vue
│   │   ├── AppFooter.vue
│   │   ├── ImageUploader.vue
│   │   └── LoadingSpinner.vue
│   ├── router/        # 路由配置
│   ├── styles/        # 全局样式
│   │   └── main.css   # 设计系统
│   ├── views/         # 页面组件
│   │   ├── HomeView.vue
│   │   ├── InspectView.vue
│   │   └── AboutView.vue
│   ├── App.vue        # 根组件
│   └── main.js        # 入口文件
├── index.html
├── package.json
├── vite.config.js
└── README.md
```

## API 代理配置

开发环境下，所有 `/api` 请求会自动代理到后端服务 `http://localhost:5000`。

## 后端接口

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /health | 健康检查 |
| POST | /chat | 消防安全检测 |

### 检测接口参数

```json
{
  "query": "检测问题描述（必填）",
  "image": "图片Base64或URL（可选）"
}
```

## 开发规范

- 使用 Composition API + `<script setup>` 语法
- 组件命名采用 PascalCase
- CSS 使用 BEM 命名规范
- 遵循 ESLint 代码规范
