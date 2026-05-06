import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import type { AppStackParamList } from './types';
import { HomeScreen } from '../screens/home/HomeScreen';
import { SettingsScreen } from '../screens/settings/SettingsScreen';
import { DataPrivacyScreen } from '../screens/settings/DataPrivacyScreen';

const Stack = createNativeStackNavigator<AppStackParamList>();

export function AppStack(): React.ReactElement {
  return (
    <Stack.Navigator initialRouteName="Home">
      <Stack.Screen name="Home" component={HomeScreen} />
      <Stack.Screen name="Settings" component={SettingsScreen} />
      <Stack.Screen name="DataPrivacy" component={DataPrivacyScreen} />
    </Stack.Navigator>
  );
}
