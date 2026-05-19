import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import type { AppStackParamList } from './types';
import { HomeScreen } from '../screens/home/HomeScreen';
import { SettingsScreen } from '../screens/settings/SettingsScreen';
import { DataPrivacyScreen } from '../screens/settings/DataPrivacyScreen';
import { CapturePhoneScreen } from '../screens/capture/CapturePhoneScreen';

const Stack = createNativeStackNavigator<AppStackParamList>();

export function AppStack(): React.ReactElement {
  return (
    <Stack.Navigator initialRouteName="Home">
      <Stack.Screen name="Home" component={HomeScreen} />
      <Stack.Screen name="Settings" component={SettingsScreen} />
      <Stack.Screen name="DataPrivacy" component={DataPrivacyScreen} />
      {/* Dev-mode capture entry point — gated by feature flag in slice 2;
          ADR-0009 keeps phone capture out of any customer-visible nav. */}
      <Stack.Screen name="CapturePhone" component={CapturePhoneScreen} />
    </Stack.Navigator>
  );
}
