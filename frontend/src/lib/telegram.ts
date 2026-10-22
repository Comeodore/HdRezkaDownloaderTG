interface TelegramWebApp {
  initData: string;
  version: string;
  platform: string;
  colorScheme: 'light' | 'dark';
  isVersionAtLeast(version: string): boolean;
  ready(): void;
  expand(): void;
  disableVerticalSwipes?(): void;
  setHeaderColor(color: string): void;
  setBackgroundColor(color: string): void;
  setBottomBarColor?(color: string): void;
  onEvent(event: string, handler: () => void): void;
  showConfirm(message: string, callback: (ok: boolean) => void): void;
  BackButton: { show(): void; hide(): void; onClick(cb: () => void): void; offClick(cb: () => void): void };
  HapticFeedback?: {
    impactOccurred(style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft'): void;
    notificationOccurred(type: 'success' | 'warning' | 'error'): void;
    selectionChanged(): void;
  };
}

const tg: TelegramWebApp | undefined = (window as unknown as { Telegram?: { WebApp?: TelegramWebApp } }).Telegram
  ?.WebApp;

/** The app is dark by design; Telegram's chrome is painted to match it in any theme. */
const CHROME = '#0b0b0e';

function supports(version: string): boolean {
  return Boolean(tg?.isVersionAtLeast?.(version));
}

export function initTelegram(): void {
  if (!tg?.initData) return;
  tg.ready();
  tg.expand();
  if (supports('6.1')) {
    tg.setHeaderColor(CHROME);
    tg.setBackgroundColor(CHROME);
  }
  if (supports('7.10')) tg.setBottomBarColor?.(CHROME);
  // Without this a downward swipe inside a scrolled list minimises the whole app.
  if (supports('7.7')) tg.disableVerticalSwipes?.();
}

export const inTelegram = (): boolean => Boolean(tg?.initData);
export const initData = (): string => tg?.initData ?? '';

export const haptic = {
  tap: () => tg?.HapticFeedback?.impactOccurred('light'),
  press: () => tg?.HapticFeedback?.impactOccurred('medium'),
  select: () => tg?.HapticFeedback?.selectionChanged(),
  success: () => tg?.HapticFeedback?.notificationOccurred('success'),
  warning: () => tg?.HapticFeedback?.notificationOccurred('warning'),
  error: () => tg?.HapticFeedback?.notificationOccurred('error'),
};

export function confirm(message: string): Promise<boolean> {
  if (tg && supports('6.2')) {
    return new Promise((resolve) => tg.showConfirm(message, resolve));
  }
  return Promise.resolve(window.confirm(message));
}

/** Drives Telegram's native back button from the app's navigation depth. */
export function bindBackButton(handler: () => void): (visible: boolean) => void {
  if (!tg || !supports('6.1')) return () => {};
  tg.BackButton.onClick(handler);
  return (visible) => (visible ? tg.BackButton.show() : tg.BackButton.hide());
}

export const hasNativeBack = (): boolean => Boolean(tg?.initData) && supports('6.1');
