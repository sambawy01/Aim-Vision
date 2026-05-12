import React from 'react';
import { Text, type TextProps, type TextStyle, StyleSheet } from 'react-native';
import { useRangeMode } from '../RangeMode';
import type { Colors } from '../../theme/tokens';

export interface AccessibleTextProps extends TextProps {
  variant?: 'body' | 'bodySmall' | 'caption' | 'title' | 'display';
  color?: keyof Colors;
}

export function AccessibleText({
  variant = 'body',
  color = 'textPrimary',
  style,
  ...rest
}: AccessibleTextProps): React.ReactElement {
  const { theme } = useRangeMode();
  const composed: TextStyle = {
    fontSize: theme.typography[variant],
    color: theme.colors[color],
    lineHeight: theme.typography[variant] * 1.35,
  };
  return (
    <Text
      allowFontScaling
      maxFontSizeMultiplier={1.5}
      style={[styles.base, composed, style]}
      {...rest}
    />
  );
}

const styles = StyleSheet.create({
  base: {
    includeFontPadding: false,
  },
});
