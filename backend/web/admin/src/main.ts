import { createApp } from "vue";
import ElementPlus from "element-plus";
import "element-plus/dist/index.css";

import App from "./App.vue";
import router, { pinia } from "./router";

import "./styles/variables.css";
import "./styles/global.css";
import "./styles/responsive.css";

const app = createApp(App);

app.use(pinia);
app.use(router);
app.use(ElementPlus);

app.mount("#app");
