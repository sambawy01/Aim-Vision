/**
 * QR check-in client.
 *
 * See docs/security/qr-checkin-token-spec.md §6 for the full redemption
 * protocol. Production deployments must call this endpoint over an mTLS
 * channel (the club's mTLS client cert is the authenticated identity); the
 * web dashboard's mTLS layer is provided by the API gateway, not by this
 * fetch wrapper. The `redeem` call MUST submit both the PASETO bytes and
 * the 6-digit display code (channel-binding code, §4).
 */

import { fetchJson } from './api';

export interface RedeemRequest {
  qrPayload: string;
  displayCode: string;
  sessionId: string;
  redeemingClubId: string;
}

export interface RedeemResponse {
  attributionCapability: string;
  sessionId: string;
  expiresAt: number;
  scope: 'attribution_write_only';
  auditChainAnchor: string;
}

interface RedeemResponseWire {
  attribution_capability: string;
  session_id: string;
  expires_at: number;
  scope: 'attribution_write_only';
  audit_chain_anchor: string;
}

export async function redeem(req: RedeemRequest): Promise<RedeemResponse> {
  const wire = await fetchJson<RedeemResponseWire>('/v1/checkin/redeem', {
    method: 'POST',
    body: JSON.stringify({
      qr_payload: req.qrPayload,
      display_code: req.displayCode,
      session_id: req.sessionId,
      redeeming_club_id: req.redeemingClubId,
    }),
  });
  return {
    attributionCapability: wire.attribution_capability,
    sessionId: wire.session_id,
    expiresAt: wire.expires_at,
    scope: wire.scope,
    auditChainAnchor: wire.audit_chain_anchor,
  };
}
