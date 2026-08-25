type ColorScheme = 'light' | 'dark';

interface TelegramWebApp {
  initData: string;
  colorScheme: ColorScheme;
  themeParams: Record<string, string>;
  viewportStableHeight: number;
  ready(): void;
  expand(): void;
  setHeaderColor(color: string): void;
  setBackgroundColor(color: string): void;
  onEvent(event: string, handler: () => void): void;
  BackButton: { show(): void; hide(): void; onClick(cb: () => void): void; offClick(cb: () => void): void };
  HapticFeedback?: {
    impactOccurred(style: string): void;
    notificationOccurred(type: string): void;
    selectionChanged(): void;
  };
}

const tg: TelegramWebApp | undefined = (window as unknown as { Telegram?: { WebApp: TelegramWebApp } })
  .Telegram?.WebApp;

function applyTheme(): void {
  const root = document.documentElement;
  const params = tg?.themeParams ?? {};
  for (const [key, value] of Object.entries(params)) {
    root.style.setProperty(`--tg-${key.replace(/_/g, '-')}`, value);
  }
  root.dataset.theme = tg?.colorScheme ?? 'dark';
  const bg = params.bg_color;
  if (bg) {
    tg?.setHeaderColor(bg);
    tg?.setBackgroundColor(bg);
  }
}

function applyViewport(): void {
  const height = tg?.viewportStableHeight;
  if (height) {
    document.documentElement.style.setProperty('--app-height', `${height}px`);
  }
}

export function initTelegram(): void {
  if (!tg) {
    document.documentElement.dataset.theme = 'dark';
    return;
  }
  tg.ready();
  tg.expand();
  applyTheme();
  applyViewport();
  tg.onEvent('themeChanged', applyTheme);
  tg.onEvent('viewportChanged', applyViewport);
}

export function initData(): string {
  return tg?.initData ?? '';
}

export function isTelegram(): boolean {
  return Boolean(tg?.initData);
}

export const haptic = {
  impact(style: 'light' | 'medium' | 'heavy' = 'light'): void {
    tg?.HapticFeedback?.impactOccurred(style);
  },
  success(): void {
    tg?.HapticFeedback?.notificationOccurred('success');
  },
  error(): void {
    tg?.HapticFeedback?.notificationOccurred('error');
  },
  selection(): void {
    tg?.HapticFeedback?.selectionChanged();
  },
};

export const backButton = {
  show(onClick: () => void): void {
    if (!tg) return;
    this._handler = onClick;
    tg.BackButton.onClick(onClick);
    tg.BackButton.show();
  },
  hide(): void {
    if (!tg) return;
    if (this._handler) tg.BackButton.offClick(this._handler);
    tg.BackButton.hide();
    this._handler = undefined;
  },
  _handler: undefined as (() => void) | undefined,
};
