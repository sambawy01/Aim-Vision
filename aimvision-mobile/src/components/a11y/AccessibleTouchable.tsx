import React from 'react';
import { Pressable, StyleSheet, type PressableProps, type ViewStyle } from 'react-native';
import { tapTargets } from '../../theme/tokens';

export interface AccessibleTouchableProps extends PressableProps {
  variant?: 'default' | 'primary';
  style?: ViewStyle | ViewStyle[];
  accessibilityLabel: string;
}

export function AccessibleTouchable({
  variant = 'default',
  style,
  accessibilityLabel,
  children,
  hitSlop,
  ...rest
}: AccessibleTouchableProps): React.ReactElement {
  const minSize = variant === 'primary' ? tapTargets.primary : tapTargets.minimum;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      hitSlop={hitSlop ?? 8}
      style={[styles.base, { minWidth: minSize, minHeight: minSize }, style]}
      {...rest}
    >
      {children}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    alignItems: 'center',
    justifyContent: 'center',
  },
});
