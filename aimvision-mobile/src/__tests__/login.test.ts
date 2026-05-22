/**
 * Mobile login — consumes the real backend LoginOut and stores the access
 * token + principal so the app (and recording upload) can authenticate.
 */
import { login } from '../services/auth';
import { api } from '../services/api';
import { useAuthStore } from '../state/authStore';

// babel-jest hoists this above the imports above.
jest.mock('../services/api', () => ({
  api: jest.fn(),
  ApiError: class ApiError extends Error {},
}));

const apiMock = api as jest.Mock;

describe('mobile login', () => {
  beforeEach(() => {
    apiMock.mockReset();
    useAuthStore.setState({ accessToken: null, refreshToken: null, principal: null, session: null });
  });

  it('stores the access token + principal from the backend response', async () => {
    apiMock.mockResolvedValue({
      access_token: 'tok-abc',
      token_type: 'bearer',
      expires_in: 3600,
      principal: {
        user_id: 'u1',
        tenant_id: 'org:democlub',
        role: 'coach',
        display_name: 'Demo Coach',
      },
    });

    await login({ email: 'coach@example.com', password: 'demopassword123' });

    const s = useAuthStore.getState();
    expect(s.accessToken).toBe('tok-abc');
    expect(s.principal).toEqual({
      userId: 'u1',
      tenantId: 'org:democlub',
      role: 'coach',
      displayName: 'Demo Coach',
    });
    expect(s.isAuthenticated()).toBe(true);
    expect(apiMock).toHaveBeenCalledWith('/auth/login', {
      method: 'POST',
      body: { email: 'coach@example.com', password: 'demopassword123' },
    });
  });

  it('propagates errors and leaves the store signed out', async () => {
    apiMock.mockRejectedValue(new Error('HTTP 401'));
    await expect(login({ email: 'x@example.com', password: 'wrong' })).rejects.toThrow();
    const s = useAuthStore.getState();
    expect(s.accessToken).toBeNull();
    expect(s.principal).toBeNull();
    expect(s.isAuthenticated()).toBe(false);
  });
});
