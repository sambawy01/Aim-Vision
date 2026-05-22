import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import type { AuthStackParamList } from './types';
import { LoginScreen } from '../screens/auth/LoginScreen';
import { AgeGateScreen } from '../screens/onboarding/AgeGateScreen';
import { ParentalConsentScreen } from '../screens/onboarding/ParentalConsentScreen';
import { ChildSetupScreen } from '../screens/onboarding/ChildSetupScreen';
import { ConsentMatrixScreen } from '../screens/onboarding/ConsentMatrixScreen';
import { WelcomeScreen } from '../screens/onboarding/WelcomeScreen';

const Stack = createNativeStackNavigator<AuthStackParamList>();

export function AuthStack(): React.ReactElement {
  return (
    <Stack.Navigator
      initialRouteName="Login"
      screenOptions={{ headerShown: true, headerBackTitle: '' }}
    >
      <Stack.Screen name="Login" component={LoginScreen} />
      <Stack.Screen name="AgeGate" component={AgeGateScreen} />
      <Stack.Screen name="ParentalConsent" component={ParentalConsentScreen} />
      <Stack.Screen name="ChildSetup" component={ChildSetupScreen} />
      <Stack.Screen name="ConsentMatrix" component={ConsentMatrixScreen} />
      <Stack.Screen name="Welcome" component={WelcomeScreen} />
    </Stack.Navigator>
  );
}
