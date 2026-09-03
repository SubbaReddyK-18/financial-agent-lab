export type ControlRoomSection =
  | 'operations'
  | 'decisions'
  | 'approvals'
  | 'economics'
  | 'simulation'
  | 'audit';

export interface NavItemConfig {
  id: ControlRoomSection;
  label: string;
  iconName: string;
  badgeCount?: number;
}
