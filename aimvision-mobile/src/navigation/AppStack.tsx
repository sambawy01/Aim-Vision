/**
 * The post-login stack with a persistent bottom TabBar.
 *
 * Structure:
 *   <View flex 1>
 *     <Stack.Navigator>      sessions list / detail / capture / settings
 *     <TabBar/>              fixed bottom, navigates top-level routes
 *
 * The native bottom-tabs navigator wants screens@>=4; we're on 3.31, so we
 * compose a custom TabBar (`components/TabBar.tsx`) instead. Once the RN
 * modernization (PR #92) lands, swap the layout for the official tab
 * navigator and delete the custom component.
 */
import React from 'react';
import { StyleSheet, View } from 'react-native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import type { AppStackParamList } from './types';
import { usePhoneCaptureEnabled } from '../config/flags';
import { HomeScreen } from '../screens/home/HomeScreen';
import { SettingsScreen } from '../screens/settings/SettingsScreen';
import { DataPrivacyScreen } from '../screens/settings/DataPrivacyScreen';
import { CapturePhoneScreen } from '../screens/capture/CapturePhoneScreen';
import { NewSessionScreen } from '../screens/sessions/NewSessionScreen';
import { SessionDetailScreen } from '../screens/sessions/SessionDetailScreen';
import { RecordingPlayerScreen } from '../screens/sessions/RecordingPlayerScreen';
import { AthletesScreen } from '../screens/athletes/AthletesScreen';
import { AthleteDetailScreen } from '../screens/athletes/AthleteDetailScreen';
import { EraseDataScreen } from '../screens/settings/EraseDataScreen';
import { TabBar } from '../components/TabBar';
import { colors } from '../theme/tokens';

const Stack = createNativeStackNavigator<AppStackParamList>();

export function AppStack(): React.ReactElement {
  // ADR-0009: the dev-mode phone-capture screen is only registered when the
  // `capture.phone_backend_enabled` flag is on. Default off in production, so
  // a customer build can't resolve the route even via a deep link.
  const phoneCaptureEnabled = usePhoneCaptureEnabled();

  return (
    <View style={styles.root}>
      <View style={styles.stackWrap}>
        <Stack.Navigator
          initialRouteName="Home"
          screenOptions={{ headerStyle: { backgroundColor: colors.surfaceElevated } }}
        >
          <Stack.Screen name="Home" component={HomeScreen} options={{ headerShown: false }} />
          <Stack.Screen
            name="NewSession"
            component={NewSessionScreen}
            options={{ title: 'New session', headerTintColor: colors.textPrimary }}
          />
          <Stack.Screen
            name="SessionDetail"
            component={SessionDetailScreen}
            options={{ title: 'Session', headerTintColor: colors.textPrimary }}
          />
          <Stack.Screen
            name="RecordingPlayer"
            component={RecordingPlayerScreen}
            options={{ title: 'Recording', headerTintColor: colors.textPrimary }}
          />
          <Stack.Screen
            name="Settings"
            component={SettingsScreen}
            options={{ title: 'Settings', headerTintColor: colors.textPrimary }}
          />
          <Stack.Screen
            name="DataPrivacy"
            component={DataPrivacyScreen}
            options={{ title: 'Data & privacy', headerTintColor: colors.textPrimary }}
          />
          <Stack.Screen
            name="Athletes"
            component={AthletesScreen}
            options={{ headerShown: false }}
          />
          <Stack.Screen
            name="AthleteDetail"
            component={AthleteDetailScreen}
            options={{ title: 'Athlete', headerTintColor: colors.textPrimary }}
          />
          <Stack.Screen
            name="EraseData"
            component={EraseDataScreen}
            options={{ title: 'Erase data', headerTintColor: colors.textPrimary }}
          />
          {phoneCaptureEnabled ? (
            <Stack.Screen
              name="CapturePhone"
              component={CapturePhoneScreen}
              options={{ title: 'Capture', headerTintColor: colors.textPrimary }}
            />
          ) : null}
        </Stack.Navigator>
      </View>
      <TabBar />
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bg,
  },
  stackWrap: {
    flex: 1,
  },
});
