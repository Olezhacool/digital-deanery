// Проверка подписи initData Telegram (без паролей: личность = подпись Telegram).
import { createHmac, timingSafeEqual } from "node:crypto";
import { env } from "./env.js";

export interface TgUser {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
}

/**
 * Валидирует initData по официальной схеме Telegram:
 * secret_key = HMAC_SHA256(key="WebAppData", msg=BOT_TOKEN),
 * hash = HMAC_SHA256(key=secret_key, msg=data_check_string).
 * Возвращает пользователя или null.
 */
export function validateInitData(initData: string): TgUser | null {
  if (!env.botToken) return null;

  const params = new URLSearchParams(initData);
  const hash = params.get("hash");
  if (!hash) return null;
  params.delete("hash");

  const dataCheckString = [...params.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${k}=${v}`)
    .join("\n");

  const secretKey = createHmac("sha256", "WebAppData").update(env.botToken).digest();
  const calc = createHmac("sha256", secretKey).update(dataCheckString).digest();

  const calcBuf = Buffer.from(calc);
  const hashBuf = Buffer.from(hash, "hex");
  if (calcBuf.length !== hashBuf.length || !timingSafeEqual(calcBuf, hashBuf)) return null;

  const authDate = Number(params.get("auth_date") ?? 0);
  if (Math.abs(Date.now() / 1000 - authDate) > env.authMaxAge) return null;

  const raw = params.get("user");
  if (!raw) return null;
  try {
    const u = JSON.parse(raw);
    return {
      id: Number(u.id),
      first_name: String(u.first_name ?? ""),
      last_name: u.last_name ? String(u.last_name) : undefined,
      username: u.username ? String(u.username) : undefined,
    };
  } catch {
    return null;
  }
}
