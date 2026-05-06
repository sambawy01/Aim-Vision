import { create } from 'zustand';
import * as SecureStore from 'expo-secure-store';

const ACCESS_KEY = 'aimv.auth.access';
const REFRESH_KEY = 'aimv.auth.refresh';

export interface AuthSession {
  athleteIdHash: string;
  email: string | null;
  ageGroup: 'adult' | 'minor_13_17' | 'minor_under_13';
  parentLinked: boolean;
}

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  session: AuthSession | null;
  hydrated: boolean;
  isAuthenticated: () => boolean;
  hydrate: () => Promise<void>;
  setTokens: (access: string, refresh: string) => Promise<void>;
  setSession: (session: AuthSession | null) => void;
  signOut: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  accessToken: null,
  refreshToken: null,
  session: null,
  hydrated: false,
  isAuthenticated: () => Boolean(get().accessToken && get().session),
  hydrate: async () => {
    const [access, refresh] = await Promise.all([
      SecureStore.getItemAsync(ACCESS_KEY),
      SecureStore.getItemAsync(REFRESH_KEY),
    ]);
    set({ accessToken: access, refreshToken: refresh, hydrated: true });
  },
  setTokens: async (access, refresh) => {
    await SecureStore.setItemAsync(ACCESS_KEY, access);
    await SecureStore.setItemAsync(REFRESH_KEY, refresh);
    set({ accessToken: access, refreshToken: refresh });
  },
  setSession: (session) => set({ session }),
  signOut: async () => {
    await Promise.all([
      SecureStore.deleteItemAsync(ACCESS_KEY),
      SecureStore.deleteItemAsync(REFRESH_KEY),
    ]);
    set({ accessToken: null, refreshToken: null, session: null });
  },
}));
