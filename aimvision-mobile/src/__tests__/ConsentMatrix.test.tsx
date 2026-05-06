import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import en from '../locales/en/common.json';
import { ConsentMatrix } from '../components/ConsentMatrix';
import { CONSENT_CATEGORIES, CONSENT_PURPOSES, useConsentStore } from '../state/consentStore';

beforeAll(async () => {
  if (!i18n.isInitialized) {
    await i18n.use(initReactI18next).init({
      resources: { en: { common: en } },
      lng: 'en',
      fallbackLng: 'en',
      defaultNS: 'common',
      interpolation: { escapeValue: false },
      compatibilityJSON: 'v4',
      returnNull: false,
    });
  }
});

beforeEach(() => {
  useConsentStore.getState().reset();
});

describe('ConsentMatrix', () => {
  it('renders all category × purpose checkboxes off by default', () => {
    const { getByTestId } = render(<ConsentMatrix />);
    for (const category of CONSENT_CATEGORIES) {
      for (const purpose of CONSENT_PURPOSES) {
        const node = getByTestId(`consent-${category}-${purpose}`);
        expect(node.props.value).toBe(false);
      }
    }
  });

  it('toggles store state when two boxes are tapped', () => {
    const { getByTestId } = render(<ConsentMatrix />);
    fireEvent(getByTestId('consent-video-coaching'), 'valueChange', true);
    fireEvent(getByTestId('consent-pose-coaching'), 'valueChange', true);
    const matrix = useConsentStore.getState().matrix;
    expect(matrix.video.coaching).toBe(true);
    expect(matrix.pose.coaching).toBe(true);
    expect(matrix.video.marketing).toBe(false);
    expect(matrix.ML_training.validity_study).toBe(false);
    expect(useConsentStore.getState().dirty).toBe(true);
  });
});
