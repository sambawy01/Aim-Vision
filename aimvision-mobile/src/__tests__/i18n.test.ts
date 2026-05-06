import { I18nManager } from 'react-native';
import i18n from '../config/i18n';
import { setLocale } from '../config/i18n';

describe('i18n', () => {
  beforeAll(async () => {
    if (!i18n.isInitialized) {
      const { initI18n } = await import('../config/i18n');
      await initI18n();
    }
  });

  it('returns English by default', async () => {
    await setLocale('en');
    expect(i18n.t('app.name')).toBe('AIMVISION');
    expect(i18n.t('ageGate.title')).toBe('When were you born?');
  });

  it('switches to Arabic and forces RTL', async () => {
    await setLocale('ar');
    expect(i18n.language).toBe('ar');
    expect(i18n.t('app.name')).toBe('إيم فيجن');
    expect(i18n.t('ageGate.title')).toBe('متى ولدت؟');
    expect(I18nManager.isRTL).toBe(true);
  });

  it('falls back to English when key is missing', async () => {
    await setLocale('en');
    expect(i18n.t('does.not.exist', { defaultValue: 'fallback' })).toBe('fallback');
  });
});
