import React from 'react';
import { StyleSheet, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useTranslation } from '../../hooks/useTranslation';
import { AccessibleText } from '../../components/a11y/AccessibleText';
import { RangeButton } from '../../components/RangeMode/RangeButton';
import { colors, spacing } from '../../theme/tokens';
import type { AuthStackParamList } from '../../navigation/types';

type Nav = NativeStackNavigationProp<AuthStackParamList, 'Welcome'>;

export function WelcomeScreen(): React.ReactElement {
  const navigation = useNavigation<Nav>();
  const { t } = useTranslation();
  return (
    <View style={styles.container}>
      <AccessibleText variant="display">{t('welcome.title')}</AccessibleText>
      <AccessibleText variant="body" color="textSecondary" style={styles.body}>
        {t('welcome.body')}
      </AccessibleText>
      <View style={styles.actions}>
        <RangeButton
          label={t('welcome.signIn', { defaultValue: 'Sign in' })}
          onPress={() => navigation.navigate('Login')}
          accessibilityLabel={t('welcome.signIn', { defaultValue: 'Sign in' })}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg,
    padding: spacing.lg,
  },
  body: {
    marginTop: spacing.md,
  },
  actions: {
    marginTop: spacing.xl,
  },
});
