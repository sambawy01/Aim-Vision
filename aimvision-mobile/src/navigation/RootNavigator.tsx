import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { useAuthStore } from '../state/authStore';
import { AuthStack } from './AuthStack';
import { AppStack } from './AppStack';
import type { RootStackParamList } from './types';

const Stack = createNativeStackNavigator<RootStackParamList>();

export function RootNavigator(): React.ReactElement {
  const accessToken = useAuthStore((s) => s.accessToken);
  const session = useAuthStore((s) => s.session);
  const principal = useAuthStore((s) => s.principal);
  // Signed in via either the onboarding session (athlete) or a login principal
  // (coach/admin). Both ride the same access token.
  const authed = Boolean(accessToken && (session || principal));

  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      {authed ? (
        <Stack.Screen name="App" component={AppStack} />
      ) : (
        <Stack.Screen name="Auth" component={AuthStack} />
      )}
    </Stack.Navigator>
  );
}
