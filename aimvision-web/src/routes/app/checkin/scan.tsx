/**
 * QR check-in scan route.
 *
 * See docs/security/qr-checkin-token-spec.md for the full token + redemption
 * protocol. This route is a placeholder shell:
 *
 *   - Sprint 16 will plug `html5-qrcode` into <QrScanner /> for camera-driven
 *     scanning.
 *   - Production deployments must call /v1/checkin/redeem over an mTLS
 *     channel (the club's mTLS client cert is the authenticated identity);
 *     the mTLS layer is enforced at the API gateway, not in this fetch
 *     wrapper.
 *   - Manual entry exercises the same redemption code path with both the
 *     PASETO bytes and the 6-digit channel-binding code (§4).
 */

import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { QrScanner, type QrScannerSubmit } from '@/components/QrScanner';
import { redeem, type RedeemResponse } from '@/services/checkin';
import { useTenancy } from '@/hooks/useTenancy';

export function CheckinScanRoute() {
  const { t } = useTranslation();
  const { current } = useTenancy();
  const [result, setResult] = useState<RedeemResponse | null>(null);

  const mutation = useMutation({
    mutationFn: (v: QrScannerSubmit) =>
      redeem({
        qrPayload: v.qrPayload,
        displayCode: v.displayCode,
        sessionId: v.sessionId,
        // Authenticated identity wins server-side; we still send the asserted
        // club id for the mismatch check (qr-checkin-token-spec.md §6.2).
        redeemingClubId: current?.tenantId ?? '',
      }),
    onSuccess: (r) => setResult(r),
  });

  return (
    <section aria-labelledby="checkin-heading" className="space-y-6">
      <header>
        <h1 id="checkin-heading" className="text-2xl font-semibold">
          {t('checkin.title')}
        </h1>
        <p className="text-sm text-text-muted mt-1">{t('checkin.specRef')}</p>
      </header>

      <QrScanner onSubmit={(v) => mutation.mutate(v)} isSubmitting={mutation.isPending} />

      {mutation.isError ? (
        <p role="alert" className="text-danger">
          {mutation.error instanceof Error ? mutation.error.message : t('common.error')}
        </p>
      ) : null}

      {result ? (
        <div role="status" className="rounded-lg border border-success p-4 text-sm bg-surface">
          <p className="font-semibold text-success">Capability issued</p>
          <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 mt-2">
            <dt className="text-text-muted">session</dt>
            <dd className="font-mono break-all">{result.sessionId}</dd>
            <dt className="text-text-muted">scope</dt>
            <dd className="font-mono">{result.scope}</dd>
            <dt className="text-text-muted">expires_at</dt>
            <dd className="font-mono">{result.expiresAt}</dd>
          </dl>
        </div>
      ) : null}
    </section>
  );
}
