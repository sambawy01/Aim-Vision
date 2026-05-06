import React from 'react';
import { render, fireEvent, screen } from '@testing-library/react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import en from '../locales/en/common.json';
import { AgeGateScreen, ageFromDob } from '../screens/onboarding/AgeGateScreen';

beforeAll(async () => {
  await i18n.use(initReactI18next).init({
    resources: { en: { common: en } },
    lng: 'en',
    fallbackLng: 'en',
    defaultNS: 'common',
    interpolation: { escapeValue: false },
    compatibilityJSON: 'v4',
    returnNull: false,
  });
});

const Stack = createNativeStackNavigator();

function renderWithNav(): void {
  render(
    <NavigationContainer>
      <Stack.Navigator>
        <Stack.Screen name="AgeGate" component={AgeGateScreen} />
        <Stack.Screen name="ParentalConsent" component={() => null} />
        <Stack.Screen name="Welcome" component={() => null} />
      </Stack.Navigator>
    </NavigationContainer>,
  );
}

function dobForAge(age: number): string {
  const now = new Date();
  const y = now.getUTCFullYear() - age;
  const m = String(now.getUTCMonth() + 1).padStart(2, '0');
  const d = String(now.getUTCDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

describe('ageFromDob', () => {
  it('computes age correctly', () => {
    const today = new Date(Date.UTC(2026, 4, 6));
    expect(ageFromDob(new Date(Date.UTC(2008, 4, 6)), today)).toBe(18);
    expect(ageFromDob(new Date(Date.UTC(2008, 4, 7)), today)).toBe(17);
    expect(ageFromDob(new Date(Date.UTC(2014, 0, 1)), today)).toBe(12);
  });
});

describe('AgeGateScreen', () => {
  it('shows the COPPA notice when DOB makes the user under 13', () => {
    renderWithNav();
    fireEvent.changeText(screen.getByTestId('age-gate-dob'), dobForAge(12));
    fireEvent.changeText(screen.getByTestId('age-gate-country'), 'EG');
    expect(screen.getByTestId('age-gate-coppa-notice')).toBeTruthy();
    expect(screen.getByText(en.ageGate.coppaWarning)).toBeTruthy();
  });

  it('shows the minor parental-consent notice for ages 13–17', () => {
    renderWithNav();
    fireEvent.changeText(screen.getByTestId('age-gate-dob'), dobForAge(15));
    fireEvent.changeText(screen.getByTestId('age-gate-country'), 'US');
    expect(screen.getByTestId('age-gate-minor-notice')).toBeTruthy();
    expect(screen.getByText(en.ageGate.parentRequiredDescription)).toBeTruthy();
  });

  it('enables the proceed-to-signup button at age 25', () => {
    renderWithNav();
    fireEvent.changeText(screen.getByTestId('age-gate-dob'), dobForAge(25));
    fireEvent.changeText(screen.getByTestId('age-gate-country'), 'US');
    expect(screen.queryByTestId('age-gate-coppa-notice')).toBeNull();
    expect(screen.queryByTestId('age-gate-minor-notice')).toBeNull();
    const button = screen.getByLabelText(en.ageGate.continue);
    expect(button.props.accessibilityState?.disabled).toBeFalsy();
  });
});
