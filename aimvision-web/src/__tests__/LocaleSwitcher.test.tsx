import { describe, it, expect, beforeAll, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { LocaleSwitcher } from '@/components/LocaleSwitcher';
import { initI18n } from '@/config/i18n';
import i18n from '@/config/i18n';

beforeAll(() => {
  initI18n();
});

beforeEach(async () => {
  await i18n.changeLanguage('en');
  document.documentElement.dir = 'ltr';
});

describe('LocaleSwitcher', () => {
  it('switches html dir to rtl when Arabic is selected', async () => {
    const user = userEvent.setup();
    render(<LocaleSwitcher />);

    expect(document.documentElement.dir).toBe('ltr');

    const select = screen.getByRole('combobox', { name: /language/i });
    await user.selectOptions(select, 'ar');

    expect(document.documentElement.dir).toBe('rtl');
    expect(document.documentElement.lang).toBe('ar');
  });

  it('switches html dir back to ltr when English is selected', async () => {
    const user = userEvent.setup();
    await i18n.changeLanguage('ar');
    render(<LocaleSwitcher />);

    expect(document.documentElement.dir).toBe('rtl');

    const select = screen.getByRole('combobox', { name: /language|اللغة/i });
    await user.selectOptions(select, 'en');

    expect(document.documentElement.dir).toBe('ltr');
    expect(document.documentElement.lang).toBe('en');
  });
});
