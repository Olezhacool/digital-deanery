// Telegram-бот: только входная точка. Отдаёт кнопку, открывающую мини-апп.
import { Bot, Keyboard } from "grammy";
import { env } from "./env.js";

const DISCLAIMER = "Концепт для конкурса, не официальный сервис вуза.";

export function createBot(): Bot {
  const bot = new Bot(env.botToken);

  bot.command("start", async (ctx) => {
    const k = new Keyboard().webApp("Открыть кабинет", env.webAppUrl).resized().oneTime();
    await ctx.reply(
      [
        "Привет! Это «Цифровой деканат будущего» — личный кабинет студента без очереди в деканат.",
        "",
        "Нажми кнопку ниже, чтобы открыть кабинет.",
        "",
        DISCLAIMER,
      ].join("\n"),
      { reply_markup: k }
    );
  });

  bot.command("help", async (ctx) => {
    await ctx.reply(
      [
        "Команды:",
        "/start — открыть личный кабинет",
        "/help — эта справка",
        "",
        DISCLAIMER,
      ].join("\n")
    );
  });

  bot.on("message", async (ctx) => {
    await ctx.reply("Все действия — внутри мини-приложения. Нажмите «Открыть кабинет».");
  });

  return bot;
}
