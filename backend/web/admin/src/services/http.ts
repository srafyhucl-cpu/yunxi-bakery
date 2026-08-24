import axios from "axios";

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE,
  withCredentials: true,
  timeout: 60000,
});

http.interceptors.response.use(
  (response) => response,
  (error) => {
    const requestUrl = String(error.config?.url || "");
    const routerBase = import.meta.env.VITE_ROUTER_BASE;
    const isProfileCheck = /(?:^|\/)me(?:\?|$)/.test(requestUrl);
    const isLoginPage = window.location.pathname === `${routerBase}login`;

    if (error.response?.status === 401 && !isProfileCheck && !isLoginPage) {
      const currentPath = window.location.pathname.startsWith(routerBase)
        ? window.location.pathname.slice(routerBase.length - 1)
        : window.location.pathname;
      const redirect = `${currentPath}${window.location.search}`;
      window.location.href = `${routerBase}login?redirect=${encodeURIComponent(redirect)}`;
    }
    return Promise.reject(error);
  },
);

export default http;
