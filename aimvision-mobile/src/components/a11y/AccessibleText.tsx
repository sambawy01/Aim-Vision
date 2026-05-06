import React from 'react';
import { Text, type TextProps, type TextStyle, StyleSheet } from 'react-native';
import { colors, typography } from '../../theme/tokens';

export interface AccessibleTextProps extends TextProps {
  variant?: 'body' | 'bodySmall' | 'caption' | 'title' | 'display';
  color?: keyof typeof colors;
}

export function AccessibleText({
  variant = 'body',
  color = 'textPrimary',
  style,
  ...rest
}: AccessibleTextProps): React.ReactElement {
  const composed: TextStyle = {
    fontSize: typography[variant],
    color: colors[color],
    lineHeight: typography[variant] * 1.35,
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
