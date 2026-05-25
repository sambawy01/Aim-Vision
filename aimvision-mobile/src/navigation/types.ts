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
  CapturePhone: { sessionId?: string } | undefined;
  NewSession: undefined;
  SessionDetail: { sessionId: string };
  RecordingPlayer: { sessionId: string; recordingId: string };
  Athletes: undefined;
  AthleteDetail: { athleteId: string };
  EraseData: undefined;
};

export type RootStackParamList = {
  Auth: undefined;
  App: undefined;
};
