// Точка входа: поднимает API и запускает бота (long polling).
import { serve } from "@hono/node-server";
import { app } from "./api.js";
import { createBot } from "./bot.js";
import { env } from "./env.js";

if (!env.botToken) {
  console.error(
    "BOT_TOKEN не задан. Скопируй server/.env.example в server/.env и впиши токен от @BotFather."
  );
  process.exit(1);
}

serve({ fetch: app.fetch, port: env.port }, (info) => {
  console.log(`API: http://localhost:${info.port}/api/health`);
});

const bot = createBot();
bot.start({
  onStart: (me) => console.log(`Бот @${me.username} запущен (long polling)`),
});
