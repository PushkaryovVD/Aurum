import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { telegramWebApp } from "@/lib/telegram";

// Top-level screens have nothing to go back to; Telegram shows its own
// "Close" there instead.
const ROOT_PATHS = new Set(["/", "/login"]);

/** Drives Telegram's native back button from the router. Renders nothing and
 * does nothing outside a Telegram Mini App. */
export function TelegramBackButton() {
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    const backButton = telegramWebApp()?.BackButton;
    if (!backButton) return;
    if (ROOT_PATHS.has(location.pathname)) {
      backButton.hide();
      return;
    }
    // "default" is the entry the app was opened on: with no in-app history,
    // going back would leave Aurum, so return to the dashboard instead.
    const onBack = () => (location.key === "default" ? navigate("/") : navigate(-1));
    backButton.onClick(onBack);
    backButton.show();
    return () => backButton.offClick(onBack);
  }, [location.key, location.pathname, navigate]);

  return null;
}
