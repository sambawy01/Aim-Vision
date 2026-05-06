import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from './a11y/Button';

/**
 * QR scanner placeholder.
 *
 * Sprint 16 will replace this with `html5-qrcode` (camera-driven scanning).
 * For now, the dashboard exposes a manual entry form that calls
 * services/checkin.ts::redeem with (qr_payload, display_code, session_id).
 *
 * The redemption protocol requires BOTH the PASETO bytes AND the 6-digit
 * channel-binding code per docs/security/qr-checkin-token-spec.md §4 — this
 * UI surfaces both inputs so the manual flow exercises the full validation
 * path.
 */

export interface QrScannerSubmit {
  qrPayload: string;
  displayCode: string;
  sessionId: string;
}

interface QrScannerProps {
  onSubmit: (v: QrScannerSubmit) => void;
  isSubmitting?: boolean;
}

export function QrScanner({ onSubmit, isSubmitting = false }: QrScannerProps) {
  const { t } = useTranslation();
  const [qrPayload, setQrPayload] = useState('');
  const [displayCode, setDisplayCode] = useState('');
  const [sessionId, setSessionId] = useState('');

  const valid = qrPayload.startsWith('av1:') && /^\d{6}$/.test(displayCode) && sessionId.length > 0;

  return (
    <form
      className="space-y-4 max-w-xl"
      onSubmit={(e) => {
        e.preventDefault();
        if (valid) onSubmit({ qrPayload, displayCode, sessionId });
      }}
    >
      <div
        role="region"
        aria-label="QR scanner placeholder"
        className="border border-dashed border-border-strong rounded-lg p-8 bg-surface-muted text-center text-text-muted"
      >
        {t('checkin.scanPlaceholder')}
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="qr-token" className="text-sm font-medium text-text">
          {t('checkin.manualEntryLabel')}
        </label>
        <input
          id="qr-token"
          name="qr-token"
          type="text"
          autoComplete="off"
          spellCheck={false}
          required
          value={qrPayload}
          onChange={(e) => setQrPayload(e.target.value)}
          placeholder="av1:v4.local....-123456"
          className="min-h-touch px-3 py-2 rounded-md border border-border bg-surface text-text font-mono text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="display-code" className="text-sm font-medium text-text">
          {t('checkin.displayCodeLabel')}
        </label>
        <input
          id="display-code"
          name="display-code"
          type="text"
          inputMode="numeric"
          pattern="\d{6}"
          maxLength={6}
          required
          value={displayCode}
          onChange={(e) => setDisplayCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
          className="min-h-touch px-3 py-2 rounded-md border border-border bg-surface text-text font-mono text-sm w-32 tracking-widest focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="session-id" className="text-sm font-medium text-text">
          {t('checkin.sessionIdLabel')}
        </label>
        <input
          id="session-id"
          name="session-id"
          type="text"
          autoComplete="off"
          required
          value={sessionId}
          onChange={(e) => setSessionId(e.target.value)}
          className="min-h-touch px-3 py-2 rounded-md border border-border bg-surface text-text font-mono text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
        />
      </div>

      <Button type="submit" disabled={!valid || isSubmitting}>
        {t('checkin.redeem')}
      </Button>
    </form>
  );
}
