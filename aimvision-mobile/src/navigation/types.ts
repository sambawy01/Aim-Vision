export type AuthStackParamList = {
  AgeGate: undefined;
  ParentalConsent: { dob: string; ageYears: number; mode: 'minor' | 'coppa' };
  ChildSetup: { parentConsentToken: string };
  ConsentMatrix: { childAccountId?: string };
  Welcome: undefined;
  Login: undefined;
};

export type AppStackParamList = {
  Home: undefined;
  Settings: undefined;
  DataPrivacy: undefined;
  CapturePhone: undefined;
  NewSession: undefined;
  SessionDetail: { sessionId: string };
};

export type RootStackParamList = {
  Auth: undefined;
  App: undefined;
};
