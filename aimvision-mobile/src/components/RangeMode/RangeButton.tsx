import React from 'react';
import { StyleSheet, View } from 'react-native';
import { AccessibleTouchable } from '../a11y/AccessibleTouchable';
import { AccessibleText } from '../a11y/AccessibleText';
import { useRangeMode } from './RangeModeProvider';

export interface RangeButtonProps {
  label: string;
  onPress: () => void;
  accessibilityLabel?: string;
  disabled?: boolean;
}

export function RangeButton({
  label,
  onPress,
  accessibilityLabel,
  disabled,
}: RangeButtonProps): React.ReactElement {
  const { theme } = useRangeMode();
  return (
    <AccessibleTouchable
      onPress={onPress}
      disabled={disabled}
      variant="primary"
      accessibilityLabel={accessibilityLabel ?? label}
      style={[
        styles.button,
        {
          backgroundColor: theme.colors.accent,
          borderRadius: theme.radii.md,
          paddingHorizontal: theme.spacing.lg,
          minHeight: theme.tapTargets.primary,
          opacity: disabled ? 0.5 : 1,
        },
      ]}
    >
      <View>
        <AccessibleText variant="title" color="black">
          {label}
        </AccessibleText>
      </View>
    </AccessibleTouchable>
  );
}

const styles = StyleSheet.create({
  button: {
    alignItems: 'center',
    justifyContent: 'center',
    alignSelf: 'stretch',
  },
});
