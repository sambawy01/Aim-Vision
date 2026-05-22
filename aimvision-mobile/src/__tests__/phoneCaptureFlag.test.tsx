import React from 'react';
import { render, renderHook, act } from '@testing-library/react-native';
import { NavigationContainer, createNavigationContainerRef } from '@react-navigation/native';

import { FLAG_PHONE_CAPTURE, usePhoneCaptureEnabled } from '../config/flags';
import { useFlag } from '../hooks/useFlag';
import { AppStack } from '../navigation/AppStack';
import type { AppStackParamList } from '../navigation/types';

// Gate the flag at the source so the test is deterministic regardless of
// Statsig init state. The screens are stubbed so the navigator renders
// without their providers / native deps (CapturePhoneScreen pulls in
// react-native-vision-camera); the test asserts only the routing gate.
jest.mock('../hooks/useFlag');
jest.mock('../screens/home/HomeScreen', () => ({ HomeScreen: () => null }));
jest.mock('../screens/settings/SettingsScreen', () => ({ SettingsScreen: () => null }));
jest.mock('../screens/settings/DataPrivacyScreen', () => ({ DataPrivacyScreen: () => null }));
jest.mock('../screens/capture/CapturePhoneScreen', () => ({ CapturePhoneScreen: () => null }));

const mockUseFlag = useFlag as jest.MockedFunction<typeof useFlag>;

beforeEach(() => {
  mockUseFlag.mockReset();
});

describe('usePhoneCaptureEnabled', () => {
  it('checks the ADR-0009 gate with a __DEV__ default', () => {
    mockUseFlag.mockReturnValue(true);
    const { result } = renderHook(() => usePhoneCaptureEnabled());
    expect(mockUseFlag).toHaveBeenCalledWith(FLAG_PHONE_CAPTURE, __DEV__);
    expect(result.current).toBe(true);
  });
});

describe('AppStack phone-capture gating', () => {
  function renderStack(navRef: ReturnType<typeof createNavigationContainerRef<AppStackParamList>>) {
    render(
      <NavigationContainer ref={navRef}>
        <AppStack />
      </NavigationContainer>,
    );
  }

  it('does NOT register the CapturePhone route when the flag is off', () => {
    mockUseFlag.mockReturnValue(false);
    const navRef = createNavigationContainerRef<AppStackParamList>();
    renderStack(navRef);

    // Navigating to an unregistered route is a no-op: the route stays Home.
    // Suppress React Navigation's expected "not handled" error log.
    const errSpy = jest.spyOn(console, 'error').mockImplementation(() => undefined);
    act(() => {
      navRef.navigate('CapturePhone');
    });
    errSpy.mockRestore();

    expect(navRef.getCurrentRoute()?.name).toBe('Home');
  });

  it('registers the CapturePhone route when the flag is on', () => {
    mockUseFlag.mockReturnValue(true);
    const navRef = createNavigationContainerRef<AppStackParamList>();
    renderStack(navRef);

    act(() => {
      navRef.navigate('CapturePhone');
    });

    expect(navRef.getCurrentRoute()?.name).toBe('CapturePhone');
  });
});
