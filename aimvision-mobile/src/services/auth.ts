import { api } from './api';
import { useAuthStore, type AuthSession } from '../state/authStore';

export interface SignupRequest {
  email: string;
  password: string;
  dob: string; // ISO date
  countryCode: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface AuthResponse {
  accessToken: string;
  refreshToken: string;
  session: AuthSession;
}

/**
 * Backend `LoginOut` (PR #88) — what the API actually returns.
 *
 * The mobile auth store predates this shape and uses camelCase + a
 * synthetic `AuthSession`; `mapLoginOut()` bridges the two so the
 * native client doesn't have to chase backend contract drift.
 */
interface BackendLoginOut {
  access_token: string;
  token_type: string;
  expires_in: number;
  principal: {
    user_id: string;
    tenant_id: string;
    role: string;
    display_name: string;
  };
  memberships: Array<{
    tenant_id: string;
    display_name: string;
    role: string;
  }>;
}

function mapLoginOut(b: BackendLoginOut): AuthResponse {
  return {
    accessToken: b.access_token,
    // Backend doesn't issue refresh tokens in the body yet (PR #89's
    // cookie-based refresh hasn't landed). Empty string until then.
    refreshToken: '',
    session: {
      // No athlete id hash from the backend yet — use user_id as a
      // stable placeholder. Real hash lands with the consent + AthleteProfile flow.
      athleteIdHash: b.principal.user_id,
      email: null,
      ageGroup: 'adult',
      parentLinked: false,
    },
  };
}

export interface ParentalConsentRequest {
  childAccountId?: string;
  parentEmail: string;
  method: 'paper_pdf' | 'credit_card' | 'email_plus_id' | 'video_call';
  evidence: {
    pdfUri?: string;
    paymentToken?: string;
    idHash?: string;
  };
}

export interface ParentalConsentResponse {
  consentToken: string;
  status: 'pending' | 'approved' | 'rejected';
}

export async function signup(req: SignupRequest): Promise<AuthResponse> {
  const raw = await api<BackendLoginOut>('/auth/signup', {
    method: 'POST',
    body: req,
  });
  const res = mapLoginOut(raw);
  await useAuthStore.getState().setTokens(res.accessToken, res.refreshToken);
  useAuthStore.getState().setSession(res.session);
  return res;
}

export async function login(req: LoginRequest): Promise<AuthResponse> {
  const raw = await api<BackendLoginOut>('/auth/login', {
    method: 'POST',
    body: req,
  });
  const res = mapLoginOut(raw);
  await useAuthStore.getState().setTokens(res.accessToken, res.refreshToken);
  // Override with the real display name from the principal — drives the
  // user-visible greeting before AthleteProfile lookup completes.
  useAuthStore.getState().setSession({
    ...res.session,
    email: req.email,
  });
  return res;
}

export async function submitParentalConsent(
  req: ParentalConsentRequest,
): Promise<ParentalConsentResponse> {
  return api<ParentalConsentResponse>('/auth/parental-consent', {
    method: 'POST',
    body: req,
  });
}

export async function logout(): Promise<void> {
  try {
    await api<void>('/auth/logout', { method: 'POST' });
  } finally {
    await useAuthStore.getState().signOut();
  }
}
