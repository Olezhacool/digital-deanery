// Переменные окружения. Загружаются из .env (встроенный process.loadEnvFile, без dotenv).
try {
  if (typeof process.loadEnvFile === "function") process.loadEnvFile();
} catch {
  // .env нет — берём переменные из окружения напрямую.
}

export const env = {
  botToken: process.env.BOT_TOKEN ?? "",
  botUsername: process.env.BOT_USERNAME ?? "",
  webAppUrl: process.env.WEBAPP_URL ?? "http://localhost:5173",
  port: Number(process.env.PORT ?? 3000),
  authMaxAge: Number(process.env.AUTH_MAX_AGE ?? 86400),
  adminIds: (process.env.ADMIN_TG_IDS ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .map(Number),
  dev: process.env.DEV === "true",
};
