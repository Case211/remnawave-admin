/**
 * ─── Xray GUI UI Component Library ───────────────────────────────────────────
 *
 * Reusable, typed UI primitives.
 * Import from here to ensure you always get the correct component.
 *
 * Usage:
 *   import { Button, Input, Switch, Badge } from '@/components/ui';
 * ─────────────────────────────────────────────────────────────────────────────
 */

// Atoms
export { Icon } from './Icon';
export type {} from './Icon';

export { Button } from './Button';
export type { ButtonProps, ButtonVariant, ButtonSize } from './Button';

export { Input } from './Input';
export type { InputProps } from './Input';

export { NumberInput } from './NumberInput';
export type { NumberInputProps } from './NumberInput';

export { Textarea } from './Textarea';
export type { TextareaProps } from './Textarea';

export { Select } from './Select';
export type { SelectProps, SelectOption } from './Select';

export { Switch } from './Switch';

export { Checkbox } from './Checkbox';
export type { CheckboxProps } from './Checkbox';

export { RadioGroup } from './RadioGroup';
export type { RadioGroupProps, RadioOption } from './RadioGroup';

export { Badge } from './Badge';
export type { BadgeProps, BadgeVariant } from './Badge';

export { Divider } from './Divider';
export type { DividerProps } from './Divider';

export { Alert } from './Alert';
export type { AlertProps, AlertVariant } from './Alert';

// Composite / Molecules
export { Help } from './Help';
export { Card } from './Card';
export { Modal } from './Modal';
export { FormField } from './FormField';
export { EditorLayout } from './EditorLayout';
export { SmartTagInput } from './SmartTagInput';
export { TagSelector } from './TagSelector';
export { JsonEditor } from './JsonEditor';
export { JsonField } from './JsonField';
