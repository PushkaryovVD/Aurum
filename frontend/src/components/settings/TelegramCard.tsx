import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Link2, Unlink } from "lucide-react";
import { createTelegramLinkCode, fetchTelegramStatus, unlinkTelegram, type TelegramLinkCode } from "@/api/telegram";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { useTranslation } from "@/lib/i18n";

export function TelegramCard() {
  const { t } = useTranslation();
  const client = useQueryClient();
  const [issued, setIssued] = useState<TelegramLinkCode | null>(null);
  const status = useQuery({ queryKey: ["telegram-status"], queryFn: fetchTelegramStatus });
  const createCode = useMutation({
    mutationFn: createTelegramLinkCode,
    onSuccess: setIssued,
  });
  const unlink = useMutation({
    mutationFn: unlinkTelegram,
    onSuccess: async () => {
      setIssued(null);
      await client.invalidateQueries({ queryKey: ["telegram-status"] });
    },
  });

  if (status.isLoading) return null;
  const value = status.data;
  const error = status.isError || createCode.isError || unlink.isError;

  return <Card>
    <CardHeader><CardTitle>{t("telegram.title")}</CardTitle></CardHeader>
    <CardContent className="space-y-4">
      <p className="text-sm text-text-secondary">{t("telegram.description")}</p>
      {!value?.configured && <p className="text-sm text-warning">{t("telegram.notConfigured")}</p>}
      {value?.configured && !value.mini_app_configured && (
        <p className="text-sm text-text-muted">{t("telegram.botOnly")}</p>
      )}
      {value?.linked && <p className="text-sm text-success">
        {t("telegram.linked", { username: value.username ? `@${value.username}` : t("telegram.account") })}
      </p>}
      <div className="flex flex-col gap-2 sm:flex-row">
        <Button
          type="button"
          disabled={!value?.configured || createCode.isPending}
          onClick={() => createCode.mutate()}
        >
          <Link2 size={16} />
          {value?.linked ? t("telegram.relink") : t("telegram.createCode")}
        </Button>
        {value?.linked && <Button
          type="button"
          variant="danger"
          disabled={unlink.isPending}
          onClick={() => { if (window.confirm(t("telegram.unlinkConfirm"))) unlink.mutate(); }}
        >
          <Unlink size={16} />{t("telegram.unlink")}
        </Button>}
      </div>
      {issued && <div className="rounded-lg border border-warning/40 bg-warning/10 p-3">
        <p className="text-sm">{t("telegram.codeInstructions")}</p>
        <code className="mt-3 block text-2xl font-semibold tracking-[0.2em]">{issued.code}</code>
        <p className="mt-2 text-xs text-text-muted">{t("telegram.codeExpiry", { minutes: Math.ceil(issued.expires_in_seconds / 60) })}</p>
        <Button type="button" variant="secondary" className="mt-3" onClick={() => void navigator.clipboard?.writeText(`/link ${issued.code}`)}>
          <Copy size={16} />{t("telegram.copyCommand")}
        </Button>
      </div>}
      {error && <p className="text-sm text-danger" role="alert">{t("telegram.error")}</p>}
    </CardContent>
  </Card>;
}
