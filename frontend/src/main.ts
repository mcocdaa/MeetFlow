import { createApp } from 'vue'

import App from './App.vue'
import { loadPluginFrontendModules } from './plugins/runtime'
import router from './router'
import './styles.css'

void loadPluginFrontendModules()
createApp(App).use(router).mount('#app')
