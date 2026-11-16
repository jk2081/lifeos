import { createApp } from 'vue'
import { FrappeUI, setConfig, frappeRequest } from 'frappe-ui'
import App from './App.vue'
import router from './router'
import './styles.css'
import { installLinkScope } from './framework/linkScope'

setConfig('resourceFetcher', frappeRequest)
installLinkScope()

const app = createApp(App)
app.use(FrappeUI)
app.use(router)
app.mount('#app')
