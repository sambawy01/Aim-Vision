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
  const res = await api<AuthResponse>('/auth/signup', {
    method: 'POST',
    body: req,
  });
  await useAuthStore.getState().setTokens(res.accessToken, res.refreshToken);
  useAuthStore.getState().setSession(res.session);
  return res;
}

/** Wire shape of the backend's LoginOut (snake_case). The refresh token is
 * delivered as an httpOnly cookie (the native cookie store replays it on
 * /auth/refresh), so it is not in the response body. */
interface LoginResponseWire {
  access_token: string;
  token_type: string;
  expires_in: number;
  principal: {
    user_id: string;
    tenant_id: string;
    role: string;
    display_name: string;
  };
}

export async function login(req: LoginRequest): Promise<void> {
  const res = await api<LoginResponseWire>('/auth/login', {
    method: 'POST',
    body: req,
  });
  await useAuthStore.getState().setTokens(res.access_token, '');
  useAuthStore.getState().setPrincipal({
    userId: res.principal.user_id,
    tenantId: res.principal.tenant_id,
    role: res.principal.role,
    displayName: res.principal.display_name,
  });
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
