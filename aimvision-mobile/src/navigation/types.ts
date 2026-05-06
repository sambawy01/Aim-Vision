export type AuthStackParamList = {
  AgeGate: undefined;
  ParentalConsent: { dob: string; ageYears: number; mode: 'minor' | 'coppa' };
  ChildSetup: { parentConsentToken: string };
  ConsentMatrix: { childAccountId?: string };
  Welcome: undefined;
};

export type AppStackParamList = {
  Home: undefined;
  Settings: undefined;
  DataPrivacy: undefined;
};

export type RootStackParamList = {
  Auth: undefined;
  App: undefined;
};
