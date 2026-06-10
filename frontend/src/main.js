import { createApp } from 'vue'
import { createPinia } from 'pinia'
import {
  NA,
  NAlert,
  NButton,
  NCard,
  NDatePicker,
  NDescriptions,
  NDescriptionsItem,
  NDivider,
  NDynamicInput,
  NEmpty,
  NForm,
  NFormItem,
  NGi,
  NGrid,
  NInput,
  NLi,
  NList,
  NListItem,
  NPopover,
  NSelect,
  NSpace,
  NSpin,
  NTag,
  NText,
  NThing,
  NUl
} from 'naive-ui'
import App from './App.vue'
import router from './router'
import './styles/main.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)

const naiveComponents = [
  ['NA', NA],
  ['NAlert', NAlert],
  ['NButton', NButton],
  ['NCard', NCard],
  ['NDatePicker', NDatePicker],
  ['NDescriptions', NDescriptions],
  ['NDescriptionsItem', NDescriptionsItem],
  ['NDivider', NDivider],
  ['NDynamicInput', NDynamicInput],
  ['NEmpty', NEmpty],
  ['NForm', NForm],
  ['NFormItem', NFormItem],
  ['NGi', NGi],
  ['NGrid', NGrid],
  ['NInput', NInput],
  ['NLi', NLi],
  ['NList', NList],
  ['NListItem', NListItem],
  ['NPopover', NPopover],
  ['NSelect', NSelect],
  ['NSpace', NSpace],
  ['NSpin', NSpin],
  ['NTag', NTag],
  ['NText', NText],
  ['NThing', NThing],
  ['NUl', NUl]
]

naiveComponents.forEach(([name, component]) => {
  app.component(name, component)
})
app.mount('#app')
