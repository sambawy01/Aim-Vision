import React from 'react';
import { Pressable, StyleSheet, type PressableProps, type ViewStyle } from 'react-native';
// Direct import to avoid the require cycle through `../RangeMode/index.ts`
// (the barrel pulls in `RangeButton`, which uses this component).
import { useRangeMode } from '../RangeMode/RangeModeProvider';

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
  const { theme } = useRangeMode();
  const minSize = variant === 'primary' ? theme.tapTargets.primary : theme.tapTargets.minimum;
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
