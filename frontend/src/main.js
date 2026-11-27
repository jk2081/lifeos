import { createApp } from 'vue'
import { FrappeUI, setConfig, frappeRequest } from 'frappe-ui'
import App from './App.vue'
import router from './router'
import './styles.css'
import { installLinkScope } from './framework/linkScope'
import { installDocCache } from './lib/docCache'
import { appErrorHandler, routerErrorHandler } from './lib/screenError'

setConfig('resourceFetcher', frappeRequest)
installLinkScope()
installDocCache()

const app = createApp(App)
app.use(FrappeUI)
app.use(router)
// a screen that fails shows a message in the page area instead of stopping the app (bug fix 1; ScreenBoundary in App.vue)
app.config.errorHandler = appErrorHandler
router.onError((err, to) => routerErrorHandler(err, to && router.resolve(to)))
app.mount('#app')
// the phone app (issue 50): a service worker for /life that caches only the app's own static files and takes what other apps share
if ('serviceWorker' in navigator) navigator.serviceWorker.register('/life/sw.js', { scope: '/life/' }).catch(() => {})
