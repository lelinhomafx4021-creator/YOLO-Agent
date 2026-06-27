/**
 * 主入口文件 - 应用启动模块
 *
 * 该文件负责初始化 Vue 应用实例，注册路由插件，
 * 并将应用挂载到 DOM 中的 #app 元素上。
 */

import { createApp } from 'vue'        // 从 Vue 框架导入创建应用实例的方法
import App from './App.vue'            // 引入根组件 App.vue
import router from './router'          // 引入路由配置模块
import './style.css'                   // 引入全局样式文件

// 创建 Vue 应用实例，注册路由插件，挂载到 #app 容器
createApp(App).use(router).mount('#app')
