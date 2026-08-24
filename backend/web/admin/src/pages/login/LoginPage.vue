<script setup lang="ts">
import { ref } from "vue";
import { ElMessage } from "element-plus";
import { useRoute, useRouter } from "vue-router";

import { useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();
const route = useRoute();
const router = useRouter();

const token = ref("");

async function submitLogin() {
  const trimmedToken = token.value.trim();
  if (!trimmedToken) {
    ElMessage.warning("请输入管理员 Token");
    return;
  }

  try {
    await authStore.login(trimmedToken);
    const rawRedirect = typeof route.query.redirect === "string" ? route.query.redirect : "/ai-dialog";
    const routerBase = import.meta.env.VITE_ROUTER_BASE;
    const redirectPath = rawRedirect.startsWith(routerBase)
      ? rawRedirect.slice(routerBase.length - 1)
      : rawRedirect;
    await router.replace(redirectPath);
    ElMessage.success("登录成功");
  } catch {
    ElMessage.error("Token 无效，请重新输入");
  }
}
</script>

<template>
  <section class="login-page">
    <el-card shadow="never" class="login-page__card">
      <div class="login-page__header">
        <h1>登录新后台</h1>
        <p>使用管理员 Token 进入 Vue 新后台，登录后会写入本地 Cookie。</p>
      </div>

      <el-form class="login-page__form" @submit.prevent="submitLogin">
        <el-form-item label="管理员 Token" required>
          <el-input
            v-model="token"
            type="password"
            show-password
            placeholder="请输入管理员 Token"
            @keyup.enter="submitLogin"
          />
        </el-form-item>

        <el-button
          type="primary"
          class="login-page__submit"
          :loading="authStore.loading"
          @click="submitLogin"
        >
          登录
        </el-button>
      </el-form>
    </el-card>
  </section>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
  background: linear-gradient(180deg, #fff8f6 0%, #fff 100%);
}

.login-page__card {
  width: min(440px, 100%);
  border-radius: 18px;
}

.login-page__header h1 {
  margin: 0;
  font-size: 28px;
}

.login-page__header p {
  margin: 10px 0 0;
  line-height: 1.6;
  color: var(--yx-text-muted);
}

.login-page__form {
  margin-top: 24px;
}

.login-page__submit {
  width: 100%;
}
</style>
