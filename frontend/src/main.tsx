import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import App from "@/App";
import { AuthStatusGate } from "@/components/auth/AuthStatusGate";
import { TelegramBackButton } from "@/components/layout/TelegramBackButton";
import { initTelegramShell } from "@/lib/telegram";
import "@/lib/theme";
import "@/index.css";

// Inside Telegram: full screen, matching colours, no swipe-to-close.
initTelegramShell();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <TelegramBackButton />
        <AuthStatusGate>
          <App />
        </AuthStatusGate>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>
);
