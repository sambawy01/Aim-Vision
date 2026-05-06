import { create } from 'zustand';

export const CONSENT_CATEGORIES = [
  'video',
  'pose',
  'voice',
  'LLM_coaching',
  'ML_training',
] as const;

export const CONSENT_PURPOSES = ['coaching', 'marketing', 'validity_study'] as const;

export type ConsentCategory = (typeof CONSENT_CATEGORIES)[number];
export type ConsentPurpose = (typeof CONSENT_PURPOSES)[number];

export type ConsentMatrix = Record<ConsentCategory, Record<ConsentPurpose, boolean>>;

function emptyMatrix(): ConsentMatrix {
  const out = {} as ConsentMatrix;
  for (const cat of CONSENT_CATEGORIES) {
    out[cat] = {} as Record<ConsentPurpose, boolean>;
    for (const pur of CONSENT_PURPOSES) {
      out[cat][pur] = false;
    }
  }
  return out;
}

interface ConsentState {
  matrix: ConsentMatrix;
  version: string;
  dirty: boolean;
  toggle: (category: ConsentCategory, purpose: ConsentPurpose) => void;
  set: (category: ConsentCategory, purpose: ConsentPurpose, value: boolean) => void;
  reset: () => void;
  isGranted: (category: ConsentCategory, purpose: ConsentPurpose) => boolean;
}

export const useConsentStore = create<ConsentState>((set, get) => ({
  matrix: emptyMatrix(),
  version: 'v1',
  dirty: false,
  toggle: (category, purpose) =>
    set((state) => {
      const next = { ...state.matrix, [category]: { ...state.matrix[category] } };
      next[category][purpose] = !state.matrix[category][purpose];
      return { matrix: next, dirty: true };
    }),
  set: (category, purpose, value) =>
    set((state) => {
      const next = { ...state.matrix, [category]: { ...state.matrix[category] } };
      next[category][purpose] = value;
      return { matrix: next, dirty: true };
    }),
  reset: () => set({ matrix: emptyMatrix(), dirty: false }),
  isGranted: (category, purpose) => get().matrix[category][purpose],
}));
