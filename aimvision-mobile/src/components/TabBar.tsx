/**
 * Persistent bottom tab bar for the AppStack.
 *
 * Sits underneath the Stack.Navigator (composed in AppStack.tsx). Pressing a
 * tab calls `navigation.navigate(routeName)` which the stack handles via
 * route-name lookup. We avoid `@react-navigation/bottom-tabs` because its v7
 * peers on `react-native-screens@>=4` and we're still on screens 3.31 with
 * Expo SDK 51. Once the RN modernization (PR #92) lands, swap this for the
 * official tab navigator.
 */
import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { useNavigation, useNavigationState } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { AccessibleText } from './a11y/AccessibleText';
import { colors, spacing } from '../theme/tokens';
import { usePhoneCaptureEnabled } from '../config/flags';
import type { AppStackParamList } from '../navigation/types';

type Nav = NativeStackNavigationProp<AppStackParamList>;

interface Tab {
  key: keyof AppStackParamList;
  label: string;
  glyph: string;
}

const ALWAYS_TABS: Tab[] = [
  { key: 'Home', label: 'Sessions', glyph: '◐' },
  { key: 'Athletes', label: 'Athletes', glyph: '☻' },
  { key: 'Settings', label: 'Settings', glyph: '⚙' },
];

export function TabBar(): React.ReactElement {
  const navigation = useNavigation<Nav>();
  const insets = useSafeAreaInsets();
  const phoneCaptureEnabled = usePhoneCaptureEnabled();
  const currentRoute = useNavigationState((s) => {
    if (!s || !s.routes || s.index === undefined) return undefined;
    return s.routes[s.index]?.name;
  });

  // Sessions · Athletes · Capture? · Settings
  const tabs: Tab[] = phoneCaptureEnabled
    ? [
        ALWAYS_TABS[0],
        ALWAYS_TABS[1],
        { key: 'CapturePhone', label: 'Capture', glyph: '●' },
        ALWAYS_TABS[2],
      ]
    : ALWAYS_TABS;

  return (
    <View style={[styles.bar, { paddingBottom: Math.max(insets.bottom, spacing.sm) }]}>
      {tabs.map((t) => {
        const active = currentRoute === t.key;
        return (
          <Pressable
            key={t.key}
            onPress={() => navigation.navigate(t.key as never)}
            style={styles.tab}
            accessibilityRole="tab"
            accessibilityState={{ selected: active }}
            accessibilityLabel={t.label}
          >
            <AccessibleText variant="title" color={active ? 'accent' : 'textSecondary'}>
              {t.glyph}
            </AccessibleText>
            <AccessibleText variant="caption" color={active ? 'accent' : 'textSecondary'}>
              {t.label}
            </AccessibleText>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: 'row',
    backgroundColor: colors.surfaceElevated,
    borderTopColor: colors.border,
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingTop: spacing.sm,
  },
  tab: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.xs,
  },
});
